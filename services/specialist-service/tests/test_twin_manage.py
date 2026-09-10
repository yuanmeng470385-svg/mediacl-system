"""分身管理测试（Task 4）：风格设置/启停/风格测试生成 + 从历史记录生成分身（2026-09-10）"""
import os
import sys
from datetime import datetime

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", ".."))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

os.environ.setdefault("JWT_SECRET", "test-secret-not-a-default-value")
os.environ["AUTH_DEV_MODE"] = "true"

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
from shared.models.practice import PracticeSession
from shared.models.user import User
from shared.models.visit import VisitRecord

from app.models.conversation import Conversation
import app.api.specialists as spec_api
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
    from app.models.conversation import Conversation as _Conv
    tables = [User.__table__, Specialist.__table__, _Conv.__table__,
              PracticeSession.__table__, VisitRecord.__table__]
    Base.metadata.drop_all(engine, tables=tables)
    Base.metadata.create_all(engine, tables=tables)
    db = TestSession()
    db.add_all([
        User(id=1, username="rep01", full_name="张代表", phone="13800000001", role="rep", status="active"),
        User(id=2, username="admin", full_name="管理员", phone="13800000000", role="admin", status="active"),
        User(id=3, username="medical", full_name="医学部", phone="13800000003", role="medical", status="active"),
        User(id=4, username="rep02", full_name="李代表", phone="13800000004", role="rep", status="active"),
    ])
    db.commit()
    db.close()
    monkeypatch.setitem(app.dependency_overrides, get_db, _override_db)
    # 清除其它 FakeDb 测试文件（test_specialist_list_stats.py 等）遗留的
    # get_current_user 覆盖，否则本文件 get_current_user 端点会拿到伪造的 role。
    monkeypatch.delitem(app.dependency_overrides, get_current_user, raising=False)
    audit_mock = AsyncMock(return_value=None)
    monkeypatch.setattr(spec_api, "write_audit_log", audit_mock)
    yield audit_mock


def _add_twin(**kw):
    db = TestSession()
    defaults = dict(id=kw.pop("id", 1), name="张代表分身", product_id=1, status="active",
                    representative_id=1, persona={})
    defaults.update(kw)
    db.add(Specialist(**defaults))
    db.commit()
    db.close()
    return defaults["id"]


def test_style_requires_owner():
    _add_twin(id=1, representative_id=1)
    # 非代表本人（rep02，无该分身归属）→ 403
    resp = client.put("/api/v1/specialists/1/style", json={
        "formal_level": "标准学术", "reply_length": "标准", "opening_mode": "直切主题",
    }, headers=_token(4, "rep"))
    assert resp.status_code == 403
    assert resp.json()["code"] == 3000


def test_set_style_updates_persona(fresh_state):
    _add_twin(id=1, representative_id=1, persona={})
    resp = client.put("/api/v1/specialists/1/style", json={
        "formal_level": "标准学术", "reply_length": "标准", "opening_mode": "直切主题",
    }, headers=_token(1, "rep"))
    body = resp.json()
    assert body["code"] == 0
    assert body["data"]["persona"]["style"]["formal_level"] == "标准学术"
    assert body["data"]["persona"]["style"]["opening_mode"] == "直切主题"


def test_pause_resume(fresh_state):
    _add_twin(id=1, representative_id=1, status="active")
    resp = client.post("/api/v1/specialists/1/pause", json={}, headers=_token(1, "rep"))
    assert resp.json()["data"]["status"] == "paused"
    resp = client.post("/api/v1/specialists/1/resume", json={}, headers=_token(1, "rep"))
    assert resp.json()["data"]["status"] == "active"


def test_pause_only_own_twin():
    _add_twin(id=1, representative_id=99)
    resp = client.post("/api/v1/specialists/1/pause", json={}, headers=_token(1, "rep"))
    assert resp.status_code == 403


def test_style_test_creates_twin(fresh_state):
    resp = client.post("/api/v1/specialists/style-test", json={
        "answers": [1, 2, 0, 1, 2],
    }, headers=_token(1, "rep"))
    body = resp.json()
    assert body["code"] == 0
    assert body["data"]["representative_id"] == 1
    assert body["data"]["status"] == "active"
    assert "style" in (body["data"]["persona"] or {})


def test_style_test_attaches_default_bailian_app(fresh_state, monkeypatch):
    # 演示安全批：配置了 DEFAULT_TWIN_BAILIAN_APP_ID 时风格测试分身建完即可对话
    #（挂共享官方 App 知识库），未配置时保持 None（旧行为）
    from app.config import settings as app_settings
    monkeypatch.setattr(app_settings, "DEFAULT_TWIN_BAILIAN_APP_ID", "app-default-shared")
    resp = client.post("/api/v1/specialists/style-test", json={
        "answers": [0, 1, 2, 1, 0],
    }, headers=_token(1, "rep"))
    assert resp.json()["data"]["bailian_app_id"] == "app-default-shared"

    monkeypatch.setattr(app_settings, "DEFAULT_TWIN_BAILIAN_APP_ID", "")
    resp = client.post("/api/v1/specialists/style-test", json={
        "answers": [1, 1, 1, 1, 1],
    }, headers=_token(1, "rep"))
    assert resp.json()["data"]["bailian_app_id"] is None


# ==================== 从历史记录生成分身（2026-09-10） ====================

def _seed_style_material(user_id=1):
    """三类素材：2 个专员会话（各 4 条 user 行）、1 条本人拜访（代表 6 行）、
    1 场完成陪练（rep 5 轮）；另埋 prep 机器会话与他人拜访做排除/归属用例。"""
    db = TestSession()
    for sid in ("sess-a", "sess-b"):
        for i in range(4):
            db.add(Conversation(user_id=user_id, specialist_id=None, session_id=sid,
                                role="user", content=f"关于适应症的问题{i}",
                                created_at=datetime(2026, 9, 1, 10, i)))
            db.add(Conversation(user_id=user_id, specialist_id=None, session_id=sid,
                                role="assistant", content=f"答复{i}",
                                created_at=datetime(2026, 9, 1, 10, i)))
    db.add(Conversation(user_id=user_id, specialist_id=None, session_id="visit_prep_x",
                        role="user", content="系统指令", created_at=datetime(2026, 9, 1, 11)))
    db.add(VisitRecord(id=1, user_id=user_id, visit_time=datetime(2026, 9, 2, 9),
                       status="in_progress",
                       conversation_transcript="[代表] 王主任您好，好久不见。\n[医生] 你好。\n" * 3))
    db.add(VisitRecord(id=2, user_id=4, visit_time=datetime(2026, 9, 2, 9),
                       status="in_progress", conversation_transcript="[代表] 他人拜访发言\n"))
    transcript = []
    for i in range(5):
        transcript.append({"turn": i + 1, "role": "rep", "content": f"代表发言{i}"})
        transcript.append({"turn": i + 1, "role": "ai", "content": f"医生回应{i}"})
    db.add(PracticeSession(id=1, representative_id=user_id, scenario="心内科",
                           status="completed", turn_count=5, transcript=transcript,
                           created_at=datetime(2026, 9, 3)))
    db.commit()
    db.close()


_ALL_SOURCES = [
    {"type": "chat", "id": "sess-a"},
    {"type": "chat", "id": "sess-b"},
    {"type": "visit", "id": 1},
    {"type": "practice", "id": 1},
]


def test_style_sources_lists_three_types(fresh_state):
    _seed_style_material(1)
    resp = client.get("/api/v1/specialists/style-sources", headers=_token(1, "rep"))
    body = resp.json()
    assert body["code"] == 0
    d = body["data"]
    # prep 机器会话排除；他人拜访（user_id=4）不出现
    assert sorted(c["turns"] for c in d["chats"]) == [4, 4]
    assert all("visit_prep" not in c["session_id"] for c in d["chats"])
    assert len(d["visits"]) == 1
    assert d["visits"][0]["rep_lines"] == 3
    assert len(d["practices"]) == 1
    assert d["practices"][0]["turn_count"] == 5


def test_style_from_records_creates_twin(fresh_state, monkeypatch):
    import app.services.qwen_client as qc
    monkeypatch.setattr(qc.QwenClient, "chat", lambda self, *a, **k: {
        "content": '{"name":"沉稳学术型","style":{"formal_level":"非常严谨",'
                   '"reply_length":"简洁","opening_mode":"先寒暄再进入"},'
                   '"style_profile":"开场先寒暄，短句为主"}',
        "usage": {},
    })
    monkeypatch.setattr("app.services.audit_client.count_audit_logs", AsyncMock(return_value=None))
    _seed_style_material(1)
    resp = client.post("/api/v1/specialists/style-from-records", json={
        "sources": _ALL_SOURCES,
    }, headers=_token(1, "rep"))
    body = resp.json()
    assert body["code"] == 0
    assert body["message"] == "分身已生成"
    assert body["data"]["representative_id"] == 1
    assert body["data"]["status"] == "active"
    assert body["data"]["name"] == "沉稳学术型"
    persona = body["data"]["persona"]
    assert persona["style"]["formal_level"] == "非常严谨"
    assert persona["style"]["opening_mode"] == "先寒暄再进入"
    assert persona["style_profile"].startswith("开场先寒暄")
    assert persona["generated_from"] == "records"
    assert len(persona["sources"]) == 4


def test_style_from_records_custom_name_wins(fresh_state, monkeypatch):
    import app.services.qwen_client as qc
    monkeypatch.setattr(qc.QwenClient, "chat", lambda self, *a, **k: {
        "content": '{"name":"LLM起的名","style":{},"style_profile":"x"}', "usage": {},
    })
    monkeypatch.setattr("app.services.audit_client.count_audit_logs", AsyncMock(return_value=None))
    _seed_style_material(1)
    resp = client.post("/api/v1/specialists/style-from-records", json={
        "sources": _ALL_SOURCES, "name": "我指定的名字",
    }, headers=_token(1, "rep"))
    assert resp.json()["data"]["name"] == "我指定的名字"
    # style 传空对象 → 枚举归一回默认值（与 _parse_draft 同口径）
    assert resp.json()["data"]["persona"]["style"]["formal_level"] == "标准学术"


def test_style_from_records_insufficient_material(fresh_state):
    _seed_style_material(1)
    # 单会话 4 条 < 10 条门槛
    resp = client.post("/api/v1/specialists/style-from-records", json={
        "sources": [{"type": "chat", "id": "sess-a"}],
    }, headers=_token(1, "rep"))
    assert resp.json()["code"] == 1000
    assert "素材不足" in resp.json()["message"]


def test_style_from_records_rejects_foreign_visit(fresh_state):
    _seed_style_material(1)
    # visit_id=2 是 rep02（user_id=4）的记录 → 归属校验拦截
    resp = client.post("/api/v1/specialists/style-from-records", json={
        "sources": [{"type": "visit", "id": 2}],
    }, headers=_token(1, "rep"))
    assert resp.json()["code"] == 1000
    assert "非本人" in resp.json()["message"]


def test_style_from_records_rejects_prep_chat(fresh_state):
    _seed_style_material(1)
    resp = client.post("/api/v1/specialists/style-from-records", json={
        "sources": [{"type": "chat", "id": "visit_prep_x"}],
    }, headers=_token(1, "rep"))
    assert resp.json()["code"] == 1000


def test_style_from_records_daily_limit(fresh_state, monkeypatch):
    monkeypatch.setattr("app.services.audit_client.count_audit_logs", AsyncMock(return_value=3))
    _seed_style_material(1)
    resp = client.post("/api/v1/specialists/style-from-records", json={
        "sources": _ALL_SOURCES,
    }, headers=_token(1, "rep"))
    assert resp.json()["code"] == 4002


def test_style_from_records_llm_failure_no_twin(fresh_state, monkeypatch):
    import app.services.qwen_client as qc
    monkeypatch.setattr(qc.QwenClient, "chat", lambda self, *a, **k: {"content": "not json", "usage": {}})
    monkeypatch.setattr("app.services.audit_client.count_audit_logs", AsyncMock(return_value=None))
    _seed_style_material(1)
    resp = client.post("/api/v1/specialists/style-from-records", json={
        "sources": _ALL_SOURCES,
    }, headers=_token(1, "rep"))
    assert resp.json()["code"] == 4003
    db = TestSession()
    assert db.query(Specialist).count() == 0
    db.close()
