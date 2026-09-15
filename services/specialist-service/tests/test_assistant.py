"""产品使用 AI 助手测试（2026-09-15）：角色定制功能地图注入 / 参数校验 / LLM 失败降级 / 审计留痕"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", ".."))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

os.environ.setdefault("JWT_SECRET", "test-secret-not-a-default-value")
os.environ["AUTH_DEV_MODE"] = "true"

from unittest.mock import AsyncMock

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import BigInteger, create_engine
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.ext.compiler import compiles
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from shared.common.auth import create_token, get_current_user
from shared.common.db_session import get_db
from shared.models.base import Base
from shared.models.user import User

import app.api.assistant as assistant_api
from app.main import app


@compiles(BigInteger, "sqlite")
def _compile_bigint_for_sqlite(type_, compiler, **kw):
    return "INTEGER"


@compiles(JSONB, "sqlite")
def _compile_jsonb_for_sqlite(type_, compiler, **kw):
    return "JSON"


engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
TestSession = sessionmaker(bind=engine, autocommit=False, autoflush=False)


def _override_db():
    db = TestSession()
    try:
        yield db
    finally:
        db.close()


client = TestClient(app)


def _token(user_id: int, role: str) -> dict:
    token = create_token(user_id=user_id, username=f"u{user_id}", role=role)
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture(autouse=True)
def fresh_state(monkeypatch):
    User.__table__.create(engine)
    db = TestSession()
    db.add(User(id=1, username="rep01", full_name="张代表", phone="13800000001", role="rep", status="active"))
    db.add(User(id=2, username="doctor01", full_name="王医生", phone="13800000002", role="doctor", status="active"))
    db.add(User(id=3, username="admin", full_name="管理员", phone="13800000000", role="admin", status="active"))
    db.commit()
    db.close()
    monkeypatch.setitem(app.dependency_overrides, get_db, _override_db)
    monkeypatch.delitem(app.dependency_overrides, get_current_user, raising=False)
    audit_mock = AsyncMock(return_value=None)
    monkeypatch.setattr(assistant_api, "write_audit_log", audit_mock)
    yield audit_mock
    User.__table__.drop(engine)


@pytest.fixture
def capture_messages(monkeypatch):
    """捕获发往 qwen 的 messages，同时返回固定回答"""
    seen = {}

    def _fake_chat(self, messages, **kwargs):
        seen["messages"] = messages
        seen["kwargs"] = kwargs
        return {"content": "在「我的 → 分身管理」里可以管理你的数字分身。", "usage": {}}

    import app.services.qwen_client as qc
    monkeypatch.setattr(qc.QwenClient, "chat", _fake_chat)
    return seen


def test_qa_happy_path(fresh_state, capture_messages):
    resp = client.post("/api/v1/assistant/qa", json={
        "question": "在哪里管理我的数字分身？",
    }, headers=_token(1, "rep"))
    body = resp.json()
    assert body["code"] == 0
    assert "分身管理" in body["data"]["answer"]
    assert body["data"]["disclaimer"]
    # 审计留痕：action + 角色 + 问题片段
    calls = [c.kwargs["action"] for c in fresh_state.await_args_list]
    assert "assistant_qa" in calls
    # 用户问题必须 <user_content> 定界（防注入口径）
    user_msg = capture_messages["messages"][1]["content"]
    assert user_msg.startswith("<user_content>") and user_msg.endswith("</user_content>")


@pytest.mark.parametrize("uid,role,marker", [
    (1, "rep", "代表端 App"),
    (2, "doctor", "医生端 App"),
    (3, "admin", "Web 管理后台"),
])
def test_qa_feature_map_per_role(fresh_state, capture_messages, uid, role, marker):
    resp = client.post("/api/v1/assistant/qa", json={"question": "怎么用"},
                       headers=_token(uid, role))
    assert resp.json()["code"] == 0
    system = capture_messages["messages"][0]["content"]
    assert marker in system
    # 定界与拒答约束是所有角色共用的底座
    assert "<user_content>" in system


@pytest.mark.parametrize("question", [None, "", "   ", "x" * 501])
def test_qa_question_validation(fresh_state, question):
    resp = client.post("/api/v1/assistant/qa", json={"question": question},
                       headers=_token(1, "rep"))
    assert resp.json()["code"] == 1000


def test_qa_llm_failure_returns_4003(fresh_state, monkeypatch):
    import app.services.qwen_client as qc
    monkeypatch.setattr(qc.QwenClient, "chat", lambda self, *a, **k: {"content": "", "usage": {}})
    resp = client.post("/api/v1/assistant/qa", json={"question": "在哪看简报"},
                       headers=_token(1, "rep"))
    assert resp.json()["code"] == 4003
