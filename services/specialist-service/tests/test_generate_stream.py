"""AnswerGenerator.generate_stream 流式测试"""
import asyncio
import pytest
from app.core.answer_generator import AnswerGenerator
from app.models.specialist import Specialist


def _spec(**kwargs):
    data = dict(
        id=1, name="测试专员", bailian_app_id="app-1",
        persona="", knowledge_scope="", compliance_level="internal",
    )
    data.update(kwargs)
    return Specialist(**data)


class FakeBailianStream:
    """替代 bailian.chat_stream：预置 delta/done 帧"""
    def __init__(self, frames):
        self._frames = list(frames)

    async def chat_stream(self, app_id, prompt, session_id=None, history=None):
        for f in self._frames:
            yield f


def _delta(text):
    return {"type": "delta", "text": text}


def _done(text):
    return {"type": "done", "text": text, "dialog_id": "dlg-1", "citations": []}


async def _fake_check_pass(content, context, fast=False):
    await asyncio.sleep(0)
    return {"blocked": False, "violations": []}


async def _fake_check_blocked(content, context, fast=False):
    await asyncio.sleep(0)
    return {"blocked": True, "violations": [{"rule_code": "R001", "description": "违规"}]}


async def _fake_check_gate(content, context, fast=False):
    """流式门禁：累积文本含"违禁"才拦（覆盖逐帧检查 + 阻断时全量复核）"""
    await asyncio.sleep(0)
    if "违禁" in content:
        return {"blocked": True, "violations": [{"rule_code": "R001", "description": "违禁词"}]}
    return {"blocked": False, "violations": []}


class _FakeQwen:
    def __init__(self, content="降级答案"):
        self.content = content

    def chat(self, messages, model, temperature):
        return {"content": self.content}


class _BailianDown:
    """chat_stream 首次迭代即抛错，触发 qwen 降级路径（须是 async generator，
    普通 async def 返回协程无法被 async for 消费）"""

    async def chat_stream(self, app_id, prompt, session_id=None, history=None):
        from app.services.bailian_client import BailianException
        raise BailianException("bailian down")
        yield  # pragma: no cover —— 让函数成为 async generator


async def _fake_audit(**kw):
    await asyncio.sleep(0)


def test_generate_stream_delta_and_done(monkeypatch):
    monkeypatch.setattr(
        "app.core.answer_generator.check_compliance", _fake_check_pass,
    )
    monkeypatch.setattr(
        "app.core.answer_generator.write_audit_log", _fake_audit,
    )
    generator = AnswerGenerator()
    generator.bailian = FakeBailianStream([_delta("你"), _delta("你好"), _done("你好呀")])

    async def run():
        frames = []
        async for frame in generator.generate_stream("你好", _spec(), user_id=1):
            frames.append(frame)
        return frames

    frames = asyncio.run(run())
    types = [f["type"] for f in frames]
    assert types == ["delta", "delta", "done"]
    assert frames[0]["text"] == "你"
    done = frames[-1]
    assert done["answer"] == "你好呀"
    assert done["blocked"] is False
    assert done["session_id"] == "dlg-1"
    assert done["request_id"]


def test_generate_stream_question_blocked(monkeypatch):
    monkeypatch.setattr(
        "app.core.answer_generator.check_compliance", _fake_check_blocked,
    )
    generator = AnswerGenerator()

    async def run():
        frames = []
        async for frame in generator.generate_stream("违禁问题", _spec(), user_id=1):
            frames.append(frame)
        return frames

    frames = asyncio.run(run())
    assert len(frames) == 1
    assert frames[0]["type"] == "done"
    assert frames[0]["blocked"] is True
    assert frames[0]["violations"][0]["rule_code"] == "R001"


def test_generate_stream_midstream_blocked_not_forwarded(monkeypatch):
    """逐帧门禁：违规 delta 不转发，产出 compliance 帧 + 掩码 done"""
    monkeypatch.setattr(
        "app.core.answer_generator.check_compliance", _fake_check_gate,
    )
    monkeypatch.setattr(
        "app.core.answer_generator.write_audit_log", _fake_audit,
    )
    generator = AnswerGenerator()
    generator.bailian = FakeBailianStream([_delta("正常"), _delta("违禁"), _done("正常违禁")])

    async def run():
        frames = []
        async for frame in generator.generate_stream("你好", _spec(), user_id=1):
            frames.append(frame)
        return frames

    frames = asyncio.run(run())
    types = [f["type"] for f in frames]
    # 正常 delta 透传；违禁 delta 被阻断；随后 compliance 门禁帧 + 掩码 done
    assert types == ["delta", "compliance", "done"]
    assert frames[0]["text"] == "正常"
    assert frames[1]["blocked"] is True
    assert frames[1]["violations"][0]["rule_code"] == "R001"
    done = frames[-1]
    assert done["blocked"] is True
    assert "咨询医学顾问" in done["answer"]  # 掩码话术，不含违规原文
    assert done["violations"][0]["rule_code"] == "R001"


def test_generate_stream_fallback_blocked_not_forwarded(monkeypatch):
    """降级整段输出同样过门禁：命中不 yield delta，直接 compliance + 掩码 done"""
    calls = []

    async def _fake_check(content, context, fast=False):
        await asyncio.sleep(0)
        calls.append((content, context.get("type"), fast))
        if context.get("type") == "ai_output":
            return {"blocked": True, "violations": [{"rule_code": "R001", "description": "违禁词"}]}
        return {"blocked": False, "violations": []}

    monkeypatch.setattr(
        "app.core.answer_generator.check_compliance", _fake_check,
    )
    monkeypatch.setattr(
        "app.core.answer_generator.write_audit_log", _fake_audit,
    )
    generator = AnswerGenerator()
    generator.bailian = _BailianDown()
    generator.qwen = _FakeQwen("违禁降级答案")

    async def run():
        frames = []
        async for frame in generator.generate_stream("你好", _spec(), user_id=1):
            frames.append(frame)
        return frames

    frames = asyncio.run(run())
    types = [f["type"] for f in frames]
    assert types == ["compliance", "done"]  # 无 delta：违规降级输出一字未发
    assert frames[1]["blocked"] is True
    # 降级文本先过 fast 门禁，再全量复核（拦截记录用）
    assert calls[-1][2] is False
    assert "违禁降级答案" in calls[-1][0]
