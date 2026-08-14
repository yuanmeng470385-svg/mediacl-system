"""M15 回归：服务间内部调用路径不占用用户限流配额

回归背景（2026-08-14）：rate_limiter 的豁免表不含 INTERNAL_PATHS
（/api/v1/compliance/check、/api/v1/audit/log、/api/v1/hcps/profile-update）——
多 ASR 并发时每句都调 compliance，与用户请求共用 60/min 配额，超限后 429 →
调用方 fail-closed，正常拜访被误拦。修复：限流豁免引用 auth_middleware 的
INTERNAL_PATHS 常量（避免两处维护漂移），内部路径仍受 AuthMiddleware 的
X-Internal-Key 校验（无 key 403），豁免限流不削弱防护。

本文件验证：
- 三条内部路径（含子路径）带 key 连发超过限流阈值不 429；
- 普通路径（/api/v1/auth/profile、/api/v1/auth/login）仍受限流约束；
- 无 key 的内部路径仍 403（Auth 层拦截）；
- 形似内部路径的 /api/v1/audit/logs（复数）不被误豁免，仍受限流约束。
"""
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", ".."))

from fastapi import FastAPI  # noqa: E402
from starlette.testclient import TestClient  # noqa: E402

from app.core.auth_middleware import AuthMiddleware, INTERNAL_PATHS  # noqa: E402
from app.core.rate_limiter import RateLimiter  # noqa: E402


class TestInternalPathsExempt:
    """限流层：内部路径不经过限流计数（Auth 层仍独立校验 key）"""

    def test_internal_paths_never_consult_limiter(self, monkeypatch):
        app = FastAPI()

        for p in INTERNAL_PATHS:
            @app.post(p)
            async def _ok():
                return {"ok": True}

        def _fail(self, key, now):
            raise AssertionError("内部路径不应走限流计数")

        monkeypatch.setattr(RateLimiter, "_redis_allows", _fail)
        app.add_middleware(RateLimiter, max_requests_per_minute=1, redis_url="redis://localhost:1/0")
        client = TestClient(app)

        # 三条内部路径：即使限额为 1/min，连发也不 429（豁免）
        for p in INTERNAL_PATHS:
            for _ in range(3):
                resp = client.post(p)
                assert resp.status_code == 200, f"{p} 不应被限流"

    def test_internal_subpath_exempt(self, monkeypatch):
        """子路径（p + "/"）与精确匹配同口径豁免 —— 与 auth_middleware._is_internal 一致"""
        app = FastAPI()

        @app.post("/api/v1/compliance/check/sub")
        async def _ok():
            return {"ok": True}

        def _fail(self, key, now):
            raise AssertionError("内部子路径不应走限流计数")

        monkeypatch.setattr(RateLimiter, "_redis_allows", _fail)
        app.add_middleware(RateLimiter, max_requests_per_minute=1, redis_url="redis://localhost:1/0")
        client = TestClient(app)
        assert client.post("/api/v1/compliance/check/sub").status_code == 200


class TestNormalPathsStillLimited:
    """普通用户路径（含 PUBLIC_PATHS 入口）继续受限流约束，不得豁免"""

    @staticmethod
    def _limited_client(monkeypatch, path: str):
        app = FastAPI()

        @app.post(path)
        async def _ok():
            return {"ok": True}

        def _redis_down(self, key, now):
            raise ConnectionError("redis down")

        monkeypatch.setattr(RateLimiter, "_redis_allows", _redis_down)
        app.add_middleware(RateLimiter, max_requests_per_minute=1, redis_url="redis://localhost:1/0")
        return TestClient(app)

    def test_profile_path_rate_limited(self, monkeypatch):
        """用户路径 /api/v1/auth/profile：限额 1/min，第 2 次请求 429"""
        client = self._limited_client(monkeypatch, "/api/v1/auth/profile")
        assert client.post("/api/v1/auth/profile").status_code == 200
        resp = client.post("/api/v1/auth/profile")
        assert resp.status_code == 429
        assert resp.json()["code"] == 5003

    def test_public_login_path_rate_limited(self, monkeypatch):
        """PUBLIC_PATHS 入口（login）是用户路径，必须继续受限流保护"""
        client = self._limited_client(monkeypatch, "/api/v1/auth/login")
        assert client.post("/api/v1/auth/login").status_code == 200
        assert client.post("/api/v1/auth/login").status_code == 429

    def test_audit_logs_plural_not_over_exempted(self, monkeypatch):
        """精确匹配语义：/api/v1/audit/logs（复数）不是内部路径，仍受限流"""
        client = self._limited_client(monkeypatch, "/api/v1/audit/logs")
        assert client.post("/api/v1/audit/logs").status_code == 200
        assert client.post("/api/v1/audit/logs").status_code == 429


class TestInternalStillAuthGuarded:
    """安全边界：豁免限流不削弱鉴权 —— 无 key 的内部路径仍在 Auth 层被 403"""

    @staticmethod
    def _full_client(monkeypatch):
        """按网关中间件顺序组装：RateLimiter 先注册、Auth 后注册
        （Starlette LIFO → Auth 先执行，与 gateway main.py 一致）"""
        monkeypatch.setenv("INTERNAL_API_KEY", "test-internal-key-for-test")
        monkeypatch.setattr("shared.common.internal_auth._INTERNAL_KEY", None)

        app = FastAPI()

        @app.post("/api/v1/compliance/check")
        async def _ok():
            return {"ok": True}

        def _fail(self, key, now):
            raise AssertionError("内部路径不应走限流计数")

        monkeypatch.setattr(RateLimiter, "_redis_allows", _fail)
        app.add_middleware(RateLimiter, max_requests_per_minute=1, redis_url="redis://localhost:1/0")
        app.add_middleware(AuthMiddleware)
        return TestClient(app)

    def test_no_key_returns_403(self, monkeypatch):
        """无 X-Internal-Key 的内部路径 → 403（Auth 层拦截，非放行）"""
        client = self._full_client(monkeypatch)
        resp = client.post("/api/v1/compliance/check")
        assert resp.status_code == 403
        assert resp.json()["code"] == 3001

    def test_wrong_key_returns_403(self, monkeypatch):
        """错误 key → 403"""
        client = self._full_client(monkeypatch)
        resp = client.post(
            "/api/v1/compliance/check",
            headers={"X-Internal-Key": "wrong-key"},
        )
        assert resp.status_code == 403
        assert resp.json()["code"] == 3001

    def test_valid_key_bypasses_limit_even_over_threshold(self, monkeypatch):
        """有效 key + 内部路径：限额 1/min 下连发 5 次不 429（豁免），
        同时证明 key 校验仍在生效（无 key 会被 403）"""
        client = self._full_client(monkeypatch)
        headers = {"X-Internal-Key": "test-internal-key-for-test"}
        for _ in range(5):
            resp = client.post("/api/v1/compliance/check", headers=headers)
            assert resp.status_code == 200
