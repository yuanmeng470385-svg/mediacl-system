"""审核/上传链路线程池化回归：长同步阻塞期间事件循环不得被占

回归背景（2026-08-11）：review_document/upload_document 在 async 端点里
同步执行百炼导入轮询（最长 1h）+ OSS/向量化 IO —— 阻塞事件循环，2 worker
时一个导入卡死全服务。修复：asyncio.to_thread 丢线程池执行。

本文件验证：审核请求在后台线程池长时间阻塞（模拟百炼轮询）时，
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


class _FakeDoc:
    def __init__(self, status="draft"):
        self.id = 5
        self.status = status
        self.title = "指南"
        self.doc_type = "guideline"

    def to_dict(self):
        return {"id": self.id, "status": self.status, "title": self.title}


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


async def _fake_audit_log(**kwargs):
    return None


class _SlowManager:
    """approve_document 同步 sleep 模拟百炼长轮询（最长可达 1h）"""

    def __init__(self, db):
        self.slow_seconds = 0.6

    def approve_document(self, doc_id, reviewer_id):
        time.sleep(self.slow_seconds)
        return _FakeDoc(status="ready")

    def reject_document(self, doc_id, reviewer_id):
        time.sleep(self.slow_seconds)
        return _FakeDoc(status="rejected")


@pytest.fixture
def slow_client(monkeypatch):
    monkeypatch.setattr(knowledge_api, "DocumentManager", _SlowManager)
    monkeypatch.setattr(knowledge_api, "write_audit_log", _fake_audit_log)
    app.dependency_overrides[get_db] = lambda: _FakeDb()
    app.dependency_overrides[get_current_user] = _fake_current_user
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()


def test_review_blocking_does_not_stall_event_loop(slow_client):
    """审核在后台线程池阻塞 0.6s 期间，health 请求立即返回（事件循环未被占）"""
    client = slow_client
    result = {"health_elapsed": None}

    def _run_review():
        client.post("/api/v1/knowledge/documents/5/review", json={"approved": True})

    t = threading.Thread(target=_run_review)
    t.start()
    time.sleep(0.15)  # 审核请求已进入线程池阻塞

    start = time.time()
    resp = client.get("/health")
    result["health_elapsed"] = time.time() - start
    t.join(timeout=5)

    assert resp.status_code == 200
    # 若事件循环被同步轮询占住，health 要等 0.6s 阻塞结束才能返回；
    # 线程池化后应立即响应（远小于阻塞时长）
    assert result["health_elapsed"] < 0.4, (
        f"health 耗时 {result['health_elapsed']:.3f}s —— 事件循环疑似被同步阻塞占住"
    )


def test_review_returns_after_blocking_completes(slow_client):
    """审核请求本身正常完成（阻塞在后台线程，不挂起请求）"""
    resp = slow_client.post("/api/v1/knowledge/documents/5/review", json={"approved": True})
    assert resp.status_code == 200
    body = resp.json()
    assert body["code"] == 0
    assert body["data"]["status"] == "ready"


def test_reject_blocking_does_not_stall_event_loop(slow_client):
    """驳回路径（含索引清理 IO）同样线程池化"""
    client = slow_client
    result = {"health_elapsed": None}

    def _run_reject():
        client.post("/api/v1/knowledge/documents/5/review", json={"approved": False})

    t = threading.Thread(target=_run_reject)
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
