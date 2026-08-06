"""
JWT 认证中间件（网关层统一验证）

所有请求到达网关后，先过此中间件验证 token。
白名单路径无需认证。

使用方式（在 gateway main.py 中）:
    from app.core.auth_middleware import AuthMiddleware
    app.add_middleware(AuthMiddleware)
"""

import logging
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse
from starlette.requests import Request

import jwt

from app.config import settings
from shared.common.internal_auth import get_internal_api_key

logger = logging.getLogger(__name__)

# 无需认证的路径白名单
#
# 注意 _is_public 用的是前缀匹配，新增条目前先确认不会顺带放开别的路由
# （例如 "/api/v1/audit/log" 会连 "/api/v1/audit/logs" 一起放开）。
PUBLIC_PATHS = [
    "/health",
    # 认证入口（auth-service :8007）—— 只有这两个免认证，
    # /api/v1/auth/profile 和 /api/v1/auth/me 需要携带 token
    "/api/v1/auth/login",
    "/api/v1/auth/send-code",
    "/docs",
    "/openapi.json",
    "/redoc",
]

# 服务间内部调用路径 —— 不走 JWT，但必须携带 X-Internal-Key 头
# （S2 修复：audit/log 曾被未认证者伪造，compliance/check 曾被未授权调用触发付费 LLM）。
# 注意这里用的是"精确匹配或子路径"（p + "/"），避免 /api/v1/audit/logs 被误判为内部路径。
INTERNAL_PATHS = [
    "/api/v1/compliance/check",
    "/api/v1/audit/log",
    "/api/v1/hcps/profile-update",
]


class AuthMiddleware(BaseHTTPMiddleware):
    """JWT 认证中间件"""

    async def dispatch(self, request: Request, call_next):
        path = request.url.path

        # 内部接口：必须携带有效的 X-Internal-Key（服务间调用）
        if self._is_internal(path):
            key = request.headers.get("X-Internal-Key", "")
            if key != get_internal_api_key():
                return JSONResponse(
                    status_code=403,
                    content={"code": 3001, "message": "禁止访问：内部接口需要有效的 X-Internal-Key", "data": None}
                )
            return await call_next(request)

        # 白名单路径直接放行
        if self._is_public(path):
            return await call_next(request)

        # 从 Authorization Header 提取 token
        auth_header = request.headers.get("Authorization", "")
        if not auth_header.startswith("Bearer "):
            return JSONResponse(
                status_code=401,
                content={"code": 2000, "message": "未登录，缺少 Authorization Header", "data": None}
            )

        token = auth_header[7:]  # 去掉 "Bearer " 前缀

        try:
            # 统一从 settings 读取 —— 唯一读取点，弱密钥在 app/config.py 启动守卫已拦下
            secret = settings.JWT_SECRET
            payload = jwt.decode(token, secret, algorithms=["HS256"])

            # 将用户信息注入请求头，下游服务可直接读取
            request.scope["user"] = {
                "id": int(payload["sub"]),
                "username": payload.get("username", ""),
                "role": payload.get("role", ""),
            }

            return await call_next(request)

        except jwt.ExpiredSignatureError:
            return JSONResponse(
                status_code=401,
                content={"code": 2001, "message": "Token 已过期，请重新登录", "data": None}
            )
        except jwt.InvalidTokenError:
            return JSONResponse(
                status_code=401,
                content={"code": 2002, "message": "Token 无效", "data": None}
            )
        except Exception as e:
            logger.error(f"JWT 验证异常: {e}")
            return JSONResponse(
                status_code=500,
                content={"code": 5000, "message": "认证服务异常", "data": None}
            )

    def _is_public(self, path: str) -> bool:
        """判断路径是否在白名单中"""
        return any(path == p or path.startswith(p) for p in PUBLIC_PATHS)

    def _is_internal(self, path: str) -> bool:
        """判断路径是否是内部接口（精确匹配或子路径，防止 /audit/logs 误伤）"""
        return any(path == p or path.startswith(p + "/") for p in INTERNAL_PATHS)
