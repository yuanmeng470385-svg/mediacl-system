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
def fresh_state(monkeypatch):
    """每用例重建 users + privacy_requests 表；审计打桩。

    doctor_profiles/doctor_certifications/conversations 按需在用例内建表
    （Task 2/4 引入后再放进 tables 列表或用 DDL 建）。
    """
    tables = [User.__table__, PrivacyRequest.__table__]
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
