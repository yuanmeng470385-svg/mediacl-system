"""
认证服务 API

    POST /api/v1/auth/send-code   发送手机验证码
    POST /api/v1/auth/login       登录（手机号+验证码 或 用户名+密码）
    GET  /api/v1/auth/profile     当前用户（移动端调这个）
    GET  /api/v1/auth/me          当前用户（Web 后台调这个，同一实现）

安全约定：
  - 错误信息统一模糊化，不区分"用户不存在"和"凭证错误"，避免账号枚举。
  - 验证码校验成功后立即作废，防重放。
  - Redis 不可用 → 抛 5xx，绝不放行。
  - profile/me 每次都从库里重新读用户，被停用的账号即便持有有效 token 也会被拒。
"""

import re
import logging
from typing import Optional

from fastapi import APIRouter, Depends, Request
from sqlalchemy.orm import Session

from shared.common.auth import create_token, get_current_user
from shared.common.db_session import get_db
from shared.common.response import success, ParamError, AuthError, BusinessError

from app.config import settings
from app.core.code_store import CodeStore, CodeStoreError, RedisCodeStore
from app.core.security import codes_equal, generate_code, verify_password
from app.db.repositories.user_repo import UserRepo
from app.services.audit_client import write_audit_log
from app.services.sms import SmsSendError, get_sms_sender

router = APIRouter(prefix="/api/v1/auth", tags=["auth"])
logger = logging.getLogger(__name__)

PHONE_RE = re.compile(r"^1[3-9]\d{9}$")

# 统一的模糊错误信息
_ERR_CODE_LOGIN = "手机号或验证码错误"
_ERR_PWD_LOGIN = "用户名或密码错误"

# ---- 依赖：验证码存储 / 短信发送器（单测通过 dependency_overrides 注入替身）----

_code_store_singleton: Optional[CodeStore] = None


def get_code_store() -> CodeStore:
    global _code_store_singleton
    if _code_store_singleton is None:
        _code_store_singleton = RedisCodeStore(settings.REDIS_URL)
    return _code_store_singleton


def get_sender():
    return get_sms_sender(settings.SMS_PROVIDER)


def _client_ip(request: Request) -> Optional[str]:
    """取真实来源 IP。网关转发时以 X-Forwarded-For 首段为准。"""
    forwarded = request.headers.get("x-forwarded-for", "")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.client.host if request.client else None


# ==================== 发送验证码 ====================

@router.post("/send-code")
async def send_code(
    payload: dict,
    request: Request,
    db: Session = Depends(get_db),
    store: CodeStore = Depends(get_code_store),
    sender=Depends(get_sender),
):
    """
    Request:  {"phone": "13800000000"}
    Response: {"expire_seconds": 300}   dev 模式下额外返回 {"code": "123456"}
    """
    phone = str(payload.get("phone") or "").strip()
    if not PHONE_RE.match(phone):
        raise ParamError("手机号格式不正确")

    try:
        remaining = store.in_cooldown(phone)
    except CodeStoreError as exc:
        logger.error(f"验证码存储不可用: {exc}")
        raise BusinessError("验证码服务暂时不可用，请稍后重试", code=5004) from exc

    if remaining > 0:
        raise BusinessError(f"请 {remaining} 秒后再试", code=4002)

    user = UserRepo.get_by_phone(db, phone)
    issued: Optional[str] = None

    if UserRepo.is_active(user):
        issued = generate_code(settings.CODE_LENGTH)
        try:
            store.save(phone, issued, settings.CODE_TTL_SECONDS, settings.CODE_RESEND_SECONDS)
        except CodeStoreError as exc:
            logger.error(f"验证码写入失败: {exc}")
            raise BusinessError("验证码服务暂时不可用，请稍后重试", code=5004) from exc
        try:
            sender.send_code(phone, issued)
        except SmsSendError as exc:
            logger.error(f"短信发送失败 phone={phone}: {exc}")
            raise BusinessError(f"短信发送失败: {exc}", code=6001) from exc
    else:
        # 手机号未注册或已停用：不生成验证码，但仍然起冷却，
        # 让响应和耗时特征与正常流程一致，避免用 send-code 枚举账号。
        try:
            store.save(phone, generate_code(settings.CODE_LENGTH), 1, settings.CODE_RESEND_SECONDS)
            store.drop(phone)
        except CodeStoreError:
            pass
        logger.info("send-code 请求的手机号未注册或已停用，静默处理")

    await write_audit_log(
        action="auth_send_code",
        user_id=user.id if user else None,
        resource_type="user",
        resource_id=phone,
        client_ip=_client_ip(request),
        user_agent=request.headers.get("user-agent"),
        request_id=request.headers.get("x-request-id"),
    )

    data = {"expire_seconds": settings.CODE_TTL_SECONDS}
    if settings.DEV_MODE and issued:
        # 仅开发联调用。AUTH_DEV_MODE 必须在生产关闭。
        data["code"] = issued
    return success(data)


# ==================== 登录 ====================

@router.post("/login")
async def login(
    payload: dict,
    request: Request,
    db: Session = Depends(get_db),
    store: CodeStore = Depends(get_code_store),
):
    """
    两种方式，二选一：
        移动端  {"phone": "13800000000", "code": "123456"}
        Web     {"username": "admin", "password": "..."}

    Response: {"token": "...", "user": {...}}
    """
    phone = str(payload.get("phone") or "").strip()
    code = str(payload.get("code") or "").strip()
    username = str(payload.get("username") or "").strip()
    password = str(payload.get("password") or "")

    if phone and code:
        user = _login_by_code(db, store, phone, code)
    elif username and password:
        user = _login_by_password(db, username, password)
    else:
        raise ParamError("请提供 phone+code 或 username+password")

    token = create_token(user_id=user.id, username=user.username, role=user.role)

    await write_audit_log(
        action="auth_login",
        user_id=user.id,
        resource_type="user",
        resource_id=str(user.id),
        after_value={"method": "sms_code" if phone else "password", "role": user.role},
        client_ip=_client_ip(request),
        user_agent=request.headers.get("user-agent"),
        request_id=request.headers.get("x-request-id"),
    )
    logger.info(f"登录成功 user_id={user.id} role={user.role}")

    return success({"token": token, "user": user.to_dict()})


def _login_by_code(db: Session, store: CodeStore, phone: str, code: str):
    """手机号 + 验证码"""
    if not PHONE_RE.match(phone):
        raise ParamError("手机号格式不正确")

    try:
        stored, exhausted = store.take_attempt(phone, settings.CODE_MAX_ATTEMPTS)
    except CodeStoreError as exc:
        logger.error(f"验证码存储不可用: {exc}")
        raise BusinessError("验证码服务暂时不可用，请稍后重试", code=5004) from exc

    if exhausted:
        # 对外文案与通用登录失败完全一致：exhausted 只会出现在"手机号已注册
        # 且验证码在存"的路径上，文案差异会泄露注册状态，真实原因只进 debug 日志
        logger.debug(f"验证码尝试次数已用尽，需重新获取 phone={phone}")
        raise AuthError(_ERR_CODE_LOGIN)
    if not codes_equal(stored, code):
        raise AuthError(_ERR_CODE_LOGIN)

    user = UserRepo.get_by_phone(db, phone)
    if not UserRepo.is_active(user):
        # 正常流程下这里不该命中（未注册的手机号拿不到验证码），仍兜一层
        raise AuthError(_ERR_CODE_LOGIN)

    # 一次性：校验通过立刻作废
    try:
        store.drop(phone)
    except CodeStoreError as exc:
        logger.error(f"验证码作废失败: {exc}")
        raise BusinessError("验证码服务暂时不可用，请稍后重试", code=5004) from exc

    return user


def _login_by_password(db: Session, username: str, password: str):
    """用户名 + 密码

    注意：当前没有做账号级失败锁定，暴力破解只受网关 IP 限流约束。
    """
    user = UserRepo.get_by_username(db, username)
    if not UserRepo.is_active(user) or not verify_password(password, user.password_hash):
        logger.info(f"密码登录失败 username={username}")
        raise AuthError(_ERR_PWD_LOGIN)
    return user


# ==================== 当前用户 ====================

async def _current_user_payload(current_user: dict, db: Session):
    """token 只是入场券，用户状态以库为准"""
    user = UserRepo.get_by_id(db, current_user["id"])
    if not UserRepo.is_active(user):
        raise AuthError("账号不存在或已停用")
    return success(user.to_dict())


@router.get("/profile")
async def profile(
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """当前用户信息（移动端）"""
    return await _current_user_payload(current_user, db)


@router.get("/me")
async def me(
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """当前用户信息（Web 后台）"""
    return await _current_user_payload(current_user, db)
