"""API 网关 - 统一入口

路由规则:
    /api/v1/specialists/*  → specialist-service (8001)
    /api/v1/visits/*       → visit-service (8002)
    /api/v1/knowledge/*    → knowledge-service (8003)
    /api/v1/compliance/*   → compliance-service (8004)
    /api/v1/audit/*        → audit-service (8005)
    /api/v1/hcps/*         → hcp-service (8006)
    /health                → 健康检查聚合
"""
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", ".."))

from fastapi import FastAPI, Request, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
import httpx
import logging
import time

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

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 路由映射表
ROUTE_MAP = {
    "/api/v1/specialists": settings.SPECIALIST_SERVICE_URL,
    "/api/v1/conversations": settings.SPECIALIST_SERVICE_URL,
    "/api/v1/visits": settings.VISIT_SERVICE_URL,
    "/api/v1/knowledge": settings.KNOWLEDGE_SERVICE_URL,
    "/api/v1/compliance": settings.COMPLIANCE_SERVICE_URL,
    "/api/v1/audit": settings.AUDIT_SERVICE_URL,
    "/api/v1/hcps": settings.HCP_SERVICE_URL,
    "/api/v1/auth": settings.SPECIALIST_SERVICE_URL,  # 认证临时走 specialist
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
    services = {
        "specialist": settings.SPECIALIST_SERVICE_URL,
        "visit": settings.VISIT_SERVICE_URL,
        "knowledge": settings.KNOWLEDGE_SERVICE_URL,
        "compliance": settings.COMPLIANCE_SERVICE_URL,
        "audit": settings.AUDIT_SERVICE_URL,
        "hcp": settings.HCP_SERVICE_URL,
    }
    return {"status": "ok", "service": settings.SERVICE_NAME, "version": "1.0.0", "backends": services}


# ==================== 通配代理路由（兜底，所有 API 请求转发到后端微服务） ====================

@app.api_route("/{path:path}", methods=["GET", "POST", "PUT", "DELETE", "PATCH", "OPTIONS"])
async def proxy(request: Request, path: str):
    """统一代理：将请求转发到对应的微服务"""
    backend_url = get_backend_url(f"/{path}")

    if backend_url is None:
        raise HTTPException(status_code=404, detail={"code": 1004, "message": "路由不存在"})

    target_url = f"{backend_url}/{path}"

    # 转发请求
    async with httpx.AsyncClient(timeout=30.0) as client:
        try:
            body = await request.body()
            headers = dict(request.headers)
            # 移除 hop-by-hop headers
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

            return JSONResponse(
                content=response.json(),
                status_code=response.status_code,
                headers=dict(response.headers),
            )
        except httpx.ConnectError:
            logger.error(f"无法连接到后端服务: {target_url}")
            raise HTTPException(
                status_code=503,
                detail={"code": 5001, "message": "后端服务不可用"}
            )
        except httpx.TimeoutException:
            logger.error(f"后端服务超时: {target_url}")
            raise HTTPException(
                status_code=504,
                detail={"code": 5002, "message": "后端服务超时"}
            )


@app.get("/health")
async def health():
    """聚合所有服务的健康检查"""
    services = {
        "gateway": settings.SERVICE_URL if hasattr(settings, 'SERVICE_URL') else "ok",
        "specialist": settings.SPECIALIST_SERVICE_URL,
        "visit": settings.VISIT_SERVICE_URL,
        "knowledge": settings.KNOWLEDGE_SERVICE_URL,
        "compliance": settings.COMPLIANCE_SERVICE_URL,
        "audit": settings.AUDIT_SERVICE_URL,
        "hcp": settings.HCP_SERVICE_URL,
    }
    return {"status": "ok", "service": settings.SERVICE_NAME, "version": "1.0.0", "backends": services}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=settings.SERVICE_PORT)
