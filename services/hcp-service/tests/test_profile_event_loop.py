"""画像生成事件循环回归：同步 LLM 不得阻塞 hcp-service 其他请求

回归背景（2026-08-12 真机实测）：/profile 端点在 async 路由里同步调用
generator.generate()（内部 QwenClient.chat 是 OpenAI SDK 同步阻塞调用），
画像生成 ~8s 期间 hcp-service 事件循环被占——同网关同时发来的
/hcps/{id} 与 /interactions 全部排队 7.7s（LLM 结束才一起返回），
拜访总结页实际等待 ≈ 8s。修复：asyncio.to_thread 丢线程池。

本文件验证：画像生成在后台线程阻塞时，其他端点（/hcps 列表）立即响应。
"""
import os
import sys
import threading
import time

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", ".."))

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from app.main import app  # noqa: E402
from app.api import hcps as hcps_api  # noqa: E402
from shared.common.db_session import get_db  # noqa: E402
from shared.common.auth import get_current_user  # noqa: E402


class _FakeHcp:
    def __init__(self):
        self.id = 1
        self.name = "张伟"
        self.hospital = "协和医院"
        self.department = "心内科"
        self.title = "主任医师"
        self.tags = ["KOL"]

    def to_dict(self):
        return {"id": self.id, "name": self.name, "hospital": self.hospital}


class _FakeDb:
    """hcp 查得到 + 其余查询不崩"""

    def __init__(self):
        self._fetched = []

    def query(self, *a, **k):
        return self

    def filter(self, *a, **k):
        return self

    def first(self):
        return _FakeHcp()

    def all(self):
        return []

    def count(self):
        return 0

    def order_by(self, *a, **k):
        return self

    def offset(self, *a, **k):
        return self

    def limit(self, *a, **k):
        return self

    def commit(self):
        pass

    def close(self):
        pass


class _SlowGenerator:
    """模拟画像 LLM：同步 sleep 0.6s（旧实现会占死事件循环）"""

    def __init__(self):
        self.slow_seconds = 0.6

    def generate(self, db, hcp, user_id=None, **kwargs):
        time.sleep(self.slow_seconds)
        return {"ai_profile": {"summary": "学术型KOL"}, "interactions": [], "degraded": False}


async def _fake_current_user():
    return {"id": 1, "username": "admin", "role": "admin"}


async def _fake_audit_log(**kwargs):
    return None


@pytest.fixture
def slow_client(monkeypatch):
    monkeypatch.setattr(hcps_api, "ProfileGenerator", _SlowGenerator)
    monkeypatch.setattr(hcps_api, "write_audit_log", _fake_audit_log)
    monkeypatch.setattr(hcps_api.hcp_cache, "get", lambda *a, **k: None)  # 恒 cache miss
    monkeypatch.setattr(hcps_api.hcp_cache, "set", lambda *a, **k: None)
    app.dependency_overrides[get_db] = lambda: _FakeDb()
    app.dependency_overrides[get_current_user] = _fake_current_user
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()


def test_profile_blocking_does_not_stall_event_loop(slow_client):
    """画像生成在后台线程阻塞 0.6s 期间，/hcps 列表请求立即返回（事件循环未被占）"""
    client = slow_client
    result = {"list_elapsed": None}

    def _run_profile():
        client.get("/api/v1/hcps/1/profile")

    t = threading.Thread(target=_run_profile)
    t.start()
    time.sleep(0.15)  # 画像请求已进入线程池阻塞

    start = time.time()
    resp = client.get("/api/v1/hcps")
    result["list_elapsed"] = time.time() - start
    t.join(timeout=5)

    assert resp.status_code == 200
    # 若事件循环被同步 LLM 占住，列表要等 0.6s 阻塞结束才能返回；
    # 线程池化后应立即响应（远小于阻塞时长）
    assert result["list_elapsed"] < 0.4, (
        f"/hcps 列表耗时 {result['list_elapsed']:.3f}s —— 事件循环疑似被同步 LLM 阻塞占住"
    )


def test_profile_returns_after_blocking_completes(slow_client):
    """画像请求本身正常完成（阻塞在后台线程，不挂起请求）"""
    resp = slow_client.get("/api/v1/hcps/1/profile")
    assert resp.status_code == 200
    body = resp.json()
    assert body["code"] == 0
    assert body["data"]["ai_profile"]["summary"] == "学术型KOL"
