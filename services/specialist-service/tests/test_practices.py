"""陪练会话测试（Task 3）：创建/多轮对话/评分/历史"""
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
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.ext.compiler import compiles
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from shared.common.auth import create_token
from shared.common.db_session import get_db
from shared.models.base import Base
from shared.models.practice import ObjectionScript, PracticeSession
from shared.models.skill import SkillPackage
from shared.models.user import User

import app.api.practices as practices_api
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
    tables = [User.__table__, SkillPackage.__table__, PracticeSession.__table__, ObjectionScript.__table__]
    Base.metadata.drop_all(engine, tables=tables)
    Base.metadata.create_all(engine, tables=tables)
    db = TestSession()
    db.add_all([
        User(id=1, username="rep01", full_name="张代表", phone="13800000001", role="rep", status="active"),
        User(id=2, username="admin", full_name="管理员", phone="13800000000", role="admin", status="active"),
        User(id=3, username="medical", full_name="医学部", phone="13800000003", role="medical", status="active"),
    ])
    db.commit()
    db.close()
    monkeypatch.setitem(app.dependency_overrides, get_db, _override_db)
    audit_mock = AsyncMock(return_value=None)
    monkeypatch.setattr(practices_api, "write_audit_log", audit_mock)
    yield audit_mock


def test_create_session_requires_rep():
    resp = client.post("/api/v1/practices", json={"skill_id": 1, "scenario": "心内科推广"},
                       headers=_token(2, "admin"))
    assert resp.status_code == 403


def test_create_session(fresh_state):
    db = TestSession()
    db.add(SkillPackage(id=1, name="严谨学术风", creator_id=3, is_public=True,
                        audit_status="approved", skill_weights={"formal_level": "标准学术"}))
    db.commit()
    db.close()
    resp = client.post("/api/v1/practices", json={"skill_id": 1, "scenario": "心内科推广"},
                       headers=_token(1, "rep"))
    body = resp.json()
    assert body["code"] == 0
    assert body["data"]["status"] == "in_progress"
    assert body["data"]["scenario"] == "心内科推广"


def test_turn_ai_responds(fresh_state, monkeypatch):
    db = TestSession()
    db.add(SkillPackage(id=1, name="严谨学术风", creator_id=3, is_public=True,
                        audit_status="approved", skill_weights={"formal_level": "标准学术"}))
    db.add(PracticeSession(id=1, representative_id=1, skill_id=1, scenario="心内科推广",
                           status="in_progress", turn_count=0))
    db.commit()
    db.close()

    from app.services import qwen_client as qc
    monkeypatch.setattr(qc.QwenClient, "chat", lambda self, *a, **k: {
        "content": "医生：您好，请介绍下这款降压药的核心优势？", "usage": {},
    })
    monkeypatch.setattr(practices_api, "check_compliance", AsyncMock(return_value={"blocked": False}))

    resp = client.post("/api/v1/practices/1/turn", json={"message": "您好，这款药降压效果平稳"},
                       headers=_token(1, "rep"))
    body = resp.json()
    assert body["code"] == 0
    assert "医生" in body["data"]["ai_message"]
    assert body["data"]["turn_count"] == 1


def test_turn_blocked_fails_closed(fresh_state, monkeypatch):
    db = TestSession()
    db.add(PracticeSession(id=1, representative_id=1, skill_id=None, scenario="x",
                           status="in_progress", turn_count=0))
    db.commit()
    db.close()
    monkeypatch.setattr(practices_api, "check_compliance", AsyncMock(return_value={"blocked": True, "rule_code": "R001"}))
    resp = client.post("/api/v1/practices/1/turn", json={"message": "保证治好"},
                       headers=_token(1, "rep"))
    assert resp.status_code == 400
    assert resp.json()["code"] == 1000


def test_complete_scores(fresh_state):
    db = TestSession()
    db.add(PracticeSession(id=1, representative_id=1, skill_id=None, scenario="x",
                           status="in_progress", turn_count=3))
    db.commit()
    db.close()
    resp = client.post("/api/v1/practices/1/complete", json={}, headers=_token(1, "rep"))
    body = resp.json()
    assert body["code"] == 0
    assert body["data"]["status"] == "completed"
    assert body["data"]["scores"]["overall"] > 0
    # 4.5 后半段：逐句/逐轮反馈 per_turn 数组按轮数生成
    per_turn = body["data"]["scores"]["per_turn"]
    assert len(per_turn) == 3
    assert "evidence_accuracy" in per_turn[0]
    assert "objection_handling" in per_turn[0]
    assert "communication_logic" in per_turn[0]


# ============ 异议话术库（3.2(5)，终审修复 #3） ============

def _add_objection(**kw):
    db = TestSession()
    defaults = dict(
        id=kw.pop("id", 1), scenario_type="心内科", objection_content="医生异议：和竞品相比优势在哪？",
        review_status="pending", version="1.0", created_by=3,
    )
    defaults.update(kw)
    db.add(ObjectionScript(**defaults))
    db.commit()
    db.close()
    return defaults["id"]


def test_create_objection_script_requires_admin():
    resp = client.post("/api/v1/practices/objection-scripts", json={
        "scenario_type": "心内科", "objection_content": "医生异议：优势在哪？",
    }, headers=_token(1, "rep"))
    assert resp.status_code == 403
    assert resp.json()["code"] == 3000


def test_create_objection_script_sets_pending(fresh_state):
    resp = client.post("/api/v1/practices/objection-scripts", json={
        "scenario_type": "心内科", "objection_content": "医生异议：优势在哪？",
        "response_guidance": "用循证数据回应",
    }, headers=_token(3, "medical"))
    body = resp.json()
    assert body["code"] == 0
    assert body["data"]["review_status"] == "pending"
    assert body["data"]["objection_content"] == "医生异议：优势在哪？"
    assert body["data"]["response_guidance"] == "用循证数据回应"


def test_list_objection_scripts_filters_status(fresh_state):
    _add_objection(id=1, review_status="approved")
    _add_objection(id=2, review_status="pending")
    resp = client.get("/api/v1/practices/objection-scripts", params={"review_status": "approved"},
                      headers=_token(2, "admin"))
    body = resp.json()
    assert body["code"] == 0
    assert body["data"]["total"] == 1
    assert body["data"]["items"][0]["id"] == 1


def test_review_objection_script_approve(fresh_state):
    _add_objection(id=1)
    resp = client.post("/api/v1/practices/objection-scripts/1/review", json={"verdict": "approve"},
                       headers=_token(2, "admin"))
    body = resp.json()
    assert body["code"] == 0
    assert body["data"]["review_status"] == "approved"
    assert body["data"]["reviewed_by"] == 2


def test_review_objection_script_reject_requires_reason(fresh_state):
    _add_objection(id=1)
    resp = client.post("/api/v1/practices/objection-scripts/1/review", json={"verdict": "reject"},
                       headers=_token(2, "admin"))
    assert resp.status_code == 400
    assert resp.json()["code"] == 1000


def test_turn_injects_approved_objection(fresh_state, monkeypatch):
    db = TestSession()
    db.add(SkillPackage(id=1, name="严谨学术风", creator_id=3, is_public=True,
                        audit_status="approved", skill_weights={"formal_level": "标准学术"}))
    db.add(PracticeSession(id=1, representative_id=1, skill_id=1, scenario="心内科推广",
                           status="in_progress", turn_count=0))
    db.add(ObjectionScript(id=1, scenario_type="心内科", objection_content="医生异议：和竞品相比优势在哪？",
                           review_status="approved"))
    db.commit()
    db.close()

    captured = {}
    from app.services import qwen_client as qc

    def fake_chat(self, messages, **kwargs):
        captured["messages"] = messages
        return {"content": "医生：请介绍下这款药的优势。", "usage": {}}

    monkeypatch.setattr(qc.QwenClient, "chat", fake_chat)
    monkeypatch.setattr(practices_api, "check_compliance", AsyncMock(return_value={"blocked": False}))

    resp = client.post("/api/v1/practices/1/turn", json={"message": "您好，这款药降压平稳"},
                       headers=_token(1, "rep"))
    assert resp.json()["code"] == 0
    user_msg = captured["messages"][1]["content"]
    assert "医生异议：和竞品相比优势在哪？" in user_msg


def test_turn_no_objection_falls_back(fresh_state, monkeypatch):
    # 该场景无 approved 话术 → 不注入异议，自由生成（prompt 中无 objection 标记）
    db = TestSession()
    db.add(PracticeSession(id=1, representative_id=1, skill_id=None, scenario="肿瘤科推广",
                           status="in_progress", turn_count=0))
    db.add(ObjectionScript(id=1, scenario_type="心内科", objection_content="医生异议：优势在哪？",
                           review_status="approved"))
    db.commit()
    db.close()

    captured = {}
    from app.services import qwen_client as qc

    def fake_chat(self, messages, **kwargs):
        captured["messages"] = messages
        return {"content": "医生：请介绍下这款药。", "usage": {}}

    monkeypatch.setattr(qc.QwenClient, "chat", fake_chat)
    monkeypatch.setattr(practices_api, "check_compliance", AsyncMock(return_value={"blocked": False}))

    resp = client.post("/api/v1/practices/1/turn", json={"message": "您好"},
                       headers=_token(1, "rep"))
    assert resp.json()["code"] == 0
    user_msg = captured["messages"][1]["content"]
    assert "医生异议：优势在哪？" not in user_msg


# ============ 进步曲线（4.5 后半段，终审修复 #4） ============

def test_progress_aggregates_completed(fresh_state):
    db = TestSession()
    db.add(PracticeSession(id=1, representative_id=1, skill_id=None, scenario="x",
                           status="completed", turn_count=2,
                           scores={"overall": 0.7, "per_turn": []}))
    db.add(PracticeSession(id=2, representative_id=1, skill_id=None, scenario="y",
                           status="completed", turn_count=3,
                           scores={"overall": 0.8, "per_turn": []}))
    db.add(PracticeSession(id=3, representative_id=1, skill_id=None, scenario="z",
                           status="in_progress", turn_count=1, scores=None))
    db.commit()
    db.close()

    resp = client.get("/api/v1/practices/progress", headers=_token(1, "rep"))
    body = resp.json()
    assert body["code"] == 0
    data = body["data"]
    assert data["total_sessions"] == 2
    assert data["avg_overall"] == 0.75
    assert len(data["trend"]) == 2
    assert data["trend"][0]["session_id"] == 1
    assert data["trend"][0]["overall"] == 0.7
    assert data["trend"][1]["session_id"] == 2


def test_progress_empty(fresh_state):
    resp = client.get("/api/v1/practices/progress", headers=_token(1, "rep"))
    body = resp.json()
    assert body["code"] == 0
    assert body["data"]["total_sessions"] == 0
    assert body["data"]["avg_overall"] == 0.0
    assert body["data"]["trend"] == []


def test_create_session_rejects_off_shelved(fresh_state):
    db = TestSession()
    db.add(SkillPackage(id=1, name="已下架", creator_id=3, is_public=True,
                        audit_status="approved", skill_weights={},
                        off_shelf_status="off_shelved", off_shelf_type="author", off_shelf_reason="作者申请"))
    db.commit()
    db.close()
    resp = client.post("/api/v1/practices", json={"skill_id": 1, "scenario": "心内科推广"},
                       headers=_token(1, "rep"))
    assert resp.status_code == 422
    assert resp.json()["code"] == 4001


def test_practice_turn_disabled_for_compliance_off_shelved(fresh_state, monkeypatch):
    db = TestSession()
    db.add(SkillPackage(id=1, name="违规下架", creator_id=3, is_public=True,
                        audit_status="approved", skill_weights={},
                        off_shelf_status="off_shelved", off_shelf_type="compliance", off_shelf_reason="含敏感信息"))
    db.add(PracticeSession(id=1, representative_id=1, skill_id=1, scenario="x",
                           status="in_progress", turn_count=1))
    db.commit()
    db.close()
    resp = client.post("/api/v1/practices/1/turn", json={"message": "您好"},
                       headers=_token(1, "rep"))
    assert resp.status_code == 422
    assert resp.json()["code"] == 4001
    assert "含敏感信息" in resp.json()["message"]


def test_practice_turn_allowed_for_author_off_shelved(fresh_state, monkeypatch):
    # 作者申请下架：已加载用户不受影响（3.6(3)）
    db = TestSession()
    db.add(SkillPackage(id=1, name="作者下架", creator_id=1, is_public=True,
                        audit_status="approved", skill_weights={},
                        off_shelf_status="off_shelved", off_shelf_type="author", off_shelf_reason="不想发了"))
    db.add(PracticeSession(id=1, representative_id=1, skill_id=1, scenario="x",
                           status="in_progress", turn_count=1))
    db.commit()
    db.close()
    from app.services import qwen_client as qc
    monkeypatch.setattr(qc.QwenClient, "chat", lambda self, *a, **k: {"content": "医生：请介绍下。", "usage": {}})
    monkeypatch.setattr(practices_api, "check_compliance", AsyncMock(return_value={"blocked": False}))
    resp = client.post("/api/v1/practices/1/turn", json={"message": "您好"},
                       headers=_token(1, "rep"))
    assert resp.json()["code"] == 0


def test_to_dict_includes_transcript():
    db = TestSession()
    s = PracticeSession(id=9, representative_id=1, scenario="x", status="in_progress", turn_count=2,
                        transcript=[{"turn": 1, "role": "rep", "content": "您好"}, {"turn": 1, "role": "ai", "content": "医生回应"}])
    db.add(s)
    db.commit()
    d = s.to_dict()
    assert d["transcript"][0]["content"] == "您好"
    assert d["transcript"][1]["role"] == "ai"
    db.close()


def test_turn_persists_transcript(fresh_state, monkeypatch):
    db = TestSession()
    db.add(PracticeSession(id=1, representative_id=1, skill_id=None, scenario="x",
                           status="in_progress", turn_count=0, transcript=[]))
    db.commit()
    db.close()
    from app.services import qwen_client as qc
    monkeypatch.setattr(qc.QwenClient, "chat", lambda self, *a, **k: {"content": "医生：请介绍下这款药。", "usage": {}})
    monkeypatch.setattr(practices_api, "check_compliance", AsyncMock(return_value={"blocked": False}))
    resp = client.post("/api/v1/practices/1/turn", json={"message": "您好"},
                       headers=_token(1, "rep"))
    assert resp.json()["code"] == 0
    db = TestSession()
    s = db.query(PracticeSession).filter(PracticeSession.id == 1).first()
    assert s.turn_count == 1
    assert s.transcript == [
        {"turn": 1, "role": "rep", "content": "您好"},
        {"turn": 1, "role": "ai", "content": "医生：请介绍下这款药。"},
    ]
    db.close()


# ============ 三期 N Task 3：LLM 深度评分 + 失败降级基线 ============

def test_complete_uses_llm_scores(fresh_state, monkeypatch):
    db = TestSession()
    db.add(PracticeSession(id=1, representative_id=1, skill_id=None, scenario="x",
                           status="in_progress", turn_count=2,
                           transcript=[{"turn": 1, "role": "rep", "content": "您好"},
                                       {"turn": 1, "role": "ai", "content": "医生回应"},
                                       {"turn": 2, "role": "rep", "content": "这款药降压平稳"},
                                       {"turn": 2, "role": "ai", "content": "医生再回应"}]))
    db.commit()
    db.close()
    from app.services import qwen_client as qc

    def fake_chat(self, messages, **kwargs):
        captured = {"messages": messages}
        captured["user"] = messages[1]["content"]
        return {"content": '{"evidence_accuracy":0.8,"objection_handling":0.7,"communication_logic":0.9,'
                           '"overall":0.8,"per_turn":[{"turn":1,"evidence_accuracy":0.8,"objection_handling":0.7,'
                           '"communication_logic":0.9,"feedback":"开场清晰，可加强循证引用"}],'
                           '"summary":"整体流畅，注意引用数据"}', "usage": {}}

    monkeypatch.setattr(qc.QwenClient, "chat", fake_chat)
    resp = client.post("/api/v1/practices/1/complete", json={}, headers=_token(1, "rep"))
    body = resp.json()
    assert body["code"] == 0
    scores = body["data"]["scores"]
    assert scores["overall"] == 0.8
    assert scores["evidence_accuracy"] == 0.8
    assert len(scores["per_turn"]) == 1
    assert scores["per_turn"][0]["feedback"] == "开场清晰，可加强循证引用"
    assert scores["summary"] == "整体流畅，注意引用数据"


def test_complete_falls_back_on_llm_error(fresh_state, monkeypatch):
    db = TestSession()
    db.add(PracticeSession(id=1, representative_id=1, skill_id=None, scenario="x",
                           status="in_progress", turn_count=2,
                           transcript=[{"turn": 1, "role": "rep", "content": "您好"},
                                       {"turn": 1, "role": "ai", "content": "医生回应"}]))
    db.commit()
    db.close()
    from app.services import qwen_client as qc
    monkeypatch.setattr(qc.QwenClient, "chat", lambda self, *a, **k: {"content": "not json", "usage": {}})
    resp = client.post("/api/v1/practices/1/complete", json={}, headers=_token(1, "rep"))
    body = resp.json()
    assert body["code"] == 0
    scores = body["data"]["scores"]
    assert scores["overall"] == round(min(0.9, 0.45 + 2 * 0.1), 2)  # 确定性基线
    assert body["data"]["status"] == "completed"


def test_complete_rejects_bool_scores(fresh_state, monkeypatch):
    # JSON true/false 是 int/bool 子类，会通过 0-1 分数校验落库为 True/False；
    # 应触发非法字段校验并回退确定性基线，而非污染分数。
    db = TestSession()
    db.add(PracticeSession(id=1, representative_id=1, skill_id=None, scenario="x",
                           status="in_progress", turn_count=2,
                           transcript=[{"turn": 1, "role": "rep", "content": "您好"},
                                       {"turn": 1, "role": "ai", "content": "医生回应"}]))
    db.commit()
    db.close()
    from app.services import qwen_client as qc

    def fake_chat(self, messages, **kwargs):
        return {"content": '{"evidence_accuracy":0.8,"objection_handling":0.7,"communication_logic":0.9,'
                           '"overall":true,"per_turn":[{"turn":1,"evidence_accuracy":0.8,"objection_handling":0.7,'
                           '"communication_logic":0.9,"feedback":"开场清晰"}],"summary":"整体流畅"}', "usage": {}}

    monkeypatch.setattr(qc.QwenClient, "chat", fake_chat)
    resp = client.post("/api/v1/practices/1/complete", json={}, headers=_token(1, "rep"))
    body = resp.json()
    assert body["code"] == 0
    scores = body["data"]["scores"]
    assert scores["overall"] == round(min(0.9, 0.45 + 2 * 0.1), 2)  # 回退确定性基线
    assert scores["overall"] is not True
    assert body["data"]["status"] == "completed"


# ============ 三期 P Task 5：风格对照评分（学习闭环，决策 9/10/11） ============

_TEST_WEIGHTS = {"formal_level": "标准学术", "reply_length": "详尽", "opening_mode": "先寒暄再进入"}


def _add_score_session(skill: dict | None = None):
    """建一条 2 轮带 transcript 的 in_progress 会话；skill 非空时一并建 SkillPackage"""
    db = TestSession()
    if skill:
        db.add(SkillPackage(**skill))
    db.add(PracticeSession(
        id=1, representative_id=1, skill_id=skill.get("id") if skill else None,
        scenario="心内科推广", status="in_progress", turn_count=2,
        transcript=[{"turn": 1, "role": "rep", "content": "您好，久仰久仰"},
                    {"turn": 1, "role": "ai", "content": "医生回应"},
                    {"turn": 2, "role": "rep", "content": "这款药降压平稳"},
                    {"turn": 2, "role": "ai", "content": "医生再回应"}]))
    db.commit()
    db.close()


def _mk_score_chat(captured: dict, style_match: str):
    """构造捕获 messages/kwargs 的 fake chat；style_match 为回填进 JSON 的字面量（0.85/null/1.5）"""
    from app.services import qwen_client as qc
    content = (
        '{"evidence_accuracy":0.8,"objection_handling":0.7,"communication_logic":0.9,"overall":0.8,'
        f'"style_match":{style_match},'
        '"per_turn":[{"turn":1,"evidence_accuracy":0.8,"objection_handling":0.7,'
        '"communication_logic":0.9,"feedback":"模版要求直切主题，你的开场寒暄了 3 句"}],'
        '"summary":"整体流畅，注意对照模版风格"}'
    )

    def fake_chat(self, messages, **kwargs):
        captured["messages"] = messages
        captured["kwargs"] = kwargs
        return {"content": content, "usage": {}}

    return qc, fake_chat


def test_complete_with_skill_injects_style(fresh_state, monkeypatch):
    # 加载 skill 的 complete：prompt 注入模版风格段 + scores 含 style_match/template_style（决策 9）
    _add_score_session(skill=dict(id=1, name="亲和详尽风", creator_id=3, is_public=True,
                                  audit_status="approved", skill_weights=_TEST_WEIGHTS))
    captured = {}
    qc, fake = _mk_score_chat(captured, "0.85")
    monkeypatch.setattr(qc.QwenClient, "chat", fake)
    resp = client.post("/api/v1/practices/1/complete", json={}, headers=_token(1, "rep"))
    body = resp.json()
    assert body["code"] == 0
    user_msg = captured["messages"][1]["content"]
    assert "本次练习加载的模版风格" in user_msg
    assert "先寒暄再进入" in user_msg
    # 决策 11：评分链超时放宽（输出加长 → max_tokens 2500、chat timeout=90）
    assert captured["kwargs"]["max_tokens"] == 2500
    assert captured["kwargs"]["timeout"] == 90.0
    scores = body["data"]["scores"]
    assert scores["style_match"] == 0.85
    assert scores["template_style"] == _TEST_WEIGHTS  # 权重 dict 回显（决策 10）
    assert "模版要求直切主题" in scores["per_turn"][0]["feedback"]  # 逐轮对照反馈随 feedback


def test_complete_without_skill_no_style_section(fresh_state, monkeypatch):
    # 无 skill：契约要求 style_match null、prompt 无模版段、不回显 template_style
    _add_score_session()
    captured = {}
    qc, fake = _mk_score_chat(captured, "null")
    monkeypatch.setattr(qc.QwenClient, "chat", fake)
    resp = client.post("/api/v1/practices/1/complete", json={}, headers=_token(1, "rep"))
    body = resp.json()
    assert body["code"] == 0
    assert "模版风格" not in captured["messages"][1]["content"]
    scores = body["data"]["scores"]
    assert scores["style_match"] is None
    assert "template_style" not in scores


def test_complete_style_fallback_keeps_baseline(fresh_state, monkeypatch):
    # LLM 失败降级：四维基线照旧、style_match null（基线不伪造风格分）、template_style 照回显
    _add_score_session(skill=dict(id=1, name="亲和详尽风", creator_id=3, is_public=True,
                                  audit_status="approved", skill_weights=_TEST_WEIGHTS))
    from app.services import qwen_client as qc
    monkeypatch.setattr(qc.QwenClient, "chat", lambda self, *a, **k: {"content": "not json", "usage": {}})
    resp = client.post("/api/v1/practices/1/complete", json={}, headers=_token(1, "rep"))
    body = resp.json()
    assert body["code"] == 0
    scores = body["data"]["scores"]
    assert scores["overall"] == round(min(0.9, 0.45 + 2 * 0.1), 2)
    assert len(scores["per_turn"]) == 2
    assert scores["style_match"] is None
    assert scores["template_style"] == _TEST_WEIGHTS


def test_complete_compliance_off_shelf_skips_injection(fresh_state, monkeypatch):
    # 合规下架：评分照常（complete 不拦截），但不注入模版段、不回显 template_style（决策 9 与 turn 拦截对齐）
    _add_score_session(skill=dict(id=1, name="违规下架", creator_id=3, is_public=True,
                                  audit_status="approved", skill_weights=_TEST_WEIGHTS,
                                  off_shelf_status="off_shelved", off_shelf_type="compliance",
                                  off_shelf_reason="含敏感信息"))
    captured = {}
    qc, fake = _mk_score_chat(captured, "null")
    monkeypatch.setattr(qc.QwenClient, "chat", fake)
    resp = client.post("/api/v1/practices/1/complete", json={}, headers=_token(1, "rep"))
    body = resp.json()
    assert body["code"] == 0
    assert body["data"]["status"] == "completed"
    assert "模版风格" not in captured["messages"][1]["content"]
    scores = body["data"]["scores"]
    assert scores["style_match"] is None
    assert "template_style" not in scores


def test_complete_author_off_shelf_still_injects(fresh_state, monkeypatch):
    # 作者申请下架：已加载用户不受影响（3.6(3)），照常注入模版风格
    _add_score_session(skill=dict(id=1, name="作者下架", creator_id=1, is_public=True,
                                  audit_status="approved", skill_weights=_TEST_WEIGHTS,
                                  off_shelf_status="off_shelved", off_shelf_type="author",
                                  off_shelf_reason="不想发了"))
    captured = {}
    qc, fake = _mk_score_chat(captured, "0.8")
    monkeypatch.setattr(qc.QwenClient, "chat", fake)
    resp = client.post("/api/v1/practices/1/complete", json={}, headers=_token(1, "rep"))
    body = resp.json()
    assert body["code"] == 0
    assert "本次练习加载的模版风格" in captured["messages"][1]["content"]
    scores = body["data"]["scores"]
    assert scores["style_match"] == 0.8
    assert scores["template_style"] == _TEST_WEIGHTS


def test_complete_style_match_out_of_range_nullified(fresh_state, monkeypatch):
    # LLM 输出 style_match 越界 → 置 null（宁缺毋假），不因新字段解析失败整体降级
    _add_score_session(skill=dict(id=1, name="亲和详尽风", creator_id=3, is_public=True,
                                  audit_status="approved", skill_weights=_TEST_WEIGHTS))
    captured = {}
    qc, fake = _mk_score_chat(captured, "1.5")
    monkeypatch.setattr(qc.QwenClient, "chat", fake)
    resp = client.post("/api/v1/practices/1/complete", json={}, headers=_token(1, "rep"))
    body = resp.json()
    assert body["code"] == 0
    scores = body["data"]["scores"]
    assert scores["style_match"] is None
    assert scores["overall"] == 0.8  # 四维分数照常用，未回退基线
    assert scores["template_style"] == _TEST_WEIGHTS

# ========== 2026-09-01 审核盲审修复批：受控查看陪练原始 transcript ==========

def _add_completed_session(sid=7, rep_id=1):
    db = TestSession()
    db.add(PracticeSession(
        id=sid, representative_id=rep_id, skill_id=None, scenario="心内科推广",
        status="completed", turn_count=12,
        transcript=[
            {"turn": 1, "role": "rep", "content": "主任您好"},
            {"turn": 1, "role": "ai", "content": "你好，请讲"},
        ],
    ))
    db.commit()
    db.close()


def test_review_transcript_admin_sees_transcript_and_audits(fresh_state):
    _add_completed_session(7)
    resp = client.get("/api/v1/practices/7/review-transcript", headers=_token(2, "admin"))
    body = resp.json()
    assert body["code"] == 0
    data = body["data"]
    assert data["id"] == 7
    assert data["rep_name"] == "张代表"  # join users 取姓名
    assert data["turn_count"] == 12
    assert len(data["transcript"]) == 2
    args, kwargs = fresh_state.call_args
    assert kwargs["action"] == "practice_source_view"
    assert kwargs["resource_id"] == "7"


def test_review_transcript_medical_allowed_rep_403(fresh_state):
    _add_completed_session(7)
    resp = client.get("/api/v1/practices/7/review-transcript", headers=_token(3, "medical"))
    assert resp.json()["code"] == 0
    resp = client.get("/api/v1/practices/7/review-transcript", headers=_token(1, "rep"))
    assert resp.status_code == 403


def test_review_transcript_missing_404(fresh_state):
    resp = client.get("/api/v1/practices/999/review-transcript", headers=_token(2, "admin"))
    assert resp.json()["code"] == 4000
