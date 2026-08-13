"""检索链路（search / search-test）线程池化回归：同步网络 IO 不得阻塞事件循环

回归背景（2026-08-13）：search_knowledge/search_test 在 async 端点里同步执行
embedding HTTP（DashVector）/ES/百炼网络往返——阻塞事件循环（与 2026-08-11
审核链路同根因）。修复：与 upload/review 一致用 asyncio.to_thread 丢线程池执行。

本文件验证：检索请求在后台线程池长时间阻塞（模拟网络往返）时，
其他请求（health）仍能立即响应。
"""
import sys
import os
import threading
import time

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", ".."))

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from app.main import app  # noqa: E402
from app.api import knowledge as knowledge_api  # noqa: E402
from shared.common.db_session import get_db  # noqa: E402
from shared.common.auth import get_current_user  # noqa: E402


class _UserStub:
    """require_roles 实时查库：需返回 active 的 admin 才能通过 RBAC"""

    def __init__(self):
        self.id = 1
        self.status = "active"
        self.role = "admin"


class _FakeDb:
    def __init__(self):
        self.user = _UserStub()

    def query(self, *a, **k):
        return self

    def filter(self, *a, **k):
        return self

    def first(self):
        return self.user

    def add(self, obj):
        pass

    def commit(self):
        pass


async def _fake_current_user():
    return {"id": 1, "username": "admin", "role": "admin"}


class _SlowSearchManager:
    """search 同步 sleep 模拟 embedding/ES/百炼网络往返"""

    def __init__(self, db):
        self.slow_seconds = 0.6

    def search(self, query, product_id=None, doc_type=None, top_k=10):
        time.sleep(self.slow_seconds)
        return [], "local_fallback"


class _UnconfiguredDV:
    def is_configured(self):
        return False


class _SlowBailian:
    def __init__(self, seconds):
        self.seconds = seconds

    def search(self, query, top_k=10):
        time.sleep(self.seconds)
        return []


class _LocalRepo:
    def local_search(self, query, top_k=10):
        return []


class _SlowBackendManager:
    """search-test 默认后端链（dashvector/bailian/local）中百炼同步阻塞"""

    def __init__(self, db):
        self.slow_seconds = 0.6
        self.dashvector = _UnconfiguredDV()
        self.bailian = _SlowBailian(self.slow_seconds)
        self.repo = _LocalRepo()


@pytest.fixture
def slow_search_client(monkeypatch):
    monkeypatch.setattr(knowledge_api, "DocumentManager", _SlowSearchManager)
    app.dependency_overrides[get_db] = lambda: _FakeDb()
    app.dependency_overrides[get_current_user] = _fake_current_user
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()


@pytest.fixture
def slow_search_test_client(monkeypatch):
    monkeypatch.setattr(knowledge_api, "DocumentManager", _SlowBackendManager)
    app.dependency_overrides[get_db] = lambda: _FakeDb()
    app.dependency_overrides[get_current_user] = _fake_current_user
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()


def test_search_blocking_does_not_stall_event_loop(slow_search_client):
    """search 在后台线程池阻塞 0.6s 期间，health 请求立即返回（事件循环未被占）"""
    client = slow_search_client
    result = {"health_elapsed": None}

    def _run_search():
        client.post("/api/v1/knowledge/search", json={"query": "剂量"})

    t = threading.Thread(target=_run_search)
    t.start()
    time.sleep(0.15)  # 检索请求已进入线程池阻塞

    start = time.time()
    resp = client.get("/health")
    result["health_elapsed"] = time.time() - start
    t.join(timeout=5)

    assert resp.status_code == 200
    # 若事件循环被同步网络 IO 占住，health 要等 0.6s 阻塞结束才能返回；
    # 线程池化后应立即响应（远小于阻塞时长）
    assert result["health_elapsed"] < 0.4, (
        f"health 耗时 {result['health_elapsed']:.3f}s —— 事件循环疑似被同步阻塞占住"
    )


def test_search_returns_after_blocking_completes(slow_search_client):
    """检索请求本身正常完成（阻塞在后台线程，不挂起请求）"""
    resp = slow_search_client.post("/api/v1/knowledge/search", json={"query": "剂量"})
    assert resp.status_code == 200
    body = resp.json()
    assert body["code"] == 0
    assert body["data"]["source"] == "local_fallback"


def test_search_test_blocking_does_not_stall_event_loop(slow_search_test_client):
    """search-test 串行调多后端（含百炼同步往返）同样不阻塞事件循环"""
    client = slow_search_test_client
    result = {"health_elapsed": None}

    def _run_search_test():
        client.post("/api/v1/knowledge/search-test", json={"query": "剂量"})

    t = threading.Thread(target=_run_search_test)
    t.start()
    time.sleep(0.15)

    start = time.time()
    resp = client.get("/health")
    result["health_elapsed"] = time.time() - start
    t.join(timeout=5)

    assert resp.status_code == 200
    assert result["health_elapsed"] < 0.4, (
        f"health 耗时 {result['health_elapsed']:.3f}s —— 事件循环疑似被同步阻塞占住"
    )


def test_search_test_returns_after_blocking_completes(slow_search_test_client):
    """search-test 请求本身正常完成并返回各后端结果"""
    resp = slow_search_test_client.post("/api/v1/knowledge/search-test", json={"query": "剂量"})
    assert resp.status_code == 200
    body = resp.json()
    assert body["code"] == 0
    backends = {b["backend"] for b in body["data"]["backends"]}
    assert backends == {"dashvector", "bailian", "local"}
