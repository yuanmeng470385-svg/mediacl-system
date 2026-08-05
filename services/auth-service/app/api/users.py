"""
用户管理 API（Web 后台）

    GET  /api/v1/users         用户列表（分页 + role 筛选）
    POST /api/v1/users         创建用户
    PUT  /api/v1/users/{id}    更新用户（角色/状态/手机号/全名）

仅 admin/manager 可用（S6 RBAC）。创建的用户 password_hash 为 NULL ——
需用 scripts/seed_admin.py --username <user> 设置密码后才能登录。
"""

import logging
from typing import Optional

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from shared.common.auth import require_roles
from shared.common.db_session import get_db
from shared.common.response import success, ParamError, BusinessError
from shared.common.pagination import paginate, PaginationParams

from app.db.repositories.user_repo import UserRepo
from app.services.audit_client import write_audit_log
from shared.models.user import User

router = APIRouter(prefix="/api/v1/users", tags=["users"])
logger = logging.getLogger(__name__)

# 合法角色（init_db.sql）：admin / manager / rep / compliance / medical / finance
VALID_ROLES = {"admin", "manager", "rep", "compliance", "medical", "finance"}

# 可更新字段白名单（禁止改 username/role 敏感变更？role 允许改但限管理员——白名单包含 role）
UPDATEABLE_FIELDS = {"full_name", "phone", "email", "role", "region", "status"}


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
    username = (request.get("username") or "").strip()
    full_name = (request.get("full_name") or request.get("name") or "").strip()
    role = request.get("role", "rep")
    phone = request.get("phone")

    if not username or not full_name:
        raise ParamError("username 和 full_name 不能为空")
    if role not in VALID_ROLES:
        raise ParamError(f"role 不合法，可选：{'/'.join(sorted(VALID_ROLES))}")
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
        status=request.get("status", "active"),
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    logger.info(f"创建用户: {username} role={role} by user {current_user['id']}")
    await write_audit_log(
        user_id=current_user["id"], action="user_create",
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
    user = UserRepo.get_by_id(db, user_id)
    if not user:
        raise BusinessError(f"用户不存在: user_id={user_id}", code=4001)

    changed = {k: v for k, v in request.items() if k in UPDATEABLE_FIELDS and v is not None}
    if changed.get("role") is not None and changed["role"] not in VALID_ROLES:
        raise ParamError(f"role 不合法，可选：{'/'.join(sorted(VALID_ROLES))}")
    for field, value in changed.items():
        setattr(user, field, value)
    db.commit()
    db.refresh(user)
    logger.info(f"更新用户: id={user_id} fields={list(changed)} by user {current_user['id']}")
    await write_audit_log(
        user_id=current_user["id"], action="user_update",
        resource_type="user", resource_id=str(user_id),
        before_value={f: None for f in changed},
        after_value=changed,
    )
    return success(user.to_dict())
