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
from shared.models.skill import SkillAudit, SkillPackage, SkillOffShelf
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
    tables = [User.__table__, SkillPackage.__table__, SkillAudit.__table__, SkillOffShelf.__table__]
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


def test_create_skill_public_flag(fresh_state):
    resp = client.post("/api/v1/skill-packages", json={
        "name": "严谨学术风", "style_tags": ["严谨学术"],
        "skill_weights": {"formal_level": "标准学术"}, "is_public": True,
    }, headers=_token(3, "medical"))
    body = resp.json()
    assert body["code"] == 0
    assert body["data"]["is_public"] is True
    assert body["data"]["audit_status"] == "pending"
    assert "skill_weights" not in body["data"]


def test_detail_exposes_weights_to_admin(fresh_state):
    _add_skill(id=1)
    resp = client.get("/api/v1/skill-packages/1/detail", headers=_token(2, "admin"))
    body = resp.json()
    assert body["code"] == 0
    assert body["data"]["skill_weights"] == {"formal_level": "标准学术"}
    # rep 无权限查看权重
    resp = client.get("/api/v1/skill-packages/1/detail", headers=_token(1, "rep"))
    assert resp.status_code == 403
    assert resp.json()["code"] == 3000


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


def test_to_dict_hides_content_weights_by_default():
    db = TestSession()
    sk = SkillPackage(
        id=99, name="测试", creator_id=1, description="心内科", content="话术素材",
        is_public=True, is_anonymous=False, audit_status="pending",
        style_tags=["严谨"], heat=0, skill_weights={"formal_level": "标准学术"},
        off_shelf_status="active",
    )
    db.add(sk)
    db.commit()
    d = sk.to_dict()
    assert d["description"] == "心内科"
    assert d["off_shelf_status"] == "active"
    assert "content" not in d
    assert "skill_weights" not in d
    d2 = sk.to_dict(expose_weights=True)
    assert d2["content"] == "话术素材"
    assert d2["skill_weights"] == {"formal_level": "标准学术"}
    db.close()


def test_release_requires_rep():
    resp = client.post("/api/v1/skill-packages/release", json={
        "name": "亲和力型", "description": "心内科", "content": "话术素材",
        "skill_weights": {"formal_level": "标准学术"},
    }, headers=_token(2, "admin"))
    assert resp.status_code == 403
    assert resp.json()["code"] == 3000


def test_release_creates_pending_public(fresh_state):
    resp = client.post("/api/v1/skill-packages/release", json={
        "name": "亲和力型", "description": "心内科", "content": "话术素材",
        "style_tags": ["亲和力"], "skill_weights": {"formal_level": "标准学术"}, "is_anonymous": True,
    }, headers=_token(1, "rep"))
    body = resp.json()
    assert body["code"] == 0
    data = body["data"]
    assert data["audit_status"] == "pending"
    assert data["is_public"] is True
    assert data["is_anonymous"] is True
    assert data["description"] == "心内科"
    assert "content" not in data
    assert "skill_weights" not in data
    fresh_state.assert_awaited_once()


def test_release_requires_description_content_weights():
    resp = client.post("/api/v1/skill-packages/release", json={"name": "缺内容"},
                       headers=_token(1, "rep"))
    assert resp.status_code == 400
    assert resp.json()["code"] == 1000


def test_mine_returns_own_skills(fresh_state):
    db = TestSession()
    db.add(SkillPackage(id=1, name="医学部建的", creator_id=3, is_public=True, is_anonymous=False,
                        audit_status="approved", style_tags=[], heat=0, skill_weights={}))
    db.add(SkillPackage(id=2, name="我的", creator_id=1, is_public=True, is_anonymous=False,
                        audit_status="approved", style_tags=["严谨"], heat=5, skill_weights={}))
    db.commit()
    db.close()
    resp = client.get("/api/v1/skill-packages/mine", headers=_token(1, "rep"))
    body = resp.json()
    assert body["code"] == 0
    assert body["data"]["total"] == 1
    item = body["data"]["items"][0]
    assert item["id"] == 2
    assert item["heat"] == 5
    assert "skill_weights" not in item


def test_mine_requires_rep():
    resp = client.get("/api/v1/skill-packages/mine", headers=_token(2, "admin"))
    assert resp.status_code == 403
