"""医生偏好引擎测试（Task 2）：学习/查询/修改/关闭/简报"""
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

from shared.common.auth import create_token, get_current_user
from shared.common.db_session import get_db
from shared.models.base import Base
from shared.models.doctor_profile import DoctorProfile
from shared.models.user import User

import app.api.doctor_profiles as dp_api
from app.main import app
from app.models.conversation import Conversation


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
    tables = [User.__table__, DoctorProfile.__table__, Conversation.__table__]
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
    # 清除其它 FakeDb 测试文件（test_specialist_list_stats.py 等）遗留的
    # get_current_user 覆盖，否则 require_roles 的 get_current_user 依赖会拿到伪造的 role
    # （与 test_twin_manage.py 同款清理）。
    monkeypatch.delitem(app.dependency_overrides, get_current_user, raising=False)
    audit_mock = AsyncMock(return_value=None)
    monkeypatch.setattr(dp_api, "write_audit_log", audit_mock)
    yield


def test_profile_requires_doctor():
    resp = client.get("/api/v1/doctor-profiles", headers=_token(1, "rep"))
    assert resp.status_code == 403
    assert resp.json()["code"] == 3000


def test_get_profile_empty(fresh_state):
    resp = client.get("/api/v1/doctor-profiles", headers=_token(2, "doctor"))
    body = resp.json()
    assert body["code"] == 0
    assert body["data"] is None  # 无画像返回 null


def test_update_profile(fresh_state):
    resp = client.put("/api/v1/doctor-profiles", json={
        "interest_areas": ["心血管", "内分泌"],
        "preferred_doc_type": "guideline",
        "preferred_style": "标准",
    }, headers=_token(2, "doctor"))
    body = resp.json()
    assert body["code"] == 0
    assert body["data"]["interest_areas"] == ["心血管", "内分泌"]
    assert body["data"]["closed"] is False


def test_close_personalization(fresh_state):
    resp = client.put("/api/v1/doctor-profiles", json={"closed": True}, headers=_token(2, "doctor"))
    body = resp.json()
    assert body["code"] == 0
    assert body["data"]["closed"] is True


def test_learn_from_history(fresh_state):
    db = TestSession()
    # citations 用真实形状（{title,url,doc_id}，无 doc_type）；doc_type 由问题文本关键词推断
    db.add(Conversation(id=1, user_id=2, specialist_id=None, session_id="medical_qa", role="user",
                        content="高血压指南推荐什么？",
                        citations=[{"title": "高血压防治指南", "url": "http://a", "doc_id": "d1"}]))
    db.add(Conversation(id=2, user_id=2, specialist_id=None, session_id="medical_qa", role="user",
                        content="糖尿病如何管理？",
                        citations=[{"title": "糖尿病诊疗指南", "url": "http://b", "doc_id": "d2"}]))
    db.commit()
    db.close()

    resp = client.post("/api/v1/doctor-profiles/learn", json={}, headers=_token(2, "doctor"))
    body = resp.json()
    assert body["code"] == 0
    data = body["data"]
    assert data["preferred_doc_type"] == "guideline"
    assert "心血管" in (data["interest_areas"] or [])


def test_briefing_requires_profile():
    resp = client.get("/api/v1/doctor-profiles/briefing", headers=_token(2, "doctor"))
    body = resp.json()
    assert body["code"] == 0
    # 无画像 → 返回空简报而非错误
    assert isinstance(body["data"]["items"], list)
