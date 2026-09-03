"""卡片推送/接收/追踪/反馈测试（Task 3）"""
import os
import sys
from datetime import datetime

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
from shared.models.academic import AcademicCard, CardPushRecord, Notification
from shared.models.digital_specialist import Specialist
from shared.models.product import Product
from shared.models.user import User

from shared.models.doctor import DoctorTwinSubscription
from shared.models.doctor_profile import DoctorProfile

import app.api.academic_cards as ac_api
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
    tables = [User.__table__, Specialist.__table__, Product.__table__, AcademicCard.__table__,
              CardPushRecord.__table__, Notification.__table__, DoctorTwinSubscription.__table__,
              Conversation.__table__, ConversationFeedback.__table__, DoctorProfile.__table__]
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
    monkeypatch.setattr(ac_api, "write_audit_log", AsyncMock(return_value=None))
    yield


def test_push_requires_rep():
    resp = client.post("/api/v1/academic-cards/1/push", json={"doctor_ids": [2]}, headers=_token(3, "admin"))
    assert resp.status_code == 403


def test_push_creates_records(fresh_state):
    db = TestSession()
    db.add(AcademicCard(id=1, representative_id=1, title="卡", content={"conclusion": "x"}, is_ai_generated=True))
    db.add(DoctorTwinSubscription(id=1, doctor_id=2, twin_id=1, status="subscribed",
                                  consent_version="1.0", consent_at=datetime.utcnow()))
    db.add(Specialist(id=1, name="分身", product_id=1, status="active", representative_id=1))
    db.commit()
    db.close()

    resp = client.post("/api/v1/academic-cards/1/push", json={"doctor_ids": [2]}, headers=_token(1, "rep"))
    body = resp.json()
    assert body["code"] == 0
    assert body["data"]["pushed"] == 1
    assert body["data"]["skipped"] == 0

    db = TestSession()
    rec = db.query(CardPushRecord).filter_by(card_id=1, doctor_id=2).first()
    assert rec is not None
    assert rec.read_status == "unread"
    assert rec.specialist_id == 1
    db.close()


def test_push_only_subscribed_doctors(fresh_state):
    # doctor 3 未订阅该代表分身 → skipped
    db = TestSession()
    db.add(AcademicCard(id=1, representative_id=1, title="卡", content={"conclusion": "x"}, is_ai_generated=True))
    db.add(Specialist(id=1, name="分身", product_id=1, status="active", representative_id=1))
    db.add(DoctorTwinSubscription(id=1, doctor_id=2, twin_id=1, status="subscribed",
                                  consent_version="1.0", consent_at=datetime.utcnow()))
    db.commit()
    db.close()
    # doctor 3 未建订阅

    resp = client.post("/api/v1/academic-cards/1/push", json={"doctor_ids": [2, 3]}, headers=_token(1, "rep"))
    body = resp.json()
    assert body["code"] == 0
    assert body["data"]["pushed"] == 1
    assert body["data"]["skipped"] == 1


def test_push_records_matched_interest_by_doctor(monkeypatch, fresh_state):
    from app.core import preference_ranking

    class FakeProf:
        def __init__(self, areas):
            self.interest_areas = areas
            self.preferred_doc_type = None
            self.preferred_style = None
            self.closed = False

    # doctor 2 兴趣含"肿瘤"、doctor 4 兴趣为"心血管" → 各自 matched_interest 正确
    monkeypatch.setattr(
        preference_ranking, "get_profiles_batch",
        lambda db, ids: {2: FakeProf(["肿瘤"]), 4: FakeProf(["心血管"])},
    )

    db = TestSession()
    db.add(User(id=4, username="doctor2", full_name="李医生", phone="13800000004", role="doctor", status="active"))
    db.add(AcademicCard(id=1, representative_id=1, title="肿瘤免疫治疗新进展",
                        content={"conclusion": "x"}, is_ai_generated=True))
    db.add(Specialist(id=1, name="分身", product_id=1, status="active", representative_id=1))
    db.add(DoctorTwinSubscription(id=1, doctor_id=2, twin_id=1, status="subscribed",
                                  consent_version="1.0", consent_at=datetime.utcnow()))
    db.add(DoctorTwinSubscription(id=2, doctor_id=4, twin_id=1, status="subscribed",
                                  consent_version="1.0", consent_at=datetime.utcnow()))
    db.commit()
    db.close()

    resp = client.post("/api/v1/academic-cards/1/push", json={"doctor_ids": [2, 4]},
                       headers=_token(1, "rep"))
    body = resp.json()
    assert body["code"] == 0
    assert body["data"]["pushed"] == 2
    assert body["data"]["skipped"] == 0

    db = TestSession()
    push = db.query(CardPushRecord).filter_by(card_id=1).all()
    by_doc = {r.doctor_id: r.matched_interest for r in push}
    assert by_doc[2] is True
    assert by_doc[4] is False
    db.close()


def test_doctor_inbox_lists_pushes():
    db = TestSession()
    db.add(AcademicCard(id=1, representative_id=1, title="高血压指南", content={"conclusion": "控盐"},
                        is_ai_generated=True))
    db.add(CardPushRecord(id=1, representative_id=1, card_id=1, doctor_id=2, read_status="unread"))
    db.commit()
    db.close()

    resp = client.get("/api/v1/card-pushes", headers=_token(2, "doctor"))
    body = resp.json()
    assert body["code"] == 0
    assert body["data"]["total"] == 1
    assert body["data"]["items"][0]["card"]["title"] == "高血压指南"


def test_track_read(fresh_state):
    db = TestSession()
    db.add(CardPushRecord(id=1, representative_id=1, card_id=1, doctor_id=2, read_status="unread"))
    db.commit()
    db.close()

    resp = client.post("/api/v1/card-pushes/1/track", json={"read_status": "read", "seconds": 42},
                       headers=_token(2, "doctor"))
    body = resp.json()
    assert body["code"] == 0
    assert body["data"]["read_status"] == "read"
    assert body["data"]["tracked_seconds"] == 42


def test_feedback_useful_notifies_rep(fresh_state):
    db = TestSession()
    db.add(CardPushRecord(id=1, representative_id=1, card_id=1, doctor_id=2,
                          specialist_id=1, read_status="read"))
    db.commit()
    db.close()

    resp = client.post("/api/v1/card-pushes/1/feedback", json={"feedback": "useful"},
                       headers=_token(2, "doctor"))
    body = resp.json()
    assert body["code"] == 0
    assert body["data"]["feedback"] == "useful"
    # 通知回流给代表
    db = TestSession()
    n = db.query(Notification).filter_by(user_id=1, type="card_feedback").first()
    assert n is not None
    # 有用反馈：累加分身好评计数（写 conversation_feedback rating=1，同步管理后台统计）
    fb = db.query(ConversationFeedback).filter_by(specialist_id=1, rating=1).first()
    assert fb is not None
    assert fb.user_id == 2
    assert fb.comment == "学术卡片有用"
    db.close()


def test_feedback_useful_duplicate_not_duplicated(fresh_state):
    db = TestSession()
    db.add(CardPushRecord(id=1, representative_id=1, card_id=1, doctor_id=2,
                          specialist_id=1, read_status="read"))
    db.commit()
    db.close()

    for _ in range(2):
        resp = client.post("/api/v1/card-pushes/1/feedback", json={"feedback": "useful"},
                           headers=_token(2, "doctor"))
        assert resp.json()["code"] == 0

    db = TestSession()
    rows = db.query(ConversationFeedback).filter_by(specialist_id=1, rating=1).all()
    assert len(rows) == 1
    db.close()


def test_doctor_inbox_rejects_rep():
    resp = client.get("/api/v1/card-pushes", headers=_token(1, "rep"))
    assert resp.status_code == 403


# ==================== M-4（2026-08-24 审查修复）：反馈唯一性（防评分注水） ====================

def _add_conv(cid=10, uid=2, sid=1):
    db = TestSession()
    db.add(Conversation(id=cid, user_id=uid, specialist_id=sid, session_id=f"s-{cid}",
                        role="assistant", content="回答"))
    db.commit()
    db.close()


def test_conversation_feedback_upsert_single_row():
    """同一用户对同一对话多次反馈 → 仅一行，rating 覆盖（此前每次 POST 插新行可注水 approval_rate）"""
    _add_conv()

    r1 = client.post("/api/v1/conversations/10/feedback", json={"rating": 1, "comment": "好"},
                     headers=_token(2, "doctor"))
    r2 = client.post("/api/v1/conversations/10/feedback", json={"rating": -1, "comment": "改主意"},
                     headers=_token(2, "doctor"))
    assert r1.json()["code"] == 0 and r2.json()["code"] == 0

    db = TestSession()
    rows = db.query(ConversationFeedback).filter_by(conversation_id=10, user_id=2).all()
    assert len(rows) == 1
    assert rows[0].rating == -1
    assert rows[0].comment == "改主意"
    db.close()


def test_card_feedback_useful_useless_useful_no_inflation():
    """useful→useless→useful 反复切换 → 卡片好评仍只一条（此前 was_useful 复位后重复插行）"""
    db = TestSession()
    db.add(CardPushRecord(id=1, representative_id=1, card_id=1, doctor_id=2,
                          specialist_id=1, read_status="read"))
    db.commit()
    db.close()

    for fb in ("useful", "useless", "useful", "useless", "useful"):
        resp = client.post("/api/v1/card-pushes/1/feedback", json={"feedback": fb},
                           headers=_token(2, "doctor"))
        assert resp.json()["code"] == 0

    db = TestSession()
    rows = db.query(ConversationFeedback).filter_by(
        specialist_id=1, rating=1, conversation_id=None).all()
    assert len(rows) == 1
    db.close()


# ==================== 通知已读（2026-09-03 业务审查批：is_read 此前无写入点） ====================

def _add_notification(nid=1, uid=1, is_read=False, ntype="briefing_ready"):
    db = TestSession()
    db.add(Notification(id=nid, user_id=uid, type=ntype, title="你的夜间简报已生成",
                        content="查看医生提问汇总", link="/briefings", is_read=is_read))
    db.commit()
    db.close()


def test_notifications_unread_filter_and_count(fresh_state):
    _add_notification(nid=1, uid=1, is_read=False)
    _add_notification(nid=2, uid=1, is_read=True)
    _add_notification(nid=3, uid=2, is_read=False)  # 他人通知不可见

    resp = client.get("/api/v1/card-pushes/notifications", headers=_token(1, "rep"))
    body = resp.json()
    assert body["code"] == 0
    assert body["data"]["total"] == 2

    resp = client.get("/api/v1/card-pushes/notifications?unread_only=true", headers=_token(1, "rep"))
    assert resp.json()["data"]["total"] == 1
    assert resp.json()["data"]["items"][0]["id"] == 1

    resp = client.get("/api/v1/card-pushes/notifications/unread-count", headers=_token(1, "rep"))
    assert resp.json()["data"]["unread"] == 1


def test_mark_read_single_and_ownership(fresh_state):
    _add_notification(nid=1, uid=1)
    # 他人通知 → 4001，不可标记
    resp = client.post("/api/v1/card-pushes/notifications/read", json={"notification_id": 1},
                       headers=_token(2, "rep"))
    assert resp.json()["code"] == 4001
    # 本人标记 → is_read=True
    resp = client.post("/api/v1/card-pushes/notifications/read", json={"notification_id": 1},
                       headers=_token(1, "rep"))
    assert resp.json()["code"] == 0
    assert resp.json()["data"]["is_read"] is True
    # 重复标记幂等
    resp = client.post("/api/v1/card-pushes/notifications/read", json={"notification_id": 1},
                       headers=_token(1, "rep"))
    assert resp.json()["code"] == 0


def test_mark_read_all_and_validation(fresh_state):
    _add_notification(nid=1, uid=1)
    _add_notification(nid=2, uid=1)
    _add_notification(nid=3, uid=2)

    resp = client.post("/api/v1/card-pushes/notifications/read", json={"all": True},
                       headers=_token(1, "rep"))
    assert resp.json()["code"] == 0
    assert resp.json()["data"]["marked"] == 2
    # 只清本人的，他人未动
    resp = client.get("/api/v1/card-pushes/notifications/unread-count", headers=_token(2, "rep"))
    assert resp.json()["data"]["unread"] == 1

    # 既无 id 又无 all → 参数错
    resp = client.post("/api/v1/card-pushes/notifications/read", json={},
                       headers=_token(1, "rep"))
    assert resp.json()["code"] == 1000


# ==================== 推送目标清单（2026-09-03 业务审查批：替代手输数字 doctor_id） ====================

def test_push_targets_lists_subscribed_doctors(fresh_state):
    db = TestSession()
    db.add(Specialist(id=1, name="分身A", product_id=1, status="active", representative_id=1))
    db.add(Specialist(id=2, name="分身B", product_id=1, status="active", representative_id=1))
    db.add(Specialist(id=3, name="他人分身", product_id=1, status="active", representative_id=9))
    db.add(DoctorTwinSubscription(doctor_id=2, twin_id=1, status="subscribed",
                                  consent_version="1.0", consent_at=datetime.utcnow()))
    db.add(DoctorTwinSubscription(doctor_id=2, twin_id=2, status="subscribed",
                                  consent_version="1.0", consent_at=datetime.utcnow()))
    db.add(DoctorTwinSubscription(doctor_id=3, twin_id=1, status="blocked",
                                  consent_version="1.0", consent_at=datetime.utcnow()))
    db.add(DoctorTwinSubscription(doctor_id=4, twin_id=3, status="subscribed",
                                  consent_version="1.0", consent_at=datetime.utcnow()))  # 他人分身的订阅者
    db.commit()
    db.close()

    resp = client.get("/api/v1/academic-cards/push-targets", headers=_token(1, "rep"))
    body = resp.json()
    assert body["code"] == 0
    items = body["data"]["items"]
    # 只含本人分身的 subscribed 订阅者；blocked / 他人分身订阅者排除
    assert body["data"]["total"] == 1
    assert items[0]["doctor_id"] == 2
    assert items[0]["doctor_name"] == "王医生"  # fixture 里的用户名
    assert sorted(items[0]["twin_names"]) == ["分身A", "分身B"]
    assert items[0]["subscribed_at"]


def test_push_targets_requires_rep():
    resp = client.get("/api/v1/academic-cards/push-targets", headers=_token(2, "doctor"))
    assert resp.status_code == 403
