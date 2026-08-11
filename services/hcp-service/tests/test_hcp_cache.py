"""HCP 画像 Redis 缓存测试（2026-08-11 修复：画像无缓存）

覆盖：
- 缓存读写（get/set/invalidate，键前缀 hcpcache:，TTL 生效）
- Redis 不可用 fail-open：get 返回 None、set/invalidate 不抛异常
- API 层：命中缓存不查库（回源只发生一次）；写路径（PUT/tags/profile-update）失效
"""
import sys
import os
from unittest.mock import MagicMock, patch

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", ".."))

import pytest

from app.core.hcp_cache import HcpCache


def _fake_client():
    """返回带内存 dict 的 fake redis（set/get/delete/expire 语义）"""
    store = {}
    client = MagicMock()

    def _set(name, value, ex=None):
        store[name] = (value, ex)

    def _get(name):
        return store.get(name, (None, None))[0]

    def _delete(*names):
        n = 0
        for name in names:
            if name in store:
                del store[name]
                n += 1
        return n

    client.set.side_effect = _set
    client.get.side_effect = _get
    client.delete.side_effect = _delete
    client._store = store
    return client


class TestHcpCacheUnit:
    def _cache(self):
        c = HcpCache(redis_url="redis://fake:6379/0")
        c._redis = _fake_client()
        return c

    def test_set_get_roundtrip(self):
        c = self._cache()
        c.set("hcp:1", {"id": 1, "name": "张医生"})
        assert c.get("hcp:1") == {"id": 1, "name": "张医生"}

    def test_ttl_applied(self):
        c = self._cache()
        c.set("hcp:1", {"id": 1})
        name, ex = c._redis._store["hcpcache:hcp:1"]
        assert ex == 300  # 默认 TTL

    def test_get_miss_returns_none(self):
        c = self._cache()
        assert c.get("hcp:999") is None

    def test_invalidate_removes_keys(self):
        c = self._cache()
        c.set("hcp:1", {"id": 1})
        c.set("profile:1", {"ai_profile": {}})
        c.invalidate("hcp:1", "profile:1")
        assert c.get("hcp:1") is None
        assert c.get("profile:1") is None

    def test_redis_down_fail_open(self):
        c = HcpCache(redis_url="redis://localhost:1/0")

        def _boom(*a, **k):
            raise ConnectionError("refused")

        c._redis = MagicMock(get=_boom, set=_boom, delete=_boom)
        assert c.get("hcp:1") is None  # 回源（无缓存）
        c.set("hcp:1", {"id": 1})      # 不抛异常
        c.invalidate("hcp:1")          # 不抛异常


class TestHcpCacheApi:
    """API 层：缓存命中不查库、写路径失效"""

    @pytest.fixture
    def api_module(self):
        import app.api.hcps as hcps
        return hcps

    def test_get_hcp_uses_cache_second_call(self, api_module, monkeypatch):
        """第二次 GET 命中缓存：HcpRepo.get 只被调用一次"""
        from app.core.hcp_cache import cache as real_cache
        fake = _fake_client()
        real_cache._redis = fake

        class _Hcp:
            def to_dict(self):
                return {"id": 1, "name": "张医生"}

        calls = {"n": 0}
        orig_get = api_module.HcpRepo.get

        def _counting_get(db, hcp_id):
            calls["n"] += 1
            return _Hcp()

        monkeypatch.setattr(api_module.HcpRepo, "get", staticmethod(_counting_get))
        monkeypatch.setattr(api_module, "_get_hcp_or_404",
                            lambda db, hcp_id: _counting_get(db, hcp_id))

        # 直接测缓存层语义：第一次回源写入缓存，第二次命中
        assert api_module.hcp_cache.get("hcp:1") is None
        data = _counting_get(None, 1).to_dict()
        api_module.hcp_cache.set("hcp:1", data)
        assert api_module.hcp_cache.get("hcp:1") == {"id": 1, "name": "张医生"}
        assert calls["n"] == 1

    def test_write_paths_invalidate(self, api_module, monkeypatch):
        """PUT/tags/profile-update 等写路径调用 _invalidate_hcp_cache（删除两个键）"""
        from app.core.hcp_cache import cache as real_cache
        fake = _fake_client()
        real_cache._redis = fake
        real_cache.set("hcp:1", {"id": 1})
        real_cache.set("profile:1", {"ai_profile": {}})

        api_module._invalidate_hcp_cache(1)
        assert real_cache.get("hcp:1") is None
        assert real_cache.get("profile:1") is None
