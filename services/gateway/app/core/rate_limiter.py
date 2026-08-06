"""
限流中间件

基于内存的滑动窗口限流。

执行序（M43 修复）：
    main.py 中注册顺序为 RateLimiter → Auth → CORS，Starlette 是"后注册的先执行"，
    实际执行顺序：CORS → Auth → RateLimiter → 路由。
    Auth 先通过 JWT 校验并把 scope["user"] 注入，本中间件运行时才有 user 可用：
    已认证请求按 user_id 限流；未认证请求（白名单路径）按 IP 限流。
    注意：若把限流注册到 Auth 外层（旧顺序），scope["user"] 恒为空，
    按 user_id 限流将成为死代码 —— 不要调整 main.py 中的注册顺序。

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
    """内存滑动窗口限流器（单 worker 实例适用）"""

    def __init__(self, app, max_requests_per_minute: int = 60):
        super().__init__(app)
        self.max_requests = max_requests_per_minute
        # key: "u:{user_id}"（已认证）/ "ip:{host}"（未认证） → list of timestamps
        self._windows: dict = defaultdict(list)
        self._window_size = 60  # 窗口大小（秒）
        # 全量键清扫间隔：只清理当前 key 会漏掉其它 key，导致字典无限增长（M43）
        self._sweep_interval = 60
        self._last_sweep = 0.0

    async def dispatch(self, request, call_next):
        path = request.url.path

        # 白名单不限流
        if any(path.startswith(p) for p in UNLIMITED_PATHS):
            return await call_next(request)

        # 已认证请求（Auth 先于本中间件执行并注入 scope["user"]）按 user_id 限流；
        # 未认证请求（public 路径）按 IP 限流。
        user = request.scope.get("user") or {}
        if user.get("id") is not None:
            client_key = f"u:{user['id']}"
        else:
            client_key = f"ip:{request.client.host if request.client else 'unknown'}"

        now = time.time()
        window_start = now - self._window_size

        # 定期清扫全量过期键，防内存无限增长（M43）
        if now - self._last_sweep >= self._sweep_interval:
            self._sweep(now)
            self._last_sweep = now

        # 清理当前 key 的过期记录
        windows = [t for t in self._windows[client_key] if t > window_start]
        self._windows[client_key] = windows

        # 检查是否超限
        if len(windows) >= self.max_requests:
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

    def _sweep(self, now: float):
        """移除所有过期 key（窗口内已无记录），防止字典无限增长。"""
        window_start = now - self._window_size
        for key in list(self._windows.keys()):
            self._windows[key] = [t for t in self._windows[key] if t > window_start]
            if not self._windows[key]:
                del self._windows[key]

    def reset(self, client_key: str = None):
        """重置限流计数器"""
        if client_key:
            self._windows.pop(client_key, None)
        else:
            self._windows.clear()
