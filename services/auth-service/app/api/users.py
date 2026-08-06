"""
用户管理 API（Web 后台）

    GET  /api/v1/users         用户列表（分页 + role 筛选）
    POST /api/v1/users         创建用户
    PUT  /api/v1/users/{id}    更新用户（角色/状态/手机号/全名）

仅 admin/manager 可用（S6 RBAC）。创建的用户 password_hash 为 NULL ——
需用 scripts/seed_admin.py --username <user> 设置密码后才能登录。

安全加固（2026-08 审计修复）：
  - role 变更（创建/更新）仅限 admin：manager 传 role 一律拒绝（code 3000）；
  - 任何人（含 admin）都不能改自己的 role/status，防误操作自锁死（改别人不受限）；
  - 三个端点处理前从库重读当前用户 status/role：停用/降级即时生效，
    持有未过期 token 也以库为准（token 只是入场券）。
"""

import logging
from typing import Optional

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from shared.common.auth import require_roles
from shared.common.db_session import get_db
from shared.common.response import success, ParamError, BusinessError, PermissionError
from shared.common.pagination import paginate, PaginationParams

from app.db.repositories.user_repo import UserRepo
from app.services.audit_client import write_audit_log
from shared.models.user import User

router = APIRouter(prefix="/api/v1/users", tags=["users"])
logger = logging.getLogger(__name__)

# 合法角色（init_db.sql）：admin / manager / rep / compliance / medical / finance
VALID_ROLES = {"admin", "manager", "rep", "compliance", "medical", "finance"}

# status 只允许这两个枚举值，拒绝任意字符串写入垃圾状态
VALID_STATUSES = {"active", "disabled"}

# 可更新字段白名单。role 虽在清单里，但只有 admin 能改（见 update_user 的校验）
UPDATEABLE_FIELDS = {"full_name", "phone", "email", "role", "region", "status"}


def _reload_current_user(db: Session, current_user: dict) -> User:
    """RBAC 以库为准：token 只是入场券，停用/降级即时生效。

    require_roles（shared/common/auth.py）只信任 token 里的 role/status 声明：
    被停用或降级的用户只要 token 没过期，就能拿着旧声明继续操作。用户管理是
    权限最高风险入口，这里在每个端点处理请求前重读库：
      - 用户不存在或 status != active → 403：账号已停用，旧 token 立即作废；
      - 库中 role 与 token 声明不一致（被降级/提权）→ 403：以库为准，
        旧声明不得继续操作。
    返回库里的 User（调用方以此做角色判断，不再信 token 声明）。
    """
    user = UserRepo.get_by_id(db, current_user["id"])
    if not user or user.status != "active":
        raise PermissionError("账号不存在或已停用，请重新登录")
    if user.role != current_user.get("role"):
        raise PermissionError("角色已变更，请重新登录后再操作")
    return user


@router.get("")
async def list_users(
    page: int = 1,
    page_size: int = 20,
    role: Optional[str] = None,
    status: Optional[str] = None,
    current_user: dict = Depends(require_roles("admin", "manager")),
    db: Session = Depends(get_db),
):
    """用户列表（不含 password_hash，模型 to_dict 已保证）"""
    _reload_current_user(db, current_user)
    p = PaginationParams(page=page, page_size=page_size)
    query = db.query(User)
    if role:
        query = query.filter(User.role == role)
    if status:
        query = query.filter(User.status == status)
    total = query.count()
    items = query.order_by(User.id.desc()).offset((p.page - 1) * p.page_size).limit(p.page_size).all()
    return success(paginate([u.to_dict() for u in items], total, p.page, p.page_size))


@router.post("")
async def create_user(
    request: dict,
    current_user: dict = Depends(require_roles("admin", "manager")),
    db: Session = Depends(get_db),
):
    """创建用户。密码留空（password_hash=None）→ 该账号无法密码登录，需 seed_admin 设置"""
    actor = _reload_current_user(db, current_user)
    username = (request.get("username") or "").strip()
    full_name = (request.get("full_name") or request.get("name") or "").strip()
    role = request.get("role", "rep")
    phone = request.get("phone")

    if not username or not full_name:
        raise ParamError("username 和 full_name 不能为空")
    # 角色变更仅限 admin：manager 传 role（哪怕 role=rep）一律拒绝，
    # 只能创建默认角色 rep —— 防止 manager 直接造出 admin 账号
    if "role" in request and actor.role != "admin":
        raise PermissionError("仅 admin 可指定新用户角色")
    if role not in VALID_ROLES:
        raise ParamError(f"role 不合法，可选：{'/'.join(sorted(VALID_ROLES))}")
    status = request.get("status", "active")
    if status not in VALID_STATUSES:
        raise ParamError(f"status 不合法，可选：{'/'.join(sorted(VALID_STATUSES))}")
    if db.query(User).filter(User.username == username).first():
        raise BusinessError(f"用户名已存在: {username}", code=4001)

    user = User(
        username=username,
        full_name=full_name,
        phone=phone,
        email=request.get("email"),
        role=role,
        region=request.get("region"),
        manager_id=request.get("manager_id"),
        status=status,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    logger.info(f"创建用户: {username} role={role} by user {actor.id}")
    await write_audit_log(
        user_id=actor.id, action="user_create",
        resource_type="user", resource_id=str(user.id),
        after_value=user.to_dict(),
    )
    return success(user.to_dict(), "用户已创建")


@router.put("/{user_id}")
async def update_user(
    user_id: int,
    request: dict,
    current_user: dict = Depends(require_roles("admin", "manager")),
    db: Session = Depends(get_db),
):
    """更新用户（白名单字段）。status=disabled 会立即停用该账号（profile/me 每次重读）"""
    actor = _reload_current_user(db, current_user)
    user = UserRepo.get_by_id(db, user_id)
    if not user:
        raise BusinessError(f"用户不存在: user_id={user_id}", code=4001)

    changed = {k: v for k, v in request.items() if k in UPDATEABLE_FIELDS and v is not None}

    # 角色变更仅限 admin：manager 改任何人的 role（含自己）都拒绝
    if "role" in changed and actor.role != "admin":
        raise PermissionError("仅 admin 可变更用户角色")
    if "role" in changed and changed["role"] not in VALID_ROLES:
        raise ParamError(f"role 不合法，可选：{'/'.join(sorted(VALID_ROLES))}")
    # status 只接受枚举值，拒绝垃圾状态
    if "status" in changed and changed["status"] not in VALID_STATUSES:
        raise ParamError(f"status 不合法，可选：{'/'.join(sorted(VALID_STATUSES))}")

    # 禁止自改 role/status：任何人（含 admin）都不能改自己的角色或停用/恢复自己。
    # 防止误操作把自己降级/停用造成账号自锁死（改别人不受限）。
    # 注：不拦"把自己改成更高角色"这类自提升 —— 一律不允许自改 role 更稳妥。
    if user_id == actor.id and (set(changed) & {"role", "status"}):
        raise PermissionError("不能修改自己的角色或停用自己")

    # 变更前快照：须在 setattr 之前取（user 对象随后被原地修改）
    before_values = {f: getattr(user, f) for f in changed}
    for field, value in changed.items():
        setattr(user, field, value)
    db.commit()
    db.refresh(user)
    logger.info(f"更新用户: id={user_id} fields={list(changed)} by user {actor.id}")
    await write_audit_log(
        user_id=actor.id, action="user_update",
        resource_type="user", resource_id=str(user_id),
        before_value=before_values,
        after_value=changed,
    )
    return success(user.to_dict())
