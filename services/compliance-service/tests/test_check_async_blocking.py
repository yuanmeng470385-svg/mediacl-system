"""M3 回归：/check 与 /rules/test 的同步 LLM 调用线程池化后，慢 LLM 不阻塞事件循环

回归背景（2026-08-14）：checker.check / checker.test_rule 在 async 端点内同步调用
OpenAI SDK（默认读超时 600s、重试 2 次）—— LLM 高峰变慢时 compliance 2 worker 被
占死，所有调用方（specialist/visit）10s 超时后按 fail-closed 全被拦。修复：
1. 端点改 asyncio.to_thread（与 knowledge upload/review 同款模式）；
2. qwen 客户端显式 timeout（读 15s / 连接 5s）+ max_retries=1；
3. 超时/网络异常仍落入 checker 的 except Exception → R999 fail-closed，不放行。

本文件验证（仿 knowledge-service/tests/test_review_async_blocking.py 模式）：
- 慢 LLM（mock sleep）期间 /health 快速响应（事件循环未被占）；
- LLM 超时异常经 /check 返回 blocked + R999（fail-closed 不回归）；
- fast 模式不调 LLM（无阻塞、无 LLM 调用）；
- qwen 客户端构造参数已收紧（timeout/max_retries 非 SDK 默认）。
"""
import sys
import os
import types
import threading
import time

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", ".."))

import pytest  # noqa: E402
import httpx  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from app.main import app  # noqa: E402
from app.api import rules as rules_api  # noqa: E402
from shared.common.db_session import get_db  # noqa: E402
from shared.common.auth import get_current_user  # noqa: E402


# ==================== 假 DB / 假登录（与 test_rules_api.py 同款） ====================

class _FakeUser:
    """require_roles 库查（S6 修复）：主键查 User 返回的 active admin 用户"""

    def __init__(self):
        self.id = 1
        self.status = "active"
        self.role = "admin"


class _UserQuery:
    """users 表查询 stub：first() 返回 active admin 用户"""

    def filter(self, *a, **kw):
        return self

    def first(self):
        return _FakeUser()


class _FakeDb:
    """假 session：add/commit/rollback 全在内存，不连真库"""

    def query(self, *a, **kw):
        model = a[0] if a else None
        if model is not None and getattr(model, "__name__", "") == "User":
            return _UserQuery()
        return self

    def filter(self, *a, **kw):
        return self

    def all(self):
        return []

    def first(self):
        return None

    def add(self, obj):
        pass

    def commit(self):
        pass

    def rollback(self):
        pass

    def close(self):
        pass


async def _fake_current_user():
    return {"id": 1, "username": "tester", "role": "admin"}


@pytest.fixture
def client(monkeypatch):
    """TestClient：假 DB + 内部 key + admin 登录，只测 /check 与 /rules/test 线程池化路径"""
    monkeypatch.setenv("INTERNAL_API_KEY", "test-internal-key")
    monkeypatch.setattr("shared.common.internal_auth._INTERNAL_KEY", None)
    # checker 的 TTL 规则重载用独立 SessionLocal —— 置空表避免连真库
    monkeypatch.setattr("shared.common.db_session.SessionLocal", lambda: _FakeDb())

    app.dependency_overrides[get_db] = lambda: _FakeDb()
    app.dependency_overrides[get_current_user] = _fake_current_user
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()


# ==================== 假 qwen 客户端 ====================

def _fake_qwen_slow(sleep_seconds=0.8, raw_text='{"violations": []}'):
    """create 同步 sleep 模拟慢 LLM（修复前：阻塞事件循环）"""
    def _slow_create(**kw):
        time.sleep(sleep_seconds)
        return types.SimpleNamespace(
            choices=[types.SimpleNamespace(message=types.SimpleNamespace(content=raw_text))]
        )

    return types.SimpleNamespace(
        chat=types.SimpleNamespace(completions=types.SimpleNamespace(create=_slow_create))
    )


def _fake_qwen_timeout():
    """create 即抛 httpx 读超时（模拟 LLM 侧超时）"""
    def _raise_timeout(**kw):
        raise httpx.ReadTimeout("LLM 语义审核读超时")

    return types.SimpleNamespace(
        chat=types.SimpleNamespace(completions=types.SimpleNamespace(create=_raise_timeout))
    )


# ==================== 事件循环不阻塞 ====================

def test_check_slow_llm_does_not_block_event_loop(client, monkeypatch):
    """/check 语义层在后台线程池阻塞 0.8s 期间，/health 立即返回（事件循环未被占）"""
    monkeypatch.setattr(rules_api.checker, "qwen_client", _fake_qwen_slow(sleep_seconds=0.8))
    outcome = {}
    result = {"health_elapsed": None}

    def _run_check():
        outcome["resp"] = client.post(
            "/api/v1/compliance/check",
            headers={"X-Internal-Key": "test-internal-key"},
            json={"content": "今天天气不错，适合开会讨论"},
        )

    t = threading.Thread(target=_run_check)
    t.start()
    time.sleep(0.2)  # 检查请求已进入线程池阻塞

    start = time.time()
    resp = client.get("/health")
    result["health_elapsed"] = time.time() - start
    t.join(timeout=10)

    assert not t.is_alive(), "检查请求应在线程池完成阻塞并返回"
    assert resp.status_code == 200
    assert result["health_elapsed"] < 0.5, (
        f"health 耗时 {result['health_elapsed']:.3f}s —— 事件循环疑似被同步 LLM 占住"
    )
    # 检查请求本身正常完成（阻塞在后台线程，不挂起请求）
    assert outcome["resp"].status_code == 200
    body = outcome["resp"].json()
    assert body["code"] == 0
    assert body["data"]["blocked"] is False


def test_rules_test_slow_llm_does_not_block_event_loop(client, monkeypatch):
    """/rules/test 对 semantic 规则同样线程池化：慢 LLM 期间 /health 立即返回"""
    monkeypatch.setattr(rules_api.checker, "qwen_client", _fake_qwen_slow(sleep_seconds=0.8))
    outcome = {}
    result = {"health_elapsed": None}

    def _run_test():
        outcome["resp"] = client.post(
            "/api/v1/compliance/rules/test",
            json={"content": "今天天气不错，适合开会讨论", "rule_code": "R003"},
        )

    t = threading.Thread(target=_run_test)
    t.start()
    time.sleep(0.2)

    start = time.time()
    resp = client.get("/health")
    result["health_elapsed"] = time.time() - start
    t.join(timeout=10)

    assert not t.is_alive()
    assert resp.status_code == 200
    assert result["health_elapsed"] < 0.5, (
        f"health 耗时 {result['health_elapsed']:.3f}s —— 事件循环疑似被同步 LLM 占住"
    )
    assert outcome["resp"].status_code == 200
    assert outcome["resp"].json()["code"] == 0


# ==================== fail-closed 不回归 ====================

def test_check_llm_timeout_fails_closed(client, monkeypatch):
    """M3：LLM 读超时异常经线程池化端点返回 blocked + R999 —— 超时收敛进
    checker 的 except Exception → R999 拦截路径，不得变成放行（fail-closed）"""
    monkeypatch.setattr(rules_api.checker, "qwen_client", _fake_qwen_timeout())
    resp = client.post(
        "/api/v1/compliance/check",
        headers={"X-Internal-Key": "test-internal-key"},
        json={"content": "今天天气不错，适合开会讨论"},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["code"] == 0
    assert body["data"]["blocked"] is True
    assert any(v["rule_code"] == "R999" for v in body["data"]["violations"])


# ==================== fast 模式不受影响 ====================

def test_check_fast_mode_does_not_call_llm(client, monkeypatch):
    """fast 模式只跑关键词/正则（毫秒级），不调 LLM、无阻塞"""
    calls = []

    def _create(**kw):
        calls.append(1)
        raise AssertionError("fast 模式不应调用 LLM")

    fake = types.SimpleNamespace(
        chat=types.SimpleNamespace(completions=types.SimpleNamespace(create=_create))
    )
    monkeypatch.setattr(rules_api.checker, "qwen_client", fake)
    resp = client.post(
        "/api/v1/compliance/check",
        headers={"X-Internal-Key": "test-internal-key"},
        json={"content": "今天天气不错，适合开会讨论", "fast": True},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["code"] == 0
    assert body["data"]["blocked"] is False
    assert calls == []


# ==================== 客户端构造参数收紧 ====================

def test_qwen_client_tight_timeout_and_retries(monkeypatch):
    """M3：构造的 OpenAI 客户端读超时 15s / 连接超时 5s / max_retries=1
    （非 SDK 默认 600s/2 次 —— 默认值会让线程池被慢响应占满）"""
    captured = {}

    class _FakeCompletions:
        def create(self, **kw):
            return types.SimpleNamespace(
                choices=[types.SimpleNamespace(
                    message=types.SimpleNamespace(content='{"violations": []}')
                )]
            )

    class _FakeOpenAI:
        def __init__(self, **kwargs):
            captured.update(kwargs)
            self.chat = types.SimpleNamespace(completions=_FakeCompletions())

    import app.core.checker as checker_module
    monkeypatch.setattr(checker_module, "OpenAI", _FakeOpenAI)
    monkeypatch.setenv("DASHSCOPE_API_KEY", "test-dashscope-key")
    monkeypatch.setattr("shared.common.db_session.SessionLocal", lambda: _FakeDb())
    monkeypatch.setattr(rules_api.checker, "qwen_client", None)

    result = rules_api.checker.check("今天天气不错，适合开会讨论", {"type": "chat"})

    assert result["blocked"] is False
    assert captured.get("max_retries") == 1
    assert captured.get("base_url") == "https://dashscope.aliyuncs.com/compatible-mode/v1"
    timeout = captured.get("timeout")
    assert isinstance(timeout, httpx.Timeout)
    assert timeout.read == 15
    assert timeout.connect == 5
