"""密码登录失败锁定（M9，2026-08-21 审计）——guard 存储语义

验证码路径自带单码尝试上限（CodeStore max_attempts）；密码路径此前无锁定，
暴力破解只受网关 IP 限流约束。锁定按 username 维度计数：
  - 定窗：第一次错密起 lockout_seconds 内累计 max_failures 次即锁
  - 锁定期内 lock_remaining > 0，端点在 bcrypt 验证前直接拒绝
  - 成功登录清零；Redis 版任何异常 fail-open（放行登录 + error 日志），
    不把管理员锁在门外——bcrypt 慢哈希仍天然限速
"""
import sys
import os
from unittest.mock import MagicMock

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", ".."))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

os.environ.setdefault("JWT_SECRET", "test-secret-not-a-default-value")
os.environ["AUTH_DEV_MODE"] = "true"

from app.core.login_guard import MemoryLoginGuard, RedisLoginGuard  # noqa: E402


class TestMemoryGuard:
    def _guard(self):
        return MemoryLoginGuard(max_failures=3, lockout_seconds=900, clock=lambda: 1000.0)

    def test_未达阈值不锁(self):
        g = self._guard()
        assert g.lock_remaining("u") == 0
        g.record_failure("u")
        g.record_failure("u")
        assert g.lock_remaining("u") == 0

    def test_达阈值锁定_剩余时间递减(self):
        g = self._guard()
        for _ in range(3):
            g.record_failure("u")
        assert g.lock_remaining("u") == 900
        g._clock = lambda: 1100.0
        assert g.lock_remaining("u") == 800

    def test_锁到期自动解除(self):
        g = self._guard()
        for _ in range(3):
            g.record_failure("u")
        g._clock = lambda: 1901.0   # 越过锁定期
        assert g.lock_remaining("u") == 0
        # 解锁后重新计数（新窗口）
        assert g.record_failure("u") == 1

    def test_成功登录清零(self):
        g = self._guard()
        g.record_failure("u")
        g.record_failure("u")
        g.reset("u")
        assert g.record_failure("u") == 1   # 重新从 1 计

    def test_定窗_窗口过期后计数重开(self):
        g = self._guard()
        g.record_failure("u")          # 1000s 起窗
        g._clock = lambda: 2500.0      # 窗口已过（>900s）
        assert g.record_failure("u") == 1   # 新窗口重新从 1 计，不累计旧账


class TestRedisGuard:
    def _guard(self, redis):
        return RedisLoginGuard(redis_url="redis://localhost:6379/0",
                               max_failures=3, lockout_seconds=900,
                               redis_client=redis)

    def test_计数达阈值置锁并清计数(self):
        fake = MagicMock()
        fake.incr.side_effect = [1, 2, 3]
        g = self._guard(fake)
        assert g.record_failure("u") == 1
        assert g.record_failure("u") == 2
        assert g.record_failure("u") == 3
        # 首次计数设了定窗 TTL；第 3 次达阈值 → 置锁 + 清计数
        fake.expire.assert_called_once()
        fake.set.assert_called_once()
        assert fake.set.call_args.kwargs.get("ex") == 900
        fake.delete.assert_called_once()

    def test_锁内查询走锁键TTL(self):
        fake = MagicMock()
        fake.ttl.return_value = 742
        g = self._guard(fake)
        assert g.lock_remaining("u") == 742

    def test_redis挂_fail_open(self):
        """fail-open 决策：锁定是风控增强而非认证本体（对比 CodeStore fail-closed），
        Redis 故障不把所有人锁在门外；错失计数由 auth_login_failed 审计兜底"""
        fake = MagicMock()
        fake.ttl.side_effect = Exception("redis down")
        fake.incr.side_effect = Exception("redis down")
        g = self._guard(fake)
        assert g.lock_remaining("u") == 0   # 当作未锁，放行登录
        assert g.record_failure("u") == 0   # 计数失败不炸登录
        g.reset("u")                        # 不抛
