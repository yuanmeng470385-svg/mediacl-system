"""合规监控端点测试（Task 2）：聚合日报/趋势/待复核名单"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", ".."))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

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
from shared.models.compliance import ComplianceBlock, ComplianceRule
from shared.models.user import User

import app.api.monitor as monitor_api
from app.main import app


@compiles(BigInteger, "sqlite")
def _compile_bigint_for_sqlite(type_, compiler, **kw):
    return "INTEGER"


# ComplianceRule.content / ComplianceBlock.context 是 JSONB，SQLite 渲染不了
# （SQLAlchemy 2.0 无 JSONB 兜底），参照 auth/specialist 测试模式加编译垫片。
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
    tables = [User.__table__, ComplianceRule.__table__, ComplianceBlock.__table__]
    Base.metadata.drop_all(engine, tables=tables)
    Base.metadata.create_all(engine, tables=tables)
    db = TestSession()
    db.add_all([
        User(id=1, username="rep01", full_name="张代表", phone="13800000001", role="rep", status="active", region="华东"),
        User(id=2, username="admin", full_name="管理员", phone="13800000000", role="admin", status="active", region="总部"),
        User(id=3, username="compliance", full_name="合规部", phone="13800000003", role="compliance", status="active", region="总部"),
    ])
    db.commit()
    db.close()
    monkeypatch.setitem(app.dependency_overrides, get_db, _override_db)
    yield


def _add_block(**kw):
    db = TestSession()
    defaults = dict(
        id=kw.pop("id", 1), user_id=1, service_name="specialist",
        content="违规内容", rule_code="R001", rule_name="保证疗效",
        severity="high", action="reject", context={"snippet": "x"},
        blocked_at=datetime.utcnow(),
    )
    defaults.update(kw)
    db.add(ComplianceBlock(**defaults))
    db.commit()
    db.close()


def test_daily_summary_requires_admin():
    resp = client.get("/api/v1/compliance/daily-summary", headers=_token(1, "rep"))
    assert resp.status_code == 403
    assert resp.json()["code"] == 3000


def test_daily_summary_aggregates():
    _add_block(id=1, rule_code="R001")
    _add_block(id=2, rule_code="R001")
    _add_block(id=3, rule_code="R009")
    # warn 只记录在案不拦截 —— 不计入拦截总量/规则聚合
    _add_block(id=4, rule_code="R005", action="warn")
    resp = client.get("/api/v1/compliance/daily-summary", headers=_token(3, "compliance"))
    body = resp.json()
    assert body["code"] == 0
    by_rule = {r["rule_code"]: r["count"] for r in body["data"]["by_rule"]}
    assert by_rule["R001"] == 2
    assert by_rule["R009"] == 1
    assert "R005" not in by_rule
    assert body["data"]["total"] == 3


def test_trends_rep_ranking():
    _add_block(id=1, user_id=1, rule_code="R001")
    resp = client.get("/api/v1/compliance/trends", headers=_token(2, "admin"))
    body = resp.json()
    assert body["code"] == 0
    assert body["data"]["rep_ranking"][0]["rep_name"] == "张代表"
    assert body["data"]["rep_ranking"][0]["count"] == 1
    assert body["data"]["time_series"]  # 至少一个数据点


def test_review_queue_requires_admin():
    resp = client.get("/api/v1/compliance/review-queue", headers=_token(1, "rep"))
    assert resp.status_code == 403


def test_review_queue_marks_high_blockers():
    # 同一 user 近窗口内 ≥ 阈值条拦截 → 进入待复核
    for i in range(6):
        _add_block(id=i + 1, user_id=1, rule_code="R001")
    resp = client.get("/api/v1/compliance/review-queue", headers=_token(3, "compliance"))
    body = resp.json()
    assert body["code"] == 0
    items = body["data"]["items"]
    assert any(item["user_id"] == 1 for item in items)
    assert items[0]["block_count"] >= 5


def test_review_queue_below_threshold_excluded():
    _add_block(id=1, user_id=1)
    _add_block(id=2, user_id=1)
    resp = client.get("/api/v1/compliance/review-queue", headers=_token(3, "compliance"))
    body = resp.json()
    assert body["code"] == 0
    assert body["data"]["items"] == []
