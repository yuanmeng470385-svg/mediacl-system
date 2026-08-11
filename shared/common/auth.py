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

# 弱密钥集合（H1，2026-08-11）：空 / 代码默认值 / .env.example 模板占位值都算"未配置"。
# 此前 create_token/verify_token 静默回退到公开默认密钥 "dev-secret-change-me"——
# 漏配 JWT_SECRET 时任何人可用公开密钥伪造任意角色 token 直连各服务端口（8001-8007）。
# 现统一 fail-fast：未配置/弱值在启动（各服务 main.py 守卫）与调用（本函数）两处拦截。
WEAK_JWT_SECRETS = {"", "dev-secret-change-me", "change_me_to_a_random_secret_string"}


def validate_jwt_secret(secret: str) -> str:
    """校验 JWT_SECRET；未配置或为弱值直接抛 RuntimeError（fail-fast）。

    各服务 main.py 启动时调用（与 gateway/auth 已有守卫同源）；create_token/verify_token
    内部同样检查——双保险，运行时环境变化也不会回到公开默认密钥。
    """
    if secret in WEAK_JWT_SECRETS:
        raise RuntimeError(
            "JWT_SECRET 未配置或仍是默认值，服务拒绝启动。"
            "请在 .env 中设置一个足够随机的 JWT_SECRET（例：openssl rand -hex 32）。"
        )
    return secret


def _jwt_secret() -> str:
    """读取并校验 JWT_SECRET（create_token/verify_token 共用，无默认回退）"""
    return validate_jwt_secret(os.getenv("JWT_SECRET", ""))


def create_token(user_id: int, username: str, role: str, **kwargs) -> str:
    """生成 JWT Token"""
    secret = _jwt_secret()
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
    secret = _jwt_secret()
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
    credentials: HTTPAuthorizationCredentials = Depends(security),
    db: Session = Depends(get_db),
) -> Dict:
    """FastAPI 依赖注入：从 Authorization Header 获取当前用户

    H2（2026-08-11）：账号状态与角色以库为准——token 只是登录时刻快照（最长 7 天），
    只验签名会让停用/降级账号的旧 token 继续访问全部非 require_roles 端点（列表、
    收藏、知识库可见性、两个 WS 等）。每次请求主键查库：用户不存在/非 active → 401；
    返回库内实时 role（降级立即生效，admin 旁路判断不再被旧快照蒙蔽）。
    """
    token = credentials.credentials
    payload = verify_token(token)
    user = db.query(User).filter(User.id == int(payload["sub"])).first()
    if not user or user.status != "active":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"code": 2003, "message": "账号不存在或已停用"}
        )
    return {
        "id": user.id,
        "username": user.username,
        "role": user.role,
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
