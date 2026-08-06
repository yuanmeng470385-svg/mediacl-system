"""
HTTP 请求计数中间件 —— http_requests_total（REQUESTS）接线

修复审计缺口：app/api/metrics.py 定义了 REQUESTS 计数器但从未 .inc()，
http_requests_total 恒为 0。网关是统一入口但无 /metrics 端点、未装
prometheus-client，故计数放在核心流量服务（specialist）的请求中间件：
请求成功/失败都计（调用方可在响应前拿到计数值的端点场景不受影响）。

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
