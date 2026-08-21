"""隐私请求（三期 L，需求 3.8(4)(5)/5.7）：提交/本人查询/管理端处理

医生侧行使隐私权利（查阅/更正/删除/导出/注销）走请求工单：
  - 提交/me：仅 role=doctor；
  - 列表/handle：admin/manager/compliance（PRIVACY_ADMIN_ROLES，Task 4）；
  - SLA = 创建时间 + 30 自然日（sla_deadline 落库；超时仅管理端高亮不自动执行）；
  - 审计 action=privacy_request_create / privacy_request_handle。

角色与审计模式移植自 qualifications/doctors；分页复用 PaginationParams。
"""
import json
import logging
import os
import re
from datetime import datetime, timedelta
from typing import Optional

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from shared.common.auth import require_roles
from shared.common.context import get_request_id
from shared.common.db_session import get_db
from shared.common.pagination import PaginationParams, paginate
from shared.common.response import BusinessError, ParamError, success
from shared.models.doctor import DoctorCertification
from shared.models.doctor_profile import DoctorProfile
from shared.models.privacy import (
    PRIVACY_REQUEST_STATUSES,
    PRIVACY_REQUEST_TYPES,
    PrivacyRequest,
)
from shared.models.user import User

from app.services.audit_client import write_audit_log

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/privacy-requests", tags=["privacy-requests"])

PRIVACY_ADMIN_ROLES = ("admin", "manager", "compliance")
SLA_DAYS = 30
PHONE_RE = re.compile(r"^1\d{10}$")


class PrivacyRequestCreate(BaseModel):
    request_type: str
    detail: str = ""
    fields: Optional[dict] = None   # correct 用：{full_name?, phone?} 至少一项
    confirm: bool = False           # account_delete 必须 True


@router.post("")
async def create_privacy_request(
    payload: PrivacyRequestCreate,
    current_user: dict = Depends(require_roles("doctor")),
    db: Session = Depends(get_db),
):
    if payload.request_type not in PRIVACY_REQUEST_TYPES:
        raise ParamError(f"request_type 必须是 {'/'.join(PRIVACY_REQUEST_TYPES)} 之一")
    if len(payload.detail) > 500:
        raise ParamError("detail 最长 500 字")
    fields = payload.fields or {}
    if payload.request_type == "correct":
        if not fields.get("full_name") and not fields.get("phone"):
            raise ParamError("更正申请必须至少提供 full_name/phone 之一")
        if fields.get("phone") and not PHONE_RE.match(str(fields["phone"])):
            raise ParamError("phone 格式不正确（11 位手机号）")
        if fields.get("full_name") and len(str(fields["full_name"])) > 100:
            raise ParamError("full_name 最长 100 字")
    if payload.request_type == "account_delete" and not payload.confirm:
        raise ParamError("注销申请必须先确认（confirm=true）")

    req = PrivacyRequest(
        doctor_id=current_user["id"],
        request_type=payload.request_type,
        status="pending",
        content={"detail": payload.detail, "fields": fields, "confirm": payload.confirm},
        sla_deadline=datetime.utcnow() + timedelta(days=SLA_DAYS),
    )
    db.add(req)
    db.commit()
    db.refresh(req)

    await write_audit_log(
        action="privacy_request_create",
        user_id=current_user["id"],
        resource_type="privacy_request",
        resource_id=str(req.id),
        after_value={"request_type": req.request_type},
        request_id=get_request_id(),
    )
    return success(req.to_dict())


@router.get("/me")
def list_my_privacy_requests(
    status: Optional[str] = None,
    paging: PaginationParams = Depends(),
    current_user: dict = Depends(require_roles("doctor")),
    db: Session = Depends(get_db),
):
    """本人请求分页 + 状态过滤（只能看到自己的）"""
    if status and status not in PRIVACY_REQUEST_STATUSES:
        raise ParamError("status 取值不合法")
    q = db.query(PrivacyRequest).filter(PrivacyRequest.doctor_id == current_user["id"])
    if status:
        q = q.filter(PrivacyRequest.status == status)
    total = q.count()
    items = (
        q.order_by(PrivacyRequest.created_at.desc())
        .offset((paging.page - 1) * paging.page_size)
        .limit(paging.page_size)
        .all()
    )
    return success(paginate([r.to_dict() for r in items], total, paging.page, paging.page_size))


EXPORT_DIR = os.path.join("logs", "exports")
CONVERSATION_EXPORT_LIMIT = 5000
HANDLE_ACTIONS = ("processing", "done", "rejected")


class PrivacyRequestHandle(BaseModel):
    action: str          # processing / done / rejected
    response: str = ""   # done/rejected 必填（≤500 字）


def _serialize_admin(req: PrivacyRequest, doctor_name: Optional[str]) -> dict:
    data = req.to_dict()
    data["doctor_name"] = doctor_name
    data["sla_overdue"] = bool(
        req.status in ("pending", "processing")
        and req.sla_deadline
        and req.sla_deadline < datetime.utcnow()
    )
    return data


def _deidentify_user(db: Session, doctor: User) -> None:
    """注销/删除去标识化（需求 3.8(5)，法务拍板不做物理删除）：
    full_name→"已注销医生"、phone→"DELETED-{id}"（嵌 id 防脱敏串互撞）、
    status→"deleted"、deleted_at=now；历史业务数据一律留存不动。
    token 失效由 get_current_user 实时查库（status != active → 401）天然拦截。
    """
    doctor.full_name = "已注销医生"
    doctor.phone = f"DELETED-{doctor.id}"
    doctor.status = "deleted"
    doctor.deleted_at = datetime.utcnow()
    db.commit()


def _build_privacy_package(db: Session, doctor: User, request_id: int) -> str:
    """生成医生个人数据包（export 请求 done 处理的产物）。

    JSON 落 EXPORT_DIR/privacy_<request_id>.json（logs/ 已 gitignore）：
    用户安全字段 + 偏好画像 + 医师认证 + 对话历史 + 隐私请求历史。
    conversation 模型在 specialist-service 本地，auth 不跨服务 import——对话用
    text() 显式列只读查询（同库直读；上限 5000 行；绝不含患者诊断信息）。
    """
    profile = db.query(DoctorProfile).filter(DoctorProfile.doctor_id == doctor.id).first()
    certs = (
        db.query(DoctorCertification)
        .filter(DoctorCertification.doctor_id == doctor.id)
        .order_by(DoctorCertification.id)
        .all()
    )
    conv_rows = db.execute(
        text(
            "SELECT id, specialist_id, session_id, role, content, compliance_result, created_at "
            "FROM conversations WHERE user_id = :uid ORDER BY created_at LIMIT :lim"
        ),
        {"uid": doctor.id, "lim": CONVERSATION_EXPORT_LIMIT},
    ).fetchall()
    history = (
        db.query(PrivacyRequest)
        .filter(PrivacyRequest.doctor_id == doctor.id)
        .order_by(PrivacyRequest.id)
        .all()
    )

    package = {
        "generated_at": datetime.utcnow().isoformat(),
        "request_id": request_id,
        "user": doctor.to_dict(),
        "doctor_profile": profile.to_dict() if profile else None,
        "doctor_certifications": [
            {
                "id": c.id,
                "cert_type": c.cert_type,
                "cert_status": c.cert_status,
                "cert_image_url": c.cert_image_url,
                "created_at": c.created_at.isoformat() if c.created_at else None,
            }
            for c in certs
        ],
        "conversations": [
            {
                "id": r.id,
                "specialist_id": r.specialist_id,
                "session_id": r.session_id,
                "role": r.role,
                "content": r.content,
                "compliance_result": r.compliance_result,
                "created_at": r.created_at.isoformat() if r.created_at else None,
            }
            for r in conv_rows
        ],
        "privacy_requests": [h.to_dict() for h in history],
    }

    os.makedirs(EXPORT_DIR, exist_ok=True)
    path = os.path.join(EXPORT_DIR, f"privacy_{request_id}.json")
    with open(path, "w", encoding="utf-8") as f:
        json.dump(package, f, ensure_ascii=False, indent=2, default=str)
    return path


@router.get("")
def list_privacy_requests(
    status: Optional[str] = None,
    request_type: Optional[str] = None,
    paging: PaginationParams = Depends(),
    current_user: dict = Depends(require_roles(*PRIVACY_ADMIN_ROLES)),
    db: Session = Depends(get_db),
):
    """管理端全量分页（admin/manager/compliance）+ 状态/类型过滤 + 30 日 SLA 超时高亮"""
    if status and status not in PRIVACY_REQUEST_STATUSES:
        raise ParamError("status 取值不合法")
    if request_type and request_type not in PRIVACY_REQUEST_TYPES:
        raise ParamError("request_type 取值不合法")
    q = db.query(PrivacyRequest, User.full_name).join(
        User, PrivacyRequest.doctor_id == User.id
    )
    if status:
        q = q.filter(PrivacyRequest.status == status)
    if request_type:
        q = q.filter(PrivacyRequest.request_type == request_type)
    total = q.count()
    rows = (
        q.order_by(PrivacyRequest.created_at.desc())
        .offset((paging.page - 1) * paging.page_size)
        .limit(paging.page_size)
        .all()
    )
    items = [_serialize_admin(r, name) for r, name in rows]
    return success(paginate(items, total, paging.page, paging.page_size))


@router.post("/{request_id}/handle")
async def handle_privacy_request(
    request_id: int,
    payload: PrivacyRequestHandle,
    current_user: dict = Depends(require_roles(*PRIVACY_ADMIN_ROLES)),
    db: Session = Depends(get_db),
):
    """处理留痕（需求 3.8(4)）：done 落地动作、rejected/processing 只改状态。

    执行语义（仅 done）：correct→更新 user 字段；export→生成数据包 JSON；
    delete/account_delete→去标识化（不做物理删除）。handled_by/handled_at/
    response 必填留痕；审计 action=privacy_request_handle。
    """
    if payload.action not in HANDLE_ACTIONS:
        raise ParamError("action 必须是 processing/done/rejected 之一")
    if payload.action in ("done", "rejected") and not payload.response.strip():
        raise ParamError("处理必须填写回复（response）")
    if len(payload.response) > 500:
        raise ParamError("response 最长 500 字")

    req = db.query(PrivacyRequest).filter(PrivacyRequest.id == request_id).first()
    if not req:
        raise BusinessError("请求不存在")
    if req.status in ("done", "rejected"):
        raise BusinessError("该请求已处理完毕，不能重复处理")

    doctor = db.query(User).filter(
        User.id == req.doctor_id, User.role == "doctor"
    ).first()

    file_url = None
    if payload.action == "done" and doctor:
        if req.request_type == "correct":
            fields = (req.content or {}).get("fields") or {}
            if not fields.get("full_name") and not fields.get("phone"):
                raise BusinessError("更正请求缺少待更正字段，请驳回并让医生重新提交")
            if fields.get("full_name"):
                doctor.full_name = str(fields["full_name"])[:100]
            if fields.get("phone"):
                new_phone = str(fields["phone"])
                # 撞号预检（A2，同 users.py）：更正成他人手机号等于劫持其登录凭据；
                # 真库唯一索引下直接提交只会 IntegrityError→500
                dup = db.query(User).filter(
                    User.phone == new_phone, User.id != doctor.id
                ).first()
                if dup:
                    raise BusinessError(
                        f"手机号已被用户 {dup.id} 使用，请驳回并让医生重新提交",
                        code=4001)
                doctor.phone = new_phone
            try:
                db.commit()
            except IntegrityError:
                db.rollback()
                raise BusinessError("手机号已被其他用户使用（并发更正），请驳回重新提交",
                                    code=4001)
        elif req.request_type == "export":
            file_url = _build_privacy_package(db, doctor, req.id)
        elif req.request_type in ("delete", "account_delete"):
            _deidentify_user(db, doctor)

    content = dict(req.content or {})
    content["response"] = payload.response
    req.content = content
    req.status = payload.action
    req.handled_by = current_user["id"]
    req.handled_at = datetime.utcnow()
    if file_url:
        req.file_url = file_url
    db.commit()
    db.refresh(req)

    await write_audit_log(
        action="privacy_request_handle",
        user_id=current_user["id"],
        resource_type="privacy_request",
        resource_id=str(req.id),
        after_value={"action": payload.action, "request_type": req.request_type},
        request_id=get_request_id(),
    )
    return success(_serialize_admin(req, doctor.full_name if doctor else None))
