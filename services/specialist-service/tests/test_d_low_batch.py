"""D 域低危批回归测试（2026-08-13，D1-D5）

- D1 COMPLIANCE_BLOCKS 指标接线（原死代码恒 0）+ qwen_client.chat_stream 死代码删除
- D2 specialists CRUD：product_id int 转换 + 产品存在性、name 非空、update 显式 null 清空
- D3 问题预检被拦留痕（REST + 流式）：question_blocked 审计 + CHAT_LATENCY 观测
- D4 toggle_favorite 并发撞唯一约束 → 幂等成功不 500
- D5 降级 300 字截断 + 同 session 最近几轮问答拼入 qwen messages
"""
import asyncio
from types import SimpleNamespace

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient
from prometheus_client import REGISTRY

from app.core.answer_generator import AnswerGenerator
from app.models.specialist import Specialist
from app.services.bailian_client import BailianException


def _spec(specialist_id=1, name="测试专员"):
    return Specialist(
        id=specialist_id, name=name, bailian_app_id="app-1",
        persona="", knowledge_scope="", compliance_level="internal",
    )


async def _check_pass(content, context, fast=False):
    await asyncio.sleep(0)
    return {"blocked": False, "violations": []}


async def _check_question_blocked(content, context, fast=False):
    await asyncio.sleep(0.005)  # 保证 latency_ms > 0（延迟观测可断言）
    return {"blocked": True, "violations": [{"rule_code": "R001"}]}


async def _audit(**kw):
    await asyncio.sleep(0)


# ==================== D1：COMPLIANCE_BLOCKS 接线 + chat_stream 死代码 ====================

def test_compliance_blocks_incremented_on_stream_gate_block(monkeypatch):
    """D1：流式门禁阻断落点 _blocked_frames 给 COMPLIANCE_BLOCKS 计数。

    修复前该 Counter 恒 0 —— arms-alerts.yaml 引用的 compliance_blocks_total
    在 specialist 侧无样本。口径对齐 compliance checker：只计 action=reject。
    """

    async def _gate(content, context, fast=False):
        await asyncio.sleep(0)
        if context.get("type") == "user_input":
            return {"blocked": False, "violations": []}  # 预检放行
        if fast:
            if "违禁" in content:
                return {"blocked": True, "violations": [{"rule_code": "R001"}]}
            return {"blocked": False, "violations": []}
        # 全量复核（_blocked_frames 内）：真实形状带 action/severity
        return {"blocked": True, "violations": [
            {"action": "reject", "severity": "high", "rule_code": "R001"},
        ]}

    monkeypatch.setattr("app.core.answer_generator.check_compliance", _gate)
    monkeypatch.setattr("app.core.answer_generator.write_audit_log", _audit)

    labels = {"action": "reject", "severity": "high"}
    before = REGISTRY.get_sample_value("compliance_blocks_total", labels) or 0.0

    class _Stream:
        async def chat_stream(self, app_id, prompt, session_id=None, history=None):
            yield {"type": "delta", "text": "正常"}
            yield {"type": "delta", "text": "违禁内容"}
            yield {"type": "done", "text": "违禁内容", "dialog_id": "dlg-1", "citations": []}

    g = AnswerGenerator()
    g.bailian = _Stream()

    async def run():
        frames = []
        async for f in g.generate_stream("问题", _spec(), user_id=1):
            frames.append(f)
        return frames

    frames = asyncio.run(run())
    assert frames[-1]["blocked"] is True
    after = REGISTRY.get_sample_value("compliance_blocks_total", labels) or 0.0
    assert after == before + 1


def test_qwen_client_chat_stream_removed():
    """D1：qwen_client.chat_stream 死代码已删（全仓无调用方，流式走百炼）"""
    from app.services.qwen_client import QwenClient
    assert not hasattr(QwenClient, "chat_stream")


# ==================== D2：specialists CRUD 校验 ====================

def test_validate_product_id_non_int_param_error():
    from app.api.specialists import _validate_specialist_fields
    from shared.common.response import ParamError
    with pytest.raises(ParamError) as exc:
        _validate_specialist_fields({"name": "A", "product_id": "abc"}, creating=True)
    assert "product_id" in str(exc.value)


def test_validate_product_id_converts_to_int():
    from app.api.specialists import _validate_specialist_fields
    data = _validate_specialist_fields({"name": "A", "product_id": "3"}, creating=True)
    assert data["product_id"] == 3
    assert isinstance(data["product_id"], int)


def test_validate_update_name_null_or_empty_rejected():
    """D2：update 传 name 但为 null/空串 → ParamError（name 是 NOT NULL 列）"""
    from app.api.specialists import _validate_specialist_fields
    from shared.common.response import ParamError
    with pytest.raises(ParamError):
        _validate_specialist_fields({"name": None}, creating=False)
    with pytest.raises(ParamError):
        _validate_specialist_fields({"name": "   "}, creating=False)


# ---- 端点级：产品存在性 / 显式 null 清空 ----

class _UserStub:
    """require_roles 库查替身（S6 修复后每次受限请求查 users 主键）"""

    def __init__(self, db):
        self._db = db

    def filter(self, *a, **k):
        return self

    def first(self):
        return SimpleNamespace(id=1, status="active", role=self._db.user_role)


class _Chain:
    def __init__(self, rows=None):
        self.rows = list(rows or [])

    def filter(self, *a, **k):
        return self

    def order_by(self, *a, **k):
        return self

    def first(self):
        return self.rows[0] if self.rows else None

    def all(self):
        return self.rows


class _CrudDb:
    def __init__(self, specialists=None, products=None):
        self.specialists = _Chain(specialists)
        self.products = _Chain(products)
        self.added = []
        self.user_role = "admin"

    def query(self, model):
        name = getattr(getattr(model, "__table__", None), "name", None) or model.__name__
        if name == "digital_specialists":
            return self.specialists
        if name == "products":
            return self.products
        if name == "users":
            return _UserStub(self)
        raise AssertionError(f"unexpected table: {name}")

    def add(self, obj):
        self.added.append(obj)

    def commit(self):
        pass

    def refresh(self, obj):
        obj.id = 1


def _crud_client(db, monkeypatch):
    from app.main import app
    from app.api.conversations import get_current_user
    from shared.common.db_session import get_db

    async def _fake_audit(**kw):
        pass

    monkeypatch.setattr("app.api.specialists.write_audit_log", _fake_audit)
    app.dependency_overrides[get_db] = lambda: db
    app.dependency_overrides[get_current_user] = lambda: {"id": 1, "role": "admin"}
    return TestClient(app)


def test_create_product_not_exists_business_error(monkeypatch):
    """D2：product_id 引用的产品不存在 → BusinessError（4000/422），不再 FK 500"""
    db = _CrudDb(products=[])  # products 表无该产品
    resp = _crud_client(db, monkeypatch).post(
        "/api/v1/specialists", json={"name": "A", "product_id": 999},
    )
    assert resp.status_code == 422
    body = resp.json()
    assert body["code"] == 4000
    assert "产品不存在" in body["message"]
    assert db.added == []


def test_create_product_id_non_int_param_error(monkeypatch):
    """D2：product_id 不可转 int → ParamError（1000/400），不再 int() 抛 ValueError 500"""
    db = _CrudDb()
    resp = _crud_client(db, monkeypatch).post(
        "/api/v1/specialists", json={"name": "A", "product_id": "abc"},
    )
    assert resp.status_code == 400
    assert resp.json()["code"] == 1000
    assert db.added == []


def test_update_explicit_null_clears_nullable_fields(monkeypatch):
    """D2：update 显式传 null → 清空字段。旧实现 data[field] is not None
    使 persona/knowledge_scope 等可空字段永远无法清空"""
    spec = Specialist(
        id=1, name="旧名", product_id=1,
        persona={"style": "a"}, knowledge_scope=["肿瘤"],
        compliance_level="internal", bailian_app_id="mm_1", status="active",
    )
    db = _CrudDb(specialists=[spec], products=[object()])
    resp = _crud_client(db, monkeypatch).put(
        "/api/v1/specialists/1",
        json={"persona": None, "knowledge_scope": None},
    )
    assert resp.status_code == 200, resp.text
    data = resp.json()["data"]
    assert data["persona"] is None
    assert data["knowledge_scope"] is None
    assert data["name"] == "旧名"  # 未传字段不受影响
    assert data["status"] == "active"


def test_update_status_null_rejected(monkeypatch):
    """D2：status 有枚举语义，显式 null 按非法值处理（ParamError）"""
    spec = Specialist(
        id=1, name="旧名", product_id=1, persona=None,
        compliance_level="internal", bailian_app_id=None, status="active",
    )
    db = _CrudDb(specialists=[spec])
    resp = _crud_client(db, monkeypatch).put(
        "/api/v1/specialists/1", json={"status": None},
    )
    assert resp.status_code == 400
    assert "status" in resp.json()["message"]


def test_update_product_not_exists_business_error(monkeypatch):
    """D2：update 换绑不存在的产品同样预检（防 FK 500）"""
    spec = Specialist(
        id=1, name="旧名", product_id=1, persona=None,
        compliance_level="internal", bailian_app_id=None, status="active",
    )
    db = _CrudDb(specialists=[spec], products=[])
    resp = _crud_client(db, monkeypatch).put(
        "/api/v1/specialists/1", json={"product_id": 999},
    )
    assert resp.status_code == 422
    assert "产品不存在" in resp.json()["message"]


# ==================== D3：预检被拦留痕 ====================

def test_generate_question_blocked_writes_audit_and_latency(monkeypatch):
    """D3（REST）：预检被拦 → question_blocked 审计 + CHAT_LATENCY 观测
    （与答案被拦路径同口径；此前被拦请求在审计与监控中完全不可见）"""
    from app.api.metrics import CHAT_LATENCY

    calls = []

    async def _rec(**kw):
        calls.append(kw)

    monkeypatch.setattr("app.core.answer_generator.check_compliance", _check_question_blocked)
    monkeypatch.setattr("app.core.answer_generator.write_audit_log", _rec)
    sum_before = CHAT_LATENCY._sum.get()

    g = AnswerGenerator()
    result = asyncio.run(g.generate("违规问题", _spec(), user_id=7))
    assert result["blocked"] is True
    assert result["latency_ms"] >= 0
    assert len(calls) == 1
    c = calls[0]
    assert c["action"] == "question_blocked"
    assert c["user_id"] == 7
    assert c["ai_involved"] is False
    assert c["ai_prompt"] == "违规问题"
    assert c["compliance_result"]["blocked"] is True
    assert c["request_id"] == result["request_id"]
    # 延迟已观测（与答案被拦路径同口径）
    assert CHAT_LATENCY._sum.get() > sum_before


def test_generate_stream_question_blocked_writes_audit(monkeypatch):
    """D3（流式）：预检被拦 → question_blocked 审计 + done 帧，同 REST 口径"""
    calls = []

    async def _rec(**kw):
        calls.append(kw)

    monkeypatch.setattr("app.core.answer_generator.check_compliance", _check_question_blocked)
    monkeypatch.setattr("app.core.answer_generator.write_audit_log", _rec)
    g = AnswerGenerator()

    async def run():
        frames = []
        async for f in g.generate_stream("违规问题", _spec(), user_id=7):
            frames.append(f)
        return frames

    frames = asyncio.run(run())
    assert len(frames) == 1
    done = frames[0]
    assert done["type"] == "done"
    assert done["blocked"] is True
    assert done["latency_ms"] >= 0
    assert len(calls) == 1
    assert calls[0]["action"] == "question_blocked"
    assert calls[0]["user_id"] == 7
    assert calls[0]["ai_prompt"] == "违规问题"
    assert calls[0]["request_id"] == done["request_id"]


# ==================== D4：toggle_favorite 并发幂等 ====================

def test_toggle_favorite_concurrent_duplicate_idempotent(monkeypatch):
    """D4：并发双点 toggle —— check-then-insert 竞态下第二个请求 insert 撞
    (user_id, conversation_id) 唯一约束 → 捕获 IntegrityError 转幂等成功
    （该收藏已由并发请求写入，最终态即已收藏），不再 500"""
    from sqlalchemy.exc import IntegrityError

    class _ConvStub:
        def __init__(self, conv):
            self._conv = conv

        def filter(self, *a, **k):
            return self

        def order_by(self, *a, **k):
            return self

        def first(self):
            return self._conv

        def all(self):
            return [self._conv]

    class _FavStub:
        def filter(self, *a, **k):
            return self

        def first(self):
            return None  # 并发窗口：尚未见已有收藏

    class _Db:
        def __init__(self):
            self.rolled_back = False

        def query(self, model):
            if model.__name__ == "Conversation":
                return _ConvStub(SimpleNamespace(
                    id=16, user_id=3, specialist_id=1, session_id="sess-1",
                    role="user", content="问题", citations=None,
                ))
            return _FavStub()

        def add(self, obj):
            pass

        def commit(self):
            raise IntegrityError(
                "INSERT INTO conversation_favorites", {},
                Exception("duplicate key value violates unique constraint"),
            )

        def rollback(self):
            self.rolled_back = True

    from app.main import app
    from app.api.conversations import get_current_user, get_db

    db = _Db()
    app.dependency_overrides[get_db] = lambda: db
    app.dependency_overrides[get_current_user] = lambda: {"id": 3, "role": "rep"}
    resp = TestClient(app).post("/api/v1/conversations/16/favorite")
    assert resp.status_code == 200, resp.text
    assert resp.json()["data"]["is_favorite"] is True
    assert db.rolled_back is True


# ==================== D5：降级 300 字截断 + 多轮上下文 ====================

def test_fallback_truncates_to_300_chars():
    """D5：降级输出硬性 300 字符截断（提示词"不超过 300 字"只是软约束），
    max_tokens 同步收紧（600，中文约 1-2 token/字）"""
    captured = {}

    class _Qwen:
        def chat(self, messages, model, temperature, max_tokens=None):
            captured["messages"] = list(messages)
            captured["max_tokens"] = max_tokens
            return {"content": "长" * 400}

    g = AnswerGenerator()
    g.qwen = _Qwen()
    out = g._fallback_generate("问题", _spec(), history=[])
    assert out == "长" * 300
    assert len(out) == 300
    assert captured["max_tokens"] == 600


def test_fallback_injects_session_history_messages():
    """D5：history 拼在最终 prompt 之前，追问带上下文"""
    captured = {}

    class _Qwen:
        def chat(self, messages, model, temperature, max_tokens=None):
            captured["messages"] = list(messages)
            return {"content": "回答"}

    g = AnswerGenerator()
    g.qwen = _Qwen()
    history = [
        {"role": "user", "content": "第一轮问题"},
        {"role": "assistant", "content": "第一轮回答"},
    ]
    g._fallback_generate("追问：还有什么禁忌", _spec(), history=history)
    msgs = captured["messages"]
    assert msgs[0] == history[0]
    assert msgs[1] == history[1]
    assert msgs[2]["role"] == "user"
    assert "追问：还有什么禁忌" in msgs[2]["content"]
    assert "300" in msgs[2]["content"]  # 300 字约束提示仍在最终 prompt


class _HistChain:
    def __init__(self, rows):
        self._rows = list(rows)

    def filter(self, *a, **k):
        return self

    def order_by(self, *a, **k):
        return self

    def limit(self, n):
        self._rows = self._rows[:n]
        return self

    def first(self):
        return self._rows[0] if self._rows else None

    def all(self):
        return self._rows


class _HistDb:
    def __init__(self, rows):
        self._rows = list(rows)

    def query(self, model):
        return _HistChain(self._rows)


def _conv_row(id, role, content):
    return SimpleNamespace(id=id, role=role, content=content)


def test_load_fallback_history_takes_recent_3_rounds():
    """D5：同 session 按 id desc 取最近 6 行（3 轮），再转正序映射 user/assistant"""
    rows = [
        _conv_row(1, "user", "Q1"), _conv_row(2, "assistant", "A1"),
        _conv_row(3, "user", "Q2"), _conv_row(4, "assistant", "A2"),
        _conv_row(5, "user", "Q3"), _conv_row(6, "assistant", "A3"),
        _conv_row(7, "user", "Q4"), _conv_row(8, "assistant", "A4"),
    ]
    db = _HistDb(list(reversed(rows)))  # 查询按 id desc 返回
    g = AnswerGenerator()
    hist = g._load_fallback_history(db, "sess-1", 1)
    assert hist == [
        {"role": "user", "content": "Q2"},
        {"role": "assistant", "content": "A2"},
        {"role": "user", "content": "Q3"},
        {"role": "assistant", "content": "A3"},
        {"role": "user", "content": "Q4"},
        {"role": "assistant", "content": "A4"},
    ]


def test_load_fallback_history_foreign_session_rejected():
    """D5：归属校验复用 assert_session_owner —— 该 session 无该用户任何行 → 404"""
    g = AnswerGenerator()
    with pytest.raises(HTTPException) as exc:
        g._load_fallback_history(_HistDb([]), "dlg-other", 1)
    assert exc.value.status_code == 404


def test_generate_fallback_uses_session_history_from_db(monkeypatch):
    """D5 接线：REST generate 降级路径从 conversations 表取历史拼给 qwen，
    追问不再丢上下文"""

    class _BailianDown:
        async def chat(self, app_id, prompt, session_id=None):
            raise BailianException("bailian down")

    captured = {}

    class _Qwen:
        def chat(self, messages, model, temperature, max_tokens=None):
            captured["messages"] = list(messages)
            return {"content": "降级回答"}

    monkeypatch.setattr("app.core.answer_generator.check_compliance", _check_pass)
    monkeypatch.setattr("app.core.answer_generator.write_audit_log", _audit)
    g = AnswerGenerator()
    g.bailian = _BailianDown()
    g.qwen = _Qwen()

    db = _HistDb(list(reversed([  # 查询按 id desc 返回（最近在前）
        _conv_row(1, "user", "第一轮问题"),
        _conv_row(2, "assistant", "第一轮回答"),
    ])))
    result = asyncio.run(g.generate(
        "追问", _spec(), user_id=1, session_id="sess-1", db=db,
    ))
    assert result["answer"] == "降级回答"
    msgs = captured["messages"]
    assert msgs[0] == {"role": "user", "content": "第一轮问题"}
    assert msgs[1] == {"role": "assistant", "content": "第一轮回答"}
    assert "追问" in msgs[2]["content"]
