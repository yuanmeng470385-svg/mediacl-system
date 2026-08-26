"""备案与资质（需求文档 3.3/4.2）：代表提交（multipart）→ 管理端审核 → 到期冻结"""
import asyncio
import logging
import os
import tempfile
from datetime import date, datetime
from typing import Optional

from fastapi import APIRouter, Depends, File, Form, Request, UploadFile
from sqlalchemy import case, func, or_
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from shared.common.auth import get_current_user, require_roles
from shared.common.context import get_request_id
from shared.common.db_session import get_db
from shared.common.pagination import PaginationParams, paginate
from shared.common.response import BusinessError, ParamError, PermissionError, success
from shared.models.qualification import RepresentativeQualification
from shared.models.user import User

from app.api.users import _reload_current_user
from app.services.audit_client import write_audit_log
from app.services.oss_client import OSSClient

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/qualifications", tags=["qualifications"])

QUAL_ADMIN_ROLES = ("admin", "manager", "compliance", "medical")
ALLOWED_CERT_EXTENSIONS = {".jpg", ".jpeg", ".png", ".pdf"}
MAX_CERT_SIZE = 5 * 1024 * 1024      # 单文件 5MB
_CERT_READ_CHUNK = 1024 * 1024       # 1MB 分块落盘，避免全量读内存
VALID_AUDIT_STATUSES = ("pending", "approved", "rejected")

# 管理端列表按派生 filing_status 过滤用的 SQL 表达式（与模型 to_dict 计算口径一致）
_filing_status_expr = case(
    (
        or_(
            RepresentativeQualification.filing_number.is_(None),
            RepresentativeQualification.filing_number == "",
        ),
        "not_filed",
    ),
    (RepresentativeQualification.filing_expire_date < func.current_date(), "expired"),
    else_="valid",
)


def _client_ip(request: Request) -> str:
    """取真实来源 IP。网关转发时以 X-Forwarded-For 首段为准（与 auth.py 同口径：
    网关会把 XFF 覆盖为真实对端，直接 trust 首段；无 XFF 回退直连对端）。"""
    forwarded = request.headers.get("x-forwarded-for", "")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.client.host if request.client else ""


async def _save_upload(file: UploadFile) -> str:
    """分块落盘 + 扩展名/大小校验 → OSS 上传（线程池）→ 返回 URL"""
    suffix = (os.path.splitext(file.filename or "")[1] or "").lower()
    if suffix not in ALLOWED_CERT_EXTENSIONS:
        raise ParamError(f"不支持的文件类型 {suffix or '(无扩展名)'}，仅支持 jpg/jpeg/png/pdf")
    total = 0
    with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
        tmp_path = tmp.name
        while True:
            chunk = file.file.read(_CERT_READ_CHUNK)
            if not chunk:
                break
            total += len(chunk)
            if total > MAX_CERT_SIZE:
                break
            tmp.write(chunk)
    if total > MAX_CERT_SIZE:
        try:
            os.unlink(tmp_path)
        except OSError:
            pass
        raise ParamError(f"文件大小超过上限 {MAX_CERT_SIZE // (1024 * 1024)}MB")
    try:
        return await asyncio.to_thread(OSSClient().upload_local_file, tmp_path)
    finally:
        try:
            os.unlink(tmp_path)
        except OSError:
            pass


@router.post("")
async def submit_qualification(
    request: Request,
    education_cert: Optional[UploadFile] = File(None),
    training_cert: Optional[UploadFile] = File(None),
    filing_number: Optional[str] = Form(None),
    filing_expire_date: Optional[str] = Form(None),
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """代表提交/更新本人备案与资质（提交后进入待审核，重新提交重置审核态）"""
    if current_user["role"] != "rep":
        raise PermissionError("仅医药代表可提交备案与资质材料")

    number = (filing_number or "").strip()
    if len(number) > 50:
        raise ParamError("备案号长度不能超过 50 字符")
    parsed_date = None
    if filing_expire_date:
        try:
            parsed_date = date.fromisoformat(filing_expire_date)
        except ValueError as exc:
            raise ParamError("filing_expire_date 格式应为 YYYY-MM-DD") from exc

    qual = db.query(RepresentativeQualification).filter(
        RepresentativeQualification.representative_id == current_user["id"]
    ).first()
    if (not qual or not qual.education_cert) and not education_cert:
        raise ParamError("首次提交必须上传学历证明")

    before = {
        "filing_number": qual.filing_number if qual else None,
        "audit_status": qual.audit_status if qual else None,
    }
    if not qual:
        qual = RepresentativeQualification(
            representative_id=current_user["id"],
            education_cert="",  # 上传成功后覆盖
        )
        db.add(qual)

    if education_cert:
        qual.education_cert = await _save_upload(education_cert)
    if training_cert:
        qual.training_cert = await _save_upload(training_cert)
    if number:
        qual.filing_number = number
    if parsed_date:
        qual.filing_expire_date = parsed_date
    # 重新提交回到待审核；上一轮审核信息清空
    qual.audit_status = "pending"
    qual.reject_reason = None
    qual.reviewed_by = None
    qual.reviewed_at = None
    try:
        db.commit()
    except IntegrityError:
        # TOCTOU 兜底：并发双提交撞 representative_id 唯一索引 → 可读业务错误而非 500
        db.rollback()
        raise BusinessError("提交冲突，请重试", code=4001)
    db.refresh(qual)

    await write_audit_log(
        action="qualification_submit",
        user_id=current_user["id"],
        resource_type="qualification",
        resource_id=str(qual.id),
        before_value=before,
        after_value={
            "filing_number": qual.filing_number,
            "audit_status": qual.audit_status,
            "filing_expire_date": qual.filing_expire_date.isoformat() if qual.filing_expire_date else None,
        },
        client_ip=_client_ip(request),
        user_agent=request.headers.get("user-agent"),
        request_id=get_request_id() or None,
    )
    return success(qual.to_dict())


@router.get("/me")
async def get_my_qualification(
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """本人备案与资质（无记录返回 null，移动端渲染"未备案"空态）"""
    qual = db.query(RepresentativeQualification).filter(
        RepresentativeQualification.representative_id == current_user["id"]
    ).first()
    return success(qual.to_dict() if qual else None)


@router.get("")
async def list_qualifications(
    page: int = 1,
    page_size: int = 20,
    audit_status: Optional[str] = None,
    filing_status: Optional[str] = None,
    keyword: Optional[str] = None,
    current_user: dict = Depends(require_roles(*QUAL_ADMIN_ROLES)),
    db: Session = Depends(get_db),
):
    """备案与资质列表（管理端：admin/manager/compliance/medical）"""
    _reload_current_user(db, current_user)
    if audit_status and audit_status not in VALID_AUDIT_STATUSES:
        raise ParamError("audit_status 不合法")
    if filing_status and filing_status not in ("valid", "expired", "not_filed"):
        raise ParamError("filing_status 不合法")
    p = PaginationParams(page=page, page_size=page_size)
    query = db.query(RepresentativeQualification, User).join(
        User, User.id == RepresentativeQualification.representative_id
    )
    if audit_status:
        query = query.filter(RepresentativeQualification.audit_status == audit_status)
    if filing_status:
        query = query.filter(_filing_status_expr == filing_status)
    if keyword:
        like = f"%{keyword}%"
        query = query.filter(or_(
            User.full_name.ilike(like),
            User.phone.ilike(like),
            User.username.ilike(like),
            RepresentativeQualification.filing_number.ilike(like),
        ))
    total = query.count()
    rows = query.order_by(RepresentativeQualification.id.desc()).offset(p.offset).limit(p.limit).all()
    items = [{**q.to_dict(), "rep_name": u.full_name, "rep_phone": u.phone} for q, u in rows]
    return success(paginate(items, total, p.page, p.page_size))


@router.put("/{qualification_id}/review")
async def review_qualification(
    qualification_id: int,
    request: dict,
    current_user: dict = Depends(require_roles(*QUAL_ADMIN_ROLES)),
    db: Session = Depends(get_db),
):
    """资质审核（通过/驳回）。驳回必须附原因；可同时确认/修正备案有效期。"""
    actor = _reload_current_user(db, current_user)
    if not isinstance(request, dict):
        raise ParamError("请求体必须是 JSON 对象")
    verdict = request.get("verdict")
    if verdict not in ("approve", "reject"):
        raise ParamError("verdict 必须是 approve 或 reject")
    # F1（2026-08-17）：reason 非字符串（如数字）在 strip 处 AttributeError → 500，
    # 显式校验转可读的 400 参数错误
    raw_reason = request.get("reason")
    if raw_reason is not None and not isinstance(raw_reason, str):
        raise ParamError("reason 必须是字符串")
    reason = (raw_reason or "").strip()
    if verdict == "reject" and not reason:
        raise ParamError("驳回必须填写原因")
    if len(reason) > 500:
        raise ParamError("原因长度不能超过 500 字符")
    parsed_date = None
    raw_date = request.get("filing_expire_date")
    if raw_date:
        try:
            parsed_date = date.fromisoformat(str(raw_date))
        except ValueError as exc:
            raise ParamError("filing_expire_date 格式应为 YYYY-MM-DD") from exc

    qual = db.query(RepresentativeQualification).filter(
        RepresentativeQualification.id == qualification_id
    ).first()
    if not qual:
        raise BusinessError("备案记录不存在", code=4000)
    if qual.audit_status != "pending":
        raise BusinessError("当前状态不可审核（仅待审核可审）", code=4001)

    before = {
        "audit_status": qual.audit_status,
        "filing_expire_date": qual.filing_expire_date.isoformat() if qual.filing_expire_date else None,
    }
    qual.audit_status = "approved" if verdict == "approve" else "rejected"
    qual.reject_reason = reason if verdict == "reject" else None
    qual.reviewed_by = actor.id
    qual.reviewed_at = datetime.utcnow()
    if parsed_date:
        qual.filing_expire_date = parsed_date
    db.commit()
    db.refresh(qual)

    await write_audit_log(
        action="qualification_review",
        user_id=actor.id,
        resource_type="qualification",
        resource_id=str(qual.id),
        before_value=before,
        after_value={
            "audit_status": qual.audit_status,
            "reject_reason": qual.reject_reason,
            "filing_expire_date": qual.filing_expire_date.isoformat() if qual.filing_expire_date else None,
        },
    )
    return success(qual.to_dict())
