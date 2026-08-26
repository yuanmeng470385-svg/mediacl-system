"""医生端认证端点（一期 B）：医师执业资质（multipart 上传 → 管理端审核）

移植自备案资质子系统（app/api/qualifications.py），差异点：
  - 角色限制：仅 role=doctor 可提交（qualifications 为 rep）；
  - 模型：DoctorCertification（doctor_certifications 表）；
  - 字段：filing_number → cert_type（Form 必传 ∈ {physician, practice}），
         education_cert → cert_image（UploadFile 必传），无 filing_expire_date；
  - 审计 action：doctor_cert_submit / doctor_cert_review；
  - 复用 qualifications 的 _save_upload / _client_ip / QUAL_ADMIN_ROLES
    与 users 的 _reload_current_user、audit_client 的 write_audit_log。
"""
import logging
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, File, Form, Request, UploadFile
from sqlalchemy import or_
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from shared.common.auth import get_current_user, require_roles
from shared.common.context import get_request_id
from shared.common.db_session import get_db
from shared.common.pagination import PaginationParams, paginate
from shared.common.response import BusinessError, ParamError, PermissionError, success
from shared.models.doctor import DoctorCertification
from shared.models.doctor_profile import DoctorProfile
from shared.models.user import User

from app.api.qualifications import QUAL_ADMIN_ROLES, _client_ip, _save_upload
from app.api.users import _reload_current_user
from app.services.audit_client import write_audit_log

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/doctors", tags=["doctors"])

VALID_CERT_TYPES = ("physician", "practice")
VALID_CERT_STATUSES = ("pending", "approved", "rejected")


async def _save_cert(file: UploadFile) -> str:
    """复用备案资质的 _save_upload（分块落盘 + 扩展名/5MB 校验 + OSS 上传）。

    OSS 对象键仍为 qualifications/ 前缀——同一 bucket 同前缀可接受，一期 B 不新开前缀。
    """
    return await _save_upload(file)


@router.post("/certs")
async def submit_cert(
    request: Request,
    cert_image: Optional[UploadFile] = File(None),
    cert_type: Optional[str] = Form(None),
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """医生提交/更新本人执业资质（提交后进入待审核，重新提交重置审核态）"""
    if current_user["role"] != "doctor":
        raise PermissionError("仅医生可提交执业资质")

    ctype = (cert_type or "").strip()
    if ctype not in VALID_CERT_TYPES:
        raise ParamError(f"cert_type 必须是 {'/'.join(VALID_CERT_TYPES)} 之一")

    cert = db.query(DoctorCertification).filter(
        DoctorCertification.doctor_id == current_user["id"]
    ).first()
    if (not cert or not cert.cert_image_url) and not cert_image:
        raise ParamError("首次提交必须上传证书图片")

    before = {
        "cert_type": cert.cert_type if cert else None,
        "cert_status": cert.cert_status if cert else None,
    }
    if not cert:
        cert = DoctorCertification(
            doctor_id=current_user["id"],
            cert_image_url="",  # 上传成功后覆盖
        )
        db.add(cert)

    if cert_image:
        cert.cert_image_url = await _save_cert(cert_image)
    if ctype:
        cert.cert_type = ctype
    # 重新提交回到待审核；上一轮审核信息清空
    cert.cert_status = "pending"
    cert.reject_reason = None
    cert.reviewed_by = None
    cert.reviewed_at = None
    try:
        db.commit()
    except IntegrityError:
        # TOCTOU 兜底：并发双提交撞 doctor_id 唯一索引 → 可读业务错误而非 500
        db.rollback()
        raise BusinessError("提交冲突，请重试", code=4001)
    db.refresh(cert)

    await write_audit_log(
        action="doctor_cert_submit",
        user_id=current_user["id"],
        resource_type="doctor_certification",
        resource_id=str(cert.id),
        before_value=before,
        after_value={
            "cert_type": cert.cert_type,
            "cert_status": cert.cert_status,
        },
        client_ip=_client_ip(request),
        user_agent=request.headers.get("user-agent"),
        request_id=get_request_id() or None,
    )
    return success(cert.to_dict())


@router.get("/certs/me")
async def get_my_cert(
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """本人执业资质（无记录返回 null，移动端渲染"未认证"空态）"""
    cert = db.query(DoctorCertification).filter(
        DoctorCertification.doctor_id == current_user["id"]
    ).first()
    return success(cert.to_dict() if cert else None)


@router.get("/certs")
async def list_certs(
    page: int = 1,
    page_size: int = 20,
    cert_status: Optional[str] = None,
    keyword: Optional[str] = None,
    current_user: dict = Depends(require_roles(*QUAL_ADMIN_ROLES)),
    db: Session = Depends(get_db),
):
    """医生执业资质列表（管理端：admin/manager/compliance/medical）"""
    _reload_current_user(db, current_user)
    if cert_status and cert_status not in VALID_CERT_STATUSES:
        raise ParamError("cert_status 不合法")
    p = PaginationParams(page=page, page_size=page_size)
    query = db.query(DoctorCertification, User).join(
        User, User.id == DoctorCertification.doctor_id
    )
    if cert_status:
        query = query.filter(DoctorCertification.cert_status == cert_status)
    if keyword:
        like = f"%{keyword}%"
        query = query.filter(or_(
            User.full_name.ilike(like),
            User.phone.ilike(like),
            User.username.ilike(like),
            DoctorCertification.cert_type.ilike(like),
        ))
    total = query.count()
    rows = query.order_by(DoctorCertification.id.desc()).offset(p.offset).limit(p.limit).all()
    items = [{**c.to_dict(), "doctor_name": u.full_name, "doctor_phone": u.phone} for c, u in rows]
    return success(paginate(items, total, p.page, p.page_size))


@router.put("/certs/{cert_id}/review")
async def review_cert(
    cert_id: int,
    request: dict,
    current_user: dict = Depends(require_roles(*QUAL_ADMIN_ROLES)),
    db: Session = Depends(get_db),
):
    """执业资质审核（通过/驳回）。驳回必须附原因；仅 pending 可审。"""
    actor = _reload_current_user(db, current_user)
    if not isinstance(request, dict):
        raise ParamError("请求体必须是 JSON 对象")
    verdict = request.get("verdict")
    if verdict not in ("approve", "reject"):
        raise ParamError("verdict 必须是 approve 或 reject")
    # 终审修复同款：reason 非字符串（如数字）在 strip 处 AttributeError → 500，
    # 显式校验转可读的 400 参数错误
    raw_reason = request.get("reason")
    if raw_reason is not None and not isinstance(raw_reason, str):
        raise ParamError("reason 必须是字符串")
    reason = (raw_reason or "").strip()
    if verdict == "reject" and not reason:
        raise ParamError("驳回必须填写原因")
    if len(reason) > 500:
        raise ParamError("原因长度不能超过 500 字符")

    cert = db.query(DoctorCertification).filter(
        DoctorCertification.id == cert_id
    ).first()
    if not cert:
        raise BusinessError("认证记录不存在", code=4000)
    if cert.cert_status != "pending":
        raise BusinessError("当前状态不可审核（仅待审核可审）", code=4001)

    before = {
        "cert_status": cert.cert_status,
    }
    cert.cert_status = "approved" if verdict == "approve" else "rejected"
    cert.reject_reason = reason if verdict == "reject" else None
    cert.reviewed_by = actor.id
    cert.reviewed_at = datetime.utcnow()
    db.commit()
    db.refresh(cert)

    await write_audit_log(
        action="doctor_cert_review",
        user_id=actor.id,
        resource_type="doctor_certification",
        resource_id=str(cert.id),
        before_value=before,
        after_value={
            "cert_status": cert.cert_status,
            "reject_reason": cert.reject_reason,
        },
    )
    return success(cert.to_dict())


# ---------- 隐私中心（三期 L，需求 5.7） ----------

PRIVACY_POLICY = {
    "title": "MedAgent 医生端隐私政策",
    "version": "1.0",
    "updated_at": "2026-08-21",
    "content": (
        "1. 我们收集的信息：账号信息（姓名/手机号/科室/地区）、医师资质文件、"
        "您与数字分身的对话记录、学术偏好设置。\n"
        "2. 使用目的：提供医学问答、分身订阅、学术触达与患教服务；未经同意不会"
        "将您的个人信息用于其他目的。\n"
        "3. 存储与保护：数据加密存储于境内服务器，访问全程留痕审计。\n"
        "4. 对话合规：所有对话经合规系统实时检查，违规内容将被拦截。\n"
        "5. 您的权利：您可在隐私中心查看个人信息、申请更正、申请导出数据包、"
        "申请删除数据或注销账号。\n"
        "6. 删除与注销：注销采用去标识化处理（姓名置为『已注销医生』、手机号脱敏），"
        "依法留存的合规记录不做物理删除。\n"
        "7. 响应时限：您的请求将在 30 日内处理并反馈结果。\n"
        "8. 联系我们：可通过隐私请求提交说明，或联系平台管理员。"
    ),
}


@router.get("/privacy-policy")
def get_privacy_policy():
    """隐私政策全文（静态文案，公开可读——登录前亦可展示）"""
    return success(PRIVACY_POLICY)


@router.get("/personal-data")
def get_personal_data(
    current_user: dict = Depends(require_roles("doctor")),
    db: Session = Depends(get_db),
):
    """个人信息查看（需求 5.7(2)）：user 安全字段 + 偏好画像（无画像为 null）

    历史对话查看不自建端点——mobile 复用既有收藏历史（需求原文即"复用"）。
    """
    user = db.query(User).filter(User.id == current_user["id"]).first()
    if not user:
        raise BusinessError("用户不存在")
    profile = (
        db.query(DoctorProfile).filter(DoctorProfile.doctor_id == user.id).first()
    )
    return success({
        "user": user.to_dict(),
        "doctor_profile": profile.to_dict() if profile else None,
    })
