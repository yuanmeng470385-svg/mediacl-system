"""
限流中间件

基于 Redis 滑动窗口的分布式限流（2026-08-11 修复：原内存版在 --workers 2 部署下
每 worker 独立计数，限额被 N×worker 放大绕过）。

设计：
- 主路径：Redis ZSET 滑动窗口 + Lua 脚本原子执行（ZREMRANGEBYSCORE → ZCARD 检查
  → ZADD+EXPIRE），多 worker 共享同一计数，限流不可绕过。
- 降级：Redis 不可用（宕机/网络）时降级为进程内内存滑动窗口（原实现），
  记 error 日志（每 60s 节流一条，防刷屏）；Redis 恢复后自动切回主路径并记 info。
  降级不 fail-open 裸奔（仍有限流，只是退回单进程口径），也不 fail-closed 全 429。

执行序（M43 修复）：
    main.py 中注册顺序为 RateLimiter → Auth → CORS，Starlette 是"后注册的先执行"，
    实际执行顺序：CORS → Auth → RateLimiter → 路由。
    Auth 先通过 JWT 校验并把 scope["user"] 注入，本中间件运行时才有 user 可用：
    已认证请求按 user_id 限流；未认证请求（白名单路径）按 IP 限流。
    注意：若把限流注册到 Auth 外层（旧顺序），scope["user"] 恒为空，
    按 user_id 限流将成为死代码 —— 不要调整 main.py 中的注册顺序。
"""

import logging
import os
import time
from collections import defaultdict
from typing import Optional

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse

logger = logging.getLogger(__name__)

# 白名单路径不限流
UNLIMITED_PATHS = ["/health", "/docs", "/openapi.json", "/redoc"]

# Redis 滑动窗口原子脚本：清理过期成员 → 计数检查 → 记录 + 设置过期。
# 返回 1 = 放行，0 = 超限拒绝。member 用 "score_随机后缀" 防同毫秒碰撞覆盖。
_LUA_WINDOW = """
local key = KEYS[1]
local max = tonumber(ARGV[1])
local window = tonumber(ARGV[2])
local now = tonumber(ARGV[3])
local member = ARGV[4]
redis.call('ZREMRANGEBYSCORE', key, 0, now - window)
local count = redis.call('ZCARD', key)
if count >= max then
    return 0
end
redis.call('ZADD', key, now, member)
redis.call('EXPIRE', key, window + 1)
return 1
"""


class _MemoryWindow:
    """降级用内存滑动窗口（原实现，单进程口径；Redis 不可用时兜底）"""

    def __init__(self, max_requests_per_minute: int, window_size: int = 60):
        self.max_requests = max_requests_per_minute
        self._windows: dict = defaultdict(list)
        self._window_size = window_size
        # 全量键清扫间隔：只清理当前 key 会漏掉其它 key，导致字典无限增长（M43）
        self._sweep_interval = 60
        self._last_sweep = 0.0

    def check_and_record(self, client_key: str, now: float) -> bool:
        """True = 放行；False = 超限拒绝"""
        window_start = now - self._window_size
        # 定期清扫全量过期键，防内存无限增长（M43）
        if now - self._last_sweep >= self._sweep_interval:
            for key in list(self._windows.keys()):
                self._windows[key] = [t for t in self._windows[key] if t > window_start]
                if not self._windows[key]:
                    del self._windows[key]
            self._last_sweep = now

        windows = [t for t in self._windows[client_key] if t > window_start]
        if len(windows) >= self.max_requests:
            return False
        self._windows[client_key] = windows
        self._windows[client_key].append(now)
        return True

    def reset(self, client_key: Optional[str] = None):
        if client_key:
            self._windows.pop(client_key, None)
        else:
            self._windows.clear()


class RateLimiter(BaseHTTPMiddleware):
    """限流器：Redis 滑动窗口（分布式）优先，Redis 不可用降级内存版"""

    def __init__(self, app, max_requests_per_minute: int = 60,
                 redis_url: Optional[str] = None, window_size: int = 60):
        super().__init__(app)
        self.max_requests = max_requests_per_minute
        self._window_size = window_size
        self._redis_url = redis_url or os.getenv("REDIS_URL", "redis://localhost:6379/0")
        self._redis = None        # 懒连接
        self._script = None       # Lua 脚本（注册于首次连接）
        self._memory = _MemoryWindow(max_requests_per_minute, window_size)
        self._degraded_logged_at = 0.0  # 降级 error 日志节流（60s 一条）
        self._degraded = False

    def _get_redis(self):
        """懒建 Redis 连接（照搬 auth-service code_store.py 的 fail 快速超时写法）"""
        if self._redis is None:
            import redis
            self._redis = redis.Redis.from_url(
                self._redis_url, decode_responses=True,
                socket_timeout=2, socket_connect_timeout=2,
            )
            self._script = self._redis.register_script(_LUA_WINDOW)
        return self._redis

    def _redis_allows(self, client_key: str, now: float) -> bool:
        """Redis 主路径：Lua 原子滑动窗口。异常向上抛，由调用方降级。"""
        r = self._get_redis()
        member = f"{now}_{os.urandom(4).hex()}"
        allowed = self._script(
            keys=[f"rl:{client_key}"],
            args=[self.max_requests, self._window_size, now, member],
            client=r,
        )
        return bool(allowed)

    def _check_and_record(self, client_key: str, now: float) -> bool:
        try:
            allowed = self._redis_allows(client_key, now)
            if self._degraded:
                logger.info("限流已切回 Redis 分布式模式（client=%s）", client_key)
                self._degraded = False
            return allowed
        except Exception as exc:
            # Redis 不可用 → 降级内存版（原行为，不裸奔也不全 429）；
            # error 日志节流（60s 一条），避免 Redis 抖动刷爆日志
            if now - self._degraded_logged_at >= 60:
                logger.error("限流 Redis 不可用，降级内存版（限流为单进程口径）: %s", exc)
                self._degraded_logged_at = now
            self._degraded = True
            return self._memory.check_and_record(client_key, now)

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
        if not self._check_and_record(client_key, now):
            logger.warning("限流触发: client=%s, path=%s", client_key, path)
            return JSONResponse(
                status_code=429,
                content={
                    "code": 5003,
                    "message": f"请求过于频繁，每分钟最多 {self.max_requests} 次请求",
                    "data": None
                }
            )
        return await call_next(request)

    def reset(self, client_key: Optional[str] = None):
        """重置限流计数器（Redis key 或内存键）"""
        try:
            r = self._get_redis()
            if client_key:
                r.delete(f"rl:{client_key}")
            else:
                # 全量重置：扫描 rl:* 键（规模可控；懒连接下仅测试/运维调用）
                keys = list(r.scan_iter("rl:*"))
                if keys:
                    r.delete(*keys)
        except Exception as exc:
            logger.warning("限流 Redis reset 失败（内存键已清）: %s", exc)
        self._memory.reset(client_key)
