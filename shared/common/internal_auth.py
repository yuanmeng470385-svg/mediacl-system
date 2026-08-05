"""
服务间内部调用鉴权（S2 修复）

网关白名单里的内部接口（/api/v1/compliance/check、/api/v1/audit/log）此前
无需任何认证 —— 未登录者可伪造审计记录、触发付费 LLM 调用。现在所有内部
调用必须携带 X-Internal-Key 头，网关和服务端双重校验：

- 网关 auth_middleware：内部路径要求 X-Internal-Key（拦截绕过网关的外部请求）
- 服务端 require_internal_key 依赖：挂在内网接口上（防 8001-8006 端口直连绕过）

INTERNAL_API_KEY 未配置或仍为默认值时抛 RuntimeError —— 服务拒绝启动，
与 JWT_SECRET 相同的模式，防止带默认密钥上线。
"""

import os

from fastapi import HTTPException
from starlette.requests import Request

# 与 JWT_SECRET 的 "dev-secret-change-me" 同模式：检测到默认值就拒绝启动
DEFAULT_INTERNAL_API_KEY = "change-me-internal-key"

_INTERNAL_KEY = None


def get_internal_api_key() -> str:
    """读取并校验内部 API Key（首次调用时校验，不满足直接抛错拒绝启动）"""
    global _INTERNAL_KEY
    if _INTERNAL_KEY is None:
        key = os.getenv("INTERNAL_API_KEY", "")
        if not key or key == DEFAULT_INTERNAL_API_KEY:
            raise RuntimeError(
                "INTERNAL_API_KEY 未配置或仍为默认值，拒绝启动。"
                "生成：openssl rand -hex 32"
            )
        _INTERNAL_KEY = key
    return _INTERNAL_KEY


def internal_headers() -> dict:
    """服务间 HTTP 调用统一携带的请求头"""
    return {"X-Internal-Key": get_internal_api_key()}


async def require_internal_key(request: Request) -> None:
    """FastAPI 依赖：校验 X-Internal-Key 头（用于内部接口，防服务端口直连）。

    注意：依赖里必须 raise HTTPException —— 返回 Response 对象不会短路请求。
    """
    key = request.headers.get("X-Internal-Key", "")
    if key != get_internal_api_key():
        raise HTTPException(
            status_code=403,
            detail={
                "code": 3001,
                "message": "禁止访问：内部接口需要有效的 X-Internal-Key",
                "data": None,
            },
        )
