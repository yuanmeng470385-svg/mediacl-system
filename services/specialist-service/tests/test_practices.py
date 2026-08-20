"""陪练会话测试（Task 3）：创建/多轮对话/评分/历史"""
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

from shared.common.auth import create_token
from shared.common.db_session import get_db
from shared.models.base import Base
from shared.models.practice import ObjectionScript, PracticeSession
from shared.models.skill import SkillPackage
from shared.models.user import User

import app.api.practices as practices_api
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
    tables = [User.__table__, SkillPackage.__table__, PracticeSession.__table__, ObjectionScript.__table__]
    Base.metadata.drop_all(engine, tables=tables)
    Base.metadata.create_all(engine, tables=tables)
    db = TestSession()
    db.add_all([
        User(id=1, username="rep01", full_name="张代表", phone="13800000001", role="rep", status="active"),
        User(id=2, username="admin", full_name="管理员", phone="13800000000", role="admin", status="active"),
        User(id=3, username="medical", full_name="医学部", phone="13800000003", role="medical", status="active"),
    ])
    db.commit()
    db.close()
    monkeypatch.setitem(app.dependency_overrides, get_db, _override_db)
    audit_mock = AsyncMock(return_value=None)
    monkeypatch.setattr(practices_api, "write_audit_log", audit_mock)
    yield audit_mock


def test_create_session_requires_rep():
    resp = client.post("/api/v1/practices", json={"skill_id": 1, "scenario": "心内科推广"},
                       headers=_token(2, "admin"))
    assert resp.status_code == 403


def test_create_session(fresh_state):
    db = TestSession()
    db.add(SkillPackage(id=1, name="严谨学术风", creator_id=3, is_public=True,
                        audit_status="approved", skill_weights={"formal_level": "标准学术"}))
    db.commit()
    db.close()
    resp = client.post("/api/v1/practices", json={"skill_id": 1, "scenario": "心内科推广"},
                       headers=_token(1, "rep"))
    body = resp.json()
    assert body["code"] == 0
    assert body["data"]["status"] == "in_progress"
    assert body["data"]["scenario"] == "心内科推广"


def test_turn_ai_responds(fresh_state, monkeypatch):
    db = TestSession()
    db.add(SkillPackage(id=1, name="严谨学术风", creator_id=3, is_public=True,
                        audit_status="approved", skill_weights={"formal_level": "标准学术"}))
    db.add(PracticeSession(id=1, representative_id=1, skill_id=1, scenario="心内科推广",
                           status="in_progress", turn_count=0))
    db.commit()
    db.close()

    from app.services import qwen_client as qc
    monkeypatch.setattr(qc.QwenClient, "chat", lambda self, *a, **k: {
        "content": "医生：您好，请介绍下这款降压药的核心优势？", "usage": {},
    })
    monkeypatch.setattr(practices_api, "check_compliance", AsyncMock(return_value={"blocked": False}))

    resp = client.post("/api/v1/practices/1/turn", json={"message": "您好，这款药降压效果平稳"},
                       headers=_token(1, "rep"))
    body = resp.json()
    assert body["code"] == 0
    assert "医生" in body["data"]["ai_message"]
    assert body["data"]["turn_count"] == 1


def test_turn_blocked_fails_closed(fresh_state, monkeypatch):
    db = TestSession()
    db.add(PracticeSession(id=1, representative_id=1, skill_id=None, scenario="x",
                           status="in_progress", turn_count=0))
    db.commit()
    db.close()
    monkeypatch.setattr(practices_api, "check_compliance", AsyncMock(return_value={"blocked": True, "rule_code": "R001"}))
    resp = client.post("/api/v1/practices/1/turn", json={"message": "保证治好"},
                       headers=_token(1, "rep"))
    assert resp.status_code == 400
    assert resp.json()["code"] == 1000


def test_complete_scores(fresh_state):
    db = TestSession()
    db.add(PracticeSession(id=1, representative_id=1, skill_id=None, scenario="x",
                           status="in_progress", turn_count=3))
    db.commit()
    db.close()
    resp = client.post("/api/v1/practices/1/complete", json={}, headers=_token(1, "rep"))
    body = resp.json()
    assert body["code"] == 0
    assert body["data"]["status"] == "completed"
    assert body["data"]["scores"]["overall"] > 0
    # 4.5 后半段：逐句/逐轮反馈 per_turn 数组按轮数生成
    per_turn = body["data"]["scores"]["per_turn"]
    assert len(per_turn) == 3
    assert "evidence_accuracy" in per_turn[0]
    assert "objection_handling" in per_turn[0]
    assert "communication_logic" in per_turn[0]


# ============ 异议话术库（3.2(5)，终审修复 #3） ============

def _add_objection(**kw):
    db = TestSession()
    defaults = dict(
        id=kw.pop("id", 1), scenario_type="心内科", objection_content="医生异议：和竞品相比优势在哪？",
        review_status="pending", version="1.0", created_by=3,
    )
    defaults.update(kw)
    db.add(ObjectionScript(**defaults))
    db.commit()
    db.close()
    return defaults["id"]


def test_create_objection_script_requires_admin():
    resp = client.post("/api/v1/practices/objection-scripts", json={
        "scenario_type": "心内科", "objection_content": "医生异议：优势在哪？",
    }, headers=_token(1, "rep"))
    assert resp.status_code == 403
    assert resp.json()["code"] == 3000


def test_create_objection_script_sets_pending(fresh_state):
    resp = client.post("/api/v1/practices/objection-scripts", json={
        "scenario_type": "心内科", "objection_content": "医生异议：优势在哪？",
        "response_guidance": "用循证数据回应",
    }, headers=_token(3, "medical"))
    body = resp.json()
    assert body["code"] == 0
    assert body["data"]["review_status"] == "pending"
    assert body["data"]["objection_content"] == "医生异议：优势在哪？"
    assert body["data"]["response_guidance"] == "用循证数据回应"


def test_list_objection_scripts_filters_status(fresh_state):
    _add_objection(id=1, review_status="approved")
    _add_objection(id=2, review_status="pending")
    resp = client.get("/api/v1/practices/objection-scripts", params={"review_status": "approved"},
                      headers=_token(2, "admin"))
    body = resp.json()
    assert body["code"] == 0
    assert body["data"]["total"] == 1
    assert body["data"]["items"][0]["id"] == 1


def test_review_objection_script_approve(fresh_state):
    _add_objection(id=1)
    resp = client.post("/api/v1/practices/objection-scripts/1/review", json={"verdict": "approve"},
                       headers=_token(2, "admin"))
    body = resp.json()
    assert body["code"] == 0
    assert body["data"]["review_status"] == "approved"
    assert body["data"]["reviewed_by"] == 2


def test_review_objection_script_reject_requires_reason(fresh_state):
    _add_objection(id=1)
    resp = client.post("/api/v1/practices/objection-scripts/1/review", json={"verdict": "reject"},
                       headers=_token(2, "admin"))
    assert resp.status_code == 400
    assert resp.json()["code"] == 1000


def test_turn_injects_approved_objection(fresh_state, monkeypatch):
    db = TestSession()
    db.add(SkillPackage(id=1, name="严谨学术风", creator_id=3, is_public=True,
                        audit_status="approved", skill_weights={"formal_level": "标准学术"}))
    db.add(PracticeSession(id=1, representative_id=1, skill_id=1, scenario="心内科推广",
                           status="in_progress", turn_count=0))
    db.add(ObjectionScript(id=1, scenario_type="心内科", objection_content="医生异议：和竞品相比优势在哪？",
                           review_status="approved"))
    db.commit()
    db.close()

    captured = {}
    from app.services import qwen_client as qc

    def fake_chat(self, messages, **kwargs):
        captured["messages"] = messages
        return {"content": "医生：请介绍下这款药的优势。", "usage": {}}

    monkeypatch.setattr(qc.QwenClient, "chat", fake_chat)
    monkeypatch.setattr(practices_api, "check_compliance", AsyncMock(return_value={"blocked": False}))

    resp = client.post("/api/v1/practices/1/turn", json={"message": "您好，这款药降压平稳"},
                       headers=_token(1, "rep"))
    assert resp.json()["code"] == 0
    user_msg = captured["messages"][1]["content"]
    assert "医生异议：和竞品相比优势在哪？" in user_msg


def test_turn_no_objection_falls_back(fresh_state, monkeypatch):
    # 该场景无 approved 话术 → 不注入异议，自由生成（prompt 中无 objection 标记）
    db = TestSession()
    db.add(PracticeSession(id=1, representative_id=1, skill_id=None, scenario="肿瘤科推广",
                           status="in_progress", turn_count=0))
    db.add(ObjectionScript(id=1, scenario_type="心内科", objection_content="医生异议：优势在哪？",
                           review_status="approved"))
    db.commit()
    db.close()

    captured = {}
    from app.services import qwen_client as qc

    def fake_chat(self, messages, **kwargs):
        captured["messages"] = messages
        return {"content": "医生：请介绍下这款药。", "usage": {}}

    monkeypatch.setattr(qc.QwenClient, "chat", fake_chat)
    monkeypatch.setattr(practices_api, "check_compliance", AsyncMock(return_value={"blocked": False}))

    resp = client.post("/api/v1/practices/1/turn", json={"message": "您好"},
                       headers=_token(1, "rep"))
    assert resp.json()["code"] == 0
    user_msg = captured["messages"][1]["content"]
    assert "医生异议：优势在哪？" not in user_msg


# ============ 进步曲线（4.5 后半段，终审修复 #4） ============

def test_progress_aggregates_completed(fresh_state):
    db = TestSession()
    db.add(PracticeSession(id=1, representative_id=1, skill_id=None, scenario="x",
                           status="completed", turn_count=2,
                           scores={"overall": 0.7, "per_turn": []}))
    db.add(PracticeSession(id=2, representative_id=1, skill_id=None, scenario="y",
                           status="completed", turn_count=3,
                           scores={"overall": 0.8, "per_turn": []}))
    db.add(PracticeSession(id=3, representative_id=1, skill_id=None, scenario="z",
                           status="in_progress", turn_count=1, scores=None))
    db.commit()
    db.close()

    resp = client.get("/api/v1/practices/progress", headers=_token(1, "rep"))
    body = resp.json()
    assert body["code"] == 0
    data = body["data"]
    assert data["total_sessions"] == 2
    assert data["avg_overall"] == 0.75
    assert len(data["trend"]) == 2
    assert data["trend"][0]["session_id"] == 1
    assert data["trend"][0]["overall"] == 0.7
    assert data["trend"][1]["session_id"] == 2


def test_progress_empty(fresh_state):
    resp = client.get("/api/v1/practices/progress", headers=_token(1, "rep"))
    body = resp.json()
    assert body["code"] == 0
    assert body["data"]["total_sessions"] == 0
    assert body["data"]["avg_overall"] == 0.0
    assert body["data"]["trend"] == []
