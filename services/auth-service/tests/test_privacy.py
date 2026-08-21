"""隐私中心测试（三期 L）

覆盖：模型往返（content JSONB / sla_deadline）、隐私政策公开读、个人信息查看
（doctor-only）、请求提交校验（类型/字段/确认）、本人查询隔离与分页、管理端
列表（JOIN 医生名 / SLA 高亮 / 过滤）、handle 执行语义（更正/数据包/去标识化/
终态拦截）、审计留痕。

不依赖真实 Redis/PostgreSQL/OSS：DB 用 SQLite（BigInteger/JSONB 编译垫片）。
"""
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
from sqlalchemy import BigInteger, create_engine, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.ext.compiler import compiles
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from shared.common.auth import create_token
from shared.common.db_session import get_db
from shared.models.base import Base
from shared.models.doctor_profile import DoctorProfile
from shared.models.privacy import PrivacyRequest
from shared.models.user import User

import app.api.privacy as privacy_api
from app.main import app


@compiles(BigInteger, "sqlite")
def _compile_bigint_for_sqlite(type_, compiler, **kw):
    return "INTEGER"


@compiles(JSONB, "sqlite")
def _compile_jsonb_for_sqlite(type_, compiler, **kw):
    return "JSON"


engine = create_engine(
    "sqlite://",
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)
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
def audit_mock(monkeypatch):
    """每用例重建 users + privacy_requests + doctor_profiles 表；审计打桩。

    doctor_profiles 已随 Task 2 加入 tables 列表（否则 without_profile 用例
    在无表/残留数据下不稳定）。doctor_certifications/conversations 仍按需在
    用例内建表（Task 4 DDL）。
    """
    tables = [User.__table__, PrivacyRequest.__table__, DoctorProfile.__table__]
    Base.metadata.drop_all(engine, tables=tables)
    Base.metadata.create_all(engine, tables=tables)
    db = TestSession()
    db.add_all([
        User(id=1, username="doc01", full_name="张医生", phone="13800000001",
             role="doctor", status="active"),
        User(id=2, username="admin", full_name="管理员", phone="13800000000",
             role="admin", status="active"),
        User(id=3, username="rep01", full_name="李代表", phone="13800000002",
             role="rep", status="active"),
    ])
    db.commit()
    db.close()

    monkeypatch.setitem(app.dependency_overrides, get_db, _override_db)
    audit_mock = AsyncMock(return_value=None)
    monkeypatch.setattr(privacy_api, "write_audit_log", audit_mock)
    yield audit_mock


# ---------- Task 1：模型往返 ----------

def test_privacy_request_model_roundtrip():
    db = TestSession()
    req = PrivacyRequest(
        doctor_id=1,
        request_type="correct",
        status="pending",
        content={"detail": "改名", "fields": {"full_name": "张三丰"}},
        sla_deadline=datetime.utcnow() + timedelta(days=30),
    )
    db.add(req)
    db.commit()
    db.refresh(req)

    loaded = db.query(PrivacyRequest).filter(PrivacyRequest.id == req.id).first()
    assert loaded.content["fields"]["full_name"] == "张三丰"
    d = loaded.to_dict()
    assert d["request_type"] == "correct"
    assert d["status"] == "pending"
    assert d["doctor_id"] == 1
    assert d["content"]["detail"] == "改名"
    assert d["sla_deadline"] is not None
    assert d["handled_by"] is None and d["handled_at"] is None


def test_user_model_has_deleted_at():
    db = TestSession()
    u = db.query(User).filter(User.id == 1).first()
    u.status = "deleted"
    u.deleted_at = datetime.utcnow()
    db.commit()
    loaded = db.query(User).filter(User.id == 1).first()
    assert loaded.status == "deleted"
    assert loaded.deleted_at is not None


# ---------- Task 2：隐私政策 + 个人信息 ----------

def test_privacy_policy_public_no_auth_required():
    r = client.get("/api/v1/doctors/privacy-policy")
    assert r.status_code == 200
    body = r.json()
    assert body["code"] == 0
    data = body["data"]
    assert data["version"] == "1.0"
    assert "注销" in data["content"]
    assert "30" in data["content"]


def test_personal_data_returns_user_and_profile():
    db = TestSession()
    db.add(DoctorProfile(doctor_id=1, interest_areas=["心血管"],
                         preferred_doc_type="rct", preferred_style="标准", closed=False))
    db.commit()
    db.close()

    r = client.get("/api/v1/doctors/personal-data", headers=_token(1, "doctor"))
    assert r.status_code == 200
    data = r.json()["data"]
    assert data["user"]["id"] == 1
    assert data["user"]["full_name"] == "张医生"
    assert "password_hash" not in data["user"]
    assert data["doctor_profile"]["interest_areas"] == ["心血管"]


def test_personal_data_without_profile_returns_null():
    r = client.get("/api/v1/doctors/personal-data", headers=_token(1, "doctor"))
    assert r.status_code == 200
    assert r.json()["data"]["doctor_profile"] is None


def test_personal_data_doctor_only_rep_403():
    r = client.get("/api/v1/doctors/personal-data", headers=_token(3, "rep"))
    assert r.status_code == 403

# ---------- Task 3：提交 + 本人查询 ----------

def test_create_privacy_request_success_with_30d_sla(audit_mock):
    r = client.post("/api/v1/privacy-requests", headers=_token(1, "doctor"),
                    json={"request_type": "export", "detail": "申请导出本人数据"})
    assert r.status_code == 200
    data = r.json()["data"]
    assert data["status"] == "pending"
    assert data["request_type"] == "export"
    deadline = datetime.fromisoformat(data["sla_deadline"])
    assert timedelta(days=29) < (deadline - datetime.utcnow()) <= timedelta(days=31)
    audit_mock.assert_awaited_once()
    assert audit_mock.await_args.kwargs["action"] == "privacy_request_create"


def test_create_invalid_type_400():
    r = client.post("/api/v1/privacy-requests", headers=_token(1, "doctor"),
                    json={"request_type": "destroy"})
    assert r.status_code == 400


def test_create_correct_requires_at_least_one_field():
    r = client.post("/api/v1/privacy-requests", headers=_token(1, "doctor"),
                    json={"request_type": "correct", "fields": {}})
    assert r.status_code == 400


def test_create_correct_phone_format_validated():
    r = client.post("/api/v1/privacy-requests", headers=_token(1, "doctor"),
                    json={"request_type": "correct", "fields": {"phone": "123"}})
    assert r.status_code == 400


def test_create_account_delete_requires_confirm():
    r = client.post("/api/v1/privacy-requests", headers=_token(1, "doctor"),
                    json={"request_type": "account_delete"})
    assert r.status_code == 400
    r2 = client.post("/api/v1/privacy-requests", headers=_token(1, "doctor"),
                     json={"request_type": "account_delete", "confirm": True})
    assert r2.status_code == 200


def test_create_doctor_only_rep_403():
    r = client.post("/api/v1/privacy-requests", headers=_token(3, "rep"),
                    json={"request_type": "view"})
    assert r.status_code == 403


def test_me_lists_only_own_requests_with_pagination():
    db = TestSession()
    for i in range(3):
        db.add(PrivacyRequest(
            doctor_id=1, request_type="view", status="done",
            content={}, sla_deadline=datetime.utcnow() + timedelta(days=30),
        ))
    db.add(PrivacyRequest(
        doctor_id=4, request_type="view", status="pending",
        content={}, sla_deadline=datetime.utcnow() + timedelta(days=30),
    ))
    db.commit()
    db.close()

    r = client.get("/api/v1/privacy-requests/me", headers=_token(1, "doctor"))
    assert r.status_code == 200
    data = r.json()["data"]
    assert data["total"] == 3
    assert all(item["doctor_id"] == 1 for item in data["items"])

    r2 = client.get("/api/v1/privacy-requests/me?status=done", headers=_token(1, "doctor"))
    assert r2.json()["data"]["total"] == 3
    r3 = client.get("/api/v1/privacy-requests/me?status=pending", headers=_token(1, "doctor"))
    assert r3.json()["data"]["total"] == 0
