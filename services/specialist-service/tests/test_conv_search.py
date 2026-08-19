"""对话全文检索测试（Task 3）：多条件筛选 + 完整上下文 + 权限"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", ".."))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

os.environ.setdefault("JWT_SECRET", "test-secret-not-a-default-value")
os.environ["AUTH_DEV_MODE"] = "true"

from datetime import datetime

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
from shared.models.product import Product
from shared.models.user import User

import app.api.conversations as conv_api
from app.main import app
from app.models.conversation import Conversation


@compiles(BigInteger, "sqlite")
def _compile_bigint_for_sqlite(type_, compiler, **kw):
    return "INTEGER"


# Conversation/Specialist/Product 含 JSONB 列，SQLite 渲染不了，需同款垫片
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
    tables = [User.__table__, Product.__table__, Specialist.__table__, Conversation.__table__]
    Base.metadata.drop_all(engine, tables=tables)
    Base.metadata.create_all(engine, tables=tables)
    db = TestSession()
    db.add_all([
        User(id=1, username="rep01", full_name="张代表", phone="13800000001", role="rep", status="active"),
        User(id=2, username="admin", full_name="管理员", phone="13800000000", role="admin", status="active"),
        User(id=3, username="compliance", full_name="合规部", phone="13800000003", role="compliance", status="active"),
    ])
    db.add(Specialist(id=1, name="心内科专员", product_id=1, status="active"))
    db.commit()
    db.close()
    monkeypatch.setitem(app.dependency_overrides, get_db, _override_db)
    yield


def _add_conv(**kw):
    db = TestSession()
    defaults = dict(
        id=kw.pop("id", 1), user_id=1, specialist_id=1, session_id="s1",
        role="user", content="高血压用药方案", citations=None,
        compliance_result=None, created_at=datetime.utcnow(),
    )
    defaults.update(kw)
    db.add(Conversation(**defaults))
    db.commit()
    db.close()


def test_search_requires_admin():
    resp = client.get("/api/v1/conversations/search?keyword=高血压", headers=_token(1, "rep"))
    assert resp.status_code == 403


def test_search_by_keyword():
    _add_conv(id=1, content="高血压用药方案讨论")
    _add_conv(id=2, content="糖尿病患者饮食")
    resp = client.get("/api/v1/conversations/search?keyword=高血压", headers=_token(2, "admin"))
    body = resp.json()
    assert body["code"] == 0
    assert body["data"]["total"] == 1
    assert body["data"]["items"][0]["content"] == "高血压用药方案讨论"


def test_search_filters_by_rep():
    _add_conv(id=1, content="问题一", user_id=1)
    _add_conv(id=2, content="问题二", user_id=99)
    resp = client.get("/api/v1/conversations/search?user_id=1", headers=_token(3, "compliance"))
    body = resp.json()
    assert body["data"]["total"] == 1
    assert body["data"]["items"][0]["content"] == "问题一"


def test_search_filters_by_specialist():
    _add_conv(id=1, content="问题一", specialist_id=1)
    _add_conv(id=2, content="问题二", specialist_id=2)
    resp = client.get("/api/v1/conversations/search?specialist_id=1", headers=_token(2, "admin"))
    body = resp.json()
    assert body["data"]["total"] == 1


def test_search_returns_full_context():
    _add_conv(id=1, content="问题", session_id="s1", role="user")
    _add_conv(id=2, content="回答", session_id="s1", role="assistant")
    resp = client.get("/api/v1/conversations/search?keyword=问题", headers=_token(2, "admin"))
    body = resp.json()
    assert body["code"] == 0
    item = body["data"]["items"][0]
    assert item["context"] and len(item["context"]) == 2  # 完整会话上下文
    assert {c["role"] for c in item["context"]} == {"user", "assistant"}
