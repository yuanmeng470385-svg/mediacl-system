"""医生端分身订阅 + 分享链接激活端点测试（SQLite 内存库，同 test_doctors.py 双表模式）

覆盖 8 条契约（Task 6 Step 3）：
- activate 返回 twin + subscribed 标志（twin 手写 dict，不含内部字段）
- activate token 不存在/过期 → 4001
- subscribe 缺 consent → 400
- subscribe 建订阅行 + consent 行 + 审计
- subscribe 同 twin 幂等（不建第二行、consent 不重复）
- subscribe 停用/不存在 twin → 4001
- list 只返回本人订阅并 join twin 信息
- toggle 阻断/恢复 + 审计
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


# ==================== activate ====================

def test_activate_returns_twin_and_subscribed_flag(fresh_state):
    _add(
        ShareLink(id=1, twin_id=1, url_token="abc123", created_by=1),
        DoctorTwinSubscription(id=1, doctor_id=1, twin_id=1, status="subscribed",
                               consent_version="1.0", consent_at=datetime.utcnow()),
    )
    resp = client.post("/api/v1/share-links/abc123/activate", headers=_token(1))
    assert resp.status_code == 200, resp.text
    data = resp.json()["data"]
    assert data["twin"] == {"id": 1, "name": "肿瘤专员", "status": "active"}
    assert "bailian_app_id" not in data["twin"]
    assert data["subscribed"] is True
    assert data["subscription_status"] == "subscribed"


def test_activate_unknown_or_expired_token_4000(fresh_state):
    # 未知 token
    resp = client.post("/api/v1/share-links/nope/activate", headers=_token(1))
    assert resp.status_code == 404
    assert resp.json()["code"] == 4000

    # 已过期 token
    _add(ShareLink(id=1, twin_id=1, url_token="expired", created_by=1,
                   expire_at=datetime.utcnow() - timedelta(hours=1)))
    resp = client.post("/api/v1/share-links/expired/activate", headers=_token(1))
    assert resp.status_code == 404
    assert resp.json()["code"] == 4000


# ==================== subscribe ====================

def test_subscribe_requires_consent(fresh_state):
    # consent_agreed 缺失
    resp = client.post("/api/v1/twin-subscriptions", json={"twin_id": 1}, headers=_token(1))
    assert resp.status_code == 400
    assert resp.json()["code"] == 1000

    # consent_agreed False
    resp = client.post("/api/v1/twin-subscriptions",
                       json={"twin_id": 1, "consent_agreed": False}, headers=_token(1))
    assert resp.status_code == 400
    assert resp.json()["code"] == 1000


def test_subscribe_creates_subscription_and_consent(fresh_state):
    resp = client.post("/api/v1/twin-subscriptions",
                       json={"twin_id": 1, "consent_agreed": True}, headers=_token(1))
    assert resp.status_code == 200, resp.text
    data = resp.json()["data"]
    assert data["doctor_id"] == 1
    assert data["twin_id"] == 1
    assert data["status"] == "subscribed"
    assert data["consent_version"] == "1.0"

    db = TestSession()
    subs = db.query(DoctorTwinSubscription).all()
    consents = db.query(DoctorConsent).all()
    db.close()
    assert len(subs) == 1
    assert len(consents) == 1
    assert consents[0].doctor_id == 1
    assert consents[0].twin_id == 1
    assert consents[0].consent_type == "twin"
    assert consents[0].version == "1.0"

    fresh_state.assert_awaited_once()
    assert fresh_state.call_args.kwargs["action"] == "twin_subscribe"


def test_subscribe_idempotent_for_same_twin(fresh_state):
    r1 = client.post("/api/v1/twin-subscriptions",
                     json={"twin_id": 1, "consent_agreed": True}, headers=_token(1))
    assert r1.status_code == 200
    sub_id = r1.json()["data"]["id"]

    r2 = client.post("/api/v1/twin-subscriptions",
                     json={"twin_id": 1, "consent_agreed": True}, headers=_token(1))
    assert r2.status_code == 200
    assert r2.json()["data"]["id"] == sub_id

    db = TestSession()
    subs = db.query(DoctorTwinSubscription).all()
    consents = db.query(DoctorConsent).all()
    db.close()
    assert len(subs) == 1      # 不建第二行
    assert len(consents) == 1  # consent 不重复

    assert fresh_state.await_count == 1  # 幂等分支不写审计


def test_subscribe_inactive_twin_4000(fresh_state):
    # 停用 twin
    resp = client.post("/api/v1/twin-subscriptions",
                       json={"twin_id": 3, "consent_agreed": True}, headers=_token(1))
    assert resp.status_code == 404
    assert resp.json()["code"] == 4000

    # 不存在 twin
    resp = client.post("/api/v1/twin-subscriptions",
                       json={"twin_id": 999, "consent_agreed": True}, headers=_token(1))
    assert resp.status_code == 404
    assert resp.json()["code"] == 4000


# ==================== list ====================

def test_list_returns_own_subscriptions_joined(fresh_state):
    _add(
        DoctorTwinSubscription(id=1, doctor_id=1, twin_id=1, status="subscribed",
                               consent_version="1.0", consent_at=datetime.utcnow()),
        DoctorTwinSubscription(id=2, doctor_id=1, twin_id=2, status="blocked",
                               consent_version="1.0", consent_at=datetime.utcnow()),
        DoctorTwinSubscription(id=3, doctor_id=2, twin_id=1, status="subscribed",
                               consent_version="1.0", consent_at=datetime.utcnow()),
    )
    resp = client.get("/api/v1/twin-subscriptions", headers=_token(1))
    assert resp.status_code == 200, resp.text
    data = resp.json()["data"]
    assert len(data) == 2
    by_twin = {item["twin_id"]: item for item in data}
    assert by_twin[1]["twin_name"] == "肿瘤专员"
    assert by_twin[1]["twin_status"] == "active"
    assert by_twin[2]["twin_name"] == "心血管专员"
    assert by_twin[2]["twin_status"] == "active"
    # 不含他人（doctor_id=2）的订阅行
    assert all(item["doctor_id"] == 1 for item in data)


# ==================== toggle ====================

def test_toggle_block_and_restore_audited(fresh_state):
    _add(DoctorTwinSubscription(id=1, doctor_id=1, twin_id=1, status="subscribed",
                                consent_version="1.0", consent_at=datetime.utcnow()))

    resp = client.post("/api/v1/twin-subscriptions/1/toggle",
                       json={"status": "blocked"}, headers=_token(1))
    assert resp.status_code == 200, resp.text
    assert resp.json()["data"]["status"] == "blocked"

    resp = client.post("/api/v1/twin-subscriptions/1/toggle",
                       json={"status": "subscribed"}, headers=_token(1))
    assert resp.status_code == 200
    assert resp.json()["data"]["status"] == "subscribed"

    assert fresh_state.await_count == 2
    actions = [c.kwargs["action"] for c in fresh_state.await_args_list]
    assert actions == ["twin_subscription_toggle", "twin_subscription_toggle"]
    # before/after 双留痕：迁移前旧状态（subscribed → blocked → subscribed）
    assert [c.kwargs["before_value"]["status"] for c in fresh_state.await_args_list] == [
        "subscribed", "blocked",
    ]
    assert [c.kwargs["after_value"]["status"] for c in fresh_state.await_args_list] == [
        "blocked", "subscribed",
    ]
