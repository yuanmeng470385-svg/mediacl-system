"""隐私请求（三期 L，需求 3.8(4)(5)/5.7）：提交/本人查询/管理端处理

医生侧行使隐私权利（查阅/更正/删除/导出/注销）走请求工单：
  - 提交/me：仅 role=doctor；
  - 列表/handle：admin/manager/compliance（PRIVACY_ADMIN_ROLES，Task 4）；
  - SLA = 创建时间 + 30 自然日（sla_deadline 落库；超时仅管理端高亮不自动执行）；
  - 审计 action=privacy_request_create / privacy_request_handle。

角色与审计模式移植自 qualifications/doctors；分页复用 PaginationParams。
"""
import logging
import re
from datetime import datetime, timedelta
from typing import Optional

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.orm import Session

from shared.common.auth import require_roles
from shared.common.context import get_request_id
from shared.common.db_session import get_db
from shared.common.pagination import PaginationParams, paginate
from shared.common.response import ParamError, success
from shared.models.privacy import (
    PRIVACY_REQUEST_STATUSES,
    PRIVACY_REQUEST_TYPES,
    PrivacyRequest,
)

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
