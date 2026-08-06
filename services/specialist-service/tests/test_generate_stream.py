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


async def _fake_check_pass(content, context):
    await asyncio.sleep(0)
    return {"blocked": False, "violations": []}


async def _fake_check_blocked(content, context):
    await asyncio.sleep(0)
    return {"blocked": True, "violations": [{"rule_code": "R001", "description": "违规"}]}


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
