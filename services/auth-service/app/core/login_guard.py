"""密码登录失败锁定（M9，2026-08-21 审计）

验证码路径自带单码尝试上限（CodeStore consume 的 max_attempts 语义）；
密码路径此前无锁定，暴力破解只受网关 IP 限流约束。按 username 维度计数，
定窗语义：第一次错密起 lockout_seconds 内累计 max_failures 次即锁
lockout_seconds；锁内 lock_remaining() > 0，端点在 bcrypt 验证前直接拒绝
（不消耗哈希）；成功登录 reset 清零。

fail-open 决策（区别于 CodeStore 的 fail-closed 哲学）：锁定是风控增强而
非认证本体，Redis 故障时不把所有人锁在门外——放行登录，错失的计数由
auth_login_failed 审计留痕兜底，bcrypt 慢哈希（~100ms/次）仍天然限速。
"""
import logging
import time
from typing import Callable, Dict, Optional, Tuple

logger = logging.getLogger(__name__)


class MemoryLoginGuard:
    """内存实现（单测注入/开发用；生产选 RedisLoginGuard）。

    clock 可注入，便于测「定窗过期后计数重开」等时间语义。
    """

    def __init__(self, max_failures: int = 5, lockout_seconds: int = 900,
                 clock: Callable[[], float] = time.time):
        self._max = max_failures
        self._lockout = lockout_seconds
        self._clock = clock
        self._fails: Dict[str, Tuple[int, float]] = {}      # username -> (count, window_start)
        self._locked_until: Dict[str, float] = {}            # username -> 解锁时间戳

    def lock_remaining(self, username: str) -> int:
        """锁定期剩余秒数；0 = 未锁"""
        until = self._locked_until.get(username)
        if not until:
            return 0
        return max(0, int(until - self._clock()))

    def record_failure(self, username: str) -> int:
        """记一次错密，返回窗口内当前累计次数；达阈值即置锁"""
        now = self._clock()
        count, started = self._fails.get(username, (0, now))
        if now - started >= self._lockout:   # 定窗已过：重开窗口不累计旧账
            count, started = 0, now
        count += 1
        if count >= self._max:
            self._locked_until[username] = now + self._lockout
            self._fails.pop(username, None)
        else:
            self._fails[username] = (count, started)
        return count

    def reset(self, username: str) -> None:
        """登录成功：清失败计数与锁（若因并发余量残留）"""
        self._fails.pop(username, None)
        self._locked_until.pop(username, None)

    def clear(self) -> None:
        """测试/运维：清空全部状态"""
        self._fails.clear()
        self._locked_until.clear()


class RedisLoginGuard:
    """生产实现：fail 键 INCR（首次 EXPIRE 定窗）+ lock 键 SET EX。

    任何 Redis 异常 fail-open（见模块 docstring）：lock_remaining 当作未锁、
    record_failure 返回 0、reset 静默；error 日志 60s 节流（照限流器模式）。
    """

    _FAIL_KEY = "pwdlock:fail:{u}"
    _LOCK_KEY = "pwdlock:lock:{u}"

    def __init__(self, redis_url: str = "", max_failures: int = 5,
                 lockout_seconds: int = 900, redis_client=None):
        self._max = max_failures
        self._lockout = lockout_seconds
        self._redis_url = redis_url
        self._redis = redis_client
        self._err_logged_at = 0.0

    def _conn(self):
        if self._redis is None:
            import redis  # 延迟导入：单测注入 redis_client 时无需安装
            self._redis = redis.Redis.from_url(
                self._redis_url, decode_responses=True,
                socket_timeout=2, socket_connect_timeout=2)
        return self._redis

    def _fail_open(self, exc: Exception) -> None:
        now = time.monotonic()
        if now - self._err_logged_at > 60:
            logger.error("登录锁定存储不可用（fail-open 放行）: %s", exc)
            self._err_logged_at = now

    def lock_remaining(self, username: str) -> int:
        try:
            ttl = self._conn().ttl(self._LOCK_KEY.format(u=username))
            return ttl if ttl and ttl > 0 else 0
        except Exception as exc:
            self._fail_open(exc)
            return 0

    def record_failure(self, username: str) -> int:
        try:
            r = self._conn()
            fail_key = self._FAIL_KEY.format(u=username)
            n = int(r.incr(fail_key))
            if n == 1:
                # 定窗：仅首次计数设 TTL —— 慢速攻击（间隔略小于窗口）不会无限续窗
                r.expire(fail_key, self._lockout)
            if n >= self._max:
                r.set(self._LOCK_KEY.format(u=username), "1", ex=self._lockout)
                r.delete(fail_key)
            return n
        except Exception as exc:
            self._fail_open(exc)
            return 0

    def reset(self, username: str) -> None:
        try:
            self._conn().delete(
                self._FAIL_KEY.format(u=username), self._LOCK_KEY.format(u=username))
        except Exception as exc:
            self._fail_open(exc)

    def clear(self) -> None:
        """测试/运维：扫描清空两前缀键（规模可控，仅测试/运维调用）"""
        try:
            r = self._conn()
            for pattern in ("pwdlock:fail:*", "pwdlock:lock:*"):
                keys = list(r.scan_iter(pattern))
                if keys:
                    r.delete(*keys)
        except Exception as exc:
            self._fail_open(exc)


_login_guard_singleton: Optional[RedisLoginGuard] = None


def get_login_guard() -> RedisLoginGuard:
    """DI 入口（生产 Redis；测试用 dependency_overrides 注入 Memory 版）"""
    global _login_guard_singleton
    if _login_guard_singleton is None:
        from app.config import settings
        _login_guard_singleton = RedisLoginGuard(
            settings.REDIS_URL,
            max_failures=settings.LOGIN_MAX_FAILURES,
            lockout_seconds=settings.LOGIN_LOCKOUT_SECONDS,
        )
    return _login_guard_singleton
