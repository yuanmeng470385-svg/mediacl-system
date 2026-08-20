"""运营统计测试（Task 5）：医生活跃度/分身排行"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", ".."))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

os.environ.setdefault("JWT_SECRET", "test-secret-not-a-default-value")
os.environ["AUTH_DEV_MODE"] = "true"

from datetime import datetime, timedelta

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
from shared.models.digital_specialist import Specialist
from shared.models.doctor import DoctorTwinSubscription
from shared.models.user import User

import app.api.doctor_stats as ds_api  # noqa: F401  确保路由模块可导入
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
              DoctorTwinSubscription.__table__, ConversationFeedback.__table__]
    Base.metadata.drop_all(engine, tables=tables)
    Base.metadata.create_all(engine, tables=tables)
    db = TestSession()
    db.add_all([
        User(id=1, username="rep01", full_name="张代表", phone="13800000001", role="rep", status="active"),
        User(id=2, username="doctor1", full_name="王医生", phone="13800000002", role="doctor", status="active"),
        User(id=3, username="admin", full_name="管理员", phone="13800000000", role="admin", status="active"),
        User(id=4, username="doctor2", full_name="李医生", phone="13800000004", role="doctor", status="active"),
    ])
    db.commit()
    db.close()
    monkeypatch.setitem(app.dependency_overrides, get_db, _override_db)
    # 清除其它 FakeDb 测试文件（test_d_low_batch.py 等）遗留的 get_current_user 覆盖，
    # 否则 require_roles 依赖会拿到伪造 role（与 test_doctor_profiles.py 同款清理）。
    monkeypatch.delitem(app.dependency_overrides, get_current_user, raising=False)
    yield


def test_activity_requires_admin():
    resp = client.get("/api/v1/doctor-stats/activity", headers=_token(2, "doctor"))
    assert resp.status_code == 403


def test_activity_counts_daily_weekly_monthly():
    db = TestSession()
    now = datetime.utcnow()
    db.add(Conversation(id=1, user_id=2, specialist_id=None, session_id="s1", role="user",
                        content="x", created_at=now))
    db.add(Conversation(id=2, user_id=2, specialist_id=None, session_id="s2", role="user",
                        content="y", created_at=now - timedelta(days=3)))
    db.add(Conversation(id=3, user_id=4, specialist_id=None, session_id="s3", role="user",
                        content="z", created_at=now - timedelta(days=5)))
    db.commit()
    db.close()

    resp = client.get("/api/v1/doctor-stats/activity", headers=_token(3, "admin"))
    body = resp.json()
    assert body["code"] == 0
    assert body["data"]["dau"] == 1   # 今天活跃的 doctor 数
    assert body["data"]["wau"] == 2   # 近 7 天
    assert body["data"]["mau"] == 2   # 近 30 天（doctor1 有 2 条，doctor2 有 1 条）


def test_twin_ranking_top10():
    db = TestSession()
    db.add(Specialist(id=1, name="心内科专员", product_id=1, status="active"))
    db.add(DoctorTwinSubscription(id=1, doctor_id=2, twin_id=1, status="subscribed",
                                  consent_version="1.0", consent_at=datetime.utcnow()))
    db.add(ConversationFeedback(id=1, user_id=2, specialist_id=1, rating=1))
    db.commit()
    db.close()

    resp = client.get("/api/v1/doctor-stats/twin-ranking", headers=_token(3, "admin"))
    body = resp.json()
    assert body["code"] == 0
    assert body["data"]["items"][0]["twin_id"] == 1
    assert body["data"]["items"][0]["added_count"] == 1
