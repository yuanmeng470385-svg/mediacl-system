"""
HTTP 请求计数中间件 —— http_requests_total（REQUESTS）接线
（照 specialist-service 同款，2026-08-26 补齐挂账：compliance 的 REQUESTS
计数器此前只定义从未 .inc()，http_requests_total 恒为 0。网关是统一入口但无
/metrics 端点、未装 prometheus-client，故计数落在核心流量服务的请求中间件：
请求成功/失败都计。

- 仅统计 http scope：WebSocket 握手不占 HTTP 请求数
- OPTIONS 预检不计：CORS 短路处理，非业务请求
"""
import logging

from starlette.middleware.base import BaseHTTPMiddleware

from app.config import settings
from app.api.metrics import REQUESTS

logger = logging.getLogger(__name__)


class MetricsMiddleware(BaseHTTPMiddleware):
    """每个 HTTP 请求使 http_requests_total{service, method} 递增。"""

    async def dispatch(self, request, call_next):
        if request.scope.get("type") != "http" or request.method == "OPTIONS":
            return await call_next(request)
        response = await call_next(request)
        REQUESTS.labels(service=settings.SERVICE_NAME, method=request.method).inc()
        return response
