"""
JWT 认证中间件（网关层统一验证）

TODO: 实现完整的 JWT 验证逻辑
- 从 Authorization Header 提取 token
- 验证 token 有效性
- 白名单路径无需认证（/health, /api/v1/auth/login 等）
"""
import logging

logger = logging.getLogger(__name__)

# 白名单路径（无需认证）
PUBLIC_PATHS = [
    "/health",
    "/api/v1/auth/login",
    "/api/v1/auth/register",
    "/docs",
    "/openapi.json",
]


class AuthMiddleware:
    """JWT 认证中间件"""

    @staticmethod
    def is_public_path(path: str) -> bool:
        return any(path.startswith(p) for p in PUBLIC_PATHS)

    # TODO: 实现完整的 JWT 验证
    # def verify_token(self, token: str) -> dict:
    #     ...
