"""夜间简报查询端点测试（SQLite 内存库，同 test_twin_subscriptions.py 表模式）

覆盖 5 条契约（Task 4 Step 3）：
- list 返回本人简报、按 briefing_date 倒序、分页形状 {items,total,page,page_size}
- list 非 rep（admin）→ 403
- get 详情返回简报 + twin_name
- get 他人简报 → 4001「简报不存在」
- get 不存在 id → 4001
"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", ".."))

os.environ.setdefault("JWT_SECRET", "test-secret-not-a-default-value")
os.environ["AUTH_DEV_MODE"] = "true"

from datetime import date

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
from shared.models.nightly_briefing import NightlyBriefing
from shared.models.product import Product
from shared.models.user import User

from app.main import app


# SQLite 编译垫片（同 test_briefings.py / test_twin_subscriptions.py 模式）：
# BigInteger → INTEGER（才能自增）；JSONB → JSON（JSONB 列 SQLite 渲染不了）
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
    NightlyBriefing.__table__,
]


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


def _add(*objs):
    db = TestSession()
    for o in objs:
        db.add(o)
    db.commit()
    db.close()


@pytest.fixture(autouse=True)
def fresh_state(monkeypatch):
    """每用例重建 4 张表 + 种子用户（rep1/rep3、admin2）/专员；重载 get_db"""
    Base.metadata.drop_all(engine, tables=TABLES)
    Base.metadata.create_all(engine, tables=TABLES)

    db = TestSession()
    db.add_all([
        User(id=1, username="u1", full_name="李代表", phone="13800000001",
             role="rep", status="active"),
        User(id=2, username="u2", full_name="管理员", phone="13800000002",
             role="admin", status="active"),
        User(id=3, username="u3", full_name="王代表", phone="13800000003",
             role="rep", status="active"),
        Specialist(id=1, name="肿瘤专员", product_id=None, status="active",
                   compliance_level="internal"),
        Specialist(id=2, name="心血管专员", product_id=None, status="active",
                   compliance_level="internal"),
    ])
    db.commit()
    db.close()

    monkeypatch.setitem(app.dependency_overrides, get_db, _override_db)
    yield


def test_list_returns_own_briefings_paginated(fresh_state):
    _add(
        NightlyBriefing(id=1, representative_id=1, specialist_id=1,
                        briefing_date=date(2026, 8, 17),
                        content={"summary": "s1", "doctors": []}, status="ready"),
        NightlyBriefing(id=2, representative_id=1, specialist_id=2,
                        briefing_date=date(2026, 8, 16),
                        content={"summary": "s2", "doctors": []}, status="ready"),
        NightlyBriefing(id=3, representative_id=3, specialist_id=1,
                        briefing_date=date(2026, 8, 17),
                        content={"summary": "s3", "doctors": []}, status="ready"),
    )
    resp = client.get("/api/v1/briefings", headers=_token(1, "rep"))
    assert resp.status_code == 200, resp.text
    data = resp.json()["data"]
    assert data["total"] == 2
    assert data["page"] == 1
    assert data["page_size"] == 20
    assert len(data["items"]) == 2
    # briefing_date 倒序：8/17(id=1) 在 8/16(id=2) 前
    assert [it["id"] for it in data["items"]] == [1, 2]
    # 仅本人（rep=1）简报，不含 rep=3 的 id=3
    assert all(it["representative_id"] == 1 for it in data["items"])
    # join Specialist 取 twin_name
    assert [it["twin_name"] for it in data["items"]] == ["肿瘤专员", "心血管专员"]


def test_list_rejects_non_rep(fresh_state):
    resp = client.get("/api/v1/briefings", headers=_token(2, "admin"))
    assert resp.status_code == 403
    assert resp.json()["code"] == 3000


def test_get_detail_returns_briefing_with_twin_name(fresh_state):
    _add(
        NightlyBriefing(id=1, representative_id=1, specialist_id=1,
                        briefing_date=date(2026, 8, 17),
                        content={"summary": "s", "doctors": []}, status="ready"),
    )
    resp = client.get("/api/v1/briefings/1", headers=_token(1, "rep"))
    assert resp.status_code == 200, resp.text
    data = resp.json()["data"]
    assert data["id"] == 1
    assert data["representative_id"] == 1
    assert data["specialist_id"] == 1
    assert data["briefing_date"] == "2026-08-17"
    assert data["status"] == "ready"
    assert data["twin_name"] == "肿瘤专员"


def test_get_other_rep_briefing_404_business(fresh_state):
    _add(
        NightlyBriefing(id=1, representative_id=3, specialist_id=1,
                        briefing_date=date(2026, 8, 17),
                        content={"summary": "s", "doctors": []}, status="ready"),
    )
    resp = client.get("/api/v1/briefings/1", headers=_token(1, "rep"))
    assert resp.status_code == 422
    assert resp.json()["code"] == 4001


def test_get_missing_4001(fresh_state):
    resp = client.get("/api/v1/briefings/999", headers=_token(1, "rep"))
    assert resp.status_code == 422
    assert resp.json()["code"] == 4001
