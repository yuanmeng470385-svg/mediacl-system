"""患教工具测试（Task 3）：模板管理/审核/生成/隐私"""
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
from shared.models.patient_edu import EduContentRecord, PatientEduTemplate
from shared.models.user import User

import app.api.patient_edu as pe_api
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
    tables = [User.__table__, PatientEduTemplate.__table__, EduContentRecord.__table__]
    Base.metadata.drop_all(engine, tables=tables)
    Base.metadata.create_all(engine, tables=tables)
    db = TestSession()
    db.add_all([
        User(id=1, username="rep01", full_name="张代表", phone="13800000001", role="rep", status="active"),
        User(id=2, username="doctor1", full_name="王医生", phone="13800000002", role="doctor", status="active"),
        User(id=3, username="medical", full_name="医学部", phone="13800000003", role="medical", status="active"),
    ])
    db.commit()
    db.close()
    monkeypatch.setitem(app.dependency_overrides, get_db, _override_db)
    audit_mock = AsyncMock(return_value=None)
    monkeypatch.setattr(pe_api, "write_audit_log", audit_mock)
    yield audit_mock


def _add_template(**kw):
    db = TestSession()
    defaults = dict(id=kw.pop("id", 1), title="高血压患教", disease_area="心血管",
                    content="按时服药、低盐饮食……", review_status="approved", created_by=3)
    defaults.update(kw)
    db.add(PatientEduTemplate(**defaults))
    db.commit()
    db.close()
    return defaults["id"]


def test_create_template_requires_medical():
    resp = client.post("/api/v1/patient-edu/templates", json={
        "title": "高血压患教", "disease_area": "心血管", "content": "低盐饮食……",
    }, headers=_token(2, "doctor"))
    assert resp.status_code == 403
    assert resp.json()["code"] == 3000


def test_create_template_sets_pending(fresh_state):
    resp = client.post("/api/v1/patient-edu/templates", json={
        "title": "高血压患教", "disease_area": "心血管", "content": "低盐饮食……",
    }, headers=_token(3, "medical"))
    body = resp.json()
    assert body["code"] == 0
    assert body["data"]["review_status"] == "pending"


def test_review_approve(fresh_state):
    _add_template(id=1, review_status="pending")
    resp = client.post("/api/v1/patient-edu/templates/1/review", json={"verdict": "approve"},
                       headers=_token(3, "medical"))
    body = resp.json()
    assert body["code"] == 0
    assert body["data"]["review_status"] == "approved"
    audit_mock = fresh_state
    audit_mock.assert_awaited_once()


def test_generate_requires_approved_template(fresh_state, monkeypatch):
    from app.services import qwen_client as qc
    monkeypatch.setattr(qc.QwenClient, "chat", lambda self, *a, **k: {
        "content": '{"title":"高血压患教","body":"低盐饮食、规律服药","notes":"监测血压","seek_care":"出现头晕立即就医"}',
        "usage": {},
    })
    monkeypatch.setattr(pe_api, "check_compliance", AsyncMock(return_value={"blocked": False}))
    _add_template(id=1, review_status="approved")
    resp = client.post("/api/v1/patient-edu/generate", json={"template_id": 1},
                       headers=_token(2, "doctor"))
    body = resp.json()
    assert body["code"] == 0
    assert body["data"]["is_ai_generated"] is True
    assert body["data"]["visibility"] == "private"
    assert body["data"]["content"]["title"] == "高血压患教"


def test_generate_rejects_pending_template():
    _add_template(id=1, review_status="pending")
    resp = client.post("/api/v1/patient-edu/generate", json={"template_id": 1},
                       headers=_token(2, "doctor"))
    assert resp.status_code == 400
    assert resp.json()["code"] == 1000


def test_to_dict_includes_audit_status():
    db = TestSession()
    rec = EduContentRecord(
        id=1, doctor_id=2, template_id=1,
        content={"title": "高血压患教", "body": "低盐饮食", "notes": "监测血压", "seek_care": "头晕就医"},
        is_ai_generated=True, visibility="shared", audit_status="pending",
    )
    db.add(rec)
    db.commit()
    d = rec.to_dict()
    assert d["audit_status"] == "pending"
    assert d["visibility"] == "shared"
    db.close()
