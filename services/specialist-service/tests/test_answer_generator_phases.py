"""AnswerGenerator 埋点测试：阶段切换写注册表，退出必置 idle"""
import asyncio
from app.core.answer_generator import AnswerGenerator
from app.core import activity_registry
from app.core.activity_registry import registry
from app.models.specialist import Specialist


def _spec(specialist_id=1):
    return Specialist(
        id=specialist_id, name="测试专员", bailian_app_id="app-1",
        persona="", knowledge_scope="", compliance_level="internal",
    )


async def _check_pass(content, context):
    await asyncio.sleep(0)
    return {"blocked": False, "violations": []}


async def _check_blocked(content, context):
    await asyncio.sleep(0)
    return {"blocked": True, "violations": [{"rule_code": "R001"}]}


async def _audit(**kw):
    await asyncio.sleep(0)


class RecordingBailian:
    """调用时记录注册表当前 phase（证明 generating 阶段已写入）"""
    def __init__(self):
        self.phase_at_call = None

    async def chat(self, app_id, prompt, session_id=None):
        self.phase_at_call = registry.get(1).phase if registry.get(1) else None
        return {"text": "你好", "citations": [], "dialog_id": "dlg-1"}


def _mk(monkeypatch, check):
    monkeypatch.setattr("app.core.answer_generator.check_compliance", check)
    monkeypatch.setattr("app.core.answer_generator.write_audit_log", _audit)
    g = AnswerGenerator()
    return g


def test_generate_phases_written_and_idle_after(monkeypatch):
    b = RecordingBailian()
    g = _mk(monkeypatch, _check_pass)
    g.bailian = b

    # 记录每个合规检查调用时刻的 phase（precheck 时应为 compliance_precheck，审核时应为 compliance_review）
    seen = []

    async def recording_check(content, context):
        await asyncio.sleep(0)
        seen.append(registry.get(1).phase if registry.get(1) else None)
        return {"blocked": False, "violations": []}

    monkeypatch.setattr("app.core.answer_generator.check_compliance", recording_check)

    result = asyncio.run(g.generate("肺癌用药注意事项", _spec(), user_id=1))
    assert result["answer"] == "你好"
    assert seen == ["compliance_precheck", "compliance_review"]
    assert b.phase_at_call == "generating"
    assert registry.get(1) is None  # finally 置 idle


def test_generate_blocked_precheck_still_idle(monkeypatch):
    g = _mk(monkeypatch, _check_blocked)
    result = asyncio.run(g.generate("违规问题", _spec(), user_id=1))
    assert result["blocked"] is True
    assert registry.get(1) is None


def test_generate_stream_phases_and_idle_after(monkeypatch):
    class FakeStream:
        async def chat_stream(self, app_id, prompt, session_id=None, history=None):
            yield {"type": "delta", "text": "你"}
            yield {"type": "done", "text": "你好", "dialog_id": "dlg-1", "citations": []}

    g = _mk(monkeypatch, _check_pass)
    g.bailian = FakeStream()

    async def run():
        frames = []
        async for frame in g.generate_stream("你好", _spec(), user_id=1):
            frames.append(frame)
        return frames

    frames = asyncio.run(run())
    assert frames[-1]["type"] == "done"
    assert registry.get(1) is None  # 流消费完后 finally 置 idle
