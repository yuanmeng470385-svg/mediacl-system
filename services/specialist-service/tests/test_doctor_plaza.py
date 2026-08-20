"""医生侧广场测试（Task 4）：官方分身浏览/添加/知情同意"""
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
from shared.models.digital_specialist import Specialist
from shared.models.doctor import DoctorConsent, DoctorTwinSubscription
from shared.models.product import Product
from shared.models.user import User

import app.api.doctor_plaza as plaza_api
from app.main import app


@compiles(BigInteger, "sqlite")
def _compile_bigint_for_sqlite(type_, compiler, **kw):
    return "INTEGER"


@compiles(JSONB, "sqlite")
def _compile_jsonb_for_sqlite(type_, compiler, **kw):
    return "JSON"


engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
TestSession = sessionmaker(bind=engine, autocommit=False, autoflush=False)

TABLES = [
    User.__table__,
    Product.__table__,
    Specialist.__table__,
    DoctorTwinSubscription.__table__,
    DoctorConsent.__table__,
]


def _override_db():
    db = TestSession()
    try:
        yield db
    finally:
        db.close()


client = TestClient(app)


def _token(user_id: int, role: str = "doctor") -> dict:
    token = create_token(user_id=user_id, username=f"u{user_id}", role=role)
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture(autouse=True)
def fresh_state(monkeypatch):
    Base.metadata.drop_all(engine, tables=TABLES)
    Base.metadata.create_all(engine, tables=TABLES)

    db = TestSession()
    db.add_all([
        User(id=1, username="u1", full_name="李代表", phone="13800000001",
             role="rep", status="active"),
        User(id=2, username="u2", full_name="王医生", phone="13800000002",
             role="doctor", status="active"),
    ])
    db.commit()
    db.close()

    monkeypatch.setitem(app.dependency_overrides, get_db, _override_db)
    # 清除其它 FakeDb 测试文件（test_specialist_list_stats.py 等）遗留的
    # get_current_user 覆盖，否则 require_roles 的 get_current_user 依赖会拿到伪造的 role
    monkeypatch.delitem(app.dependency_overrides, get_current_user, raising=False)
    audit_mock = AsyncMock(return_value=None)
    monkeypatch.setattr(plaza_api, "write_audit_log", audit_mock)
    yield audit_mock


def _add_official(**kw):
    db = TestSession()
    defaults = dict(id=kw.pop("id", 1), name="官方心内科专员", product_id=1, status="active",
                    is_official=True, representative_id=None)
    defaults.update(kw)
    db.add(Specialist(**defaults))
    db.commit()
    db.close()
    return defaults["id"]


def test_plaza_requires_doctor():
    _add_official(id=1)
    resp = client.get("/api/v1/doctor-plaza", headers=_token(1, "rep"))
    assert resp.status_code == 403


def test_plaza_lists_official_only():
    _add_official(id=1)
    _add_official(id=2, is_official=False, representative_id=99)  # 个人分身
    resp = client.get("/api/v1/doctor-plaza", headers=_token(2, "doctor"))
    body = resp.json()
    assert body["code"] == 0
    assert body["data"]["total"] == 1
    assert body["data"]["items"][0]["is_official"] is True


def test_subscribe_writes_consent(fresh_state):
    _add_official(id=1)
    resp = client.post("/api/v1/doctor-plaza/1/subscribe", json={"consent": True},
                       headers=_token(2, "doctor"))
    body = resp.json()
    assert body["code"] == 0
    assert body["data"]["status"] == "subscribed"

    db = TestSession()
    consent = db.query(DoctorConsent).filter_by(doctor_id=2, twin_id=1).first()
    assert consent is not None
    assert consent.consent_type == "twin"
    db.close()


def test_subscribe_requires_consent():
    _add_official(id=1)
    resp = client.post("/api/v1/doctor-plaza/1/subscribe", json={"consent": False},
                       headers=_token(2, "doctor"))
    assert resp.status_code == 400
    assert resp.json()["code"] == 1000
