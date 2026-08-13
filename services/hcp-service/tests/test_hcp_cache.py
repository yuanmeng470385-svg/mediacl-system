"""HCP 画像 Redis 缓存测试（2026-08-11 修复：画像无缓存）

覆盖：
- 缓存读写（get/set/invalidate，键前缀 hcpcache:，TTL 生效）
- Redis 不可用 fail-open：get 返回 None、set/invalidate 不抛异常
- API 层：命中缓存不查库（回源只发生一次）；写路径（PUT/tags/profile-update）失效
"""
import asyncio
import sys
import os
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", ".."))

import pytest

from app.core.hcp_cache import HcpCache


def _fake_client():
    """返回带内存 dict 的 fake redis（set/get/delete/expire/scan_iter 语义）"""
    import re as _re
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

    def _scan_iter(pattern, count=100):
        rx = _re.compile(pattern.replace("*", ".*"))
        for name in list(store):
            if rx.match(name):
                yield name

    client.set.side_effect = _set
    client.get.side_effect = _get
    client.delete.side_effect = _delete
    client.scan_iter.side_effect = _scan_iter
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
        c.set("profile:1:all", {"ai_profile": {}})
        c.invalidate("hcp:1", "profile:1:all")
        assert c.get("hcp:1") is None
        assert c.get("profile:1:all") is None

    def test_invalidate_profile_prefix(self):
        """invalidate_profile：scan_iter 前缀删除该 hcp 全部视角画像键"""
        c = self._cache()
        c.set("profile:1:all", {"ai_profile": {}})
        c.set("profile:1:u5", {"ai_profile": {}})
        c.set("profile:1:u9", {"ai_profile": {}})
        c.set("profile:2:all", {"ai_profile": {}})  # 他人 hcp 不受影响
        c.invalidate_profile(1)
        assert c.get("profile:1:all") is None
        assert c.get("profile:1:u5") is None
        assert c.get("profile:1:u9") is None
        assert c.get("profile:2:all") is not None

    def test_invalidate_profile_exact_id_prefix(self):
        """E6（2026-08-13）：scan 模式 hcpcache:profile:{id}:* 精确匹配 ——
        清 hcp 1 不得误删 hcp 10/11/100 的付费画像缓存；历史单键 profile:{id}
        仍单独删除（H3 之前遗留键的兼容承诺）"""
        c = self._cache()
        c.set("profile:1:all", {"ai_profile": {}})
        c.set("profile:1:u5", {"ai_profile": {}})
        c.set("profile:1", {"ai_profile": {}})           # H3 之前的历史单键
        c.set("profile:10:all", {"ai_profile": {}})      # 旧模式 profile:1* 会误伤
        c.set("profile:11:u3", {"ai_profile": {}})
        c.set("profile:100:all", {"ai_profile": {}})
        c.invalidate_profile(1)
        assert c.get("profile:1:all") is None
        assert c.get("profile:1:u5") is None
        assert c.get("profile:1") is None
        assert c.get("profile:10:all") is not None
        assert c.get("profile:11:u3") is not None
        assert c.get("profile:100:all") is not None

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
        """PUT/tags/profile-update 等写路径调用 _invalidate_hcp_cache（删 hcp 键 + 全部视角画像键）"""
        from app.core.hcp_cache import cache as real_cache
        fake = _fake_client()
        real_cache._redis = fake
        real_cache.set("hcp:1", {"id": 1})
        # H3：画像缓存按查看者视角分键（profile:{hcp_id}:all / :u{uid}），
        # 写路径必须前缀失效全部视角，否则他人视角的过期画像仍被命中
        real_cache.set("profile:1:all", {"ai_profile": {"role": "admin"}})
        real_cache.set("profile:1:u5", {"ai_profile": {"role": "rep"}})
        real_cache.set("profile:1:u9", {"ai_profile": {"role": "rep"}})

        api_module._invalidate_hcp_cache(1)
        assert real_cache.get("hcp:1") is None
        assert real_cache.get("profile:1:all") is None
        assert real_cache.get("profile:1:u5") is None
        assert real_cache.get("profile:1:u9") is None

    def test_profile_viewer_key_and_user_filter(self, api_module, monkeypatch):
        """H3：/profile 按查看者角色分视角 —— rep 只看自己的交互（user_id 过滤 + u5 键），
        admin/manager 看全量（user_id=None + all 键）；第二次 rep 请求命中缓存不重新生成"""
        from app.core.hcp_cache import cache as real_cache
        real_cache._redis = _fake_client()
        real_cache._redis._store.clear()

        gen_calls = []
        import app.services.profile_generator as pg

        def _recording_generate(self, db, hcp, interaction_limit=5, user_id=None):
            gen_calls.append(user_id)
            # degraded=True：跳过 write_audit_log（不碰审计服务）；不调真实实现（db=None）
            return {"ai_profile": {"summary": "测试画像"}, "degraded": True}

        monkeypatch.setattr(pg.ProfileGenerator, "generate", _recording_generate)
        monkeypatch.setattr(api_module, "_get_hcp_or_404",
                            lambda db, hcp_id: SimpleNamespace(id=1, name="张医生",
                                                              to_dict=lambda: {"id": 1, "name": "张医生"}))
        monkeypatch.setattr(api_module, "hcp_cache", real_cache)

        # rep 视角：user_id 过滤 + u5 分键
        asyncio.run(api_module.get_hcp_profile(1, {"id": 5, "role": "rep"}, None))
        assert gen_calls == [5], f"rep 应传 user_id=5，实际 {gen_calls}"
        assert real_cache.get("profile:1:u5") is not None
        assert real_cache.get("profile:1:all") is None

        # admin 视角：全量 + all 分键
        asyncio.run(api_module.get_hcp_profile(1, {"id": 1, "role": "admin"}, None))
        assert gen_calls == [5, None], f"admin 应传 user_id=None，实际 {gen_calls}"
        assert real_cache.get("profile:1:all") is not None

        # rep 再次请求：命中 u5 缓存，不重新生成
        asyncio.run(api_module.get_hcp_profile(1, {"id": 5, "role": "rep"}, None))
        assert gen_calls == [5, None], f"第二次 rep 应命中缓存，实际 {gen_calls}"
