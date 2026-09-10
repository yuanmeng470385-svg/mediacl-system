"""Skill 模版测试（Task 2）：创建/审核/广场浏览/隐私边界"""
import os
import sys
from datetime import datetime

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
from shared.models.practice import PracticeSession
from shared.models.skill import SkillAudit, SkillPackage, SkillOffShelf
from shared.models.user import User
from shared.models.visit import VisitRecord

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
    tables = [User.__table__, SkillPackage.__table__, SkillAudit.__table__, SkillOffShelf.__table__,
              PracticeSession.__table__, VisitRecord.__table__]
    Base.metadata.drop_all(engine, tables=tables)
    Base.metadata.create_all(engine, tables=tables)
    db = TestSession()
    db.add_all([
        User(id=1, username="rep01", full_name="张代表", phone="13800000001", role="rep", status="active"),
        User(id=2, username="admin", full_name="管理员", phone="13800000000", role="admin", status="active"),
        User(id=3, username="medical", full_name="医学部", phone="13800000003", role="medical", status="active"),
        User(id=4, username="manager", full_name="销售经理", phone="13800000004", role="manager", status="active"),
        User(id=5, username="compliance", full_name="合规部", phone="13800000005", role="compliance", status="active"),
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


def _add_visit(vid: int, rep_lines: int, owner: int = 1, status: str = "in_progress"):
    """建一条拜访记录（2026-09-10 溯源扩拜访）：[代表]/[医生] 行交错写入转写。"""
    lines = []
    for i in range(1, rep_lines + 1):
        lines.append(f"[代表] 拜访中代表第{i}条发言")
        lines.append(f"[医生] 医生第{i}条回应")
    db = TestSession()
    db.add(VisitRecord(id=vid, user_id=owner, visit_time=datetime(2026, 9, 5, 10),
                       status=status, conversation_transcript="\n".join(lines) + "\n"))
    db.commit()
    db.close()


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


def test_detail_exposes_content_to_admin_plan_a(fresh_state):
    """方案 A（2026-09-01 审核盲审修复）：SKILL_ADMIN_ROLES 全量受控可见——
    此前 admin/manager 仅元数据可审，approve 即橡皮图章；能看者 ⊇ 能审者。"""
    _add_skill(id=1, content="话术素材", source_session_ids=[7])
    resp = client.get("/api/v1/skill-packages/1/detail", headers=_token(2, "admin"))
    body = resp.json()
    assert body["code"] == 0
    assert body["data"]["content"] == "话术素材"
    assert body["data"]["skill_weights"] == {"formal_level": "标准学术"}
    assert body["data"]["source_session_ids"] == [7]
    # rep 无权限查看详情
    resp = client.get("/api/v1/skill-packages/1/detail", headers=_token(1, "rep"))
    assert resp.status_code == 403
    assert resp.json()["code"] == 3000


def test_detail_exposes_content_to_medical(fresh_state):
    _add_skill(id=1, content="话术素材")
    resp = client.get("/api/v1/skill-packages/1/detail", headers=_token(3, "medical"))
    body = resp.json()
    assert body["code"] == 0
    assert body["data"]["content"] == "话术素材"
    assert body["data"]["skill_weights"] == {"formal_level": "标准学术"}


def test_review_approve_sets_public(fresh_state):
    _add_skill(id=1)
    resp = client.post("/api/v1/skill-packages/1/review", json={"verdict": "approve"},
                       headers=_token(5, "compliance"))
    body = resp.json()
    assert body["code"] == 0
    assert body["data"]["audit_status"] == "approved"
    audit_mock = fresh_state
    audit_mock.assert_awaited_once()


def test_review_reject_requires_reason():
    _add_skill(id=1)
    resp = client.post("/api/v1/skill-packages/1/review", json={"verdict": "reject"},
                       headers=_token(5, "compliance"))
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


def test_release_content_too_long(fresh_state):
    resp = client.post("/api/v1/skill-packages/release", json={
        "name": "亲和力型", "description": "心内科", "content": "字" * 10001,
        "skill_weights": {"formal_level": "标准学术"},
    }, headers=_token(1, "rep"))
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


def test_asset_list_includes_rep_skill_with_creator(fresh_state):
    db = TestSession()
    db.add(SkillPackage(id=1, name="代表风格", creator_id=1, is_public=True, is_anonymous=False,
                        audit_status="pending", description="心内科", content="素材",
                        style_tags=["严谨"], heat=0, skill_weights={}))
    db.commit()
    db.close()
    resp = client.get("/api/v1/skill-packages/asset-list", headers=_token(2, "admin"))
    body = resp.json()
    assert body["code"] == 0
    assert body["data"]["total"] == 1
    item = body["data"]["items"][0]
    assert item["name"] == "代表风格"
    assert item["creator_name"] == "张代表"
    assert item["creator_role"] == "rep"
    assert "content" not in item
    assert "skill_weights" not in item


def test_asset_list_filters_off_shelf(fresh_state):
    db = TestSession()
    db.add_all([
        SkillPackage(id=1, name="正常", creator_id=3, is_public=True, is_anonymous=False,
                     audit_status="approved", style_tags=[], heat=0, skill_weights={}),
        SkillPackage(id=2, name="已下架", creator_id=3, is_public=True, is_anonymous=False,
                     audit_status="approved", style_tags=[], heat=0, skill_weights={},
                     off_shelf_status="off_shelved", off_shelf_reason="违规", off_shelf_type="compliance"),
    ])
    db.commit()
    db.close()
    resp = client.get("/api/v1/skill-packages/asset-list", params={"off_shelf_status": "off_shelved"},
                      headers=_token(2, "admin"))
    body = resp.json()
    assert body["data"]["total"] == 1
    assert body["data"]["items"][0]["id"] == 2


def test_detail_exposes_content_and_writes_view_audit(fresh_state):
    _add_skill(id=1, audit_status="approved", content="话术素材")
    resp = client.get("/api/v1/skill-packages/1/detail", headers=_token(3, "medical"))
    body = resp.json()
    assert body["code"] == 0
    assert body["data"]["content"] == "话术素材"
    assert body["data"]["skill_weights"] == {"formal_level": "标准学术"}
    audit_mock = fresh_state
    audit_mock.assert_awaited()
    args, kwargs = audit_mock.call_args
    assert kwargs.get("action") == "skill_detail_view"


def test_public_excludes_off_shelved(fresh_state):
    db = TestSession()
    db.add_all([
        SkillPackage(id=1, name="正常", creator_id=1, is_public=True, is_anonymous=False,
                     audit_status="approved", style_tags=[], heat=0, skill_weights={}),
        SkillPackage(id=2, name="下架", creator_id=1, is_public=True, is_anonymous=False,
                     audit_status="approved", style_tags=[], heat=0, skill_weights={},
                     off_shelf_status="off_shelved", off_shelf_type="author", off_shelf_reason="作者申请"),
    ])
    db.commit()
    db.close()
    resp = client.get("/api/v1/skill-packages/public", headers=_token(1, "rep"))
    assert resp.json()["data"]["total"] == 1
    assert resp.json()["data"]["items"][0]["id"] == 1


def test_load_excludes_off_shelved(fresh_state):
    _add_skill(id=1, is_public=True, audit_status="approved",
               off_shelf_status="off_shelved", off_shelf_type="author", off_shelf_reason="作者申请")
    resp = client.post("/api/v1/skill-packages/1/load", json={}, headers=_token(1, "rep"))
    assert resp.status_code == 422
    assert resp.json()["code"] == 4001


def test_off_shelf_compliance_fields_and_record(fresh_state):
    _add_skill(id=1)
    resp = client.post("/api/v1/skill-packages/1/off-shelf", json={"type": "compliance", "reason": "含敏感信息"},
                       headers=_token(2, "admin"))
    body = resp.json()
    assert body["code"] == 0
    data = body["data"]
    assert data["off_shelf_status"] == "off_shelved"
    assert data["off_shelf_type"] == "compliance"
    assert data["off_shelf_reason"] == "含敏感信息"
    assert data["off_shelf_by"] == 2
    assert data["off_shelf_at"] is not None
    fresh_state.assert_awaited_once()
    db = TestSession()
    rec = db.query(SkillOffShelf).filter(SkillOffShelf.skill_id == 1).first()
    assert rec is not None and rec.off_shelf_type == "compliance"
    assert rec.operator_id == 2
    db.close()


def test_off_shelf_requires_reason(fresh_state):
    _add_skill(id=1)
    resp = client.post("/api/v1/skill-packages/1/off-shelf", json={"type": "compliance"},
                       headers=_token(2, "admin"))
    assert resp.status_code == 400
    assert resp.json()["code"] == 1000


def test_off_shelf_requires_type(fresh_state):
    _add_skill(id=1)
    resp = client.post("/api/v1/skill-packages/1/off-shelf", json={"reason": "下架"},
                       headers=_token(2, "admin"))
    assert resp.status_code == 400


def test_off_shelf_twice_4001(fresh_state):
    _add_skill(id=1, off_shelf_status="off_shelved", off_shelf_type="author", off_shelf_reason="作者申请")
    resp = client.post("/api/v1/skill-packages/1/off-shelf", json={"type": "compliance", "reason": "再下架"},
                       headers=_token(2, "admin"))
    assert resp.status_code == 422
    assert resp.json()["code"] == 4001

# ========== 2026-09-01 审核盲审修复批：方案 B 审核收敛 + 溯源留档 ==========

def _add_session(sid=7, rep_id=1, status="completed", turns=12):
    db = TestSession()
    db.add(PracticeSession(
        id=sid, representative_id=rep_id, skill_id=None, scenario="心内科推广",
        status=status, turn_count=turns,
        transcript=[{"turn": 1, "role": "rep", "content": "主任您好"}],
    ))
    db.commit()
    db.close()


def test_review_allows_manager_and_admin(fresh_state):
    """审核权恢复全 SKILL_ADMIN_ROLES（2026-09-01 当日二调：小公司单账号审核）。"""
    _add_skill(id=2)
    resp = client.post("/api/v1/skill-packages/2/review", json={"verdict": "approve"},
                       headers=_token(4, "manager"))
    assert resp.json()["code"] == 0
    _add_skill(id=3)
    resp = client.post("/api/v1/skill-packages/3/review", json={"verdict": "reject", "reason": "内容不合规"},
                       headers=_token(2, "admin"))
    assert resp.json()["code"] == 0


def test_review_allows_compliance_writes_audit(fresh_state):
    _add_skill(id=1)
    resp = client.post("/api/v1/skill-packages/1/review", json={"verdict": "approve"},
                       headers=_token(5, "compliance"))
    assert resp.json()["code"] == 0
    db = TestSession()
    rows = db.query(SkillAudit).all()
    db.close()
    assert len(rows) == 1 and rows[0].audit_result == "approved"
    fresh_state.assert_awaited()


def test_audits_lists_history_with_auditor_name(fresh_state):
    _add_skill(id=1)
    client.post("/api/v1/skill-packages/1/review", json={"verdict": "reject", "reason": "内容不合规"},
                headers=_token(5, "compliance"))
    resp = client.get("/api/v1/skill-packages/1/audits", headers=_token(2, "admin"))
    body = resp.json()
    assert body["code"] == 0
    assert len(body["data"]) == 1
    row = body["data"][0]
    assert row["audit_result"] == "rejected"
    assert row["reason"] == "内容不合规"
    assert row["auditor_name"] == "合规部"
    # rep 不可见审核历史
    resp = client.get("/api/v1/skill-packages/1/audits", headers=_token(1, "rep"))
    assert resp.status_code == 403


def test_release_stores_source_session_ids(fresh_state):
    """溯源留档：release 携带来源会话（校验本人+completed+>=3轮）后落库并在审计 after_value。"""
    _add_session(7)
    _add_session(8)
    resp = client.post("/api/v1/skill-packages/release", json={
        "name": "亲和力型", "description": "心内科", "content": "话术素材",
        "skill_weights": {"formal_level": "标准学术"},
        "source_session_ids": [7, 8, 7],
    }, headers=_token(1, "rep"))
    body = resp.json()
    assert body["code"] == 0
    db = TestSession()
    sk = db.query(SkillPackage).filter(SkillPackage.creator_id == 1).first()
    db.close()
    assert sk.source_session_ids == [7, 8]  # 去重落库
    args, kwargs = fresh_state.call_args
    assert kwargs["after_value"]["source_session_ids"] == [7, 8]


def test_release_rejects_foreign_session(fresh_state):
    _add_session(7, rep_id=999)
    resp = client.post("/api/v1/skill-packages/release", json={
        "name": "亲和力型", "description": "心内科", "content": "话术素材",
        "skill_weights": {"formal_level": "标准学术"},
        "source_session_ids": [7],
    }, headers=_token(1, "rep"))
    body = resp.json()
    assert resp.status_code == 400
    assert "非本人" in body["message"]


def test_release_rejects_unfinished_session(fresh_state):
    _add_session(7, status="in_progress", turns=0)
    resp = client.post("/api/v1/skill-packages/release", json={
        "name": "亲和力型", "description": "心内科", "content": "话术素材",
        "skill_weights": {"formal_level": "标准学术"},
        "source_session_ids": [7],
    }, headers=_token(1, "rep"))
    assert resp.status_code == 400


# ==================== 溯源扩拜访（2026-09-10） ====================

def test_release_stores_source_visit_ids(fresh_state):
    """溯源扩拜访：release 携带 source_visit_ids 校验（本人+非取消+>=3 行）后去重落库并进审计。"""
    _add_visit(3, rep_lines=4)
    resp = client.post("/api/v1/skill-packages/release", json={
        "name": "亲和力型", "description": "心内科", "content": "话术素材",
        "skill_weights": {"formal_level": "标准学术"},
        "source_visit_ids": [3, 3],
    }, headers=_token(1, "rep"))
    body = resp.json()
    assert body["code"] == 0
    db = TestSession()
    sk = db.query(SkillPackage).filter(SkillPackage.creator_id == 1).first()
    db.close()
    assert sk.source_visit_ids == [3]  # 去重落库
    _, kwargs = fresh_state.call_args
    assert kwargs["after_value"]["source_visit_ids"] == [3]
    # detail 受控查看同吐 source_visit_ids（与 source_session_ids 同口径）
    resp = client.get("/api/v1/skill-packages/%d/detail" % sk.id, headers=_token(2, "admin"))
    assert resp.json()["data"]["source_visit_ids"] == [3]


def test_release_rejects_cancelled_visit(fresh_state):
    _add_visit(3, rep_lines=4, status="cancelled")
    resp = client.post("/api/v1/skill-packages/release", json={
        "name": "亲和力型", "description": "心内科", "content": "话术素材",
        "skill_weights": {"formal_level": "标准学术"},
        "source_visit_ids": [3],
    }, headers=_token(1, "rep"))
    assert resp.status_code == 400


def test_review_source_visit_admin_only(fresh_state):
    """拜访溯源受控查看：SKILL_ADMIN_ROLES 可看原文（含医生行上下文，前缀已剥离），
    rep 403，访问记审计 visit_source_view；不存在 → 4000。"""
    _add_visit(3, rep_lines=4)
    resp = client.get("/api/v1/skill-packages/source-visits/3", headers=_token(1, "rep"))
    assert resp.status_code == 403
    resp = client.get("/api/v1/skill-packages/source-visits/3", headers=_token(5, "compliance"))
    body = resp.json()
    assert body["code"] == 0
    d = body["data"]
    assert d["rep_name"] == "张代表"
    assert d["rep_lines"] == 4
    assert [l["speaker"] for l in d["lines"]] == ["rep", "doctor"] * 4
    assert all(not l["content"].startswith("[") for l in d["lines"])
    _, kwargs = fresh_state.call_args
    assert kwargs["action"] == "visit_source_view"
    assert kwargs["resource_type"] == "visit_record"
    resp = client.get("/api/v1/skill-packages/source-visits/999", headers=_token(2, "admin"))
    assert resp.json()["code"] == 4000


def test_create_rejects_invalid_weight_enum():
    resp = client.post("/api/v1/skill-packages", json={
        "name": "严谨学术风", "style_tags": ["严谨学术"],
        "skill_weights": {"formal_level": "超级随意"},
    }, headers=_token(3, "medical"))
    assert resp.status_code == 400
    body = resp.json()
    assert body["code"] == 1000
    assert "formal_level" in body["message"]


def test_release_rejects_invalid_weight_enum(fresh_state):
    resp = client.post("/api/v1/skill-packages/release", json={
        "name": "亲和力型", "description": "心内科", "content": "话术素材",
        "skill_weights": {"reply_length": "超长"},
    }, headers=_token(1, "rep"))
    assert resp.status_code == 400
    body = resp.json()
    assert body["code"] == 1000
    assert "reply_length" in body["message"]


def test_release_accepts_valid_partial_weights(fresh_state):
    """键存在才校验：只带部分枚举键（或自定义非枚举键）不误伤。"""
    resp = client.post("/api/v1/skill-packages/release", json={
        "name": "亲和力型", "description": "心内科", "content": "话术素材",
        "skill_weights": {"formal_level": "非常严谨", "custom_note": "自定义"},
    }, headers=_token(1, "rep"))
    assert resp.json()["code"] == 0


def test_weights_enums_match_specialists_whitelist():
    """跨文件枚举一致性（2026-09-02）：skill_packages 与 specialists 白名单逐字对齐，
    防止单边改动导致发布通过、陪练评分口径对不上。"""
    import app.api.specialists as specialists_api
    assert sp_api.VALID_FORMAL == specialists_api.VALID_FORMAL
    assert sp_api.VALID_LENGTH == specialists_api.VALID_LENGTH
    assert sp_api.VALID_OPENING == specialists_api.VALID_OPENING


def test_mine_returns_own_content_not_weights(fresh_state):
    """T5-4（2026-09-02）挂账收口：/mine 本人回看 content；weights 仍不吐（附录 B-1）。"""
    db = TestSession()
    db.add(SkillPackage(id=2, name="我的", creator_id=1, is_public=True, is_anonymous=False,
                        audit_status="approved", style_tags=["严谨"], heat=5,
                        skill_weights={"formal_level": "标准学术"}, content="正文话术素材"))
    db.commit()
    db.close()
    resp = client.get("/api/v1/skill-packages/mine", headers=_token(1, "rep"))
    body = resp.json()
    assert body["code"] == 0
    item = body["data"]["items"][0]
    assert item["content"] == "正文话术素材"
    assert "skill_weights" not in item
    assert "source_session_ids" not in item
