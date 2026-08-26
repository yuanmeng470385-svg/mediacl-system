"""培训材料端点测试（Task 2）：创建/列表/详情/更新/软删/权限边界"""
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
from sqlalchemy.ext.compiler import compiles
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from shared.common.auth import create_token
from shared.common.db_session import get_db
from shared.models.base import Base
from shared.models.training_exam import ExamQuestion, ExamRecord, TrainingMaterial
from shared.models.user import User

import app.api.training_materials as tm_api
from app.main import app


@compiles(BigInteger, "sqlite")
def _compile_bigint_for_sqlite(type_, compiler, **kw):
    return "INTEGER"


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
    tables = [User.__table__, TrainingMaterial.__table__]
    Base.metadata.drop_all(engine, tables=tables)
    Base.metadata.create_all(engine, tables=tables)
    db = TestSession()
    db.add_all([
        User(id=1, username="rep01", full_name="张代表", phone="13800000001", role="rep", status="active"),
        User(id=2, username="admin", full_name="管理员", phone="13800000000", role="admin", status="active"),
        User(id=3, username="med", full_name="医学部", phone="13800000003", role="medical", status="active"),
    ])
    db.commit()
    db.close()

    monkeypatch.setitem(app.dependency_overrides, get_db, _override_db)
    audit_mock = AsyncMock(return_value=None)
    monkeypatch.setattr(tm_api, "write_audit_log", audit_mock)
    yield audit_mock


def test_create_requires_admin_role():
    resp = client.post("/api/v1/training-materials", json={
        "title": "办法要点", "material_type": "regulation", "content": "正文",
    }, headers=_token(1, "rep"))
    assert resp.status_code == 403
    assert resp.json()["code"] == 3000


def test_create_material(fresh_state):
    resp = client.post("/api/v1/training-materials", json={
        "title": "医药代表管理办法要点", "material_type": "regulation", "content": "二十二项禁止行为……",
    }, headers=_token(2, "admin"))
    body = resp.json()
    assert body["code"] == 0
    data = body["data"]
    assert data["title"] == "医药代表管理办法要点"
    assert data["status"] == "active"
    assert data["material_type"] == "regulation"
    audit_mock = fresh_state
    audit_mock.assert_awaited_once()


def test_create_validates_required_fields():
    resp = client.post("/api/v1/training-materials", json={"title": ""}, headers=_token(2, "admin"))
    assert resp.status_code == 400
    assert resp.json()["code"] == 1000


def test_list_returns_materials():
    db = TestSession()
    db.add(TrainingMaterial(id=1, title="办法要点", material_type="regulation", content="x", created_by=2))
    db.add(TrainingMaterial(id=2, title="内部政策", material_type="internal", content="y", created_by=2, status="archived"))
    db.commit()
    db.close()

    resp = client.get("/api/v1/training-materials", headers=_token(1, "rep"))
    body = resp.json()
    assert body["code"] == 0
    assert body["data"]["total"] == 1  # archived 不展示
    assert body["data"]["items"][0]["title"] == "办法要点"


def test_get_detail():
    db = TestSession()
    db.add(TrainingMaterial(id=1, title="办法要点", material_type="regulation", content="正文", created_by=2))
    db.commit()
    db.close()

    resp = client.get("/api/v1/training-materials/1", headers=_token(3, "medical"))
    body = resp.json()
    assert body["code"] == 0
    assert body["data"]["content"] == "正文"


def test_update_material(fresh_state):
    db = TestSession()
    db.add(TrainingMaterial(id=1, title="旧标题", material_type="regulation", content="旧", created_by=2))
    db.commit()
    db.close()

    resp = client.put("/api/v1/training-materials/1",
                      json={"title": "新标题", "content": "新", "material_type": "regulation"},
                      headers=_token(2, "admin"))
    body = resp.json()
    assert body["code"] == 0
    assert body["data"]["title"] == "新标题"
    audit_mock = fresh_state
    audit_mock.assert_awaited_once()


def test_delete_archives(fresh_state):
    db = TestSession()
    db.add(TrainingMaterial(id=1, title="办法要点", material_type="regulation", content="x", created_by=2))
    db.commit()
    db.close()

    resp = client.delete("/api/v1/training-materials/1", headers=_token(2, "admin"))
    body = resp.json()
    assert body["code"] == 0
    assert body["data"]["status"] == "archived"
    audit_mock = fresh_state
    audit_mock.assert_awaited_once()


def test_missing_row_404():
    resp = client.put("/api/v1/training-materials/999", json={"title": "x"}, headers=_token(2, "admin"))
    assert resp.status_code == 404
    assert resp.json()["code"] == 4000
