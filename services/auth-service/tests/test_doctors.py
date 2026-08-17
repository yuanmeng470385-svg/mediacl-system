"""医生端端点测试（角色 / 认证 / 医师执业资质端点）

覆盖：仅 doctor 可提交、缺文件/缺 cert_type → 400、提交重置 pending、
审计留痕、me/列表/审核的权限边界。

不依赖真实 Redis/PostgreSQL/OSS：DB 用 SQLite，OSS 用桩。
"""
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
from sqlalchemy.ext.compiler import compiles
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from shared.common.auth import create_token
from shared.common.db_session import get_db
from shared.models.base import Base
from shared.models.doctor import DoctorCertification
from shared.models.user import User

import app.api.qualifications as qual_api
import app.api.doctors as doctors_api
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
    """每用例重建 users + doctor_certifications 表，OSS 与审计打桩"""
    tables = [User.__table__, DoctorCertification.__table__]
    Base.metadata.drop_all(engine, tables=tables)
    Base.metadata.create_all(engine, tables=tables)
    db = TestSession()
    db.add_all([
        User(id=1, username="doc01", full_name="张医生", phone="13800000001", role="doctor",
             status="active"),
        User(id=2, username="admin", full_name="管理员", phone="13800000000", role="admin",
             status="active"),
        User(id=3, username="rep01", full_name="李代表", phone="13800000002", role="rep",
             status="active"),
        User(id=4, username="doc02", full_name="王医生", phone="13800000003", role="doctor",
             status="active"),
    ])
    db.commit()
    db.close()

    # 每用例把自己的 DB 替身装回 app 单例（monkeypatch 自动还原）
    monkeypatch.setitem(app.dependency_overrides, get_db, _override_db)
    # OSS 由 qualifications._save_upload 内部解析（__globals__ 指向 qualifications），
    # 故补在 qual_api；审计由 doctors.py 直接 import，补在 doctors_api。
    monkeypatch.setattr(qual_api, "OSSClient", lambda: _FakeOSS())
    audit_mock = AsyncMock(return_value=None)
    monkeypatch.setattr(doctors_api, "write_audit_log", audit_mock)
    yield audit_mock


def test_valid_roles_includes_doctor():
    from app.api.users import VALID_ROLES
    assert "doctor" in VALID_ROLES


def _add_cert(**kw):
    db = TestSession()
    defaults = dict(
        id=kw.pop("id", 1), doctor_id=kw.pop("doctor_id", 1),
        cert_type="physician", cert_image_url="https://oss/cert.pdf",
        cert_status="pending",
    )
    defaults.update(kw)
    db.add(DoctorCertification(**defaults))
    db.commit()
    db.close()
    return defaults["id"]


def test_submit_requires_cert_image_and_type():
    # 缺 cert_type → 400
    resp = client.post(
        "/api/v1/doctors/certs",
        files={"cert_image": ("cert.pdf", b"%PDF-1.4 fake", "application/pdf")},
        headers=_token(1, "doctor"),
    )
    assert resp.status_code == 400
    assert resp.json()["code"] == 1000

    # 首次提交缺 cert_image → 400
    resp = client.post(
        "/api/v1/doctors/certs",
        data={"cert_type": "physician"},
        headers=_token(1, "doctor"),
    )
    assert resp.status_code == 400
    assert resp.json()["code"] == 1000


def test_submit_creates_pending_row(fresh_state):
    resp = client.post(
        "/api/v1/doctors/certs",
        data={"cert_type": "physician"},
        files={"cert_image": ("cert.pdf", b"%PDF-1.4 fake", "application/pdf")},
        headers=_token(1, "doctor"),
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["code"] == 0
    data = body["data"]
    assert data["cert_type"] == "physician"
    assert data["cert_status"] == "pending"
    assert data["cert_image_url"].startswith("https://fake-oss/")
    audit_mock = fresh_state
    audit_mock.assert_awaited_once()


def test_non_doctor_cannot_submit():
    resp = client.post(
        "/api/v1/doctors/certs",
        data={"cert_type": "physician"},
        files={"cert_image": ("cert.pdf", b"%PDF-1.4 fake", "application/pdf")},
        headers=_token(3, "rep"),
    )
    assert resp.status_code == 403
    body = resp.json()
    assert body["code"] == 3000
    assert "仅医生" in body["message"]


def test_me_returns_row_or_null(fresh_state):
    # 无记录 → null
    resp = client.get("/api/v1/doctors/certs/me", headers=_token(1, "doctor"))
    body = resp.json()
    assert body["code"] == 0
    assert body["data"] is None

    # 有记录 → 返回行
    _add_cert()
    resp = client.get("/api/v1/doctors/certs/me", headers=_token(1, "doctor"))
    body = resp.json()
    assert body["code"] == 0
    assert body["data"]["cert_type"] == "physician"
    assert body["data"]["cert_status"] == "pending"


def test_list_filters_and_joins(fresh_state):
    _add_cert()
    # admin 列表含 doctor_name / doctor_phone（join User）
    resp = client.get("/api/v1/doctors/certs", headers=_token(2, "admin"))
    body = resp.json()
    assert body["code"] == 0
    data = body["data"]
    assert data["total"] == 1
    assert data["items"][0]["doctor_name"] == "张医生"
    assert data["items"][0]["doctor_phone"] == "13800000001"

    # cert_status 过滤
    _add_cert(id=2, doctor_id=4, cert_status="approved")
    resp = client.get("/api/v1/doctors/certs?cert_status=approved", headers=_token(2, "admin"))
    data = resp.json()["data"]
    assert data["total"] == 1
    assert data["items"][0]["doctor_id"] == 4

    # rep → 403
    resp = client.get("/api/v1/doctors/certs", headers=_token(3, "rep"))
    assert resp.status_code == 403
    assert resp.json()["code"] == 3000


def test_review_approve_and_reject(fresh_state):
    _add_cert()
    # approve 清 reason
    resp = client.put(
        "/api/v1/doctors/certs/1/review",
        json={"verdict": "approve"},
        headers=_token(2, "admin"),
    )
    body = resp.json()
    assert body["code"] == 0
    assert body["data"]["cert_status"] == "approved"
    assert body["data"]["reject_reason"] is None
    assert body["data"]["reviewed_by"] == 2
    audit_mock = fresh_state
    audit_mock.assert_awaited_once()

    # reject 存 reason（重新建一条 pending 记录）
    _add_cert(id=2, doctor_id=4, cert_status="pending")
    resp = client.put(
        "/api/v1/doctors/certs/2/review",
        json={"verdict": "reject", "reason": "材料不清晰"},
        headers=_token(2, "admin"),
    )
    body = resp.json()
    assert body["code"] == 0
    assert body["data"]["cert_status"] == "rejected"
    assert body["data"]["reject_reason"] == "材料不清晰"


def test_review_reason_non_string_rejected(fresh_state):
    _add_cert()
    resp = client.put(
        "/api/v1/doctors/certs/1/review",
        json={"verdict": "reject", "reason": 123},
        headers=_token(2, "admin"),
    )
    assert resp.status_code == 400
    body = resp.json()
    assert body["code"] == 1000
    assert "字符串" in body["message"]
