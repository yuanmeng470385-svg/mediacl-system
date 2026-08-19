"""承诺书签署端点测试：发送验证码 + 校验签署 + 审计留痕 + 仅 rep"""
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
from shared.models.qualification import RepresentativeQualification
from shared.models.user import User

import app.api.commitment as commit_api
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


class _FakeStore:
    """内存版 code store（等价 consume 语义）"""

    def __init__(self):
        self.codes = {}
        self.attempts = {}

    def save(self, phone, code, ttl, cooldown):
        self.codes[phone] = code
        return True

    def in_cooldown(self, phone):
        return 0

    def consume(self, phone, code, max_attempts):
        saved = self.codes.get(phone)
        if saved is None:
            return "notfound"
        if saved == code:
            del self.codes[phone]
            return "matched"
        return "mismatch"

    def drop(self, phone):
        self.codes.pop(phone, None)


class _FakeSender:
    def send_code(self, phone, code):
        return None


@pytest.fixture(autouse=True)
def fresh_state(monkeypatch):
    tables = [User.__table__, RepresentativeQualification.__table__]
    Base.metadata.drop_all(engine, tables=tables)
    Base.metadata.create_all(engine, tables=tables)
    db = TestSession()
    db.add_all([
        User(id=1, username="rep01", full_name="张代表", phone="13800000001", role="rep", status="active"),
        User(id=2, username="admin", full_name="管理员", phone="13800000000", role="admin", status="active"),
    ])
    db.commit()
    db.add(RepresentativeQualification(
        representative_id=1, education_cert="https://oss/edu.pdf",
        audit_status="approved", filing_number="F-1", commitment_signed=False,
    ))
    db.commit()
    db.close()

    monkeypatch.setitem(app.dependency_overrides, get_db, _override_db)
    store = _FakeStore()
    # 注意：get_code_store/get_sender 是 FastAPI 依赖函数对象，必须覆盖
    # app.dependency_overrides（monkeypatch 模块属性对 Depends() 捕获的函数对象无效）
    from app.api.auth import get_code_store, get_sender
    monkeypatch.setitem(app.dependency_overrides, get_code_store, lambda: store)
    monkeypatch.setitem(app.dependency_overrides, get_sender, lambda: _FakeSender())
    audit_mock = AsyncMock(return_value=None)
    monkeypatch.setattr(commit_api, "write_audit_log", audit_mock)
    yield store, audit_mock


def test_send_code_returns_expire_seconds(fresh_state):
    resp = client.post("/api/v1/qualifications/commitment/send-code", json={},
                       headers=_token(1, "rep"))
    body = resp.json()
    assert body["code"] == 0
    assert body["data"]["expire_seconds"] == 300
    store, _ = fresh_state
    assert "13800000001" in store.codes


def test_sign_success(fresh_state):
    store, audit_mock = fresh_state
    store.save("13800000001", "123456", 300, 60)
    resp = client.post("/api/v1/qualifications/commitment/sign", json={"code": "123456"},
                       headers=_token(1, "rep"))
    body = resp.json()
    assert body["code"] == 0
    assert body["data"]["commitment_signed"] is True
    audit_mock.assert_awaited_once()


def test_sign_wrong_code(fresh_state):
    store, _ = fresh_state
    store.save("13800000001", "123456", 300, 60)
    resp = client.post("/api/v1/qualifications/commitment/sign", json={"code": "000000"},
                       headers=_token(1, "rep"))
    assert resp.status_code == 400
    assert resp.json()["code"] == 1000
    assert "验证码" in resp.json()["message"]


def test_sign_requires_rep():
    resp = client.post("/api/v1/qualifications/commitment/sign", json={"code": "123456"},
                       headers=_token(2, "admin"))
    assert resp.status_code == 403
