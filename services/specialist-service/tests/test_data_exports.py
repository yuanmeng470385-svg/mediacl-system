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
    tables = [User.__table__, ExportRequest.__table__, Conversation.__table__]
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
    assert resp.status_code == 422
    assert resp.json()["code"] == 4001
