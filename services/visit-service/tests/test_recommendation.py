"""LLM 实时推荐测试（假 Qwen，不连真实服务）"""
import sys
import os
from datetime import datetime, timedelta

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", ".."))

import pytest
import asyncio

import app.core.visit_manager as vm_module
from app.models.visit_record import VisitRecord

# 复用 test_visit_manager.py 的 FakeDb（同目录 import）
from test_visit_manager import FakeDb


class FakeQwen:
    """假 QwenClient：可注入返回内容或抛异常"""
    def __init__(self, content=None, error=None, call_count=None):
        self._content = content
        self._error = error
        self.calls = [] if call_count is None else call_count

    def chat(self, messages, model=None, temperature=0.1, max_tokens=2000):
        self.calls.append(messages)
        if self._error:
            raise self._error
        return {"content": self._content, "usage": {}}


def make_manager(fake_qwen):
    return vm_module.VisitManager(qwen=fake_qwen)


def make_record():
    rec = VisitRecord()
    rec.id = 1
    rec.visit_time = datetime.now()
    return rec


def test_short_sentence_not_triggered():
    q = FakeQwen(content='{"key_nodes":[]}')
    m = make_manager(q)
    db = FakeDb()
    rec = make_record()
    db.add(rec)
    result = asyncio.run(m._llm_recommend(db, rec.id, 1, "好的"))
    assert result is None
    assert q.calls == []  # 短句不触发


def test_throttled_within_cooldown():
    q = FakeQwen(content='{"key_nodes":[]}')
    m = make_manager(q)
    db = FakeDb()
    rec = make_record()
    rec.key_nodes = [{"type": "interest_point", "label": "认可", "quote": "x",
                      "created_at": datetime.now().isoformat()}]  # 刚标记过 → 冷却中
    db.add(rec)
    result = asyncio.run(m._llm_recommend(db, rec.id, 1, "这句话超过六个字了"))
    assert result is None
    assert q.calls == []


def test_llm_failure_degrades():
    q = FakeQwen(error=RuntimeError("LLM 挂了"))
    m = make_manager(q)
    db = FakeDb()
    rec = make_record()
    db.add(rec)
    result = asyncio.run(m._llm_recommend(db, rec.id, 1, "这句话超过六个字了"))
    assert result is None  # 降级：返回 None 而非抛异常


def test_success_returns_and_persists():
    content = ('{"key_nodes":[{"type":"decision_point","label":"决策表态",'
               '"quote":"主任表示考虑使用"}],"suggestion":{"topic":"价格",'
               '"advice":"建议强调药物经济学优势"}}')
    q = FakeQwen(content=content)
    m = make_manager(q)
    db = FakeDb()
    rec = make_record()
    db.add(rec)
    result = asyncio.run(m._llm_recommend(db, rec.id, 1, "主任表示考虑使用我们的产品"))
    assert result is not None
    assert result["key_nodes"][0]["type"] == "decision_point"
    assert result["ai_suggestion"]["advice"] == "建议强调药物经济学优势"
    assert len(rec.key_nodes) == 1  # 已落库
    assert rec.key_nodes[0]["created_at"]


def test_unparseable_output_degrades():
    q = FakeQwen(content="抱歉我无法处理")
    m = make_manager(q)
    db = FakeDb()
    rec = make_record()
    db.add(rec)
    result = asyncio.run(m._llm_recommend(db, rec.id, 1, "这句话超过六个字了"))
    assert result is None


def test_process_transcript_includes_recommendation(monkeypatch):
    """集成：process_transcript 响应含 key_nodes/ai_suggestion"""
    q = FakeQwen(content='{"key_nodes":[{"type":"interest_point","label":"认可","quote":"q"}],"suggestion":null}')
    m = make_manager(q)

    async def _fake_check_compliance(text, ctx):
        return {"blocked": False, "violations": []}

    monkeypatch.setattr(vm_module, "check_compliance", _fake_check_compliance)
    db = FakeDb()
    rec = make_record()
    db.add(rec)
    result = asyncio.run(m.process_transcript(db, rec.id, 1, text_content="这句话超过六个字了"))
    assert "key_nodes" in result
    assert result["key_nodes"][0]["type"] == "interest_point"
    assert "ai_suggestion" in result
