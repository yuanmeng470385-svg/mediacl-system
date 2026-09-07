"""学术卡片生成测试（Task 2）：rep 生成 + 合规预检 + 权限"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", ".."))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

os.environ.setdefault("JWT_SECRET", "test-secret-not-a-default-value")
os.environ["AUTH_DEV_MODE"] = "true"

from unittest.mock import AsyncMock, patch

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
from shared.models.academic import AcademicCard, CardPushRecord, Notification
from shared.models.digital_specialist import Specialist
from shared.models.product import Product
from shared.models.user import User

import app.api.academic_cards as ac_api
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
    tables = [User.__table__, Specialist.__table__, Product.__table__, AcademicCard.__table__,
              CardPushRecord.__table__, Notification.__table__]
    Base.metadata.drop_all(engine, tables=tables)
    Base.metadata.create_all(engine, tables=tables)
    db = TestSession()
    db.add_all([
        User(id=1, username="rep01", full_name="张代表", phone="13800000001", role="rep", status="active"),
        User(id=2, username="doctor1", full_name="王医生", phone="13800000002", role="doctor", status="active"),
        User(id=3, username="admin", full_name="管理员", phone="13800000000", role="admin", status="active"),
    ])
    db.commit()
    db.close()
    monkeypatch.setitem(app.dependency_overrides, get_db, _override_db)
    # 审计打桩：本测试不真调审计服务网络（write_audit_log fail-silent 但会发 httpx 请求）
    monkeypatch.setattr(ac_api, "write_audit_log", AsyncMock(return_value=None))
    yield


def test_create_card_requires_rep():
    resp = client.post("/api/v1/academic-cards", json={"title": "高血压指南", "topic": "高血压"},
                       headers=_token(3, "admin"))
    assert resp.status_code == 403
    assert resp.json()["code"] == 3000


def test_create_card_ai_generate_and_pass(fresh_state, monkeypatch):
    fake_card = {
        "conclusion": "高血压患者应限盐。",
        "key_points": ["限盐≤5g/日", "定期监测"],
        "summary": "一句话：控盐降压。",
        "citations": [{"doc_name": "高血压防治指南", "version": "2024版", "section": "生活方式干预"}],
    }
    monkeypatch.setattr(ac_api, "_generate_card_content", AsyncMock(return_value=fake_card))
    monkeypatch.setattr(ac_api, "check_compliance", AsyncMock(return_value={"blocked": False}))

    resp = client.post("/api/v1/academic-cards", json={"title": "高血压指南", "topic": "高血压"},
                       headers=_token(1, "rep"))
    body = resp.json()
    assert body["code"] == 0
    data = body["data"]
    assert data["title"] == "高血压指南"
    assert data["is_ai_generated"] is True
    assert data["compliance_status"] == "passed"
    assert data["content"]["conclusion"] == "高血压患者应限盐。"


def test_create_card_blocked_fails_closed(fresh_state, monkeypatch):
    fake_card = {
        "conclusion": "保证治好。",
        "key_points": [], "summary": "x",
        "citations": [],
    }
    monkeypatch.setattr(ac_api, "_generate_card_content", AsyncMock(return_value=fake_card))
    monkeypatch.setattr(ac_api, "check_compliance", AsyncMock(return_value={
        "blocked": True, "violations": [{"rule_code": "R001", "rule_name": "保证疗效"}],
    }))

    resp = client.post("/api/v1/academic-cards", json={"title": "违规卡", "topic": "疗效"},
                       headers=_token(1, "rep"))
    assert resp.status_code == 400
    assert resp.json()["code"] == 1000
    assert "合规" in resp.json()["message"]
    assert "R001" in resp.json()["message"]


def test_list_my_cards():
    db = TestSession()
    db.add(AcademicCard(id=1, representative_id=1, title="卡1", content={"conclusion": "x"}, is_ai_generated=True))
    db.add(AcademicCard(id=2, representative_id=99, title="别人的卡", content={"conclusion": "y"}, is_ai_generated=True))
    db.commit()
    db.close()

    resp = client.get("/api/v1/academic-cards", headers=_token(1, "rep"))
    body = resp.json()
    assert body["code"] == 0
    assert body["data"]["total"] == 1
    assert body["data"]["items"][0]["title"] == "卡1"


def test_stats_requires_admin():
    resp = client.get("/api/v1/academic-cards/stats", headers=_token(1, "rep"))
    assert resp.status_code == 403


def test_stats_aggregates(fresh_state):
    db = TestSession()
    db.add(AcademicCard(id=1, representative_id=1, title="卡1", content={"conclusion": "x"}, is_ai_generated=True))
    db.add(CardPushRecord(id=1, representative_id=1, card_id=1, doctor_id=2, read_status="read", tracked_seconds=10))
    db.add(CardPushRecord(id=2, representative_id=1, card_id=1, doctor_id=3, read_status="unread"))
    db.commit()
    db.close()

    resp = client.get("/api/v1/academic-cards/stats", headers=_token(3, "admin"))
    body = resp.json()
    assert body["code"] == 0
    data = body["data"]
    assert data["total_pushes"] == 2
    assert data["total_reads"] == 1
    assert data["read_rate"] == 0.5
    assert data["rep_ranking"][0]["representative_id"] == 1
    assert data["rep_ranking"][0]["reads"] == 1
    # A-5：tracked_seconds=10 ≥3 → 该条计入有效阅读
    assert data["effective_reads"] == 1
    assert data["effective_read_rate"] == 0.5


def test_stats_effective_read_and_ranking_order(fresh_state):
    """A-5（2026-09-07）：①有效阅读=已读且停留 ≥3s（秒退不计）；②代表排行按被读数
    优先（A 推多读少 < B 推少读多 → B 在前；旧口径按推送量 A 在前是反向激励）。"""
    db = TestSession()
    db.add(AcademicCard(id=1, representative_id=1, title="卡1", content={"conclusion": "x"}, is_ai_generated=True))
    db.add(AcademicCard(id=2, representative_id=4, title="卡2", content={"conclusion": "x"}, is_ai_generated=True))
    # rep1：3 推 1 读（秒退 tracked_seconds=1）
    db.add(CardPushRecord(id=1, representative_id=1, card_id=1, doctor_id=2, read_status="read", tracked_seconds=1))
    db.add(CardPushRecord(id=2, representative_id=1, card_id=1, doctor_id=3, read_status="unread"))
    db.add(CardPushRecord(id=3, representative_id=1, card_id=1, doctor_id=5, read_status="unread"))
    # rep4：2 推 2 读（均有效）
    db.add(CardPushRecord(id=4, representative_id=4, card_id=2, doctor_id=2, read_status="read", tracked_seconds=30))
    db.add(CardPushRecord(id=5, representative_id=4, card_id=2, doctor_id=3, read_status="forwarded", tracked_seconds=60))
    db.commit()
    db.close()

    resp = client.get("/api/v1/academic-cards/stats", headers=_token(3, "admin"))
    data = resp.json()["data"]
    # 有效阅读：rep4 两条；rep1 秒退那条（read 但 1s）不算
    assert data["effective_reads"] == 2
    assert data["effective_read_rate"] == 0.4  # 2/5
    # 排序：rep4（读 2）在 rep1（读 1）前——被读数优先，推送量仅次位
    assert [r["representative_id"] for r in data["rep_ranking"]] == [4, 1]
    assert data["rep_ranking"][0]["read_rate"] == 1.0


def test_track_seconds_capped(fresh_state):
    """A-5：track 停留秒数服务端封顶（客户端自报，可传 999999 刷有效阅读时长）。"""
    from datetime import datetime
    db = TestSession()
    db.add(AcademicCard(id=1, representative_id=1, title="卡1", content={"conclusion": "x"}, is_ai_generated=True))
    db.add(CardPushRecord(id=1, representative_id=1, card_id=1, doctor_id=2, read_status="unread"))
    db.commit()
    db.close()

    resp = client.post("/api/v1/card-pushes/1/track", json={"read_status": "read", "seconds": 999999},
                       headers=_token(2, "doctor"))
    assert resp.json()["code"] == 0
    db = TestSession()
    rec = db.query(CardPushRecord).get(1)
    db.close()
    assert rec.tracked_seconds == 3600
    assert rec.read_at is not None


# ==================== M-1（2026-08-24 审查修复）：引用链与检索原文入模 ====================

class _FakeQwen:
    """替身 QwenClient：捕获入参消息，返回固定卡片 JSON"""
    def __init__(self):
        self.messages = None

    def chat(self, messages, **kw):
        self.messages = messages
        return {"content": '{"conclusion": "c", "key_points": ["k"], "summary": "s"}'}


_FAKE_RESULTS = [
    {"title": "高血压防治指南", "content": "推荐每日食盐摄入量小于5克。" * 5,
     "url": "https://oss/guide.pdf", "doc_id": "doc-1", "score": 0.9},
    {"title": "限盐与血压", "content": "限盐可显著降低收缩压。",
     "url": "https://oss/salt.pdf", "doc_id": "doc-2", "score": 0.8},
]


@pytest.mark.asyncio
async def test_generate_card_citations_use_real_contract_and_feed_content(monkeypatch):
    """引用取检索层真实键（title/url/doc_id），且检索原文进 prompt（此前两者皆无 → 引用恒空、内容凭空编）"""
    fake = _FakeQwen()
    monkeypatch.setattr(ac_api, "_retrieve", AsyncMock(return_value={"results": _FAKE_RESULTS}))
    monkeypatch.setattr(ac_api, "QwenClient", lambda: fake)

    card = await ac_api._generate_card_content("高血压", "限盐建议")

    assert card["citations"] == [
        {"doc_name": "高血压防治指南", "url": "https://oss/guide.pdf", "doc_id": "doc-1"},
        {"doc_name": "限盐与血压", "url": "https://oss/salt.pdf", "doc_id": "doc-2"},
    ]
    user_msg = fake.messages[1]["content"]
    # 检索原文必须喂给模型（截断到 800 字/条）
    assert "推荐每日食盐摄入量" in user_msg
    assert "限盐可显著降低收缩压" in user_msg
    # 主题/标题是用户输入，必须留在 <user_content> 定界内（防注入）
    assert "<user_content>\n主题：高血压\n卡片标题：限盐建议" in user_msg


@pytest.mark.asyncio
async def test_generate_card_no_sources_fails_closed(monkeypatch):
    """知识库零命中 → 拒绝生成（凭空写学术内容 = 必然编造）"""
    monkeypatch.setattr(ac_api, "_retrieve", AsyncMock(return_value={"results": []}))
    with pytest.raises(Exception) as ei:
        await ac_api._generate_card_content("不存在的主题", "x")
    assert "引用" in str(ei.value)


@pytest.mark.asyncio
async def test_generate_card_skips_metadata_less_sources(monkeypatch):
    """M-1 残留：百炼降级检索 metadata 缺失 → dict 存在但 title 空。
    不可溯源条目必须剔除（sources/citations/excerpts 同步收窄），不全拒。"""
    mixed = [
        {"title": "", "content": "无元数据条目的正文", "url": "", "doc_id": ""},
        {"title": "有据文献", "content": "正文A", "url": "https://oss/a.pdf", "doc_id": 7},
        {"title": None, "content": "title 为 None 的条目", "url": None, "doc_id": None},
    ]
    fake = _FakeQwen()
    monkeypatch.setattr(ac_api, "_retrieve", AsyncMock(return_value={"results": mixed}))
    monkeypatch.setattr(ac_api, "QwenClient", lambda: fake)

    card = await ac_api._generate_card_content("主题", "标题")

    assert card["citations"] == [{"doc_name": "有据文献", "url": "https://oss/a.pdf", "doc_id": 7}]
    user_msg = fake.messages[1]["content"]
    assert "正文A" in user_msg
    assert "无元数据条目的正文" not in user_msg  # excerpts 与引用对位收窄


@pytest.mark.asyncio
async def test_generate_card_all_empty_metadata_fails_closed(monkeypatch):
    """M-1 残留：检索命中但元数据全空（无法溯源）→ 同零命中 fail-closed 4001"""
    empty_meta = [
        {"title": "", "content": "正文1", "url": "", "doc_id": ""},
        {"title": "", "content": "正文2", "url": "", "doc_id": ""},
    ]
    monkeypatch.setattr(ac_api, "_retrieve", AsyncMock(return_value={"results": empty_meta}))
    with pytest.raises(Exception) as ei:
        await ac_api._generate_card_content("主题", "标题")
    assert "引用" in str(ei.value)


def test_create_card_no_sources_returns_4001(fresh_state, monkeypatch):
    """端到端：检索空 → BusinessError 4001 透传（不被吞成笼统 6001）"""
    async def _empty_retrieve(topic, top_k=3):
        return {"results": []}
    monkeypatch.setattr(ac_api, "_retrieve", _empty_retrieve)

    resp = client.post("/api/v1/academic-cards", json={"title": "无据卡片", "topic": "任意"},
                       headers=_token(1, "rep"))
    assert resp.status_code == 422
    assert resp.json()["code"] == 4001


@pytest.mark.asyncio
async def test_generate_card_rejects_empty_llm_output(monkeypatch):
    """M-1 收尾：LLM 畸形输出（缺 conclusion/key_points）→ 拒绝，不落空壳卡"""
    class _BadQwen:
        def chat(self, messages, **kw):
            return {"content": '{"summary": "只有总结"}'}

    monkeypatch.setattr(ac_api, "_retrieve", AsyncMock(return_value={"results": _FAKE_RESULTS}))
    monkeypatch.setattr(ac_api, "QwenClient", lambda: _BadQwen())
    with pytest.raises(Exception) as ei:
        await ac_api._generate_card_content("高血压", "限盐")
    assert "conclusion" in str(ei.value) or "key_points" in str(ei.value)
