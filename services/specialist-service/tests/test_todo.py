"""管理端待办中心测试（2026-09-15 C 批）：specialist 侧四类待办计数 + 动态段防吞 + 角色门禁

关键判别：todo router 必须注册在 specialists_router 之前，否则
GET /specialists/todo-summary 会被 /{specialist_id} 动态段吞成 422（code 1000）。
"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", ".."))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

os.environ.setdefault("JWT_SECRET", "test-secret-not-a-default-value")
os.environ["AUTH_DEV_MODE"] = "true"

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
from shared.models.patient_edu import EduContentRecord
from shared.models.practice import ObjectionScript
from shared.models.skill import SkillPackage
from shared.models.user import User

from app.models.export_request import ExportRequest
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
    tables = [User.__table__, SkillPackage.__table__, EduContentRecord.__table__,
              ObjectionScript.__table__, ExportRequest.__table__]
    Base.metadata.drop_all(engine, tables=tables)
    Base.metadata.create_all(engine, tables=tables)
    db = TestSession()
    db.add_all([
        User(id=1, username="admin", full_name="管理员", phone="13800000000", role="admin", status="active"),
        User(id=2, username="rep01", full_name="李代表", phone="13800000002", role="rep", status="active"),
        User(id=3, username="doc01", full_name="张医生", phone="13800000003", role="doctor", status="active"),
    ])
    db.commit()
    db.close()
    monkeypatch.setitem(app.dependency_overrides, get_db, _override_db)
    # 清除其它 FakeDb 测试文件遗留的 get_current_user 覆盖（同 test_twin_manage），
    # 否则全量跑时角色门禁用例拿到伪造 role
    monkeypatch.delitem(app.dependency_overrides, get_current_user, raising=False)


def _counts():
    resp = client.get("/api/v1/specialists/todo-summary", headers=_token(1, "admin"))
    assert resp.json()["code"] == 0
    return {i["key"]: i["count"] for i in resp.json()["data"]["items"]}


def test_todo_summary_counts_pending_only():
    db = TestSession()
    db.add_all([
        SkillPackage(name="待审Skill", creator_id=2, audit_status="pending"),
        SkillPackage(name="已审Skill", creator_id=2, audit_status="approved"),
        EduContentRecord(doctor_id=3, content={"title": "t"}, audit_status="pending"),
        EduContentRecord(doctor_id=3, content={"title": "t2"}, audit_status="approved"),
        EduContentRecord(doctor_id=3, content={"title": "未分享"}, audit_status=None),
        ObjectionScript(scenario_type="心内科", objection_content="异议", review_status="pending"),
        ExportRequest(requester_id=1, reason="导出", status="pending"),
        ExportRequest(requester_id=1, reason="导出2", status="approved"),
    ])
    db.commit()
    db.close()

    counts = _counts()
    assert counts["skill_package_pending"] == 1
    assert counts["patient_edu_pending"] == 1
    assert counts["objection_script_pending"] == 1
    assert counts["data_export_pending"] == 1


def test_todo_summary_not_swallowed_by_dynamic_segment():
    # 路由注册顺序判别：被 /{specialist_id} 吞掉会返回 422 → 统一渲染 code 1000
    resp = client.get("/api/v1/specialists/todo-summary", headers=_token(1, "admin"))
    assert resp.json()["code"] == 0
    assert len(resp.json()["data"]["items"]) == 4


@pytest.mark.parametrize("uid,role", [(2, "rep"), (3, "doctor")])
def test_todo_summary_rejects_non_admin(uid, role):
    resp = client.get("/api/v1/specialists/todo-summary", headers=_token(uid, role))
    assert resp.status_code == 403
