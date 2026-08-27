"""AnswerGenerator 埋点测试：阶段切换写注册表，退出必置 idle"""
import asyncio
from app.core.answer_generator import AnswerGenerator
from app.core.activity_registry import registry
from app.models.specialist import Specialist
from app.services.bailian_client import BailianException


def _spec(specialist_id=1):
    return Specialist(
        id=specialist_id, name="测试专员", bailian_app_id="app-1",
        persona="", knowledge_scope="", compliance_level="internal",
    )


async def _check_pass(content, context, fast=False):
    await asyncio.sleep(0)
    return {"blocked": False, "violations": []}


async def _check_blocked(content, context, fast=False):
    await asyncio.sleep(0)
    return {"blocked": True, "violations": [{"rule_code": "R001"}]}


async def _audit(**kw):
    await asyncio.sleep(0)


def _recording_check(seen, blocked_on_review=False):
    """记录每次合规检查调用时刻的 phase；blocked_on_review 时审核阶段返回 blocked"""
    async def recording_check(content, context, fast=False):
        await asyncio.sleep(0)
        seen.append(registry.get(1).phase if registry.get(1) else None)
        if blocked_on_review and context.get("type") != "user_input":
            return {"blocked": True, "violations": [{"rule_code": "R001"}]}
        return {"blocked": False, "violations": []}
    return recording_check


class RecordingBailian:
    """调用时记录注册表当前 phase（证明 generating 阶段已写入）"""
    def __init__(self):
        self.phase_at_call = None

    async def chat(self, app_id, prompt, session_id=None):
        self.phase_at_call = registry.get(1).phase if registry.get(1) else None
        return {"text": "你好", "citations": [], "dialog_id": "dlg-1"}


class RecordingStreamBailian:
    """流式版 RecordingBailian：chat_stream 调用时记录 phase"""
    def __init__(self):
        self.phase_at_call = None

    async def chat_stream(self, app_id, prompt, session_id=None, history=None):
        self.phase_at_call = registry.get(1).phase if registry.get(1) else None
        yield {"type": "delta", "text": "你"}
        yield {"type": "done", "text": "你好", "dialog_id": "dlg-1", "citations": []}


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
    b = RecordingStreamBailian()
    g = _mk(monkeypatch, _check_pass)
    g.bailian = b

    # 记录每个合规检查调用时刻的 phase（证明 precheck/review 阶段已写入）
    seen = []
    monkeypatch.setattr(
        "app.core.answer_generator.check_compliance", _recording_check(seen),
    )

    async def run():
        frames = []
        async for frame in g.generate_stream("你好", _spec(), user_id=1):
            frames.append(frame)
        return frames

    frames = asyncio.run(run())
    assert frames[-1]["type"] == "done"
    assert seen == ["compliance_precheck", "generating", "compliance_review"]
    assert b.phase_at_call == "generating"  # 流式 generating 阶段已写入
    assert registry.get(1) is None  # 流消费完后 finally 置 idle


def test_generate_review_blocked_still_idle(monkeypatch):
    """审核阶段 blocked：返回后注册表必已置空（先证明写入过，不是测空注册表）"""
    g = _mk(monkeypatch, _check_pass)
    g.bailian = RecordingBailian()

    seen = []
    monkeypatch.setattr(
        "app.core.answer_generator.check_compliance",
        _recording_check(seen, blocked_on_review=True),
    )

    result = asyncio.run(g.generate("问题", _spec(), user_id=1))
    assert result["blocked"] is True
    assert seen == ["compliance_precheck", "compliance_review"]  # 注册表确实被写入
    assert registry.get(1) is None  # blocked 返回后 finally 置 idle


def test_generate_stream_review_blocked_still_idle(monkeypatch):
    """流式审核阶段 blocked：done 帧发出后注册表必已置空"""
    class FakeStream:
        async def chat_stream(self, app_id, prompt, session_id=None, history=None):
            yield {"type": "done", "text": "你好", "dialog_id": "dlg-1", "citations": []}

    g = _mk(monkeypatch, _check_pass)
    g.bailian = FakeStream()

    seen = []
    monkeypatch.setattr(
        "app.core.answer_generator.check_compliance",
        _recording_check(seen, blocked_on_review=True),
    )

    async def run():
        frames = []
        async for frame in g.generate_stream("问题", _spec(), user_id=1):
            frames.append(frame)
        return frames

    frames = asyncio.run(run())
    assert frames[-1]["type"] == "done"
    assert frames[-1]["blocked"] is True
    assert seen == ["compliance_precheck", "compliance_review"]
    assert registry.get(1) is None  # blocked 返回后 finally 置 idle


def test_generate_bailian_fallback_still_idle(monkeypatch):
    """百炼不可用走 qwen 降级：正常返回后注册表必已置空"""
    g = _mk(monkeypatch, _check_pass)

    phases_at_call = []

    async def _raising_chat(app_id, prompt, session_id=None):
        phases_at_call.append(registry.get(1).phase if registry.get(1) else None)
        raise BailianException("模拟百炼不可用")

    monkeypatch.setattr(g.bailian, "chat", _raising_chat)
    monkeypatch.setattr(g.qwen, "chat", lambda **kw: {"content": "降级回答"})

    result = asyncio.run(g.generate("问题", _spec(), user_id=1))
    assert result["answer"] == "降级回答"
    assert phases_at_call == ["generating"]  # 降级路径 generating 阶段也已写入
    assert registry.get(1) is None  # 降级后正常返回也置 idle


def test_generate_stream_aclose_still_idle(monkeypatch):
    """流中途断开（只消费一帧即 aclose）：finally 仍须置 idle"""
    class FakeStream:
        async def chat_stream(self, app_id, prompt, session_id=None, history=None):
            yield {"type": "delta", "text": "一"}
            yield {"type": "delta", "text": "二"}
            yield {"type": "done", "text": "你好", "dialog_id": "dlg-1", "citations": []}

    g = _mk(monkeypatch, _check_pass)
    g.bailian = FakeStream()

    async def run():
        gen = g.generate_stream("你好", _spec(), user_id=1)
        first = await gen.__anext__()
        assert first["type"] == "delta"
        assert registry.get(1).phase == "generating"  # 断开前注册表已写入（不是测空注册表）
        await gen.aclose()  # GeneratorExit 经 finally 置 idle
        return first

    first = asyncio.run(run())
    assert first["type"] == "delta"
    assert registry.get(1) is None  # 断开后 finally 置 idle


def test_generate_stream_injects_preference_context(monkeypatch):
    """Task 4（2026-08-27）：医生学术偏好作为 prompt 上下文注入（含事实约束）。

    mock get_profile 返回偏好画像 → 断言百炼 chat_stream 收到的 prompt
    同时含「不得改变医学事实」硬约束与兴趣领域关键词。db=None 时仍应注入
    （get_profile 被 mock，直接返回画像）。
    """
    from app.core import preference_ranking
    captured = {}

    def fake_get_profile(db, doctor_id):
        class P:
            interest_areas = ["肿瘤"]
            preferred_doc_type = None
            preferred_style = "简洁"
            closed = False
        return P()

    class FakeBailian:
        async def chat_stream(self, app_id, prompt, session_id=None):
            captured["prompt"] = prompt
            yield {"type": "delta", "text": "好的"}
            yield {"type": "done", "text": "好的"}

    monkeypatch.setattr(preference_ranking, "get_profile", fake_get_profile)
    g = _mk(monkeypatch, _check_pass)
    g.bailian = FakeBailian()

    async def run():
        frames = [f async for f in g.generate_stream(
            question="肿瘤怎么治疗", specialist=_spec(), user_id=2, db=None)]
        return frames

    frames = asyncio.run(run())
    assert frames[-1]["type"] == "done"
    assert "不得改变医学事实" in captured["prompt"]
    assert "肿瘤" in captured["prompt"]


def _spec_with_style():
    """带 persona.style 的分身桩（对应 set_twin_style / style-test 产物结构）"""
    return Specialist(
        id=1, name="测试专员", bailian_app_id="app-1",
        persona={"style": {"formal_level": "标准学术", "reply_length": "详尽", "opening_mode": "直切主题"}},
        knowledge_scope="", compliance_level="internal",
    )


def test_generate_stream_injects_persona_style(monkeypatch):
    """分身风格写而不读收尾（2026-08-27）：persona.style 注入 prompt。

    set_twin_style / style-test 写入的 formal_level/reply_length/opening_mode
    此前全仓无消费方，对话不受影响；注入后百炼 chat_stream 收到的 prompt
    应含风格设定。无 persona 时（_spec 默认 persona=""）原样返回。
    """
    captured = {}

    class FakeBailian:
        async def chat_stream(self, app_id, prompt, session_id=None):
            captured["prompt"] = prompt
            yield {"type": "delta", "text": "好的"}
            yield {"type": "done", "text": "好的"}

    g = _mk(monkeypatch, _check_pass)
    g.bailian = FakeBailian()

    async def run():
        frames = [f async for f in g.generate_stream(
            question="肿瘤怎么治疗", specialist=_spec_with_style(), user_id=2, db=None)]
        return frames

    asyncio.run(run())
    assert "正式程度：标准学术" in captured["prompt"]
    assert "回复长度：详尽" in captured["prompt"]
    assert "开场方式：直切主题" in captured["prompt"]


def test_generate_no_persona_style_unchanged(monkeypatch):
    """无 persona.style → question 原样（零扰动）。"""
    captured = {}

    class FakeBailian:
        async def chat(self, app_id, prompt, session_id=None):
            captured["prompt"] = prompt
            return {"text": "好的", "citations": [], "dialog_id": "dlg-1"}

    g = _mk(monkeypatch, _check_pass)
    g.bailian = FakeBailian()

    async def run():
        await g.generate(question="肿瘤怎么治疗", specialist=_spec(), user_id=2, db=None)

    asyncio.run(run())
    assert "分身风格设定" not in captured["prompt"]


def test_generate_injects_preference_context(monkeypatch):
    """Task 4 追加（2026-08-27）：REST 核心接口 generate 与 WS 流式同口径注入偏好。

    mock get_profile 返回偏好画像 → 断言百炼 chat 收到的 prompt 同时含
    「不得改变医学事实」硬约束与兴趣领域关键词。db=None 时仍应注入
    （get_profile 被 mock，直接返回画像）。
    """
    from app.core import preference_ranking
    captured = {}

    def fake_get_profile(db, doctor_id):
        class P:
            interest_areas = ["肿瘤"]
            preferred_doc_type = None
            preferred_style = "简洁"
            closed = False
        return P()

    class FakeBailian:
        async def chat(self, app_id, prompt, session_id=None):
            captured["prompt"] = prompt
            return {"text": "好的", "citations": [], "dialog_id": "dlg-1"}

    monkeypatch.setattr(preference_ranking, "get_profile", fake_get_profile)
    g = _mk(monkeypatch, _check_pass)
    g.bailian = FakeBailian()

    result = asyncio.run(g.generate(
        question="肿瘤怎么治疗", specialist=_spec(), user_id=2, db=None))
    assert result["answer"] == "好的"
    assert "不得改变医学事实" in captured["prompt"]
    assert "肿瘤" in captured["prompt"]
