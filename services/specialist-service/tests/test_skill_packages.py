"""Skill 模版测试（Task 2）：创建/审核/广场浏览/隐私边界"""
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

from shared.common.auth import create_token
from shared.common.db_session import get_db
from shared.models.base import Base
from shared.models.skill import SkillAudit, SkillPackage
from shared.models.user import User

import app.api.skill_packages as sp_api
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
    tables = [User.__table__, SkillPackage.__table__, SkillAudit.__table__]
    Base.metadata.drop_all(engine, tables=tables)
    Base.metadata.create_all(engine, tables=tables)
    db = TestSession()
    db.add_all([
        User(id=1, username="rep01", full_name="张代表", phone="13800000001", role="rep", status="active"),
        User(id=2, username="admin", full_name="管理员", phone="13800000000", role="admin", status="active"),
        User(id=3, username="medical", full_name="医学部", phone="13800000003", role="medical", status="active"),
    ])
    db.commit()
    db.close()
    monkeypatch.setitem(app.dependency_overrides, get_db, _override_db)
    audit_mock = AsyncMock(return_value=None)
    monkeypatch.setattr(sp_api, "write_audit_log", audit_mock)
    yield audit_mock


def _add_skill(**kw):
    db = TestSession()
    defaults = dict(
        id=kw.pop("id", 1), name="严谨学术风", creator_id=3, is_public=False,
        is_anonymous=False, audit_status="pending",
        style_tags=["严谨学术"], heat=0, skill_weights={"formal_level": "标准学术"},
    )
    defaults.update(kw)
    db.add(SkillPackage(**defaults))
    db.commit()
    db.close()
    return defaults["id"]


def test_create_skill_requires_medical():
    resp = client.post("/api/v1/skill-packages", json={
        "name": "严谨学术风", "style_tags": ["严谨学术"],
        "skill_weights": {"formal_level": "标准学术"},
    }, headers=_token(1, "rep"))
    assert resp.status_code == 403
    assert resp.json()["code"] == 3000


def test_create_skill_sets_pending(fresh_state):
    resp = client.post("/api/v1/skill-packages", json={
        "name": "严谨学术风", "style_tags": ["严谨学术"],
        "skill_weights": {"formal_level": "标准学术"},
    }, headers=_token(3, "medical"))
    body = resp.json()
    assert body["code"] == 0
    assert body["data"]["audit_status"] == "pending"
    assert "skill_weights" not in body["data"]  # 权重不返回


def test_review_approve_sets_public(fresh_state):
    _add_skill(id=1)
    resp = client.post("/api/v1/skill-packages/1/review", json={"verdict": "approve"},
                       headers=_token(2, "admin"))
    body = resp.json()
    assert body["code"] == 0
    assert body["data"]["audit_status"] == "approved"
    audit_mock = fresh_state
    audit_mock.assert_awaited_once()


def test_review_reject_requires_reason():
    _add_skill(id=1)
    resp = client.post("/api/v1/skill-packages/1/review", json={"verdict": "reject"},
                       headers=_token(2, "admin"))
    assert resp.status_code == 400
    assert resp.json()["code"] == 1000


def test_public_plaza_only_approved():
    _add_skill(id=1, is_public=True, audit_status="approved")
    _add_skill(id=2, is_public=True, audit_status="pending")
    _add_skill(id=3, is_public=False, audit_status="approved")
    resp = client.get("/api/v1/skill-packages/public", headers=_token(1, "rep"))
    body = resp.json()
    assert body["code"] == 0
    assert body["data"]["total"] == 1  # 只有 approved+is_public
    item = body["data"]["items"][0]
    assert "skill_weights" not in item


def test_load_increments_heat(fresh_state):
    _add_skill(id=1, is_public=True, audit_status="approved")
    resp = client.post("/api/v1/skill-packages/1/load", json={}, headers=_token(1, "rep"))
    body = resp.json()
    assert body["code"] == 0
    assert body["data"]["heat"] == 1


def test_plaza_rejects_admin():
    resp = client.get("/api/v1/skill-packages/public", headers=_token(2, "admin"))
    assert resp.status_code == 403
