"""
认证服务 API

    POST /api/v1/auth/send-code   发送手机验证码（scene=login 默认 / register 注册）
    POST /api/v1/auth/login       登录（手机号+验证码 或 用户名+密码）
    POST /api/v1/auth/register    医生自助注册（公开；验证码制，注册即登录）
    GET  /api/v1/auth/profile     当前用户（移动端调这个）
    GET  /api/v1/auth/me          当前用户（Web 后台调这个，同一实现）

安全约定：
  - 错误信息统一模糊化，不区分"用户不存在"和"凭证错误"，避免账号枚举。
  - 注册场景（scene=register）刻意反向：已注册号明确提示"请直接登录"，
    未注册号才发码——注册页行业标准做法，与登录场景的防枚举不冲突
    （愿调注册场景探测的人，本来就等于在用注册页探测）。
  - 两场景验证码键命名空间独立，互不通用（注册码不能登录，登录码不能注册）。
  - 验证码匹配即作废：比较与作废在同一原子操作内完成，防并发重放。
  - Redis 不可用 → 抛 5xx，绝不放行。
  - profile/me 每次都从库里重新读用户，被停用的账号即便持有有效 token 也会被拒。
"""

import re
import asyncio
import logging
from typing import Optional

from fastapi import APIRouter, Depends, Request
from sqlalchemy.orm import Session

from shared.common.auth import create_token, get_current_user
from shared.common.context import get_request_id
from shared.common.db_session import get_db
from shared.common.response import success, ParamError, AuthError, BusinessError
from shared.models.hcp import Hcp
from shared.models.user import User

from app.config import settings
from app.core.code_store import (
    CONSUME_EXHAUSTED,
    CONSUME_MATCHED,
    SCENE_LOGIN,
    SCENE_REGISTER,
    CodeStore,
    CodeStoreError,
    RedisCodeStore,
)
from app.core.security import generate_code, hash_password, verify_password
from app.db.repositories.user_repo import UserRepo
from app.services.audit_client import write_audit_log
from app.services.sms import SmsSendError, get_sms_sender

router = APIRouter(prefix="/api/v1/auth", tags=["auth"])
logger = logging.getLogger(__name__)

PHONE_RE = re.compile(r"^1[3-9]\d{9}$")

# 统一的模糊错误信息
_ERR_CODE_LOGIN = "手机号或验证码错误"
_ERR_PWD_LOGIN = "用户名或密码错误"

# A1 时序枚举防护：用户不存在/已停用/未设密码的失败路径会"秒回"（不执行
# bcrypt），与"密码错误"路径（一次 bcrypt 校验，约百毫秒级）存在可探测的
# 耗时差。本常量是固定合法的 bcrypt 哈希（rounds=12，仅用于拉平耗时，
# 不参与任何真实比对），失败路径用它补一次真实校验。
_DUMMY_PASSWORD_HASH = "$2b$12$kp0.wW8C1t9GBcPh2EN9Kety7cmEClhYS/tCrN.iyGC7lAe1xHcyW"

# ---- 依赖：验证码存储 / 短信发送器（单测通过 dependency_overrides 注入替身）----

_code_store_singleton: Optional[CodeStore] = None


def get_code_store() -> CodeStore:
    global _code_store_singleton
    if _code_store_singleton is None:
        _code_store_singleton = RedisCodeStore(settings.REDIS_URL)
    return _code_store_singleton


_login_guard_singleton = None


def get_login_guard():
    """M9 密码登录失败锁定（单例；测试用 dependency_overrides 注入 Memory 版）"""
    global _login_guard_singleton
    if _login_guard_singleton is None:
        from app.core.login_guard import RedisLoginGuard
        _login_guard_singleton = RedisLoginGuard(
            settings.REDIS_URL,
            max_failures=settings.LOGIN_MAX_FAILURES,
            lockout_seconds=settings.LOGIN_LOCKOUT_SECONDS,
        )
    return _login_guard_singleton


# A8：发送器实例模块级缓存（provider -> sender）。aliyun SDK client 构造有
# 开销，每次请求重建会拖慢 send-code。配置切换时自动重建。
# 线程安全说明：send_code 经 asyncio.to_thread 在线程池并发调用，
# AliyunSmsSender 的 SDK client 无共享可变状态（每次调用独立构造请求对象）、
# ConsoleSender 无状态，两种现有实现并发安全；未来新增有状态实现需自行加锁。
_sender_cache: Optional[tuple] = None


def get_sender():
    global _sender_cache
    provider = settings.SMS_PROVIDER.strip().lower()
    if _sender_cache is None or _sender_cache[0] != provider:
        _sender_cache = (provider, get_sms_sender(settings.SMS_PROVIDER))
    return _sender_cache[1]


def _client_ip(request: Request) -> Optional[str]:
    """取真实来源 IP。网关转发时以 X-Forwarded-For 首段为准。"""
    forwarded = request.headers.get("x-forwarded-for", "")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.client.host if request.client else None


# ==================== 发送验证码 ====================

async def _issue_code(store: CodeStore, sender, phone: str, scene: str) -> str:
    """生成并发送一条验证码（真实发出，计入日限）。send-code 两个场景共用。"""
    issued = generate_code(settings.CODE_LENGTH)
    try:
        saved = store.save(
            phone,
            issued,
            settings.CODE_TTL_SECONDS,
            settings.CODE_RESEND_SECONDS,
            scene=scene,
        )
    except CodeStoreError as exc:
        logger.error(f"验证码写入失败: {exc}")
        raise BusinessError("验证码服务暂时不可用，请稍后重试", code=5004) from exc
    if not saved:
        # A9：冷却检查与 save 之间不再有竞态——save 用 SET NX，键已存在
        # （并发请求已先写入）时返回 False。这里按冷却处理（响应码与
        # in_cooldown 一致），后到者不再覆盖先发验证码（覆盖会让用户拿到废码）。
        # 注：验证码 TTL（默认 300s）大于冷却（60s）时，冷却结束但验证码仍
        # 在存的重发请求也会走到这里——先发验证码未被覆盖，行为可接受。
        # 文案与实际一致：本次请求并未发出新验证码，已有验证码仍在有效期内
        raise BusinessError("验证码仍在有效期内，请稍后再试", code=4002)
    try:
        # A8：send_sms 是同步阻塞网络调用，丢线程池执行，不阻塞事件循环
        await asyncio.to_thread(sender.send_code, phone, issued)
    except SmsSendError as exc:
        logger.error(f"短信发送失败 phone={phone}: {exc}")
        raise BusinessError(f"短信发送失败: {exc}", code=6001) from exc
    try:
        store.bump_daily(phone)
    except CodeStoreError:
        # 计数失败只影响日限精度；验证码已实际发出，不回滚不阻断
        pass
    return issued


@router.post("/send-code")
async def send_code(
    payload: dict,
    request: Request,
    db: Session = Depends(get_db),
    store: CodeStore = Depends(get_code_store),
    sender=Depends(get_sender),
):
    """
    Request:  {"phone": "13800000000"}                        —— 登录场景（默认）
              {"phone": "13800000000", "scene": "register"}   —— 注册场景（只对未注册号发）
    Response: {"expire_seconds": 300}   dev 模式下额外返回 {"code": "123456"}
    """
    # A3：非 JSON 对象（数组/字符串等）直接参数错误，不让 dict 方法抛 AttributeError 500
    if not isinstance(payload, dict):
        raise ParamError("请求体必须是 JSON 对象")

    phone = str(payload.get("phone") or "").strip()
    if not PHONE_RE.match(phone):
        raise ParamError("手机号格式不正确")

    scene = str(payload.get("scene") or SCENE_LOGIN).strip().lower()
    if scene not in (SCENE_LOGIN, SCENE_REGISTER):
        raise ParamError("不支持的验证码场景")

    user = UserRepo.get_by_phone(db, phone)

    # 注册场景：已注册号（含 username 撞号）明确拒绝不发码。
    # 放在冷却/日限检查之前——注册页语义优先给「请直接登录」，
    # 否则刚发过码又撞注册入口的用户只会看到干等 60s 的冷却提示
    if scene == SCENE_REGISTER and (
        user is not None or UserRepo.get_by_username(db, phone) is not None
    ):
        raise BusinessError("该手机号已注册，请直接登录", code=4001)

    try:
        remaining = store.in_cooldown(phone, scene=scene)
        if remaining > 0:
            raise BusinessError(f"请 {remaining} 秒后再试", code=4002)
        if store.daily_count(phone) >= settings.CODE_DAILY_LIMIT:
            # 滚动 24h 日限（跨场景按手机号累计）：SMS 成本护栏
            raise BusinessError("今日验证码发送次数已达上限，请明天再试", code=4002)
    except CodeStoreError as exc:
        logger.error(f"验证码存储不可用: {exc}")
        raise BusinessError("验证码服务暂时不可用，请稍后重试", code=5004) from exc

    issued: Optional[str] = None

    if scene == SCENE_REGISTER:
        issued = await _issue_code(store, sender, phone, scene)
    elif UserRepo.is_active(user):
        issued = await _issue_code(store, sender, phone, scene)
    else:
        # 手机号未注册或已停用：不生成验证码，但仍然起冷却，
        # 让响应和耗时特征与正常流程一致，避免用 send-code 枚举账号。
        try:
            store.save(phone, generate_code(settings.CODE_LENGTH), 1, settings.CODE_RESEND_SECONDS)
            store.drop(phone)
        except CodeStoreError:
            pass
        # A7（缓解非根治）：正常路径走了一次真实短信发送（网络往返），
        # 未注册路径少了这一步、响应明显更快。aliyun 通道下用固定延迟拉平
        # 耗时特征。注意：真实网络抖动远大于该固定值，这只是缓解统计层面的
        # 明显偏差，根治需网关/风控层统一延迟策略。
        if settings.SMS_PROVIDER.strip().lower() == "aliyun":
            await asyncio.sleep(0.2)
        logger.info("send-code 请求的手机号未注册或已停用，静默处理")

    await write_audit_log(
        action="auth_send_code",
        user_id=user.id if user else None,
        resource_type="user",
        resource_id=phone,
        after_value={"scene": scene},
        client_ip=_client_ip(request),
        user_agent=request.headers.get("user-agent"),
        # A6：取 RequestIDMiddleware 校验过的上下文 ID（超长/非法头会被中间件
        # 替换成新 UUID），不用原始 X-Request-ID 头——超长头会把审计列撑爆，
        # 且审计 write 失败被吞时会连自己的审计都抹掉
        request_id=get_request_id() or None,
    )

    data = {"expire_seconds": settings.CODE_TTL_SECONDS}
    if settings.DEV_MODE and issued:
        # 仅开发联调用。AUTH_DEV_MODE 必须在生产关闭。
        data["code"] = issued
    return success(data)


# ==================== 医生自助注册（部署挂账 §5 → 2026-09-14 升级验证码制） ====================

@router.post("/register")
async def register(
    payload: dict,
    request: Request,
    db: Session = Depends(get_db),
    store: CodeStore = Depends(get_code_store),
):
    """医生自助注册（公开端点，验证码制，注册即登录）。

    Request:  {"phone","code","full_name","password?","hospital?","department?","title?"}
              code 必填——scene=register 的 send-code 下发的验证码（只对未注册号发，
              手机号真实性由短信通道验证）；password 选填，不填则该账号只能验证码登录。
    Response: {"token","user"} —— 同 login，前端注册成功直接进入已登录态。

    医院信息（hospital/department/title）落 hcps 医生档案表（与 hcp-service
    共表，按 phone 关联）；doctor_profiles 是偏好画像、不含这些列，不为此加列。
    """
    if not isinstance(payload, dict):
        raise ParamError("请求体必须是 JSON 对象")

    phone = str(payload.get("phone") or "").strip()
    full_name = str(payload.get("full_name") or "").strip()
    code = str(payload.get("code") or "").strip()
    password = str(payload.get("password") or "")
    hospital = str(payload.get("hospital") or "").strip() or None
    department = str(payload.get("department") or "").strip() or None
    title = str(payload.get("title") or "").strip() or None

    if not PHONE_RE.match(phone):
        raise ParamError("手机号格式不正确")
    if not (2 <= len(full_name) <= 30):
        raise ParamError("姓名长度须为 2-30 个字符")
    if not code:
        raise ParamError("请输入验证码")
    if password and (
        len(password) < 8
        or not re.search(r"[A-Za-z]", password)
        or not re.search(r"\d", password)
    ):
        # 密码选填：填了才校验强度；不填 = 未设密码、禁止密码登录（模型注释口径）
        raise ParamError("密码至少 8 位，且须同时包含字母和数字")

    # users.phone 有部分唯一索引、username 唯一；注册 username=phone，两查都做。
    # 查重放在验码之前——撞号不烧码（码是被真实发出的资源）
    if UserRepo.get_by_phone(db, phone) or UserRepo.get_by_username(db, phone):
        # 4001 与 users.py 创建用户撞号同码（username/phone 冲突统一口径）
        raise BusinessError("该手机号已注册，请直接登录", code=4001)

    # 验证码核销（注册场景独立命名空间，登录码不通用）。consume 原子
    # （比对+作废同一拍），并发携带同一码只有一个能通过，天然防重放
    try:
        result = store.consume(phone, code, settings.CODE_MAX_ATTEMPTS, scene=SCENE_REGISTER)
    except CodeStoreError as exc:
        logger.error(f"验证码存储不可用: {exc}")
        raise BusinessError("验证码服务暂时不可用，请稍后重试", code=5004) from exc
    if result != CONSUME_MATCHED:
        # notfound/mismatch/exhausted 对外统一文案（走到这里的号必未注册，无枚举面）
        raise ParamError("验证码错误或已过期，请重新获取")

    user = User(
        username=phone,
        full_name=full_name,
        phone=phone,
        password_hash=hash_password(password) if password else None,
        role="doctor",
        status="active",
    )
    db.add(user)
    hcp = None
    if hospital or department or title:
        hcp = Hcp(
            name=full_name,
            phone=phone,
            hospital=hospital,
            department=department,
            title=title,
        )
        db.add(hcp)
    db.commit()
    db.refresh(user)

    token = create_token(user_id=user.id, username=user.username, role=user.role)

    await write_audit_log(
        action="auth_register",
        user_id=user.id,
        resource_type="user",
        resource_id=str(user.id),
        after_value={"role": "doctor", "hcp_id": hcp.id if hcp else None},
        client_ip=_client_ip(request),
        user_agent=request.headers.get("user-agent"),
        request_id=get_request_id() or None,
    )
    logger.info(f"医生自助注册成功 user_id={user.id}")

    return success({"token": token, "user": user.to_dict()})


# ==================== 登录 ====================

@router.post("/login")
async def login(
    payload: dict,
    request: Request,
    db: Session = Depends(get_db),
    store: CodeStore = Depends(get_code_store),
    guard=Depends(get_login_guard),
):
    """
    两种方式，二选一：
        移动端  {"phone": "13800000000", "code": "123456"}
        Web     {"username": "admin", "password": "..."}

    Response: {"token": "...", "user": {...}}
    """
    # A3：非 JSON 对象（数组/字符串等）直接参数错误，不让 dict 方法抛 AttributeError 500
    if not isinstance(payload, dict):
        raise ParamError("请求体必须是 JSON 对象")

    phone = str(payload.get("phone") or "").strip()
    code = str(payload.get("code") or "").strip()
    username = str(payload.get("username") or "").strip()
    password = str(payload.get("password") or "")

    if phone and code:
        method = "sms_code"
        try:
            user = _login_by_code(db, store, phone, code)
        except AuthError:
            # 合规硬伤回归：验证码错误/用尽必须留痕（此前登录失败零审计）
            await _write_login_failed_audit(request, db, method, phone=phone)
            raise
    elif username and password:
        method = "password"
        # M9（2026-08-21 审计）：锁定检查在 bcrypt 之前 —— 锁内不消耗哈希直接拒；
        # guard 是同步 Redis 客户端，统一 to_thread 不占事件循环（同批④口径）
        remaining = await asyncio.to_thread(guard.lock_remaining, username)
        if remaining > 0:
            minutes = (remaining + 59) // 60
            await _write_login_failed_audit(request, db, method, username=username)
            raise AuthError(f"登录尝试次数过多，账号已锁定，请 {minutes} 分钟后再试")
        try:
            user = _login_by_password(db, username, password)
        except AuthError:
            # 合规硬伤回归：密码错误/用户不存在必须留痕
            await asyncio.to_thread(guard.record_failure, username)
            await _write_login_failed_audit(request, db, method, username=username)
            raise
        await asyncio.to_thread(guard.reset, username)
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
        # A6：同 send-code，用中间件校验过的上下文 request_id，不用原始头
        request_id=get_request_id() or None,
    )
    logger.info(f"登录成功 user_id={user.id} role={user.role}")

    return success({"token": token, "user": user.to_dict()})


async def _write_login_failed_audit(
    request: Request,
    db: Session,
    method: str,
    phone: str = "",
    username: str = "",
) -> None:
    """登录失败留痕（合规取证）。

    记录方法与账号标识（不含密码/验证码本身）；用户名/手机号能定位到用户时
    尽量带 user_id，方便审计按用户检索。write_audit_log 内部容错，失败不影响
    登录失败响应本身。
    """
    user_id = None
    try:
        if username:
            u = UserRepo.get_by_username(db, username)
            if u and UserRepo.is_active(u):
                user_id = u.id
        elif phone:
            u = UserRepo.get_by_phone(db, phone)
            if u and UserRepo.is_active(u):
                user_id = u.id
    except Exception:
        pass
    await write_audit_log(
        action="auth_login_failed",
        user_id=user_id,
        resource_type="user",
        after_value={"method": method, "username": username or None, "phone": phone or None},
        client_ip=_client_ip(request),
        user_agent=request.headers.get("user-agent"),
        # A6：同 send-code，用中间件校验过的上下文 request_id，不用原始头
        request_id=get_request_id() or None,
    )


def _login_by_code(db: Session, store: CodeStore, phone: str, code: str):
    """手机号 + 验证码"""
    if not PHONE_RE.match(phone):
        raise ParamError("手机号格式不正确")

    try:
        result = store.consume(phone, code, settings.CODE_MAX_ATTEMPTS)
    except CodeStoreError as exc:
        logger.error(f"验证码存储不可用: {exc}")
        raise BusinessError("验证码服务暂时不可用，请稍后重试", code=5004) from exc

    if result == CONSUME_EXHAUSTED:
        # 对外文案与通用登录失败完全一致：exhausted 只会出现在"手机号已注册
        # 且验证码在存"的路径上，文案差异会泄露注册状态，真实原因只进 debug 日志
        logger.debug(f"验证码尝试次数已用尽，需重新获取 phone={phone}")
    if result != CONSUME_MATCHED:
        # matched 之外的状态（mismatch/exhausted/notfound）对外文案统一，
        # 防账号枚举与验证码探测
        raise AuthError(_ERR_CODE_LOGIN)

    user = UserRepo.get_by_phone(db, phone)
    if not UserRepo.is_active(user):
        # 正常流程下这里不该命中（未注册的手机号拿不到验证码），仍兜一层
        raise AuthError(_ERR_CODE_LOGIN)

    # 一次性：consume 匹配成功时已在同一原子操作内作废，无需再 drop
    return user


def _login_by_password(db: Session, username: str, password: str):
    """用户名 + 密码

    M9（2026-08-21）：账号级失败锁定由 login 端点接线（guard，bcrypt 前拒）；
    本函数只管凭证校验本身。

    A1 时序枚举防护：用户不存在/已停用/未设密码这些"秒回"分支都会对固定
    dummy hash 执行一次真实 bcrypt 校验，把耗时拉到与"密码错误"路径同一量级，
    防用响应时间探测账号是否存在。各分支对外文案完全一致。
    """
    user = UserRepo.get_by_username(db, username)
    if not UserRepo.is_active(user):
        verify_password(password, _DUMMY_PASSWORD_HASH)
        logger.info(f"密码登录失败 username={username}")
        raise AuthError(_ERR_PWD_LOGIN)
    if not user.password_hash:
        # 未设密码：verify_password 对空 hash 直接返回 False，不产生 bcrypt
        # 耗时，这里补一次 dummy 校验拉平耗时
        verify_password(password, _DUMMY_PASSWORD_HASH)
        logger.info(f"密码登录失败 username={username}")
        raise AuthError(_ERR_PWD_LOGIN)
    if not verify_password(password, user.password_hash):
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
