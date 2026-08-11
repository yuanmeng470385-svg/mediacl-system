"""
JWT 认证工具

使用方式:
    from shared.common.auth import get_current_user

    @router.get("/api/v1/protected")
    async def protected_route(current_user: dict = Depends(get_current_user)):
        return success(current_user)
"""

import os
import jwt
from datetime import datetime, timedelta
from typing import Dict, Optional
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from sqlalchemy.orm import Session

from shared.common.db_session import get_db
from shared.common.response import PermissionError
from shared.models.user import User

security = HTTPBearer()


def create_token(user_id: int, username: str, role: str, **kwargs) -> str:
    """生成 JWT Token"""
    secret = os.getenv("JWT_SECRET", "dev-secret-change-me")
    expires_in = os.getenv("JWT_EXPIRES_IN", "7d")

    # 解析过期时间 (如 "7d", "24h", "60m")
    delta = _parse_expires(expires_in)

    payload = {
        "sub": str(user_id),
        "username": username,
        "role": role,
        "iat": datetime.utcnow(),
        "exp": datetime.utcnow() + delta,
        **kwargs
    }
    return jwt.encode(payload, secret, algorithm="HS256")


def verify_token(token: str) -> Dict:
    """验证并解析 JWT Token"""
    secret = os.getenv("JWT_SECRET", "dev-secret-change-me")
    try:
        payload = jwt.decode(token, secret, algorithms=["HS256"])
        return payload
    except jwt.ExpiredSignatureError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"code": 2001, "message": "Token 已过期"}
        )
    except jwt.InvalidTokenError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"code": 2002, "message": "Token 无效"}
        )


async def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(security)
) -> Dict:
    """FastAPI 依赖注入：从 Authorization Header 获取当前用户"""
    token = credentials.credentials
    payload = verify_token(token)
    return {
        "id": int(payload["sub"]),
        "username": payload["username"],
        "role": payload["role"]
    }


def require_roles(*roles: str):
    """角色校验依赖（S6 RBAC）。

    用法：
        from shared.common.auth import require_roles
        @router.put("/rules/{rule_id}")
        async def update_rule(
            rule_id: int,
            current_user: dict = Depends(require_roles("admin", "manager")),
        ):
    未登录 → 401（get_current_user 兜底）；角色不符 → 403（code 3000）。
    403 抛 PermissionError（AppError）而非裸 HTTPException：各服务已注册共享
    exception_handler，统一渲染 {code, message, data}（前端按 resp.data.code 解析）。
    角色表（init_db.sql）：admin / manager / rep / compliance / medical / finance。
    """
    async def _checker(
        db: Session = Depends(get_db),
        current_user: dict = Depends(get_current_user),
    ) -> dict:
        # 角色与账号状态以库为准（合规硬伤修复）：token 里的 role 是登录时刻的
        # 快照，旧实现只信 token → 停用/降级后旧 token 最长 7 天（JWT_EXPIRES_IN）
        # 仍能访问受限端点。每次受限请求查一次主键，状态不符或角色被降级立即拒绝。
        user = db.query(User).filter(User.id == current_user["id"]).first()
        if not user or user.status != "active":
            raise PermissionError("账号不存在或已停用")
        if user.role not in roles:
            raise PermissionError(f"无权限：需要角色 {'/'.join(roles)}")
        return current_user

    return _checker


def _parse_expires(expires_in: str) -> timedelta:
    """解析过期时间字符串"""
    unit = expires_in[-1]
    value = int(expires_in[:-1])
    if unit == "d":
        return timedelta(days=value)
    elif unit == "h":
        return timedelta(hours=value)
    elif unit == "m":
        return timedelta(minutes=value)
    else:
        return timedelta(days=7)
