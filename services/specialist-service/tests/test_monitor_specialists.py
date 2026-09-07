"""分身监控统计 + 冻结/解冻 + 官方分身（Task 4）"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", ".."))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

os.environ.setdefault("JWT_SECRET", "test-secret-not-a-default-value")
os.environ["AUTH_DEV_MODE"] = "true"

from datetime import datetime, timedelta
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
from shared.models.digital_specialist import Specialist
from shared.models.doctor import DoctorTwinSubscription
from shared.models.product import Product
from shared.models.user import User

import app.api.specialists as spec_api
from app.main import app
from app.models.conversation import Conversation
from app.models.feedback import ConversationFeedback


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
    tables = [User.__table__, Specialist.__table__, Conversation.__table__,
              ConversationFeedback.__table__, DoctorTwinSubscription.__table__,
              Product.__table__]
    Base.metadata.drop_all(engine, tables=tables)
    Base.metadata.create_all(engine, tables=tables)
    db = TestSession()
    db.add_all([
        User(id=1, username="rep01", full_name="张代表", phone="13800000001", role="rep", status="active"),
        User(id=2, username="admin", full_name="管理员", phone="13800000000", role="admin", status="active"),
        User(id=3, username="medical", full_name="医学部", phone="13800000003", role="medical", status="active"),
        Product(id=1, product_code="P001", product_name="心内科产品"),
    ])
    db.commit()
    db.close()
    monkeypatch.setitem(app.dependency_overrides, get_db, _override_db)
    audit_mock = AsyncMock(return_value=None)
    monkeypatch.setattr(spec_api, "write_audit_log", audit_mock)
    yield audit_mock


def _add_specialist(**kw):
    db = TestSession()
    defaults = dict(id=kw.pop("id", 1), name="心内科专员", product_id=1, status="active")
    defaults.update(kw)
    db.add(Specialist(**defaults))
    db.commit()
    db.close()
    return defaults["id"]


def test_freeze_requires_admin():
    _add_specialist(id=1)
    resp = client.post("/api/v1/specialists/1/freeze", headers=_token(1, "rep"))
    assert resp.status_code == 403


def test_freeze_sets_frozen(fresh_state):
    _add_specialist(id=1)
    resp = client.post("/api/v1/specialists/1/freeze", json={"reason": "24h 内拦截超阈值"},
                       headers=_token(2, "admin"))
    body = resp.json()
    assert body["code"] == 0
    assert body["data"]["status"] == "frozen"
    audit_mock = fresh_state
    audit_mock.assert_awaited_once()


def test_unfreeze_returns_active(fresh_state):
    _add_specialist(id=1, status="frozen")
    resp = client.post("/api/v1/specialists/1/unfreeze", json={}, headers=_token(2, "admin"))
    body = resp.json()
    assert body["code"] == 0
    assert body["data"]["status"] == "active"


def test_freeze_requires_reason():
    _add_specialist(id=1)
    resp = client.post("/api/v1/specialists/1/freeze", json={}, headers=_token(2, "admin"))
    assert resp.status_code == 400
    assert resp.json()["code"] == 1000


def test_create_official_specialist(fresh_state):
    resp = client.post("/api/v1/specialists", json={
        "name": "官方心内科专员", "product_id": 1, "is_official": True,
    }, headers=_token(3, "medical"))
    body = resp.json()
    assert body["code"] == 0
    assert body["data"]["is_official"] is True
    assert body["data"]["representative_id"] is None


def test_create_specialist_with_representative():
    resp = client.post("/api/v1/specialists", json={
        "name": "张代表分身", "product_id": 1, "representative_id": 1,
    }, headers=_token(2, "admin"))
    body = resp.json()
    assert body["code"] == 0
    assert body["data"]["representative_id"] == 1


def test_monitor_requires_admin():
    _add_specialist(id=1)
    resp = client.get("/api/v1/specialists/monitor", headers=_token(1, "rep"))
    assert resp.status_code == 403


def test_monitor_returns_stats(fresh_state):
    _add_specialist(id=1)
    now = datetime.utcnow()
    db = TestSession()
    db.add_all([
        Conversation(id=1, specialist_id=1, user_id=1, role="user", content="问题",
                     created_at=now),
        Conversation(id=2, specialist_id=1, user_id=1, role="assistant", content="回答",
                     latency_ms=500, created_at=now),
        Conversation(id=3, specialist_id=1, user_id=1, role="assistant", content="被拦截",
                     compliance_result={"blocked": True}, created_at=now),
        DoctorTwinSubscription(id=1, doctor_id=1, twin_id=1, status="subscribed",
                               consent_version="1.0", consent_at=now),
    ])
    db.commit()
    db.close()
    resp = client.get("/api/v1/specialists/monitor", headers=_token(2, "admin"))
    assert resp.status_code == 200, resp.text
    data = resp.json()["data"]
    assert data["total"] == 1
    item = data["items"][0]
    assert item["today_services"] == 1
    assert item["avg_latency_ms"] == 500
    assert item["service_doctors"] == 1
    assert item["added_count"] == 1
    assert "approval_rate" in item


def test_monitor_approval_rate_excludes_card_useful(fresh_state):
    """A-3（2026-09-07）：好评率只算对话反馈——卡片 useful 回流行（conversation_id=None、
    rating 恒 1，card_pushes.py 写入）此前全量计入，单向抬高好评率。"""
    _add_specialist(id=1)
    db = TestSession()
    db.add_all([
        # 对话反馈：1 好评 + 1 差评 → 真实好评率 0.5
        ConversationFeedback(id=1, conversation_id=1, user_id=1, specialist_id=1, rating=1),
        ConversationFeedback(id=2, conversation_id=2, user_id=1, specialist_id=1, rating=-1),
        # 卡片 useful 回流 ×2（rating 恒 1）：不计入——旧口径好评率被抬到 0.75
        ConversationFeedback(id=3, conversation_id=None, user_id=1, specialist_id=1, rating=1),
        ConversationFeedback(id=4, conversation_id=None, user_id=1, specialist_id=1, rating=1),
    ])
    db.commit()
    db.close()

    resp = client.get("/api/v1/specialists/monitor", headers=_token(2, "admin"))
    item = resp.json()["data"]["items"][0]
    assert item["approval_rate"] == 0.5


def test_monitor_filters_official(fresh_state):
    _add_specialist(id=1, name="官方专员", is_official=True)
    _add_specialist(id=2, name="普通专员", is_official=False)
    resp = client.get("/api/v1/specialists/monitor", params={"official": True},
                      headers=_token(2, "admin"))
    assert resp.status_code == 200, resp.text
    data = resp.json()["data"]
    assert data["total"] == 1
    assert data["items"][0]["name"] == "官方专员"
    assert data["items"][0]["is_official"] is True


def _add_conv(**kw):
    db = TestSession()
    defaults = dict(
        id=kw.pop("id", 1), user_id=1, specialist_id=1, session_id="s1",
        role="assistant", content="回答", citations=None,
        compliance_result={"blocked": True}, created_at=datetime.utcnow(),
    )
    defaults.update(kw)
    db.add(Conversation(**defaults))
    db.commit()
    db.close()
    return defaults["id"]


def test_review_queue_requires_admin():
    resp = client.get("/api/v1/specialists/review-queue", headers=_token(1, "rep"))
    assert resp.status_code == 403


def test_review_queue_marks_high_blockers():
    _add_specialist(id=1, name="心内科专员", representative_id=1)
    for i in range(6):
        _add_conv(id=i + 1, specialist_id=1)
    resp = client.get("/api/v1/specialists/review-queue", headers=_token(2, "admin"))
    body = resp.json()
    assert body["code"] == 0
    items = body["data"]["items"]
    assert any(item["specialist_id"] == 1 for item in items)
    assert items[0]["block_count"] >= 5
    assert items[0]["rep_name"] == "张代表"


def test_review_queue_below_threshold_excluded():
    _add_specialist(id=1)
    _add_conv(id=1, specialist_id=1)
    _add_conv(id=2, specialist_id=1)
    resp = client.get("/api/v1/specialists/review-queue", headers=_token(2, "admin"))
    body = resp.json()
    assert body["code"] == 0
    assert body["data"]["items"] == []


def test_review_queue_official_specialist_rep_name_null():
    _add_specialist(id=1, name="官方心内科专员", is_official=True)
    for i in range(5):
        _add_conv(id=i + 1, specialist_id=1)
    resp = client.get("/api/v1/specialists/review-queue", headers=_token(2, "admin"))
    body = resp.json()
    items = body["data"]["items"]
    assert items[0]["specialist_id"] == 1
    assert items[0]["rep_name"] is None
