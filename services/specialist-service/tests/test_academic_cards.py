"""学术卡片生成测试（Task 2）：rep 生成 + 合规预检 + 权限"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", ".."))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

os.environ.setdefault("JWT_SECRET", "test-secret-not-a-default-value")
os.environ["AUTH_DEV_MODE"] = "true"

from unittest.mock import AsyncMock, patch

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
from shared.models.academic import AcademicCard, CardPushRecord, Notification
from shared.models.digital_specialist import Specialist
from shared.models.product import Product
from shared.models.user import User

import app.api.academic_cards as ac_api
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
    tables = [User.__table__, Specialist.__table__, Product.__table__, AcademicCard.__table__,
              CardPushRecord.__table__, Notification.__table__]
    Base.metadata.drop_all(engine, tables=tables)
    Base.metadata.create_all(engine, tables=tables)
    db = TestSession()
    db.add_all([
        User(id=1, username="rep01", full_name="张代表", phone="13800000001", role="rep", status="active"),
        User(id=2, username="doctor1", full_name="王医生", phone="13800000002", role="doctor", status="active"),
        User(id=3, username="admin", full_name="管理员", phone="13800000000", role="admin", status="active"),
    ])
    db.commit()
    db.close()
    monkeypatch.setitem(app.dependency_overrides, get_db, _override_db)
    # 审计打桩：本测试不真调审计服务网络（write_audit_log fail-silent 但会发 httpx 请求）
    monkeypatch.setattr(ac_api, "write_audit_log", AsyncMock(return_value=None))
    yield


def test_create_card_requires_rep():
    resp = client.post("/api/v1/academic-cards", json={"title": "高血压指南", "topic": "高血压"},
                       headers=_token(3, "admin"))
    assert resp.status_code == 403
    assert resp.json()["code"] == 3000


def test_create_card_ai_generate_and_pass(fresh_state, monkeypatch):
    fake_card = {
        "conclusion": "高血压患者应限盐。",
        "key_points": ["限盐≤5g/日", "定期监测"],
        "summary": "一句话：控盐降压。",
        "citations": [{"doc_name": "高血压防治指南", "version": "2024版", "section": "生活方式干预"}],
    }
    monkeypatch.setattr(ac_api, "_generate_card_content", AsyncMock(return_value=fake_card))
    monkeypatch.setattr(ac_api, "check_compliance", AsyncMock(return_value={"blocked": False}))

    resp = client.post("/api/v1/academic-cards", json={"title": "高血压指南", "topic": "高血压"},
                       headers=_token(1, "rep"))
    body = resp.json()
    assert body["code"] == 0
    data = body["data"]
    assert data["title"] == "高血压指南"
    assert data["is_ai_generated"] is True
    assert data["compliance_status"] == "passed"
    assert data["content"]["conclusion"] == "高血压患者应限盐。"


def test_create_card_blocked_fails_closed(fresh_state, monkeypatch):
    fake_card = {
        "conclusion": "保证治好。",
        "key_points": [], "summary": "x",
        "citations": [],
    }
    monkeypatch.setattr(ac_api, "_generate_card_content", AsyncMock(return_value=fake_card))
    monkeypatch.setattr(ac_api, "check_compliance", AsyncMock(return_value={"blocked": True, "rule_code": "R001"}))

    resp = client.post("/api/v1/academic-cards", json={"title": "违规卡", "topic": "疗效"},
                       headers=_token(1, "rep"))
    assert resp.status_code == 400
    assert resp.json()["code"] == 1000
    assert "合规" in resp.json()["message"]


def test_list_my_cards():
    db = TestSession()
    db.add(AcademicCard(id=1, representative_id=1, title="卡1", content={"conclusion": "x"}, is_ai_generated=True))
    db.add(AcademicCard(id=2, representative_id=99, title="别人的卡", content={"conclusion": "y"}, is_ai_generated=True))
    db.commit()
    db.close()

    resp = client.get("/api/v1/academic-cards", headers=_token(1, "rep"))
    body = resp.json()
    assert body["code"] == 0
    assert body["data"]["total"] == 1
    assert body["data"]["items"][0]["title"] == "卡1"
