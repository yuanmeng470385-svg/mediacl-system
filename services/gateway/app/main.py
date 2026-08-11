"""API 网关 - 统一入口

路由规则:
    /api/v1/specialists/*  → specialist-service (8001)
    /api/v1/visits/*       → visit-service (8002)
    /api/v1/knowledge/*    → knowledge-service (8003)
    /api/v1/compliance/*   → compliance-service (8004)
    /api/v1/audit/*        → audit-service (8005)
    /api/v1/hcps/*         → hcp-service (8006)
    /api/v1/system/config  → 网关自身（系统配置只读，admin）
    /health                → 健康检查聚合（并发探测各上游）
"""
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", ".."))

import asyncio
import inspect
import websockets
from fastapi import FastAPI, Request, WebSocket
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, Response
import httpx
import logging
import time
import os as _os

from app.config import settings
from app.core.auth_middleware import AuthMiddleware
from app.core.rate_limiter import RateLimiter
from shared.common.request_id_middleware import RequestIDMiddleware

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
# 注册顺序 RateLimiter → Auth → CORS，实际执行顺序：CORS → Auth → RateLimiter → 路由。
# - CORS 最外层：OPTIONS 预检直接由 CORS 短路处理，不被认证/限流拦截（H10 修复保持）。
# - Auth 在限流之前：JWT 校验通过后注入 scope["user"]，RateLimiter 才有 user_id 可用
#   （M43：此前限流注册在认证外层，scope["user"] 恒空，按 user_id 限流是死代码）。
# - RateLimiter 最内层：已认证请求按 user_id 限流，未认证（public 路径）按 IP 限流。

# 1. 限流（最内层：在 Auth 注入 scope["user"] 之后执行）
# Redis 分布式滑动窗口（多 worker 共享计数）；Redis 不可用自动降级内存版
rate_limit = int(_os.getenv("RATE_LIMIT_PER_MINUTE", "60"))
app.add_middleware(
    RateLimiter,
    max_requests_per_minute=rate_limit,
    redis_url=settings.REDIS_URL,
)

# 2. JWT 认证
app.add_middleware(AuthMiddleware)

# 3. CORS（跨域预检先过）
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 4. X-Request-ID（最外层：最先执行，生成/校验链路 ID 并注入 scope，
#    proxy 转发时合并进上游请求头 —— 网关是唯一入口，上下游自然贯穿）。
#    OPTIONS 预检与 WS 握手直接透传（中间件内部处理，见 request_id_middleware.py）。
app.add_middleware(RequestIDMiddleware)

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

# ---- 健康探测（M46：真探活，测试注入用） ----

HEALTH_PROBE_TIMEOUT = 2.0

_health_probe_fn = None


def set_health_probe(fn):
    """测试注入：替换默认的单点探测函数。fn(url: str) -> 协程(bool)"""
    global _health_probe_fn
    _health_probe_fn = fn


async def _default_health_probe(url: str) -> bool:
    """探测单个后端 /health：2s 超时，返回 200 视为 up。"""
    try:
        async with httpx.AsyncClient(timeout=HEALTH_PROBE_TIMEOUT) as client:
            resp = await client.get(f"{url}/health")
            return resp.status_code == 200
    except Exception:
        return False


async def _probe_backend(url: str) -> bool:
    probe = _health_probe_fn or _default_health_probe
    return bool(await probe(url))


def _backend_urls() -> dict:
    """所有后端服务地址（name → url）"""
    return {
        "auth": settings.AUTH_SERVICE_URL,
        "specialist": settings.SPECIALIST_SERVICE_URL,
        "visit": settings.VISIT_SERVICE_URL,
        "knowledge": settings.KNOWLEDGE_SERVICE_URL,
        "compliance": settings.COMPLIANCE_SERVICE_URL,
        "audit": settings.AUDIT_SERVICE_URL,
        "hcp": settings.HCP_SERVICE_URL,
    }


@app.get("/health")
async def health():
    """聚合所有服务的健康检查：异步并发探测各上游 /health（超时 2s）"""
    backends = _backend_urls()
    results = await asyncio.gather(
        *(_probe_backend(url) for url in backends.values()),
        return_exceptions=True,
    )
    services = {
        name: ("up" if (isinstance(ok, bool) and ok) else "down")
        for name, ok in zip(backends.keys(), results)
    }
    return {
        "status": "ok",  # 网关自身存活；各上游状态见 services
        "service": settings.SERVICE_NAME,
        "version": "1.0.0",
        "backends": backends,
        "services": services,
    }


# ---- 系统配置只读端点（网关级信息，admin） ----

# 关键配置项 → 环境变量名。只返回"是否已配置"布尔值，绝不返回密钥值。
SYSTEM_CONFIG_ITEMS = [
    ("JWT_SECRET", "JWT 密钥"),
    ("INTERNAL_API_KEY", "内部服务调用密钥"),
    ("ALIYUN_ACCESS_KEY_ID", "阿里云 AccessKey ID"),
    ("ALIYUN_ACCESS_KEY_SECRET", "阿里云 AccessKey Secret"),
    ("DASHSCOPE_API_KEY", "通义千问 API Key"),
    ("BAILIAN_API_KEY", "百炼 API Key"),
    ("NLS_APPKEY", "阿里云 NLS 语音转写"),
    ("AUTH_SMS_PROVIDER", "短信服务商"),
    ("ES_URL", "Elasticsearch（知识库）"),
    ("REDIS_URL", "Redis"),
]

# .env.example 模板占位值标记（照抄模板部署 = 未配置）
_PLACEHOLDER_MARKERS = ("your_", "change_me_")


def _is_env_configured(env: str) -> bool:
    """环境变量已配置：非空且不是 .env.example 模板占位值。"""
    value = _os.getenv(env, "").strip()
    if not value:
        return False
    low = value.lower()
    return not any(marker in low for marker in _PLACEHOLDER_MARKERS)


@app.get("/api/v1/system/config")
async def system_config(request: Request):
    """系统级配置状态（只读，admin）。

    返回各关键配置项"是否已配置"（布尔），绝不返回密钥值本身；
    在线不可修改 —— 配置由 .env 环境变量管理，改后重启服务生效。
    """
    user = request.scope.get("user") or {}
    if user.get("role") != "admin":
        return JSONResponse(
            status_code=403,
            content={"code": 3000, "message": "无权限：需要角色 admin", "data": None},
        )
    items = [
        {"key": env, "label": label, "configured": _is_env_configured(env)}
        for env, label in SYSTEM_CONFIG_ITEMS
    ]
    return JSONResponse(
        status_code=200,
        content={
            "code": 0,
            "message": "success",
            "data": {
                "items": items,
                "info": {
                    "rate_limit_per_minute": rate_limit,
                    "log_level": settings.LOG_LEVEL,
                },
            },
        },
    )


# ==================== 代理路由（兜底） ====================

def _forward_headers(response) -> dict:
    """透传上游响应头，但剔除由新响应自己处理、透传会失配的头部（M46）。

    - content-length：JSONResponse 会重新序列化 body，长度必然变化
    - content-encoding：上游已压缩的字节被改写/解析后不能再透传该头
    - transfer-encoding：由 ASGI 服务器管理
    """
    return {
        k: v for k, v in response.headers.items()
        if k.lower() not in ("content-length", "content-encoding", "transfer-encoding")
    }


@app.api_route("/{path:path}", methods=["GET", "POST", "PUT", "DELETE", "PATCH", "OPTIONS"])
async def proxy(request: Request, path: str):
    """统一代理：将请求转发到对应的微服务"""
    backend_url = get_backend_url(f"/{path}")

    if backend_url is None:
        # M44：统一错误格式 {code, message, data}，与 auth/rate_limiter 中间件一致
        return JSONResponse(
            status_code=404,
            content={"code": 1004, "message": "路由不存在", "data": None},
        )

    target_url = f"{backend_url}/{path}"

    # 知识审核链路（百炼导入 ~30s + 向量化）对 30s 默认超时太紧，
    # 网关先超时导致"业务完成但客户端看到 504"（合规硬伤回归见 M48）
    if path.startswith("knowledge/"):
        proxy_timeout = 120.0
    else:
        proxy_timeout = 30.0

    async with httpx.AsyncClient(timeout=proxy_timeout) as client:
        try:
            body = await request.body()
            headers = dict(request.headers)
            headers.pop("host", None)
            headers.pop("content-length", None)
            # X-Request-ID：以 RequestIDMiddleware 校验后的 scope 值为准覆盖
            # （客户端原始超长/恶意值不透传上游），保证全链路同一 ID
            rid = request.scope.get("x-request-id")
            if rid:
                headers["x-request-id"] = rid

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
                    headers=_forward_headers(response),
                )
            # 非 JSON（Excel 导出/文件下载，H11）：原样透传字节，不尝试解析
            return Response(
                content=response.content,
                status_code=response.status_code,
                headers=_forward_headers(response),
                media_type=content_type,
            )
        except httpx.ConnectError:
            logger.error(f"无法连接到后端服务: {target_url}")
            return JSONResponse(
                status_code=503,
                content={"code": 5001, "message": "后端服务不可用", "data": None},
            )
        except httpx.TimeoutException:
            logger.error(f"后端服务超时: {target_url}")
            return JSONResponse(
                status_code=504,
                content={"code": 5002, "message": "后端服务超时", "data": None},
            )
        except httpx.HTTPError as exc:
            # M45：ConnectError/TimeoutException 之外的网络/协议异常
            # （RemoteProtocolError/ReadError/NetworkError 等）统一 502，
            # 不再冒泡成 500 纯文本。
            logger.error(f"后端服务连接异常: {target_url} ({type(exc).__name__}: {exc})")
            return JSONResponse(
                status_code=502,
                content={"code": 5004, "message": "后端服务连接中断", "data": None},
            )


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


async def _upstream_send(upstream, text: str) -> None:
    """上游发送适配：websockets <15 用 send_text，>=15 用 send（API 更名）"""
    send_text = getattr(upstream, "send_text", None)
    if send_text is not None:
        await send_text(text)
    else:
        await upstream.send(text)


async def _upstream_recv(upstream):
    """上游接收适配：websockets <15 用 receive_text，>=15 用 recv"""
    receive_text = getattr(upstream, "receive_text", None)
    if receive_text is not None:
        return await receive_text()
    data = await upstream.recv()
    return data.decode("utf-8") if isinstance(data, bytes) else data


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
                        await _upstream_send(upstream, msg["text"])
                    elif "bytes" in msg and msg["bytes"] is not None:
                        # 上游是文本 WS 协议（帧均为 JSON 文本），bytes 帧不转发
                        pass
                elif msg["type"] == "websocket.disconnect":
                    break
        except Exception:
            pass
        finally:
            await upstream.close()

    async def upstream_to_client():
        # M46：上游关闭码原样透传给下游 —— 4401（未授权）/4404（不存在）/
        # 4500（内部错误）等业务关闭码不再被吞成 1000，客户端可据此处理。
        upstream_close_code = 1000
        try:
            while True:
                try:
                    text = await _upstream_recv(upstream)
                    async with send_lock:
                        await websocket.send_text(text)
                except websockets.exceptions.ConnectionClosed as exc:
                    # 用 rcvd.code（关闭帧到达侧）取值，避免 .code 已废弃属性
                    rcvd = getattr(exc, "rcvd", None)
                    upstream_close_code = getattr(rcvd, "code", None) or 1000
                    break
                except Exception:
                    break
        finally:
            try:
                async with send_lock:
                    await websocket.close(code=upstream_close_code)
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
