"""Skill 风格提取测试（三期 P Task 1）：extract-draft 端点 + 每日限额 + LLM 输出防线。
LLM 全程 monkeypatch QwenClient.chat，不烧真实调用。"""
import json
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

from shared.common.auth import create_token
from shared.common.db_session import get_db
from shared.models.base import Base
from shared.models.practice import PracticeSession
from shared.models.user import User
from shared.models.visit import VisitRecord

from app.services import qwen_client as qc
import app.api.skill_packages as sp_api
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
    tables = [User.__table__, PracticeSession.__table__, VisitRecord.__table__]
    Base.metadata.drop_all(engine, tables=tables)
    Base.metadata.create_all(engine, tables=tables)
    db = TestSession()
    db.add_all([
        User(id=1, username="rep01", full_name="张代表", phone="13800000001", role="rep", status="active"),
        User(id=2, username="rep02", full_name="李代表", phone="13800000002", role="rep", status="active"),
        User(id=3, username="admin", full_name="管理员", phone="13800000000", role="admin", status="active"),
    ])
    db.commit()
    db.close()
    monkeypatch.setitem(app.dependency_overrides, get_db, _override_db)
    write_mock = AsyncMock(return_value=None)
    count_mock = AsyncMock(return_value=0)  # 限额默认未用
    monkeypatch.setattr(sp_api, "write_audit_log", write_mock)
    monkeypatch.setattr(sp_api, "count_audit_logs", count_mock)
    yield write_mock


def _add_session(sid: int, rep_count: int, owner: int = 1, status: str = "completed",
                 turn_count: int = None):
    """建一个陪练会话：rep/ai 轮次成对写入 transcript，turn_count 默认= rep 轮数"""
    transcript = []
    for i in range(1, rep_count + 1):
        transcript.append({"turn": i, "role": "rep", "content": f"代表第{i}轮发言，引用循证数据"})
        transcript.append({"turn": i, "role": "ai", "content": f"医生第{i}轮回应"})
    db = TestSession()
    db.add(PracticeSession(
        id=sid, representative_id=owner, skill_id=None, scenario="心内科推广",
        status=status, turn_count=rep_count if turn_count is None else turn_count,
        transcript=transcript,
    ))
    db.commit()
    db.close()


def _add_visit(vid: int, rep_lines: int, owner: int = 1, status: str = "in_progress"):
    """建一条拜访记录（2026-09-10 素材扩拜访）：[代表]/[医生] 行交错写入转写。"""
    lines = []
    for i in range(1, rep_lines + 1):
        lines.append(f"[代表] 拜访中代表第{i}条发言，引用循证数据")
        lines.append(f"[医生] 医生第{i}条回应")
    db = TestSession()
    db.add(VisitRecord(id=vid, user_id=owner, visit_time=datetime(2026, 9, 5, 10),
                       status=status, conversation_transcript="\n".join(lines) + "\n"))
    db.commit()
    db.close()


_DRAFT = {
    "name": "亲和力型",
    "description": "心内科",
    "content": "摘自本人陪练对话的话术片段",
    "style_tags": ["亲和力"],
    "skill_weights": {"formal_level": "标准学术", "reply_length": "标准", "opening_mode": "直切主题"},
}

# 全部枚举字面量（决策 3/12）——prompt 必须逐字列出，防漂移
_ALL_ENUMS = [
    "严谨学术", "亲和力", "幽默", "专业",
    "非常严谨", "标准学术", "略带亲和力",
    "简洁", "标准", "详尽",
    "直切主题", "先寒暄再进入",
]


def _fake_chat(captured: dict, draft: dict = None, raw: str = None):
    def chat(self, messages, **kwargs):
        captured["messages"] = messages
        captured["kwargs"] = kwargs
        content = raw if raw is not None else json.dumps(draft or _DRAFT, ensure_ascii=False)
        return {"content": content, "usage": {}}
    return chat


def test_extract_requires_rep():
    resp = client.post("/api/v1/skill-packages/extract-draft", json={"session_ids": [1]},
                       headers=_token(3, "admin"))
    assert resp.status_code == 403
    assert resp.json()["code"] == 3000


def test_extract_success_prompt_and_fields(fresh_state, monkeypatch):
    _add_session(1, rep_count=10)
    captured = {}
    monkeypatch.setattr(qc.QwenClient, "chat", _fake_chat(captured))
    resp = client.post("/api/v1/skill-packages/extract-draft", json={"session_ids": [1]},
                       headers=_token(1, "rep"))
    body = resp.json()
    assert body["code"] == 0
    data = body["data"]
    # 草稿字段齐全，与发布表单 schema 硬对齐（决策 3）
    assert data["name"] == "亲和力型"
    assert data["description"] == "心内科"
    assert data["content"] == "摘自本人陪练对话的话术片段"
    assert data["style_tags"] == ["亲和力"]
    assert data["skill_weights"] == {
        "formal_level": "标准学术", "reply_length": "标准", "opening_mode": "直切主题",
    }
    # prompt 防线：注入防护声明 + 全部枚举逐字列出（决策 3/12）
    system, user = captured["messages"][0]["content"], captured["messages"][1]["content"]
    assert "<user_content>" in system
    for v in _ALL_ENUMS:
        assert v in system, f"枚举 {v} 未在 prompt 中列出"
    # 素材仅 rep 轮次且 <user_content> 包裹；ai 轮次不进 prompt
    assert "<user_content>" in user
    assert "代表第1轮发言" in user
    assert "医生第1轮回应" not in user
    # LLM 调用参数照 _llm_score 先例
    assert captured["kwargs"]["model"] == "qwen-turbo"
    assert captured["kwargs"]["temperature"] == 0.3
    assert captured["kwargs"]["max_tokens"] == 2000
    # 终审 Important（2026-08-31）：默认 30s 会使网关 120s 预算不可达，钉住 90s
    assert captured["kwargs"]["timeout"] == 90.0
    # 成功后写审计（action + session_ids + name，决策 4 限额计数数据源）
    fresh_state.assert_awaited_once()
    _, kwargs = fresh_state.call_args
    assert kwargs["action"] == "skill_extract_draft"
    assert kwargs["user_id"] == 1
    assert kwargs["after_value"] == {"session_ids": [1], "visit_ids": [], "name": "亲和力型"}


def test_extract_rejects_invalid_session_ids(fresh_state):
    for bad in ([], list(range(1, 12)), ["a"], "1,2"):
        resp = client.post("/api/v1/skill-packages/extract-draft", json={"session_ids": bad},
                           headers=_token(1, "rep"))
        assert resp.status_code == 400, f"{bad} 应被参数校验拒绝"
        assert resp.json()["code"] == 1000


def test_extract_rejects_other_users_session(fresh_state):
    _add_session(1, rep_count=6, owner=2)
    resp = client.post("/api/v1/skill-packages/extract-draft", json={"session_ids": [1]},
                       headers=_token(1, "rep"))
    assert resp.status_code == 400
    assert resp.json()["code"] == 1000


def test_extract_rejects_incomplete_session(fresh_state):
    _add_session(1, rep_count=6, status="in_progress")
    resp = client.post("/api/v1/skill-packages/extract-draft", json={"session_ids": [1]},
                       headers=_token(1, "rep"))
    assert resp.status_code == 400
    assert resp.json()["code"] == 1000


def test_extract_rejects_session_below_min_turns(fresh_state):
    _add_session(1, rep_count=6, turn_count=2)
    resp = client.post("/api/v1/skill-packages/extract-draft", json={"session_ids": [1]},
                       headers=_token(1, "rep"))
    assert resp.status_code == 400
    assert resp.json()["code"] == 1000


def test_extract_rejects_insufficient_rep_turns(fresh_state):
    # 单会话过 3 轮门槛，但合计 rep 发言 5 条 < 10 → 引导先去陪练
    _add_session(1, rep_count=5)
    resp = client.post("/api/v1/skill-packages/extract-draft", json={"session_ids": [1]},
                       headers=_token(1, "rep"))
    assert resp.status_code == 400
    assert "对话轮次不足" in resp.json()["message"]


def test_extract_merges_sessions_until_enough_turns(fresh_state, monkeypatch):
    # 两个会话各 5 条 rep 发言，合计 10 条 → 放行（门槛按合并后口径）
    _add_session(1, rep_count=5)
    _add_session(2, rep_count=5)
    captured = {}
    monkeypatch.setattr(qc.QwenClient, "chat", _fake_chat(captured))
    resp = client.post("/api/v1/skill-packages/extract-draft", json={"session_ids": [2, 1]},
                       headers=_token(1, "rep"))
    assert resp.json()["code"] == 0
    user = captured["messages"][1]["content"]
    assert "代表第1轮发言" in user  # 两会话素材都在（按时间正序合并）


def test_extract_filters_out_of_range_enums(fresh_state, monkeypatch):
    _add_session(1, rep_count=10)
    captured = {}
    monkeypatch.setattr(qc.QwenClient, "chat", _fake_chat(captured, draft={
        "name": "越界草稿", "description": "心内科", "content": "素材",
        "style_tags": ["亲和力", "浮夸", 42],
        "skill_weights": {"formal_level": "超级随意", "reply_length": "超长",
                          "opening_mode": "先寒暄", "extra": "丢弃"},
    }))
    resp = client.post("/api/v1/skill-packages/extract-draft", json={"session_ids": [1]},
                       headers=_token(1, "rep"))
    body = resp.json()
    assert body["code"] == 0
    data = body["data"]
    # 越界 style_tags 丢弃，越界权重回退默认（决策 3：宁默认不报错）
    assert data["style_tags"] == ["亲和力"]
    assert data["skill_weights"] == {
        "formal_level": "标准学术", "reply_length": "标准", "opening_mode": "直切主题",
    }


def test_extract_keeps_legal_non_default_enums(fresh_state, monkeypatch):
    """防回归：合法非默认枚举值必须原样存活，不被白名单回退改写。
    曾因 VALID_OPENING 写成 暝（U+669D）而 prompt/specialists.py 均为 暄（U+6684），
    导致 LLM 输出合法值"先寒暄再进入"时恒被静默回退"直切主题"。"""
    _add_session(1, rep_count=10)
    captured = {}
    monkeypatch.setattr(qc.QwenClient, "chat", _fake_chat(captured, draft={
        "name": "幽默详尽风", "description": "心内科", "content": "素材",
        "style_tags": ["幽默"],
        "skill_weights": {"formal_level": "非常严谨", "reply_length": "详尽",
                          "opening_mode": "先寒暄再进入"},
    }))
    resp = client.post("/api/v1/skill-packages/extract-draft", json={"session_ids": [1]},
                       headers=_token(1, "rep"))
    body = resp.json()
    assert body["code"] == 0
    data = body["data"]
    assert data["style_tags"] == ["幽默"]
    assert data["skill_weights"] == {
        "formal_level": "非常严谨", "reply_length": "详尽", "opening_mode": "先寒暄再进入",
    }


def test_extract_llm_missing_content_400(fresh_state, monkeypatch):
    _add_session(1, rep_count=10)
    captured = {}
    monkeypatch.setattr(qc.QwenClient, "chat", _fake_chat(captured, draft={
        "name": "缺内容", "description": "心内科",
        "skill_weights": {"formal_level": "标准学术"},
    }))
    resp = client.post("/api/v1/skill-packages/extract-draft", json={"session_ids": [1]},
                       headers=_token(1, "rep"))
    # LLM 输出过不了 _validate_release_payload → 400，不降级半残草稿
    assert resp.status_code == 400
    assert resp.json()["code"] == 1000
    fresh_state.assert_not_awaited()  # 失败不写审计 → 不耗额度


def test_extract_llm_garbage_returns_retryable_error(fresh_state, monkeypatch):
    _add_session(1, rep_count=10)
    captured = {}
    monkeypatch.setattr(qc.QwenClient, "chat", _fake_chat(captured, raw="not json at all"))
    resp = client.post("/api/v1/skill-packages/extract-draft", json={"session_ids": [1]},
                       headers=_token(1, "rep"))
    assert resp.status_code == 422
    assert resp.json()["code"] == 4003


def test_extract_daily_limit_fourth_rejected(fresh_state, monkeypatch):
    _add_session(1, rep_count=10)
    captured = {}
    monkeypatch.setattr(qc.QwenClient, "chat", _fake_chat(captured))
    monkeypatch.setattr(sp_api, "count_audit_logs", AsyncMock(return_value=3))
    resp = client.post("/api/v1/skill-packages/extract-draft", json={"session_ids": [1]},
                       headers=_token(1, "rep"))
    assert resp.status_code == 422
    body = resp.json()
    assert body["code"] == 4002
    assert "上限" in body["message"]
    # 被限额拒绝时未调 LLM、未写审计
    assert "messages" not in captured
    fresh_state.assert_not_awaited()


def test_extract_limit_query_failure_passes(fresh_state, monkeypatch):
    # 计数查询异常 → 放行（审计可用性不卡死业务，决策 4）
    _add_session(1, rep_count=10)
    captured = {}
    monkeypatch.setattr(qc.QwenClient, "chat", _fake_chat(captured))
    monkeypatch.setattr(sp_api, "count_audit_logs", AsyncMock(return_value=None))
    resp = client.post("/api/v1/skill-packages/extract-draft", json={"session_ids": [1]},
                       headers=_token(1, "rep"))
    assert resp.json()["code"] == 0
    fresh_state.assert_awaited_once()


# ==================== 素材扩拜访（2026-09-10 老板需求） ====================

def test_extract_from_visits_only(fresh_state, monkeypatch):
    """拜访单源提取：无陪练会话也能从拜访对话提取，仅 [代表] 行进素材。"""
    _add_visit(1, rep_lines=10)
    captured = {}
    monkeypatch.setattr(qc.QwenClient, "chat", _fake_chat(captured))
    resp = client.post("/api/v1/skill-packages/extract-draft", json={"visit_ids": [1]},
                       headers=_token(1, "rep"))
    body = resp.json()
    assert body["code"] == 0
    user = captured["messages"][1]["content"]
    assert "拜访中代表第1条发言" in user
    assert "医生第1条回应" not in user       # 医生行不进素材
    assert "拜访医生实录" in user             # 场景分块标签
    _, kwargs = fresh_state.call_args
    assert kwargs["after_value"]["visit_ids"] == [1]
    assert kwargs["resource_id"] == "1"


def test_extract_mixed_sessions_and_visits(fresh_state, monkeypatch):
    """混合素材：陪练 5 条 + 拜访 5 条 = 10 条过门槛（单类都不足）。"""
    _add_session(1, rep_count=5)
    _add_visit(2, rep_lines=5)
    captured = {}
    monkeypatch.setattr(qc.QwenClient, "chat", _fake_chat(captured))
    resp = client.post("/api/v1/skill-packages/extract-draft",
                       json={"session_ids": [1], "visit_ids": [2]},
                       headers=_token(1, "rep"))
    assert resp.json()["code"] == 0
    user = captured["messages"][1]["content"]
    assert "代表第1轮发言" in user and "拜访中代表第1条发言" in user
    assert "陪练对话" in user and "拜访医生实录" in user
    _, kwargs = fresh_state.call_args
    assert kwargs["after_value"]["session_ids"] == [1]
    assert kwargs["after_value"]["visit_ids"] == [2]
    assert kwargs["resource_id"] == "1,2"


def test_extract_rejects_empty_sources(fresh_state):
    """两类素材都不传 → 合计 0 条，参数校验拒绝。"""
    resp = client.post("/api/v1/skill-packages/extract-draft", json={},
                       headers=_token(1, "rep"))
    assert resp.status_code == 400
    assert resp.json()["code"] == 1000


def test_extract_rejects_visit_below_min_lines(fresh_state):
    _add_visit(1, rep_lines=2)
    resp = client.post("/api/v1/skill-packages/extract-draft", json={"visit_ids": [1]},
                       headers=_token(1, "rep"))
    assert resp.status_code == 400
    assert "代表发言不足" in resp.json()["message"]


def test_extract_rejects_cancelled_visit(fresh_state):
    _add_visit(1, rep_lines=6, status="cancelled")
    resp = client.post("/api/v1/skill-packages/extract-draft", json={"visit_ids": [1]},
                       headers=_token(1, "rep"))
    assert resp.status_code == 400
    assert "取消" in resp.json()["message"]


def test_extract_rejects_foreign_visit(fresh_state):
    _add_visit(1, rep_lines=6, owner=2)
    resp = client.post("/api/v1/skill-packages/extract-draft", json={"visit_ids": [1]},
                       headers=_token(1, "rep"))
    assert resp.status_code == 400
    assert "非本人" in resp.json()["message"]
