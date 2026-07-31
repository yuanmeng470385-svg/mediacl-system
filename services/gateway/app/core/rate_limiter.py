"""
限流中间件

TODO: 实现基于 Redis 的滑动窗口限流
- 每个用户每分钟 N 次请求
- 超限返回 429 Too Many Requests
"""
import logging

logger = logging.getLogger(__name__)


class RateLimiter:
    """请求限流器"""

    def __init__(self, max_requests_per_minute: int = 60):
        self.max_requests = max_requests_per_minute

    # TODO: 实现基于 Redis 的滑动窗口限流
    # async def check(self, user_id: str) -> bool:
    #     ...
