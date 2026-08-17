"""医生端医学问答端点 /api/v1/medical/qa 测试

打桩模式同 test_answer_generator_phases.py：monkeypatch app.api.medical 模块内的
check_compliance / write_audit_log / _retrieve / _qwen_json；get_current_user / get_db
经 dependency_overrides 注入假值（端点不落库、不起真实数据库）。
"""
import pytest
from fastapi.testclient import TestClient

from app.main import app
from shared.common.auth import get_current_user
from shared.common.db_session import get_db


@pytest.fixture
def client():
    app.dependency_overrides[get_db] = lambda: None
    app.dependency_overrides[get_current_user] = lambda: {"id": 7, "role": "rep"}
    yield TestClient(app)
    app.dependency_overrides.pop(get_db, None)
    app.dependency_overrides.pop(get_current_user, None)


async def _check_pass(content, context=None, fast=False, service_name="specialist"):
    return {"blocked": False, "violations": []}


async def _audit(**kwargs):
    pass


def test_empty_question_param_error(client):
    resp = client.post("/api/v1/medical/qa", json={"question": "   "})
    assert resp.status_code == 400
    assert resp.json()["code"] == 1000


def test_question_too_long_param_error(client):
    resp = client.post("/api/v1/medical/qa", json={"question": "问" * 2001})
    assert resp.status_code == 400
    assert resp.json()["code"] == 1000


def test_question_blocked_returns_safe_answer_and_audit(monkeypatch, client):
    audit_calls = []

    async def _check_blocked(content, context=None, fast=False, service_name="specialist"):
        return {"blocked": True, "violations": [{"rule_code": "R001"}]}

    async def _recording_audit(**kwargs):
        audit_calls.append(kwargs)

    monkeypatch.setattr("app.api.medical.check_compliance", _check_blocked)
    monkeypatch.setattr("app.api.medical.write_audit_log", _recording_audit)

    resp = client.post("/api/v1/medical/qa", json={"question": "承诺疗效的问题"})
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert data["answer"] == "该问题涉及合规限制，无法回答。"
    assert data["blocked"] is True
    assert data["citations"] == []
    assert data["violations"] == [{"rule_code": "R001"}]
    # 预检被拦 → 只写 medical_qa_blocked 审计，不涉及 AI
    assert len(audit_calls) == 1
    assert audit_calls[0]["action"] == "medical_qa_blocked"
    assert audit_calls[0]["ai_involved"] is False


def test_qa_cites_only_retrieved_snippets(monkeypatch, client):
    audit_calls = []
    results = [
        {"title": "指南A", "url": "http://a", "doc_id": "d1", "content": "内容A"},
        {"title": "指南B", "url": "http://b", "doc_id": "d2", "content": "内容B"},
        {"title": "指南C", "url": "http://c", "doc_id": "d3", "content": "内容C"},
    ]

    async def _retrieve(query, top_k=5):
        return {"results": results, "source": "es", "empty": False}

    def _qwen_json(prompt):
        return {"answer": "依据 [0] 和 [2]", "cited": [0, 2]}

    async def _recording_audit(**kwargs):
        audit_calls.append(kwargs)

    monkeypatch.setattr("app.api.medical.check_compliance", _check_pass)
    monkeypatch.setattr("app.api.medical.write_audit_log", _recording_audit)
    monkeypatch.setattr("app.api.medical._retrieve", _retrieve)
    monkeypatch.setattr("app.api.medical._qwen_json", _qwen_json)

    resp = client.post("/api/v1/medical/qa", json={"question": "肺癌用药"})
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert data["answer"] == "依据 [0] 和 [2]"
    assert data["blocked"] is False
    # cited=[0,2] → 恰好 2 条且标题/文档号对应结果片段
    assert len(data["citations"]) == 2
    assert data["citations"][0]["title"] == "指南A"
    assert data["citations"][0]["doc_id"] == "d1"
    assert data["citations"][1]["title"] == "指南C"
    assert data["citations"][1]["doc_id"] == "d3"
    assert data["knowledge_empty"] is False
    assert len(audit_calls) == 1
    assert audit_calls[0]["action"] == "medical_qa"
    assert audit_calls[0]["ai_involved"] is True
    assert audit_calls[0]["ai_model"] == "qwen-max"


def test_generation_failure_returns_graceful_message(monkeypatch, client):
    async def _retrieve(query, top_k=5):
        return {"results": [], "source": None, "empty": True}

    def _qwen_json_boom(prompt):
        raise RuntimeError("模拟 qwen 生成失败")

    monkeypatch.setattr("app.api.medical.check_compliance", _check_pass)
    monkeypatch.setattr("app.api.medical.write_audit_log", _audit)
    monkeypatch.setattr("app.api.medical._retrieve", _retrieve)
    monkeypatch.setattr("app.api.medical._qwen_json", _qwen_json_boom)

    resp = client.post("/api/v1/medical/qa", json={"question": "正常问题"})
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert data["answer"] == "AI 生成失败，请稍后重试。"
    assert data["blocked"] is False
    assert data["citations"] == []


def test_empty_answer_treated_as_generation_failure(monkeypatch, client):
    """B5：合法 JSON 但 answer 为空 → _qwen_json 视为不可用 → 走生成失败分支（不 500）。

    复现历史 bug 类（百炼空答案 908af39）：空答案不得以 blocked=False 透出给医生。
    """
    class FakeQwen:
        def chat(self, messages, model=None, temperature=0.1, max_tokens=2000):
            return {"content": '{"answer": "", "cited": []}', "usage": {}}

    async def _retrieve(query, top_k=5):
        return {"results": [], "source": None, "empty": True}

    # 不 monkeypatch _qwen_json —— 走真实逻辑（QwenClient 换假），证明空答案守卫生效
    monkeypatch.setattr("app.api.medical.QwenClient", lambda: FakeQwen())
    monkeypatch.setattr("app.api.medical.check_compliance", _check_pass)
    monkeypatch.setattr("app.api.medical.write_audit_log", _audit)
    monkeypatch.setattr("app.api.medical._retrieve", _retrieve)

    resp = client.post("/api/v1/medical/qa", json={"question": "正常问题"})
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert data["answer"] == "AI 生成失败，请稍后重试。"
    assert data["blocked"] is False
    assert data["citations"] == []


def test_answer_blocked_masked_and_audited(monkeypatch, client):
    audit_calls = []
    results = [{"title": "指南A", "url": "http://a", "doc_id": "d1", "content": "内容A"}]

    async def _check(content, context=None, fast=False, service_name="specialist"):
        if context and context.get("type") == "ai_output":
            return {"blocked": True, "violations": [{"rule_code": "R003"}]}
        return {"blocked": False, "violations": []}

    async def _retrieve(query, top_k=5):
        return {"results": results, "source": "es", "empty": False}

    def _qwen_json(prompt):
        return {"answer": "违禁答案", "cited": [0]}

    async def _recording_audit(**kwargs):
        audit_calls.append(kwargs)

    monkeypatch.setattr("app.api.medical.check_compliance", _check)
    monkeypatch.setattr("app.api.medical.write_audit_log", _recording_audit)
    monkeypatch.setattr("app.api.medical._retrieve", _retrieve)
    monkeypatch.setattr("app.api.medical._qwen_json", _qwen_json)

    resp = client.post("/api/v1/medical/qa", json={"question": "问题"})
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert data["answer"] == "该问题建议直接咨询医学顾问。"
    assert data["blocked"] is True
    assert data["citations"] == []
    assert data["violations"] == [{"rule_code": "R003"}]
    assert len(audit_calls) == 1
    assert audit_calls[0]["action"] == "medical_qa"
    assert audit_calls[0]["ai_involved"] is True
