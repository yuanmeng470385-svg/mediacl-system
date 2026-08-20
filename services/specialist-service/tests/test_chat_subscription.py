"""chat 订阅硬校验测试（Task 4 一期 B 挂账收尾）：doctor 未订阅不可 chat"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", ".."))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

os.environ.setdefault("JWT_SECRET", "test-secret-not-a-default-value")
os.environ["AUTH_DEV_MODE"] = "true"

from datetime import datetime
from unittest.mock import AsyncMock

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import BigInteger, create_engine
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.ext.compiler import compiles
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from shared.common.auth import create_token, get_current_user
from shared.common.db_session import get_db
from shared.models.base import Base
from shared.models.digital_specialist import Specialist
from shared.models.doctor import DoctorTwinSubscription
from shared.models.product import Product
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

TABLES = [
    User.__table__,
    Product.__table__,
    Specialist.__table__,
    DoctorTwinSubscription.__table__,
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


@pytest.fixture(autouse=True)
def fresh_state(monkeypatch):
    Base.metadata.drop_all(engine, tables=TABLES)
    Base.metadata.create_all(engine, tables=TABLES)

    db = TestSession()
    db.add_all([
        User(id=1, username="u1", full_name="李代表", phone="13800000001",
             role="rep", status="active"),
        User(id=2, username="u2", full_name="王医生", phone="13800000002",
             role="doctor", status="active"),
    ])
    db.commit()
    db.close()

    monkeypatch.setitem(app.dependency_overrides, get_db, _override_db)
    # 清除其它 FakeDb 测试文件遗留的 get_current_user 覆盖（chat 端点走
    # get_current_user 依赖，伪造 role 会绕过真实 token 身份解析）
    monkeypatch.delitem(app.dependency_overrides, get_current_user, raising=False)
    yield


def test_doctor_chat_requires_subscription():
    db = TestSession()
    db.add(Specialist(id=1, name="心内科专员", product_id=1, status="active",
                      bailian_app_id="app-1", is_official=True))
    db.commit()
    db.close()
    resp = client.post("/api/v1/specialists/1/chat", json={"question": "高血压用药"},
                       headers=_token(2, "doctor"))
    assert resp.status_code == 403
    assert resp.json()["code"] == 3000


def test_doctor_chat_ok_when_subscribed(fresh_state, monkeypatch):
    db = TestSession()
    db.add(Specialist(id=1, name="心内科专员", product_id=1, status="active",
                      bailian_app_id="app-1", is_official=True))
    db.add(DoctorTwinSubscription(id=1, doctor_id=2, twin_id=1, status="subscribed",
                                  consent_version="1.0", consent_at=datetime.utcnow()))
    db.commit()
    db.close()
    # monkeypatch 答案生成器避免真实 LLM
    from app.core.answer_generator import AnswerGenerator
    monkeypatch.setattr(AnswerGenerator, "generate", AsyncMock(return_value={
        "answer": "建议遵医嘱", "citations": [], "evidence_level": "B",
        "session_id": "s1", "latency_ms": 10, "blocked": False, "violations": [],
    }))
    resp = client.post("/api/v1/specialists/1/chat", json={"question": "高血压用药"},
                       headers=_token(2, "doctor"))
    assert resp.status_code == 200
    assert resp.json()["code"] == 0


def test_rep_chat_not_restricted(fresh_state, monkeypatch):
    db = TestSession()
    db.add(Specialist(id=1, name="心内科专员", product_id=1, status="active",
                      bailian_app_id="app-1", is_official=True))
    db.commit()
    db.close()
    from app.core.answer_generator import AnswerGenerator
    monkeypatch.setattr(AnswerGenerator, "generate", AsyncMock(return_value={
        "answer": "回答", "citations": [], "evidence_level": "B",
        "session_id": "s1", "latency_ms": 10, "blocked": False, "violations": [],
    }))
    resp = client.post("/api/v1/specialists/1/chat", json={"question": "用药"},
                       headers=_token(1, "rep"))
    assert resp.status_code == 200
