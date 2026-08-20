"""数据分类分级清单端点测试（Task 4）：三类静态数据资产 + 角色门禁"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", ".."))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

os.environ.setdefault("JWT_SECRET", "test-secret-not-a-default-value")
os.environ["AUTH_DEV_MODE"] = "true"

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import BigInteger, create_engine
from sqlalchemy.ext.compiler import compiles
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from shared.common.auth import create_token
from shared.common.db_session import get_db
from shared.models.base import Base
from shared.models.user import User

from app.main import app


@compiles(BigInteger, "sqlite")
def _compile_bigint_for_sqlite(type_, compiler, **kw):
    return "INTEGER"


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
    """require_roles 每次实时查库（S6），需在 SQLite 落 User 行并覆盖 get_db"""
    Base.metadata.drop_all(engine, tables=[User.__table__])
    Base.metadata.create_all(engine, tables=[User.__table__])
    db = TestSession()
    db.add_all([
        User(id=1, username="rep01", full_name="张代表", phone="13800000001", role="rep", status="active", region="华东"),
        User(id=2, username="admin", full_name="管理员", phone="13800000000", role="admin", status="active", region="总部"),
        User(id=3, username="compliance", full_name="合规部", phone="13800000003", role="compliance", status="active", region="总部"),
    ])
    db.commit()
    db.close()
    monkeypatch.setitem(app.dependency_overrides, get_db, _override_db)
    yield


def test_data_assets_requires_admin():
    resp = client.get("/api/v1/compliance/data-assets", headers=_token(1, "rep"))
    assert resp.status_code == 403
    assert resp.json()["code"] == 3000


def test_data_assets_returns_three_categories(fresh_state):
    resp = client.get("/api/v1/compliance/data-assets", headers=_token(2, "admin"))
    body = resp.json()
    assert body["code"] == 0
    cats = {c["category"] for c in body["data"]}
    assert {"个人信息", "业务数据", "合规留存数据"} <= cats
    personal = next(c for c in body["data"] if c["category"] == "个人信息")
    assert "users" in personal["tables"]
    assert "representative_qualifications" in personal["tables"]
    assert "doctor_certifications" in personal["tables"]
    assert personal["level"] == "敏感"
