"""
限流中间件

基于内存的滑动窗口限流。
生产环境建议替换为 Redis 版本（支持分布式）。
"""

import time
import logging
from collections import defaultdict
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse

logger = logging.getLogger(__name__)

# 白名单路径不限流
UNLIMITED_PATHS = ["/health", "/docs", "/openapi.json", "/redoc"]


class RateLimiter(BaseHTTPMiddleware):
    """内存滑动窗口限流器（单实例适用）"""

    def __init__(self, app, max_requests_per_minute: int = 60):
        super().__init__(app)
        self.max_requests = max_requests_per_minute
        # key: "user_id" → list of timestamps
        self._windows: dict = defaultdict(list)
        self._window_size = 60  # 窗口大小（秒）

    async def dispatch(self, request, call_next):
        path = request.url.path

        # 白名单不限流
        if any(path.startswith(p) for p in UNLIMITED_PATHS):
            return await call_next(request)

        # 获取用户标识（优先使用 token 中的 user_id，否则用 IP）
        user = request.scope.get("user", {})
        client_key = str(user.get("id", request.client.host if request.client else "unknown"))

        # 清理过期记录
        now = time.time()
        window_start = now - self._window_size
        self._windows[client_key] = [
            t for t in self._windows[client_key] if t > window_start
        ]

        # 检查是否超限
        if len(self._windows[client_key]) >= self.max_requests:
            logger.warning(f"限流触发: client={client_key}, path={path}")
            return JSONResponse(
                status_code=429,
                content={
                    "code": 5003,
                    "message": f"请求过于频繁，每分钟最多 {self.max_requests} 次请求",
                    "data": None
                }
            )

        # 记录本次请求时间
        self._windows[client_key].append(now)

        return await call_next(request)

    def reset(self, client_key: str = None):
        """重置限流计数器"""
        if client_key:
            self._windows.pop(client_key, None)
        else:
            self._windows.clear()
