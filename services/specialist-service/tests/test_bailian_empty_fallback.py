"""百炼空内容帧提前降级回归（真机联调 2026-08-12）

现象：end_visit 等非流式调用经 specialist chat 耗时 11.8s——百炼 App 未发布时
WS 协议正常但 RespondingContent text 恒空，旧实现等满 60 帧才抛
"等待回答完成超时"降级 qwen（实测 ~9.2s 白白等待）。
修复：连续 _MAX_EMPTY_FRAMES 帧空文本即抛 BailianException 提前降级
（8 帧 × ~150ms ≈ 1.2s）。

本文件验证：空内容流在阈值帧处提前终止；正常内容流不受影响（计数重置）。
"""
import asyncio
import json
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", ".."))

import pytest  # noqa: E402

from app.services.bailian_client import BailianClient, BailianException, _MAX_EMPTY_FRAMES  # noqa: E402


class _FakeWs:
    """按顺序吐出预置消息帧"""

    def __init__(self, frames):
        self._frames = list(frames)
        self._sent = []

    async def __aenter__(self):
        return self

    async def __aexit__(self, *a):
        return False

    async def recv(self):
        if not self._frames:
            raise TimeoutError("no more frames")
        return json.dumps(self._frames.pop(0), ensure_ascii=False)

    async def send(self, data):
        self._sent.append(data)


def _frame(event, **output):
    return {"payload": {"output": {"event": event, **output}}}


def _run(coro):
    return asyncio.new_event_loop().run_until_complete(coro)


def _empty_content_frames(n, finished=False):
    return [_frame("RespondingContent", text="", finished=finished) for _ in range(n)]


def test_empty_content_raises_early(monkeypatch):
    """连续空内容帧达到阈值 → 提前抛 BailianException（不再等满 60 帧）"""
    frames = [
        _frame("Started", dialog_id="d1"),
        _frame("DialogStateChanged", state="Listening"),
        *_empty_content_frames(_MAX_EMPTY_FRAMES),
    ]
    monkeypatch.setattr("websockets.connect", lambda *a, **kw: _FakeWs(frames))
    client = BailianClient()
    with pytest.raises(BailianException) as ei:
        _run(client.chat(app_id="app1", prompt="问题"))
    assert "空内容" in str(ei.value)
    # 不应等满 60 帧（旧实现行为）：空内容帧只喂了 _MAX_EMPTY_FRAMES 帧
    assert len(frames) == 2 + _MAX_EMPTY_FRAMES


def test_empty_then_content_resets_counter(monkeypatch):
    """空帧后出现真实内容 → 计数重置，正常返回（阈值不误伤真实回复）"""
    frames = [
        _frame("Started", dialog_id="d1"),
        _frame("DialogStateChanged", state="Listening"),
        *_empty_content_frames(_MAX_EMPTY_FRAMES - 1),
        _frame("RespondingContent", text="真实回答", finished=False),
        _frame("RespondingContent", text="真实回答", finished=True),
    ]
    monkeypatch.setattr("websockets.connect", lambda *a, **kw: _FakeWs(frames))
    client = BailianClient()
    result = _run(client.chat(app_id="app1", prompt="问题"))
    assert result["text"] == "真实回答"
    assert result.get("error") is None  # 成功路径不带 error 键


def test_content_resets_empty_then_ok(monkeypatch):
    """空→内容→再空：内容后计数归零，第二次空帧需重新累积（防误伤长回答间隔）"""
    frames = [
        _frame("Started", dialog_id="d1"),
        _frame("DialogStateChanged", state="Listening"),
        _frame("RespondingContent", text="", finished=False),              # 1 空
        _frame("RespondingContent", text="回答第一段", finished=False),     # 重置
        *_empty_content_frames(_MAX_EMPTY_FRAMES - 1),                     # 差 1 帧到阈值
        _frame("RespondingContent", text="回答第二段", finished=True),      # 正常结束
    ]
    monkeypatch.setattr("websockets.connect", lambda *a, **kw: _FakeWs(frames))
    client = BailianClient()
    result = _run(client.chat(app_id="app1", prompt="问题"))
    assert result["text"] == "回答第二段"
