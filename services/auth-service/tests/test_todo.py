"""管理端待办中心测试（2026-09-15 C 批）：auth 侧四类待办计数 + 角色门禁

SQLite 建四张待办表（qualification/certification/question/privacy），断言
pending 计数正确、approved 不计、隐私 pending+processing 都计、rep 拒入。
"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", ".."))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

os.environ.setdefault("JWT_SECRET", "test-secret-not-a-default-value")
os.environ["AUTH_DEV_MODE"] = "true"

from datetime import datetime, timedelta

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
from shared.models.doctor import DoctorCertification
from shared.models.privacy import PrivacyRequest
from shared.models.qualification import RepresentativeQualification
from shared.models.training_exam import ExamQuestion
from shared.models.user import User

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
    tables = [User.__table__, RepresentativeQualification.__table__,
              DoctorCertification.__table__, ExamQuestion.__table__, PrivacyRequest.__table__]
    Base.metadata.drop_all(engine, tables=tables)
    Base.metadata.create_all(engine, tables=tables)
    db = TestSession()
    db.add_all([
        User(id=1, username="admin", full_name="管理员", phone="13800000000", role="admin", status="active"),
        User(id=2, username="rep01", full_name="李代表", phone="13800000002", role="rep", status="active"),
        User(id=3, username="rep02", full_name="王代表", phone="13800000003", role="rep", status="active"),
        User(id=4, username="rep03", full_name="赵代表", phone="13800000004", role="rep", status="active"),
        User(id=5, username="doc01", full_name="张医生", phone="13800000005", role="doctor", status="active"),
        User(id=6, username="doc02", full_name="李医生", phone="13800000006", role="doctor", status="active"),
    ])
    db.commit()
    db.close()
    monkeypatch.setitem(app.dependency_overrides, get_db, _override_db)


def _counts():
    resp = client.get("/api/v1/auth/todo-summary", headers=_token(1, "admin"))
    assert resp.json()["code"] == 0
    return {i["key"]: i["count"] for i in resp.json()["data"]["items"]}


def test_todo_summary_counts_pending_only():
    db = TestSession()
    # 2 条资质 pending + 1 条 approved；2 条认证 pending；1 道题 pending；
    # 隐私 1 pending + 1 processing + 1 done
    db.add_all([
        RepresentativeQualification(representative_id=2, education_cert="http://x/1", audit_status="pending"),
        RepresentativeQualification(representative_id=3, education_cert="http://x/2", audit_status="pending"),
        RepresentativeQualification(representative_id=4, education_cert="http://x/3", audit_status="approved"),
        DoctorCertification(doctor_id=5, cert_type="physician", cert_image_url="http://x/c1", cert_status="pending"),
        DoctorCertification(doctor_id=6, cert_type="practice", cert_image_url="http://x/c2", cert_status="approved"),
        ExamQuestion(question_type="single", content="题干", options=["A"], answer=[0], review_status="pending"),
        PrivacyRequest(doctor_id=5, request_type="view", status="pending",
                       content={}, sla_deadline=datetime.utcnow() + timedelta(days=30)),
        PrivacyRequest(doctor_id=5, request_type="export", status="processing",
                       content={}, sla_deadline=datetime.utcnow() + timedelta(days=30)),
        PrivacyRequest(doctor_id=5, request_type="delete", status="done",
                       content={}, sla_deadline=datetime.utcnow() + timedelta(days=30)),
    ])
    db.commit()
    db.close()

    counts = _counts()
    assert counts["qualification_pending"] == 2
    assert counts["doctor_cert_pending"] == 1
    assert counts["exam_question_pending"] == 1
    # 隐私未办结 = pending + processing（done 不计）
    assert counts["privacy_open"] == 2


def test_todo_summary_empty_state():
    counts = _counts()
    assert all(v == 0 for v in counts.values())


@pytest.mark.parametrize("uid,role", [(2, "rep"), (5, "doctor")])
def test_todo_summary_rejects_non_admin(uid, role):
    # H2：角色以库为准（token 只是快照），rep/doctor 均非四管理角色 → 403
    resp = client.get("/api/v1/auth/todo-summary", headers=_token(uid, role))
    assert resp.status_code == 403
