"""分享链接生成/列表端点 + activate 计数测试（SQLite 内存库，同 test_twin_subscriptions.py 三表模式）

覆盖 8 条契约（Task 2 Step 3）：
- create 仅 rep 可建（admin/doctor → 403 code 3000）
- create 默认 30 天过期 + url_token 64 hex + twin_name/share_url 格式
- create 停用/不存在 twin → 4001
- create expire_days 校验（0/366/非整数 → ParamError code 1000）
- create 自定义 expire_days=7
- list 只返回本人链接（倒序 + add_count/twin_name）
- activate 使 add_count +1（含重复激活）
- create 审计 action=twin_share_link_create
"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", ".."))

os.environ.setdefault("JWT_SECRET", "test-secret-not-a-default-value")
os.environ["AUTH_DEV_MODE"] = "true"

from datetime import datetime, timedelta
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
from shared.models.digital_specialist import Specialist
from shared.models.doctor import DoctorConsent, DoctorTwinSubscription, ShareLink
from shared.models.product import Product
from shared.models.user import User

import app.api.twin_subscriptions as twin_api
from app.main import app


# SQLite 编译垫片（同 auth-service/tests/test_doctors.py + visit-service 模式）：
# BigInteger → INTEGER（才能自增）；JSONB → JSON（digital_specialists/products 的 JSONB 列）
@compiles(BigInteger, "sqlite")
def _compile_bigint_for_sqlite(type_, compiler, **kw):
    return "INTEGER"


@compiles(JSONB, "sqlite")
def _compile_jsonb_for_sqlite(type_, compiler, **kw):
    return "JSON"


engine = create_engine(
    "sqlite://",
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)
TestSession = sessionmaker(bind=engine, autocommit=False, autoflush=False)

TABLES = [
    User.__table__,
    Product.__table__,
    Specialist.__table__,
    DoctorTwinSubscription.__table__,
    DoctorConsent.__table__,
    ShareLink.__table__,
]


def _override_db():
    db = TestSession()
    try:
        yield db
    finally:
        db.close()


client = TestClient(app)


def _token(user_id: int, role: str = "doctor") -> dict:
    token = create_token(user_id=user_id, username=f"u{user_id}", role=role)
    return {"Authorization": f"Bearer {token}"}


def _add(*objs):
    db = TestSession()
    for o in objs:
        db.add(o)
    db.commit()
    db.close()


@pytest.fixture(autouse=True)
def fresh_state(monkeypatch):
    """每用例重建 6 张表 + 种子用户/专员 + 审计打桩；返回审计 AsyncMock"""
    Base.metadata.drop_all(engine, tables=TABLES)
    Base.metadata.create_all(engine, tables=TABLES)

    db = TestSession()
    db.add_all([
        User(id=1, username="u1", full_name="张医生", phone="13800000001",
             role="doctor", status="active"),
        User(id=2, username="u2", full_name="王医生", phone="13800000002",
             role="doctor", status="active"),
        User(id=3, username="u3", full_name="李代表", phone="13800000003",
             role="rep", status="active"),
        User(id=4, username="u4", full_name="管理员", phone="13800000004",
             role="admin", status="active"),
        Specialist(id=1, name="肿瘤专员", product_id=None, status="active",
                   compliance_level="internal"),
        Specialist(id=2, name="心血管专员", product_id=None, status="active",
                   compliance_level="internal"),
        Specialist(id=3, name="停用专员", product_id=None, status="disabled",
                   compliance_level="internal"),
    ])
    db.commit()
    db.close()

    monkeypatch.setitem(app.dependency_overrides, get_db, _override_db)
    audit_mock = AsyncMock(return_value=None)
    monkeypatch.setattr(twin_api, "write_audit_log", audit_mock)
    yield audit_mock


# ==================== create ====================

def test_create_link_requires_rep(fresh_state):
    # rep 可建
    resp = client.post("/api/v1/share-links", json={"twin_id": 1}, headers=_token(3, "rep"))
    assert resp.status_code == 200, resp.text

    # admin → 403
    resp = client.post("/api/v1/share-links", json={"twin_id": 1}, headers=_token(4, "admin"))
    assert resp.status_code == 403
    assert resp.json()["code"] == 3000

    # doctor → 403
    resp = client.post("/api/v1/share-links", json={"twin_id": 1}, headers=_token(1))
    assert resp.status_code == 403
    assert resp.json()["code"] == 3000


def test_create_link_generates_token_and_expiry(fresh_state):
    resp = client.post("/api/v1/share-links", json={"twin_id": 1}, headers=_token(3, "rep"))
    assert resp.status_code == 200, resp.text
    data = resp.json()["data"]
    assert data["twin_id"] == 1
    assert data["twin_name"] == "肿瘤专员"
    # url_token 为 32 hex（uuid.uuid4().hex；brief 注释误写 64，String(64) 仅为列上限）
    assert len(data["url_token"]) == 32
    assert all(c in "0123456789abcdef" for c in data["url_token"])
    assert data["share_url"] == f"medagent-doctor://twin/{data['url_token']}"
    # 默认 30 天过期
    expire_at = datetime.fromisoformat(data["expire_at"])
    delta = expire_at - datetime.utcnow()
    assert timedelta(days=29) < delta < timedelta(days=31)
    # 初始 add_count 为 0
    assert data["add_count"] == 0


def test_create_link_twin_inactive_4000(fresh_state):
    # 停用 twin
    resp = client.post("/api/v1/share-links", json={"twin_id": 3}, headers=_token(3, "rep"))
    assert resp.status_code == 404
    assert resp.json()["code"] == 4000


# ==================== 部署挂账 §4：share_url 前缀双形态 ====================

def test_create_link_share_url_web_landing(fresh_state, monkeypatch):
    """设 SHARE_WEB_URL_BASE → web 落地页 URL（微信内置浏览器可打开）"""
    monkeypatch.setenv("SHARE_WEB_URL_BASE", "http://192.168.1.229:3000")
    resp = client.post("/api/v1/share-links", json={"twin_id": 1}, headers=_token(3, "rep"))
    assert resp.status_code == 200, resp.text
    data = resp.json()["data"]
    assert data["share_url"] == f"http://192.168.1.229:3000/share/twin/{data['url_token']}"


def test_create_link_share_url_deep_link_without_base(fresh_state, monkeypatch):
    """不设 SHARE_WEB_URL_BASE → 保持 App 深链（本地兼容；conftest 已清根 .env 演示值）"""
    monkeypatch.delenv("SHARE_WEB_URL_BASE", raising=False)
    resp = client.post("/api/v1/share-links", json={"twin_id": 1}, headers=_token(3, "rep"))
    assert resp.status_code == 200, resp.text
    data = resp.json()["data"]
    assert data["share_url"] == f"medagent-doctor://twin/{data['url_token']}"

    # 不存在 twin
    resp = client.post("/api/v1/share-links", json={"twin_id": 999}, headers=_token(3, "rep"))
    assert resp.status_code == 404
    assert resp.json()["code"] == 4000


def test_create_link_expire_days_validation(fresh_state):
    for bad in (0, 366, "abc"):
        resp = client.post("/api/v1/share-links",
                           json={"twin_id": 1, "expire_days": bad}, headers=_token(3, "rep"))
        assert resp.status_code == 400, bad
        assert resp.json()["code"] == 1000


def test_create_link_custom_expire_days(fresh_state):
    resp = client.post("/api/v1/share-links",
                       json={"twin_id": 1, "expire_days": 7}, headers=_token(3, "rep"))
    assert resp.status_code == 200, resp.text
    expire_at = datetime.fromisoformat(resp.json()["data"]["expire_at"])
    delta = expire_at - datetime.utcnow()
    assert timedelta(days=6) < delta < timedelta(days=8)


# ==================== list ====================

def test_list_returns_only_own_links(fresh_state):
    _add(
        ShareLink(id=1, twin_id=1, url_token="t1", created_by=3, add_count=0),
        ShareLink(id=2, twin_id=2, url_token="t2", created_by=3, add_count=5),
        ShareLink(id=3, twin_id=1, url_token="t3", created_by=1, add_count=0),
    )
    resp = client.get("/api/v1/share-links", headers=_token(3, "rep"))
    assert resp.status_code == 200, resp.text
    data = resp.json()["data"]
    assert len(data) == 2
    # 按 id 倒序
    assert [item["id"] for item in data] == [2, 1]
    # 含 add_count / twin_name / share_url
    by_id = {item["id"]: item for item in data}
    assert by_id[1]["twin_name"] == "肿瘤专员"
    assert by_id[1]["add_count"] == 0
    assert by_id[2]["twin_name"] == "心血管专员"
    assert by_id[2]["add_count"] == 5
    assert by_id[2]["share_url"] == "medagent-doctor://twin/t2"
    # 含 created_at（server_default 落库，列表项非空）
    assert all(item["created_at"] for item in data)
    # 不含他人（created_by=1）链接
    assert all(item["created_by"] == 3 for item in data)


# ==================== activate 计数 ====================

def test_activate_increments_add_count(fresh_state):
    _add(ShareLink(id=1, twin_id=1, url_token="abc123", created_by=3, add_count=0))

    resp = client.post("/api/v1/share-links/abc123/activate", headers=_token(1))
    assert resp.status_code == 200, resp.text
    db = TestSession()
    assert db.query(ShareLink).filter(ShareLink.id == 1).first().add_count == 1
    db.close()

    # 重复激活继续 +1（口径=被添加次数）
    resp = client.post("/api/v1/share-links/abc123/activate", headers=_token(2))
    assert resp.status_code == 200, resp.text
    db = TestSession()
    assert db.query(ShareLink).filter(ShareLink.id == 1).first().add_count == 2
    db.close()


# ==================== 审计 ====================

def test_create_audited(fresh_state):
    resp = client.post("/api/v1/share-links", json={"twin_id": 1}, headers=_token(3, "rep"))
    assert resp.status_code == 200, resp.text
    data = resp.json()["data"]

    fresh_state.assert_awaited_once()
    call = fresh_state.call_args
    assert call.kwargs["action"] == "twin_share_link_create"
    assert call.kwargs["resource_type"] == "share_link"
    assert call.kwargs["resource_id"] == str(data["id"])
    assert call.kwargs["after_value"]["twin_id"] == 1
    assert call.kwargs["after_value"]["expire_at"] == data["expire_at"]
