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
from shared.models.practice import PracticeSession
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
    tables = [User.__table__, SkillPackage.__table__, PracticeSession.__table__]
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
