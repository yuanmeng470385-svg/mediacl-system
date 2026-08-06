"""BailianClient.chat_stream 流式测试（mock websockets.connect）"""
import asyncio
import json
import pytest
from app.services.bailian_client import BailianClient, BailianException


class _FakeWs:
    """模拟百炼 WS：按脚本回消息"""
    def __init__(self, replies):
        self._replies = list(replies)
        self.sent = []

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        return False

    async def send(self, msg):
        self.sent.append(json.loads(msg))

    async def recv(self):
        if not self._replies:
            await asyncio.sleep(0.1)
            raise ConnectionClosedFake
        return json.dumps(self._replies.pop(0), ensure_ascii=False)


class ConnectionClosedFake(Exception):
    pass


def _ev(event: str, **output):
    return {"payload": {"output": {"event": event, **output}}}


def test_chat_stream_yields_delta_and_done(monkeypatch):
    replies = [
        _ev("Started", dialog_id="dlg-1"),
        _ev("DialogStateChanged", state="Listening"),
        _ev("RespondingContent", text="你好", finished=False),
        _ev("RespondingContent", text="你好，我是专员。", finished=True),
    ]
    fake = _FakeWs(replies)
    monkeypatch.setattr("app.services.bailian_client.websockets.connect", lambda *a, **k: fake)

    async def run():
        client = BailianClient()
        frames = []
        async for frame in client.chat_stream(app_id="app-1", prompt="你好"):
            frames.append(frame)
        return frames

    frames = asyncio.run(run())
    assert [f["type"] for f in frames] == ["delta", "delta", "done"]
    assert frames[0]["text"] == "你好"
    assert frames[1]["text"] == "你好，我是专员。"
    assert frames[-1]["dialog_id"] == "dlg-1"
    # Start 消息里带了 app_id
    start_sent = fake.sent[0]["payload"]["input"]
    assert start_sent["app_id"] == "app-1"


def test_chat_stream_error_event_raises(monkeypatch):
    replies = [
        _ev("Started", dialog_id="dlg-1"),
        _ev("DialogStateChanged", state="Listening"),
        _ev("Error", error_code="E1", error_message="模型错误"),
    ]
    fake = _FakeWs(replies)
    monkeypatch.setattr("app.services.bailian_client.websockets.connect", lambda *a, **k: fake)

    async def run():
        client = BailianClient()
        async for _ in client.chat_stream(app_id="app-1", prompt="你好"):
            pass

    with pytest.raises(BailianException):
        asyncio.run(run())
