"""夜间简报生成核心测试（SQLite 内存库 + qwen 打桩，同 test_share_links.py 表模式）

覆盖用例（Task 3 Step 3 + C3 审查修复）：
- generate_for_date 只聚合 role=doctor 的对话（非 doctor 排除）
- 重跑幂等（唯一键 upsert，不堆积）
- 无 doctor 对话的分身 skipped、不建行
- 无分享链接的 rep 不生成
- _parse_json_content 兼容 ```json 包裹
- 连续 assistant 行不配出 (None, ...)（C3 修复 1）
- run_briefing_scan 逐篇写审计 action=briefing_generated（C3 修复 2）
"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", ".."))

os.environ.setdefault("JWT_SECRET", "test-secret-not-a-default-value")
os.environ["AUTH_DEV_MODE"] = "true"

from datetime import date, datetime

import pytest
from sqlalchemy import BigInteger, create_engine
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.ext.compiler import compiles
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from shared.models.base import Base
from shared.models.academic import Notification
from shared.models.digital_specialist import Specialist
from shared.models.doctor import ShareLink
from shared.models.nightly_briefing import NightlyBriefing
from shared.models.product import Product
from shared.models.user import User

from app.core.briefing_generator import (
    _doctor_rounds,
    _parse_json_content,
    generate_for_date,
    run_briefing_scan,
)
from app.models.conversation import Conversation


# SQLite 编译垫片（同 test_share_links.py / test_twin_subscriptions.py 模式）：
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
    ShareLink.__table__,
    NightlyBriefing.__table__,
    Conversation.__table__,
    Notification.__table__,
]

TARGET = date(2026, 8, 18)


def _add(*objs):
    db = TestSession()
    for o in objs:
        db.add(o)
    db.commit()
    db.close()


@pytest.fixture(autouse=True)
def fresh_state():
    """每用例重建 6 张表"""
    Base.metadata.drop_all(engine, tables=TABLES)
    Base.metadata.create_all(engine, tables=TABLES)
    yield


def _seed_rep_doctor_and_twin():
    """种子：rep(3) 建分享链接指向 twin(1)；医生(1)；另有 rep(2) 无分享链接"""
    _add(
        User(id=1, username="u1", full_name="张医生", phone="13800000001",
             role="doctor", status="active"),
        User(id=2, username="u2", full_name="李代表", phone="13800000002",
             role="rep", status="active"),
        User(id=3, username="u3", full_name="王代表", phone="13800000003",
             role="rep", status="active"),
        Specialist(id=1, name="肿瘤专员", product_id=None, status="active",
                   compliance_level="internal"),
        ShareLink(id=1, twin_id=1, url_token="t1", created_by=3, add_count=0),
    )


def _doctor_qna():
    """医生 1 的一条问答（聚合日 2026-08-17 内）"""
    return [
        Conversation(id=1, user_id=1, specialist_id=1, session_id="s1",
                     role="user", content="问题1",
                     created_at=datetime(2026, 8, 17, 10, 0, 0)),
        Conversation(id=2, user_id=1, specialist_id=1, session_id="s1",
                     role="assistant", content="答案1",
                     created_at=datetime(2026, 8, 17, 10, 1, 0)),
    ]


def test_generate_for_date_aggregates_doctor_conversations(fresh_state, monkeypatch):
    _seed_rep_doctor_and_twin()
    _add(*_doctor_qna())
    # 非 doctor（rep=2）对话 → 应被 _doctor_rounds 的 User.role=='doctor' 过滤排除
    _add(
        Conversation(id=3, user_id=2, specialist_id=1, session_id="s2",
                     role="user", content="非医生问题",
                     created_at=datetime(2026, 8, 17, 11, 0, 0)),
        Conversation(id=4, user_id=2, specialist_id=1, session_id="s2",
                     role="assistant", content="非医生答案",
                     created_at=datetime(2026, 8, 17, 11, 1, 0)),
    )

    prompts = []

    def _stub(prompt):
        prompts.append(prompt)
        return {"summary": "简报", "doctors": [
            {"doctor_name": "张医生", "questions": ["问题1"],
             "concern": "c", "follow_up": "f"},
        ]}

    monkeypatch.setattr("app.core.briefing_generator._qwen_briefing_json", _stub)

    db = TestSession()
    result = generate_for_date(db, TARGET)
    db.close()

    assert result["generated"] == 1
    assert result["skipped"] == 0
    assert result["reps"] == 1
    assert len(result["generated_links"]) == 1
    assert result["generated_links"][0]["representative_id"] == 3
    assert result["generated_links"][0]["specialist_id"] == 1
    assert result["generated_links"][0]["id"] is not None
    assert len(prompts) == 1
    # prompt 含医生问答、不含非 doctor 对话
    assert "张医生" in prompts[0]
    assert "问题1" in prompts[0]
    assert "答案1" in prompts[0]
    assert "非医生问题" not in prompts[0]

    db = TestSession()
    rows = db.query(NightlyBriefing).all()
    db.close()
    assert len(rows) == 1
    assert rows[0].representative_id == 3
    assert rows[0].specialist_id == 1
    assert rows[0].briefing_date == TARGET
    assert rows[0].status == "ready"
    assert rows[0].content["summary"] == "简报"


def test_generate_upserts_idempotent(fresh_state, monkeypatch):
    _seed_rep_doctor_and_twin()
    _add(*_doctor_qna())

    def _stub(prompt):
        return {"summary": "简报", "doctors": [
            {"doctor_name": "张医生", "questions": ["问题1"],
             "concern": "c", "follow_up": "f"},
        ]}

    monkeypatch.setattr("app.core.briefing_generator._qwen_briefing_json", _stub)

    db = TestSession()
    r1 = generate_for_date(db, TARGET)
    db.close()
    db = TestSession()
    r2 = generate_for_date(db, TARGET)
    db.close()

    assert r1["generated"] == 1
    assert r2["generated"] == 1  # 命中 existing 分支仍计 generated
    # 两次指向同一行（更新而非新增）
    assert r1["generated_links"][0]["id"] == r2["generated_links"][0]["id"]

    db = TestSession()
    rows = db.query(NightlyBriefing).all()
    db.close()
    assert len(rows) == 1  # 不堆积第二行

    # L-2（2026-08-24 审查修复）：重跑是内容更新，通知只发一次
    db = TestSession()
    notifications = db.query(Notification).filter_by(type="briefing_ready").all()
    db.close()
    assert len(notifications) == 1


def test_generate_skips_no_doctor_dialogue(fresh_state, monkeypatch):
    _seed_rep_doctor_and_twin()
    # 只有非 doctor（rep=2）对话 → _doctor_rounds 空 → skipped，不调 qwen、不建行
    _add(
        Conversation(id=1, user_id=2, specialist_id=1, session_id="s2",
                     role="user", content="非医生问题",
                     created_at=datetime(2026, 8, 17, 11, 0, 0)),
        Conversation(id=2, user_id=2, specialist_id=1, session_id="s2",
                     role="assistant", content="非医生答案",
                     created_at=datetime(2026, 8, 17, 11, 1, 0)),
    )

    called = []

    def _stub(prompt):
        called.append(prompt)
        return {"summary": "s", "doctors": []}

    monkeypatch.setattr("app.core.briefing_generator._qwen_briefing_json", _stub)

    db = TestSession()
    result = generate_for_date(db, TARGET)
    db.close()

    assert result["generated"] == 0
    assert result["skipped"] == 1
    assert result["reps"] == 1
    assert result["generated_links"] == []
    assert called == []

    db = TestSession()
    rows = db.query(NightlyBriefing).all()
    db.close()
    assert len(rows) == 0


def test_generate_only_reps_with_share_links(fresh_state, monkeypatch):
    # 有 doctor 对话，但无任何 share_link → rep_ids 空，不生成
    _add(
        User(id=1, username="u1", full_name="张医生", phone="13800000001",
             role="doctor", status="active"),
        Specialist(id=1, name="肿瘤专员", product_id=None, status="active",
                   compliance_level="internal"),
    )
    _add(*_doctor_qna())

    called = []

    def _stub(prompt):
        called.append(prompt)
        return {"summary": "s", "doctors": []}

    monkeypatch.setattr("app.core.briefing_generator._qwen_briefing_json", _stub)

    db = TestSession()
    result = generate_for_date(db, TARGET)
    db.close()

    assert result["generated"] == 0
    assert result["skipped"] == 0
    assert result["reps"] == 0
    assert result["generated_links"] == []
    assert called == []

    db = TestSession()
    rows = db.query(NightlyBriefing).all()
    db.close()
    assert len(rows) == 0


def test_parse_json_content_handles_fenced_output():
    # ```json 包裹
    assert _parse_json_content('```json\n{"summary": "s", "doctors": []}\n```') == {
        "summary": "s", "doctors": [],
    }
    # 裸 ``` 包裹
    assert _parse_json_content('```\n{"a": 1}\n```') == {"a": 1}
    # 纯 JSON
    assert _parse_json_content('{"summary": "s"}') == {"summary": "s"}
    # 非 dict / 非法 / 空 → None
    assert _parse_json_content("[1, 2, 3]") is None
    assert _parse_json_content("not json") is None
    assert _parse_json_content("") is None
    assert _parse_json_content(None) is None


def test_doctor_rounds_consecutive_assistant_no_none_pairing(fresh_state):
    """C3 修复 1：同一医生 user→assistant→assistant（无中间 user），第二段 assistant
    不得误配出 (None, ...)，_build_prompt 对 None 切片不再抛 TypeError。"""
    _add(
        User(id=1, username="u1", full_name="张医生", phone="13800000001",
             role="doctor", status="active"),
        Specialist(id=1, name="肿瘤专员", product_id=None, status="active",
                   compliance_level="internal"),
    )
    _add(
        Conversation(id=1, user_id=1, specialist_id=1, session_id="s1",
                     role="user", content="问题1",
                     created_at=datetime(2026, 8, 17, 10, 0, 0)),
        Conversation(id=2, user_id=1, specialist_id=1, session_id="s1",
                     role="assistant", content="答案1",
                     created_at=datetime(2026, 8, 17, 10, 1, 0)),
        Conversation(id=3, user_id=1, specialist_id=1, session_id="s1",
                     role="assistant", content="答案2",
                     created_at=datetime(2026, 8, 17, 10, 2, 0)),
    )

    db = TestSession()
    rounds = _doctor_rounds(
        db, 1,
        datetime(2026, 8, 17, 0, 0, 0),
        datetime(2026, 8, 18, 0, 0, 0),
    )
    db.close()

    assert len(rounds) == 1
    assert rounds[0]["qa"] == [("问题1", "答案1")]  # 第二段 assistant 不配对


@pytest.mark.asyncio
async def test_run_briefing_scan_audits_each_generated(monkeypatch):
    """C3 修复 2：run_briefing_scan 在生成后逐篇写审计 action=briefing_generated。"""
    class FakeDb:
        def close(self):
            pass

    generated = {
        "generated": 2,
        "skipped": 0,
        "reps": 1,
        "generated_links": [
            {"id": 11, "representative_id": 3, "specialist_id": 1},
            {"id": 12, "representative_id": 3, "specialist_id": 2},
        ],
    }

    monkeypatch.setattr("app.core.briefing_generator.SessionLocal", lambda: FakeDb())
    monkeypatch.setattr(
        "app.core.briefing_generator.generate_for_date",
        lambda db, target_date: generated,
    )

    audit_calls = []

    async def _audit(**kwargs):
        audit_calls.append(kwargs)

    monkeypatch.setattr("app.core.briefing_generator.write_audit_log", _audit)

    result = await run_briefing_scan()

    assert result == generated
    assert len(audit_calls) == 2
    assert [c["action"] for c in audit_calls] == ["briefing_generated", "briefing_generated"]
    assert [c["user_id"] for c in audit_calls] == [3, 3]
    assert [c["resource_type"] for c in audit_calls] == ["nightly_briefing", "nightly_briefing"]
    assert [c["resource_id"] for c in audit_calls] == ["11", "12"]
    assert all(c["ai_involved"] is True for c in audit_calls)
    assert all(c["ai_model"] == "qwen-max" for c in audit_calls)
