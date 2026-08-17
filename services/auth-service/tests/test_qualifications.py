"""
备案资质端点测试

覆盖：首次提交必须带学历证明、非 rep 禁止提交、扩展名/大小/日期校验、
提交重置审核态、审计留痕、me/列表/审核的权限边界（Task 4/5 补齐）。

不依赖真实 Redis/PostgreSQL/OSS：DB 用 SQLite，OSS 用桩。
"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", ".."))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

os.environ.setdefault("JWT_SECRET", "test-secret-not-a-default-value")
os.environ["AUTH_DEV_MODE"] = "true"

from datetime import date, timedelta
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
from shared.models.qualification import RepresentativeQualification
from shared.models.user import User

import app.api.qualifications as qual_api
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


class _FakeOSS:
    def upload_local_file(self, local_path, object_key=None):
        return f"https://fake-oss/{os.path.basename(local_path)}"


@pytest.fixture(autouse=True)
def fresh_state(monkeypatch):
    """每用例重建 users + representative_qualifications 表，OSS 与审计打桩"""
    tables = [User.__table__, RepresentativeQualification.__table__]
    Base.metadata.drop_all(engine, tables=tables)
    Base.metadata.create_all(engine, tables=tables)
    db = TestSession()
    db.add_all([
        User(id=1, username="rep01", full_name="张代表", phone="13800000001", role="rep",
             status="active"),
        User(id=2, username="admin", full_name="管理员", phone="13800000000", role="admin",
             status="active"),
        User(id=3, username="rep02", full_name="李代表", phone="13800000002", role="rep",
             status="active"),
    ])
    db.commit()
    db.close()

    # 每用例把自己的 DB 替身装回 app 单例（模块级赋值会被后收集的模块覆盖，
    # test_auth.py 与本文件共享同一个 app 对象，逐用例挂载 + monkeypatch 自动还原）
    monkeypatch.setitem(app.dependency_overrides, get_db, _override_db)
    monkeypatch.setattr(qual_api, "OSSClient", lambda: _FakeOSS())
    audit_mock = AsyncMock(return_value=None)
    monkeypatch.setattr(qual_api, "write_audit_log", audit_mock)
    yield audit_mock


def test_submit_requires_education_cert_on_first_time():
    resp = client.post(
        "/api/v1/qualifications",
        data={"filing_number": "F-2026-001"},
        headers=_token(1, "rep"),
    )
    assert resp.status_code == 400
    body = resp.json()
    assert body["code"] == 1000
    assert "学历证明" in body["message"]


def test_submit_creates_row_and_sets_pending():
    resp = client.post(
        "/api/v1/qualifications",
        data={"filing_number": "F-2026-001", "filing_expire_date": "2028-06-30"},
        files={"education_cert": ("edu.pdf", b"%PDF-1.4 fake", "application/pdf")},
        headers=_token(1, "rep"),
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["code"] == 0
    data = body["data"]
    assert data["filing_number"] == "F-2026-001"
    assert data["filing_status"] == "valid"
    assert data["audit_status"] == "pending"
    assert data["education_cert"].startswith("https://fake-oss/")
    assert data["filing_expire_date"] == "2028-06-30"


def test_resubmit_resets_review_state(fresh_state):
    db = TestSession()
    db.add(RepresentativeQualification(
        id=1, representative_id=1, education_cert="https://oss/edu.pdf",
        filing_number="F-OLD", audit_status="rejected", reject_reason="材料不清晰",
        reviewed_by=2, reviewed_at=None,
    ))
    db.commit()
    db.close()

    resp = client.post(
        "/api/v1/qualifications",
        data={"filing_number": "F-NEW"},
        headers=_token(1, "rep"),
    )
    body = resp.json()
    assert body["code"] == 0
    assert body["data"]["audit_status"] == "pending"
    assert body["data"]["filing_number"] == "F-NEW"
    assert body["data"]["reject_reason"] is None
    assert body["data"]["reviewed_by"] is None
    audit_mock = fresh_state
    audit_mock.assert_awaited_once()


def test_non_rep_cannot_submit():
    resp = client.post(
        "/api/v1/qualifications",
        data={},
        files={"education_cert": ("edu.pdf", b"%PDF-1.4 fake", "application/pdf")},
        headers=_token(2, "admin"),
    )
    assert resp.status_code == 403
    body = resp.json()
    assert body["code"] == 3000
    assert "仅医药代表" in body["message"]


def test_bad_extension_rejected():
    resp = client.post(
        "/api/v1/qualifications",
        data={},
        files={"education_cert": ("evil.exe", b"MZ fake", "application/octet-stream")},
        headers=_token(1, "rep"),
    )
    assert resp.status_code == 400
    body = resp.json()
    assert body["code"] == 1000
    assert "文件类型" in body["message"]


def test_bad_date_format_rejected():
    resp = client.post(
        "/api/v1/qualifications",
        data={"filing_expire_date": "2028/06/30"},
        files={"education_cert": ("edu.pdf", b"%PDF-1.4 fake", "application/pdf")},
        headers=_token(1, "rep"),
    )
    assert resp.status_code == 400
    body = resp.json()
    assert body["code"] == 1000
    assert "YYYY-MM-DD" in body["message"]


def test_me_returns_row_when_exists(fresh_state):
    db = TestSession()
    db.add(RepresentativeQualification(
        id=1, representative_id=1, education_cert="https://oss/edu.pdf",
        filing_number="F-1", audit_status="approved",
        filing_expire_date=date.today() + timedelta(days=100),
    ))
    db.commit()
    db.close()

    resp = client.get("/api/v1/qualifications/me", headers=_token(1, "rep"))
    body = resp.json()
    assert body["code"] == 0
    assert body["data"]["filing_number"] == "F-1"
    assert body["data"]["days_until_expiry"] == 100


def test_me_returns_null_without_row():
    resp = client.get("/api/v1/qualifications/me", headers=_token(3, "rep"))
    body = resp.json()
    assert body["code"] == 0
    assert body["data"] is None


def test_me_requires_auth():
    # HTTPBearer 无 Authorization 头 → 403（缺头 403，无效 token 才是 401；
    # 与 test_auth.TestCurrentUser.test_无token被拒、specialist-service 既有约定一致）
    resp = client.get("/api/v1/qualifications/me")
    assert resp.status_code == 403
