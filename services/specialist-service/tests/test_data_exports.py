"""数据导出审批测试（三期 K）"""
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
from shared.models.user import User
from shared.models.qualification import RepresentativeQualification
from shared.models.digital_specialist import Specialist

from app.main import app
from app.models.conversation import Conversation
from app.models.export_request import ExportRequest


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
    tables = [User.__table__, Specialist.__table__, RepresentativeQualification.__table__,
              ExportRequest.__table__, Conversation.__table__]
    Base.metadata.drop_all(engine, tables=tables)
    Base.metadata.create_all(engine, tables=tables)
    db = TestSession()
    db.add_all([
        User(id=1, username="rep01", full_name="张代表", phone="13800000001", role="rep", status="active"),
        User(id=2, username="admin", full_name="管理员", phone="13800000000", role="admin", status="active"),
        User(id=3, username="compliance", full_name="合规部", phone="13800000003", role="compliance", status="active"),
    ])
    db.commit()
    db.close()
    monkeypatch.setitem(app.dependency_overrides, get_db, _override_db)
    # 清除其它 FakeDb 测试文件（test_d_low_batch.py 等）遗留的 get_current_user 覆盖，
    # 否则 require_roles 的 get_current_user 依赖会拿到伪造的 role（与 test_twin_manage.py 同款清理）。
    monkeypatch.delitem(app.dependency_overrides, get_current_user, raising=False)
    from app.api import data_exports as de_api
    audit_mock = AsyncMock(return_value=None)
    monkeypatch.setattr(de_api, "write_audit_log", audit_mock)
    yield audit_mock


def test_export_request_to_dict(fresh_state):
    db = TestSession()
    er = ExportRequest(id=1, requester_id=2, export_type="conversations", reason="监管自查", status="pending")
    db.add(er)
    db.commit()
    d = er.to_dict()
    assert d["export_type"] == "conversations"
    assert d["status"] == "pending"
    assert d["reason"] == "监管自查"
    db.close()


def test_create_export_requires_admin_or_manager():
    resp = client.post("/api/v1/data-exports/requests", json={"export_type": "conversations", "reason": "监管自查"},
                       headers=_token(3, "compliance"))
    assert resp.status_code == 403
    assert resp.json()["code"] == 3000


def test_create_export_sets_pending(fresh_state):
    resp = client.post("/api/v1/data-exports/requests", json={"export_type": "conversations", "reason": "监管自查"},
                       headers=_token(2, "admin"))
    body = resp.json()
    assert body["code"] == 0
    assert body["data"]["status"] == "pending"
    assert body["data"]["export_type"] == "conversations"
    fresh_state.assert_awaited_once()


def test_create_export_requires_reason():
    resp = client.post("/api/v1/data-exports/requests", json={"export_type": "conversations"},
                       headers=_token(2, "admin"))
    assert resp.status_code == 400
    assert resp.json()["code"] == 1000


def test_list_exports_filters_status(fresh_state):
    db = TestSession()
    db.add_all([
        ExportRequest(id=1, requester_id=2, export_type="conversations", reason="a", status="pending"),
        ExportRequest(id=2, requester_id=2, export_type="conversations", reason="b", status="approved"),
    ])
    db.commit()
    db.close()
    resp = client.get("/api/v1/data-exports/requests", params={"status": "approved"}, headers=_token(3, "compliance"))
    body = resp.json()
    assert body["data"]["total"] == 1
    assert body["data"]["items"][0]["id"] == 2
    assert body["data"]["items"][0]["requester_name"] == "管理员"


def test_build_conversations_xlsx_escapes_formulas(tmp_path):
    from openpyxl import load_workbook
    from app.api.data_exports import _build_conversations_xlsx
    path = _build_conversations_xlsx(
        99,
        [{"id": 1, "user_id": 1, "specialist_id": 1, "session_id": "s",
          "role": "user", "content": "=HYPERLINK(\"http://evil\")", "blocked": False, "created_at": None}],
        str(tmp_path),
    )
    wb = load_workbook(path)
    ws = wb.active
    content = ws.cell(row=2, column=6).value
    assert isinstance(content, str)
    assert content.startswith("'")
    assert content == "'=HYPERLINK(\"http://evil\")"
    wb.close()


def test_review_approve_generates_xlsx(fresh_state, monkeypatch, tmp_path):
    db = TestSession()
    db.add(ExportRequest(id=1, requester_id=2, export_type="conversations", reason="监管自查", status="pending"))
    db.commit()
    db.close()
    fake_path = str(tmp_path / "export_1.xlsx")
    monkeypatch.setattr("app.api.data_exports._build_conversations_xlsx", lambda request_id, rows, out_dir=None: fake_path)
    resp = client.post("/api/v1/data-exports/requests/1/review", json={"verdict": "approve"},
                       headers=_token(3, "compliance"))
    body = resp.json()
    assert body["code"] == 0
    assert body["data"]["status"] == "approved"
    assert body["data"]["file_url"] == fake_path
    assert body["data"]["approver_id"] == 3
    assert body["data"]["expires_at"] is not None
    fresh_state.assert_awaited_once()


def test_review_reject_requires_reason(fresh_state):
    db = TestSession()
    db.add(ExportRequest(id=1, requester_id=2, export_type="conversations", reason="a", status="pending"))
    db.commit()
    db.close()
    resp = client.post("/api/v1/data-exports/requests/1/review", json={"verdict": "reject"},
                       headers=_token(3, "compliance"))
    assert resp.status_code == 400
    assert resp.json()["code"] == 1000


def test_download_requires_approved(fresh_state):
    db = TestSession()
    db.add(ExportRequest(id=1, requester_id=2, export_type="conversations", reason="a", status="pending"))
    db.commit()
    db.close()
    resp = client.get("/api/v1/data-exports/requests/1/download", headers=_token(3, "compliance"))
    assert resp.status_code == 404
    assert resp.json()["code"] == 4000


def test_mah_overview_requires_admin():
    resp = client.get("/api/v1/specialists/mah-overview", headers=_token(1, "rep"))
    assert resp.status_code == 403
    assert resp.json()["code"] == 3000


def test_mah_overview_aggregates(fresh_state):
    db = TestSession()
    # 2 个 rep：一个有效备案+培训完成，一个未备案
    db.add(User(id=4, username="rep02", full_name="李代表", phone="13800000004", role="rep", status="active"))
    db.add(RepresentativeQualification(id=1, representative_id=1, education_cert="u1", filing_number="MAH-1",
                                       audit_status="approved", filing_expire_date=None,
                                       compliance_training_completed=True, commitment_signed=True))
    db.add(RepresentativeQualification(id=2, representative_id=4, education_cert="u4", audit_status="pending"))
    # 对话：1 条 blocked，3 条正常 → 通过率 0.75
    db.add_all([
        Conversation(id=1, user_id=1, specialist_id=1, session_id="s1", role="user", content="a", compliance_result=None),
        Conversation(id=2, user_id=1, specialist_id=1, session_id="s1", role="assistant", content="b", compliance_result={"blocked": False}),
        Conversation(id=3, user_id=1, specialist_id=1, session_id="s2", role="user", content="c", compliance_result={"blocked": False}),
        Conversation(id=4, user_id=4, specialist_id=1, session_id="s2", role="assistant", content="d", compliance_result={"blocked": True}),
    ])
    db.commit()
    db.close()
    resp = client.get("/api/v1/specialists/mah-overview", headers=_token(2, "admin"))
    body = resp.json()
    assert body["code"] == 0
    data = body["data"]
    assert data["total_reps"] == 2
    assert data["filing"]["valid"] == 1
    assert data["filing"]["pending_review"] == 1
    assert data["filing"]["not_filed"] == 0
    assert data["training_completed_rate"] == 0.5
    assert data["commitment_signed_rate"] == 0.5
    assert data["compliance_pass_rate"] == 0.75


# ==================== M-2（2026-08-24 审查修复）：审批角色收敛 + 自审自批拦截 ====================

def test_review_rejects_manager_role(fresh_state):
    """审批收敛到 compliance/admin：manager（申请人角色）不再可审（此前可自审自批）"""
    db = TestSession()
    db.add(User(id=5, username="mgr", full_name="经理", phone="13800000005", role="manager", status="active"))
    db.add(ExportRequest(id=1, requester_id=2, export_type="conversations", reason="a", status="pending"))
    db.commit()
    db.close()
    resp = client.post("/api/v1/data-exports/requests/1/review", json={"verdict": "approve"},
                       headers=_token(5, "manager"))
    assert resp.status_code == 403
    assert resp.json()["code"] == 3000


def test_review_rejects_self_approval(fresh_state):
    """本人申请本人批 → 4001（含 admin：兜底审批权也不能批自己的单）"""
    db = TestSession()
    db.add(ExportRequest(id=1, requester_id=3, export_type="conversations", reason="自查", status="pending"))
    db.commit()
    db.close()
    resp = client.post("/api/v1/data-exports/requests/1/review", json={"verdict": "approve"},
                       headers=_token(3, "compliance"))
    assert resp.status_code == 422
    assert resp.json()["code"] == 4001
    # 申请单仍为 pending，未被审批
    db = TestSession()
    assert db.query(ExportRequest).filter_by(id=1).first().status == "pending"
    db.close()
