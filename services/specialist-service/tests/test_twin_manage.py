"""分身管理测试（Task 4）：风格设置/启停/风格测试生成"""
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
from shared.models.user import User

import app.api.specialists as spec_api
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
    tables = [User.__table__, Specialist.__table__]
    Base.metadata.drop_all(engine, tables=tables)
    Base.metadata.create_all(engine, tables=tables)
    db = TestSession()
    db.add_all([
        User(id=1, username="rep01", full_name="张代表", phone="13800000001", role="rep", status="active"),
        User(id=2, username="admin", full_name="管理员", phone="13800000000", role="admin", status="active"),
        User(id=3, username="medical", full_name="医学部", phone="13800000003", role="medical", status="active"),
        User(id=4, username="rep02", full_name="李代表", phone="13800000004", role="rep", status="active"),
    ])
    db.commit()
    db.close()
    monkeypatch.setitem(app.dependency_overrides, get_db, _override_db)
    # 清除其它 FakeDb 测试文件（test_specialist_list_stats.py 等）遗留的
    # get_current_user 覆盖，否则本文件 get_current_user 端点会拿到伪造的 role。
    monkeypatch.delitem(app.dependency_overrides, get_current_user, raising=False)
    audit_mock = AsyncMock(return_value=None)
    monkeypatch.setattr(spec_api, "write_audit_log", audit_mock)
    yield audit_mock


def _add_twin(**kw):
    db = TestSession()
    defaults = dict(id=kw.pop("id", 1), name="张代表分身", product_id=1, status="active",
                    representative_id=1, persona={})
    defaults.update(kw)
    db.add(Specialist(**defaults))
    db.commit()
    db.close()
    return defaults["id"]


def test_style_requires_owner():
    _add_twin(id=1, representative_id=1)
    # 非代表本人（rep02，无该分身归属）→ 403
    resp = client.put("/api/v1/specialists/1/style", json={
        "formal_level": "标准学术", "reply_length": "标准", "opening_mode": "直切主题",
    }, headers=_token(4, "rep"))
    assert resp.status_code == 403
    assert resp.json()["code"] == 3000


def test_set_style_updates_persona(fresh_state):
    _add_twin(id=1, representative_id=1, persona={})
    resp = client.put("/api/v1/specialists/1/style", json={
        "formal_level": "标准学术", "reply_length": "标准", "opening_mode": "直切主题",
    }, headers=_token(1, "rep"))
    body = resp.json()
    assert body["code"] == 0
    assert body["data"]["persona"]["style"]["formal_level"] == "标准学术"
    assert body["data"]["persona"]["style"]["opening_mode"] == "直切主题"


def test_pause_resume(fresh_state):
    _add_twin(id=1, representative_id=1, status="active")
    resp = client.post("/api/v1/specialists/1/pause", json={}, headers=_token(1, "rep"))
    assert resp.json()["data"]["status"] == "paused"
    resp = client.post("/api/v1/specialists/1/resume", json={}, headers=_token(1, "rep"))
    assert resp.json()["data"]["status"] == "active"


def test_pause_only_own_twin():
    _add_twin(id=1, representative_id=99)
    resp = client.post("/api/v1/specialists/1/pause", json={}, headers=_token(1, "rep"))
    assert resp.status_code == 403


def test_style_test_creates_twin(fresh_state):
    resp = client.post("/api/v1/specialists/style-test", json={
        "answers": [1, 2, 0, 1, 2],
    }, headers=_token(1, "rep"))
    body = resp.json()
    assert body["code"] == 0
    assert body["data"]["representative_id"] == 1
    assert body["data"]["status"] == "active"
    assert "style" in (body["data"]["persona"] or {})
