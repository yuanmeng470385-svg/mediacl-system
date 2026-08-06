"""API 网关 - 统一入口

路由规则:
    /api/v1/specialists/*  → specialist-service (8001)
    /api/v1/visits/*       → visit-service (8002)
    /api/v1/knowledge/*    → knowledge-service (8003)
    /api/v1/compliance/*   → compliance-service (8004)
    /api/v1/audit/*        → audit-service (8005)
    /api/v1/hcps/*         → hcp-service (8006)
    /health                → 健康检查聚合

中间件顺序（先注册的先执行）:
    CORS → Auth → RateLimiter → Proxy
"""
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", ".."))

import asyncio
import inspect
import websockets
from fastapi import FastAPI, Request, HTTPException, WebSocket
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, Response
import httpx
import logging
import time
import os as _os

from app.config import settings
from app.core.auth_middleware import AuthMiddleware
from app.core.rate_limiter import RateLimiter

logging.basicConfig(
    level=getattr(logging, settings.LOG_LEVEL),
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)

app = FastAPI(
    title="MedAgent - API 网关",
    description="统一入口，负责路由转发、认证、限流",
    version="1.0.0"
)

# ==================== 中间件 ====================
# Starlette 中间件是"后注册的先执行"（LIFO）。
# 注册顺序 Auth → RateLimiter → CORS，实际执行顺序：CORS → RateLimiter → Auth → 路由。
# 这样 CORS 在最外层（OPTIONS 预检不被认证拦 401）、限流在认证外层
# （未认证流量按 IP 限流，认证流量按 user_id 限流）、Auth 最内层兜底。

# 3. JWT 认证（最内层：白名单路径自动跳过）
app.add_middleware(AuthMiddleware)

# 2. 限流（认证外层：scope["user"] 已有则按 user_id，否则按 IP）
rate_limit = int(_os.getenv("RATE_LIMIT_PER_MINUTE", "60"))
app.add_middleware(RateLimiter, max_requests_per_minute=rate_limit)

# 1. CORS（最外层：跨域预检先过）
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ==================== 路由映射 ====================

ROUTE_MAP = {
    "/api/v1/specialists": settings.SPECIALIST_SERVICE_URL,
    "/api/v1/conversations": settings.SPECIALIST_SERVICE_URL,
    "/api/v1/favorites": settings.SPECIALIST_SERVICE_URL,
    "/api/v1/visits": settings.VISIT_SERVICE_URL,
    "/api/v1/tasks": settings.VISIT_SERVICE_URL,
    "/api/v1/knowledge": settings.KNOWLEDGE_SERVICE_URL,
    "/api/v1/compliance": settings.COMPLIANCE_SERVICE_URL,
    "/api/v1/audit": settings.AUDIT_SERVICE_URL,
    "/api/v1/hcps": settings.HCP_SERVICE_URL,
    "/api/v1/auth": settings.AUTH_SERVICE_URL,
    "/api/v1/users": settings.AUTH_SERVICE_URL,  # 用户管理（Web 后台）
}


def get_backend_url(path: str) -> str:
    """根据请求路径路由到对应后端服务"""
    for prefix, url in ROUTE_MAP.items():
        if path.startswith(prefix):
            return url
    return None


# ==================== 明确路由（必须在通配路由之前定义） ====================

@app.get("/health")
async def health():
    """聚合所有服务的健康检查"""
    return {
        "status": "ok",
        "service": settings.SERVICE_NAME,
        "version": "1.0.0",
        "backends": {
            "auth": settings.AUTH_SERVICE_URL,
            "specialist": settings.SPECIALIST_SERVICE_URL,
            "visit": settings.VISIT_SERVICE_URL,
            "knowledge": settings.KNOWLEDGE_SERVICE_URL,
            "compliance": settings.COMPLIANCE_SERVICE_URL,
            "audit": settings.AUDIT_SERVICE_URL,
            "hcp": settings.HCP_SERVICE_URL,
        }
    }


# ==================== 代理路由（兜底） ====================

@app.api_route("/{path:path}", methods=["GET", "POST", "PUT", "DELETE", "PATCH", "OPTIONS"])
async def proxy(request: Request, path: str):
    """统一代理：将请求转发到对应的微服务"""
    backend_url = get_backend_url(f"/{path}")

    if backend_url is None:
        raise HTTPException(status_code=404, detail={"code": 1004, "message": "路由不存在"})

    target_url = f"{backend_url}/{path}"

    async with httpx.AsyncClient(timeout=30.0) as client:
        try:
            body = await request.body()
            headers = dict(request.headers)
            headers.pop("host", None)
            headers.pop("content-length", None)

            start_time = time.time()
            response = await client.request(
                method=request.method,
                url=target_url,
                headers=headers,
                content=body,
                params=request.query_params,
            )
            elapsed = time.time() - start_time

            logger.info(f"PROXY {request.method} {target_url} → {response.status_code} ({elapsed:.3f}s)")

            content_type = response.headers.get("content-type", "")
            if "application/json" in content_type:
                return JSONResponse(
                    content=response.json(),
                    status_code=response.status_code,
                    headers=dict(response.headers),
                )
            # 非 JSON（Excel 导出/文件下载，H11）：原样透传字节，不尝试解析
            # content-length/content-encoding/transfer-encoding 由新响应自己处理，不透传
            filtered_headers = {
                k: v for k, v in response.headers.items()
                if k.lower() not in ("content-length", "content-encoding", "transfer-encoding")
            }
            return Response(
                content=response.content,
                status_code=response.status_code,
                headers=filtered_headers,
                media_type=content_type,
            )
        except httpx.ConnectError:
            logger.error(f"无法连接到后端服务: {target_url}")
            raise HTTPException(status_code=503, detail={"code": 5001, "message": "后端服务不可用"})
        except httpx.TimeoutException:
            logger.error(f"后端服务超时: {target_url}")
            raise HTTPException(status_code=504, detail={"code": 5002, "message": "后端服务超时"})


# ==================== WS 代理（对话流式转发） ====================

# ---- WS 代理上游工厂（测试注入用） ----
_upstream_factory = None


def set_upstream_factory(fn):
    """测试注入：替换默认的上游连接函数。fn(url: str) -> 类 WebSocket 上游对象"""
    global _upstream_factory
    _upstream_factory = fn


async def _default_upstream(url: str):
    ws = await websockets.connect(url)
    return ws  # 原生 websockets WebSocket 已具备 send_text/receive_text/close 等


@app.websocket("/api/v1/specialists/{specialist_id}/chat/ws")
async def proxy_chat_ws(websocket: WebSocket, specialist_id: int):
    token = websocket.query_params.get("token", "")
    await websocket.accept()

    # 上游连接 specialist-service 的 WS 端点，token 原样透传（鉴权在 specialist 侧）
    ws_scheme = "wss" if settings.SPECIALIST_SERVICE_URL.startswith("https") else "ws"
    upstream_url = (
        f"{ws_scheme}://{settings.SPECIALIST_SERVICE_URL.split('://')[1]}"
        f"/ws/specialists/{specialist_id}/chat?token={token}"
    )
    factory = _upstream_factory or _default_upstream
    try:
        # 工厂可同步返回上游对象，也可返回协程（默认实现是 async 的）
        upstream = factory(upstream_url)
        if inspect.isawaitable(upstream):
            upstream = await upstream
    except Exception:
        await websocket.close(code=4500)
        return

    # starlette WebSocket 并发 send 会互相干扰，客户端方向统一加锁
    send_lock = asyncio.Lock()

    async def client_to_upstream():
        try:
            while True:
                msg = await websocket.receive()
                if msg["type"] == "websocket.receive":
                    if "text" in msg and msg["text"] is not None:
                        await upstream.send_text(msg["text"])
                    elif "bytes" in msg and msg["bytes"] is not None:
                        await upstream.send_bytes(msg["bytes"])
                elif msg["type"] == "websocket.disconnect":
                    break
        except Exception:
            pass
        finally:
            await upstream.close()

    async def upstream_to_client():
        try:
            while True:
                try:
                    text = await upstream.receive_text()
                    async with send_lock:
                        await websocket.send_text(text)
                except websockets.exceptions.ConnectionClosed:
                    break
                except Exception:
                    break
        finally:
            try:
                async with send_lock:
                    await websocket.close(code=1000)
            except Exception:
                pass

    t1 = asyncio.create_task(client_to_upstream())
    t2 = asyncio.create_task(upstream_to_client())
    try:
        await asyncio.gather(t1, t2)
    finally:
        t1.cancel(); t2.cancel()
        try:
            await upstream.close()
        except Exception:
            pass


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=settings.SERVICE_PORT)
