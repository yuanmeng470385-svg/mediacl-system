"""年度合规承诺书签署（需求 3.4(4)）：勾选 + 短信验证码 + 审计留痕。
一期为平台内电子确认（不接第三方 CA）；培训前置先上线不强制。"""
import asyncio
import logging
import secrets
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, Request
from sqlalchemy.orm import Session

from shared.common.auth import get_current_user, require_roles
from shared.common.context import get_request_id
from shared.common.db_session import get_db
from shared.common.response import BusinessError, ParamError, PermissionError, success
from shared.models.qualification import RepresentativeQualification
from shared.models.user import User

from app.api.auth import get_code_store, get_sender, _client_ip
from app.config import settings
from app.core.code_store import CodeStore, CodeStoreError
from app.services.audit_client import write_audit_log
from app.services.sms import SmsSendError

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/qualifications/commitment", tags=["commitment"])


def _current_phone(db: Session, current_user: dict) -> str:
    """取当前用户手机号。get_current_user/require_roles 只返回 id/username/role，
    不含 phone，需按 id 从库读（require_roles 已保证用户 active 且为 rep）。"""
    user = db.query(User).filter(User.id == current_user["id"]).first()
    return (user.phone or "") if user else ""


@router.post("/send-code")
async def send_commitment_code(
    request: Request,
    current_user: dict = Depends(require_roles("rep")),
    db: Session = Depends(get_db),
    store: CodeStore = Depends(get_code_store),
    sender=Depends(get_sender),
):
    """向当前代表手机发送承诺书签署验证码（复用 auth 验证码存储）"""
    phone = _current_phone(db, current_user)
    try:
        remaining = store.in_cooldown(phone)
        if remaining > 0:
            raise ParamError(f"请 {remaining} 秒后再试")
        code = "".join(secrets.choice("0123456789") for _ in range(settings.CODE_LENGTH))
        saved = store.save(phone, code, settings.CODE_TTL_SECONDS, settings.CODE_RESEND_SECONDS)
        if not saved:
            raise ParamError("验证码已发送，请稍后再试")
        await asyncio.to_thread(sender.send_code, phone, code)
    except CodeStoreError as exc:
        logger.error(f"承诺书验证码存储不可用: {exc}")
        raise BusinessError("验证码服务暂时不可用，请稍后重试", code=5004)
    except SmsSendError as exc:
        raise BusinessError(f"短信发送失败: {exc}", code=6001)
    await write_audit_log(
        action="commitment_send_code",
        user_id=current_user["id"],
        resource_type="commitment",
        resource_id=phone,
        client_ip=_client_ip(request),
        request_id=get_request_id() or None,
    )
    return success({"expire_seconds": settings.CODE_TTL_SECONDS})


@router.post("/sign")
async def sign_commitment(
    payload: dict,
    request: Request,
    current_user: dict = Depends(require_roles("rep")),
    db: Session = Depends(get_db),
    store: CodeStore = Depends(get_code_store),
):
    """签署承诺书：校验短信验证码 → commitment_signed=true + 审计"""
    if not isinstance(payload, dict):
        raise ParamError("请求体必须是 JSON 对象")
    code = str(payload.get("code") or "").strip()
    if not code:
        raise ParamError("请输入短信验证码")
    phone = _current_phone(db, current_user)
    try:
        result = store.consume(phone, code, settings.CODE_MAX_ATTEMPTS)
    except CodeStoreError as exc:
        logger.error(f"承诺书验证码校验存储不可用: {exc}")
        raise BusinessError("验证码服务暂时不可用，请稍后重试", code=5004)
    if result != "matched":
        raise ParamError("验证码错误或已过期")

    qual = db.query(RepresentativeQualification).filter(
        RepresentativeQualification.representative_id == current_user["id"]
    ).first()
    if qual:
        qual.commitment_signed = True
    else:
        raise ParamError("请先提交备案与资质材料")
    db.commit()
    db.refresh(qual)

    await write_audit_log(
        action="commitment_signed",
        user_id=current_user["id"],
        resource_type="commitment",
        resource_id=str(qual.id),
        after_value={"commitment_signed": True, "signed_at": datetime.utcnow().isoformat()},
        client_ip=_client_ip(request),
        request_id=get_request_id() or None,
    )
    return success({"commitment_signed": True})
