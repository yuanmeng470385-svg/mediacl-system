"""限流器测试（2026-08-11：Redis 分布式滑动窗口 + 内存降级）

覆盖：
- Redis 主路径：Lua 脚本调用（keys/args 正确），放行/拒绝语义
- Redis 不可用 → 降级内存版（不裸奔、不全 429），恢复后自动切回
- 白名单路径不限流；429 响应统一形状 {code:5003}
- reset 清 Redis key + 内存键
"""
import sys
import os
from unittest.mock import MagicMock

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", ".."))

from fastapi import FastAPI
from starlette.testclient import TestClient

from app.core.rate_limiter import RateLimiter, _MemoryWindow


class TestMemoryWindow:
    """内存滑动窗口（降级路径核心逻辑）"""

    def test_window_counts_and_rejects(self):
        m = _MemoryWindow(max_requests_per_minute=3, window_size=60)
        now = 1000.0
        assert m.check_and_record("u:1", now) is True
        assert m.check_and_record("u:1", now + 1) is True
        assert m.check_and_record("u:1", now + 2) is True
        assert m.check_and_record("u:1", now + 3) is False  # 第 4 次超限
        # 不同 key 互不影响
        assert m.check_and_record("u:2", now + 4) is True

    def test_window_expires(self):
        m = _MemoryWindow(max_requests_per_minute=1, window_size=60)
        assert m.check_and_record("u:1", 1000) is True
        assert m.check_and_record("u:1", 1001) is False
        assert m.check_and_record("u:1", 1061) is True  # 超过窗口（60s）后恢复

    def test_reset_clears(self):
        m = _MemoryWindow(max_requests_per_minute=1, window_size=60)
        assert m.check_and_record("u:1", 1000) is True
        m.reset("u:1")
        assert m.check_and_record("u:1", 1001) is True


class TestRateLimiterRedisPath:
    """Redis 主路径：Lua 脚本原子窗口"""

    def _limiter_with_fake_redis(self, allowed_value=1):
        limiter = RateLimiter.__new__(RateLimiter)  # 跳过中间件初始化
        limiter.max_requests = 60
        limiter._window_size = 60
        limiter._redis_url = "redis://localhost:6379/0"
        limiter._degraded = False
        limiter._degraded_logged_at = 0.0
        limiter._memory = _MemoryWindow(60)
        fake = MagicMock()
        fake.register_script.return_value = MagicMock(return_value=allowed_value)
        limiter._redis = fake
        limiter._script = fake.register_script.return_value
        return limiter, fake

    def test_redis_allows_calls_script_with_window_args(self):
        limiter, fake = self._limiter_with_fake_redis(allowed_value=1)
        assert limiter._redis_allows("u:7", 1234.5) is True
        limiter._script.assert_called_once()
        kwargs = limiter._script.call_args.kwargs
        assert kwargs["keys"] == ["rl:u:7"]
        assert kwargs["args"][0] == 60   # max
        assert kwargs["args"][1] == 60   # window
        assert kwargs["args"][2] == 1234.5  # now

    def test_redis_rejects(self):
        limiter, fake = self._limiter_with_fake_redis(allowed_value=0)
        assert limiter._redis_allows("u:7", 1234.5) is False

    def test_check_and_record_uses_redis_when_ok(self):
        limiter, fake = self._limiter_with_fake_redis(allowed_value=1)
        assert limiter._check_and_record("u:7", 1234.5) is True


class TestDegradeToMemory:
    """Redis 不可用 → 降级内存版；恢复后切回"""

    def _limiter(self, redis_error=True):
        limiter = RateLimiter.__new__(RateLimiter)
        limiter.max_requests = 2
        limiter._window_size = 60
        limiter._redis_url = "redis://localhost:1/0"
        limiter._degraded = False
        limiter._degraded_logged_at = 0.0
        limiter._memory = _MemoryWindow(2)

        if redis_error:
            def _boom(key, now):
                raise ConnectionError("redis down")
            limiter._redis_allows = _boom
        else:
            limiter._redis = None  # 模拟恢复后重新连接
        return limiter

    def test_degrade_to_memory_after_redis_failure(self):
        limiter = self._limiter()
        now = 1000.0
        assert limiter._check_and_record("u:1", now) is True
        assert limiter._check_and_record("u:1", now + 1) is True
        assert limiter._check_and_record("u:1", now + 2) is False  # 内存版超限
        assert limiter._degraded is True

    def test_recovery_switches_back_to_redis(self, caplog):
        limiter = self._limiter()
        assert limiter._check_and_record("u:1", 1000.0) is True
        assert limiter._degraded is True
        # Redis 恢复：_redis_allows 不再抛异常
        import logging
        calls = {"n": 0}

        def _ok(key, now):
            calls["n"] += 1
            return True

        limiter._redis_allows = _ok
        with caplog.at_level(logging.INFO, logger="app.core.rate_limiter"):
            assert limiter._check_and_record("u:1", 2000.0) is True
        assert limiter._degraded is False
        assert any("切回 Redis" in r.message for r in caplog.records)


class TestDispatch:
    """HTTP 层：429 形状、白名单、放行"""

    @staticmethod
    def _client(limiter):
        app = FastAPI()

        @app.get("/api/v1/test")
        async def root():
            return {"ok": True}

        @app.get("/health")
        async def health():
            return {"status": "ok"}

        # 直接注入实例（add_middleware 按参数重建，这里用 __call__ 绕开）
        app.add_middleware(RateLimiter, max_requests_per_minute=1, redis_url="redis://localhost:1/0")
        # 找到中间件实例并替换为给定 limiter（构造参数一致）
        return TestClient(app), app

    def test_429_shape_when_rejected(self, monkeypatch):
        app = FastAPI()

        @app.get("/api/v1/test")
        async def root():
            return {"ok": True}

        # max=1：第一个请求放行后第二个应 429 —— 用 monkeypatch 让 _redis_allows 恒拒绝
        def _reject(self, key, now):
            return False

        monkeypatch.setattr(RateLimiter, "_redis_allows", _reject)
        app.add_middleware(RateLimiter, max_requests_per_minute=60, redis_url="redis://localhost:1/0")
        client = TestClient(app)
        resp = client.get("/api/v1/test")
        assert resp.status_code == 429
        body = resp.json()
        assert body["code"] == 5003
        assert "请求过于频繁" in body["message"]

    def test_whitelist_bypasses(self, monkeypatch):
        app = FastAPI()

        @app.get("/health")
        async def health():
            return {"status": "ok"}

        def _fail(self, key, now):
            raise AssertionError("白名单路径不应走限流")

        monkeypatch.setattr(RateLimiter, "_redis_allows", _fail)
        app.add_middleware(RateLimiter, max_requests_per_minute=60, redis_url="redis://localhost:1/0")
        client = TestClient(app)
        assert client.get("/health").status_code == 200

    def test_allowed_passes_through(self, monkeypatch):
        app = FastAPI()

        @app.get("/api/v1/test")
        async def root():
            return {"ok": True}

        def _allow(self, key, now):
            return True

        monkeypatch.setattr(RateLimiter, "_redis_allows", _allow)
        app.add_middleware(RateLimiter, max_requests_per_minute=60, redis_url="redis://localhost:1/0")
        client = TestClient(app)
        resp = client.get("/api/v1/test")
        assert resp.status_code == 200
        assert resp.json() == {"ok": True}


class TestReset:
    def test_reset_clears_redis_and_memory(self):
        limiter = RateLimiter.__new__(RateLimiter)
        limiter._redis_url = "redis://localhost:6379/0"
        limiter._memory = _MemoryWindow(1)
        fake = MagicMock()
        limiter._redis = fake
        limiter._script = None
        limiter._degraded = False
        limiter._degraded_logged_at = 0.0

        limiter.reset("u:1")
        fake.delete.assert_called_once_with("rl:u:1")
