"""
RedisCodeStore.consume 的 Lua 语义测试（H1 回归，2026-08-13）

验证「计数 + 比较 + 作废」在同一 Lua 脚本内原子完成：
  - 同一验证码两次 consume 只有第一次 matched
  - 并发 consume 同一验证码只有一次 matched（Redis 单线程串行执行 Lua）
  - 每次校验消耗一次尝试，第 max_attempts 次之后作废（off-by-one 口径与
    tests/test_auth.py 的登录用例一致：第 5 次仍有效、之后作废，用尽后
    任何输入包括正确码都被拒）
  - 过期验证码返回 notfound

需要本地 Redis（默认 redis://localhost:6379，测试用 db 15 与专用手机号，
不污染开发数据）；Redis 不可达或未装 redis 包时整组跳过，CI 也能跑。
"""
import time
from concurrent.futures import ThreadPoolExecutor

import pytest

redis = pytest.importorskip("redis")

from app.core.code_store import (
    CONSUME_EXHAUSTED,
    CONSUME_MATCHED,
    CONSUME_MISMATCH,
    CONSUME_NOTFOUND,
    RedisCodeStore,
)

REDIS_URL = "redis://localhost:6379/15"
TEST_PHONE = "19900000001"


def _reachable() -> bool:
    try:
        client = redis.Redis.from_url(
            REDIS_URL, decode_responses=True, socket_timeout=1, socket_connect_timeout=1
        )
        client.ping()
        client.close()
        return True
    except Exception:
        return False


pytestmark = pytest.mark.skipif(
    not _reachable(), reason="本地 Redis 不可用，跳过 Lua 语义测试"
)


def _cleanup():
    """清掉验证码 key 与冷却 key，避免用例间残留"""
    client = redis.Redis.from_url(REDIS_URL, decode_responses=True)
    client.delete("authcode:" + TEST_PHONE, "authcode:cd:" + TEST_PHONE)
    client.close()


@pytest.fixture()
def store():
    _cleanup()
    s = RedisCodeStore(REDIS_URL)
    yield s
    _cleanup()


def _save(store, code="123456"):
    store.save(TEST_PHONE, code, ttl=300, cooldown=60)


class TestConsumeLua:
    def test_同码两次consume只有第一次matched(self, store):
        _save(store)
        assert store.consume(TEST_PHONE, "123456", 5) == CONSUME_MATCHED
        # 已一次性作废：重放返回 notfound
        assert store.consume(TEST_PHONE, "123456", 5) == CONSUME_NOTFOUND

    def test_并发同码consume只有一次matched(self, store):
        """真实 Redis 并发：Lua 串行执行，同码只能被消耗一次"""
        _save(store)

        def hit(_):
            return store.consume(TEST_PHONE, "123456", 5)

        with ThreadPoolExecutor(max_workers=8) as pool:
            results = list(pool.map(hit, range(8)))
        assert results.count(CONSUME_MATCHED) == 1
        assert results.count(CONSUME_NOTFOUND) == 7

    def test_错误码消耗尝试次数第5次后作废(self, store):
        _save(store)
        for _ in range(5):
            assert store.consume(TEST_PHONE, "000000", 5) == CONSUME_MISMATCH
        # 第 6 次（即使输对）→ exhausted，验证码已作废
        assert store.consume(TEST_PHONE, "123456", 5) == CONSUME_EXHAUSTED
        assert store.consume(TEST_PHONE, "123456", 5) == CONSUME_NOTFOUND

    def test_第5次输对仍matched(self, store):
        """上限内（含第 5 次）输对应放行 —— off-by-one 与登录用例口径一致"""
        _save(store)
        for _ in range(4):
            assert store.consume(TEST_PHONE, "000000", 5) == CONSUME_MISMATCH
        assert store.consume(TEST_PHONE, "123456", 5) == CONSUME_MATCHED
        assert store.consume(TEST_PHONE, "123456", 5) == CONSUME_NOTFOUND

    def test_过期验证码返回notfound(self, store):
        store.save(TEST_PHONE, "123456", ttl=1, cooldown=60)
        time.sleep(1.1)
        assert store.consume(TEST_PHONE, "123456", 5) == CONSUME_NOTFOUND
