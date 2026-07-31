"""
JWT 认证中间件（网关层统一验证）

所有请求到达网关后，先过此中间件验证 token。
白名单路径无需认证。

使用方式（在 gateway main.py 中）:
    from app.core.auth_middleware import AuthMiddleware
    app.add_middleware(AuthMiddleware)
"""

import os
import logging
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse
from starlette.requests import Request

import jwt

logger = logging.getLogger(__name__)

# 无需认证的路径白名单
PUBLIC_PATHS = [
    "/health",
    "/api/v1/auth/login",
    "/api/v1/auth/register",
    "/api/v1/auth/send-code",
    "/docs",
    "/openapi.json",
    "/redoc",
]


class AuthMiddleware(BaseHTTPMiddleware):
    """JWT 认证中间件"""

    async def dispatch(self, request: Request, call_next):
        path = request.url.path

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
            secret = os.getenv("JWT_SECRET", "dev-secret-change-me")
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
