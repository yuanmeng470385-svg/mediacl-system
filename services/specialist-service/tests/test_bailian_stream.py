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


# ==================== G2：传输层异常统一转 BailianException ====================

def test_chat_stream_transport_timeout_wrapped(monkeypatch):
    """G2 回归：ws.recv 超时（wait_for TimeoutError）→ BailianException（与 REST chat() 同语义）"""
    class _TimeoutWs(_FakeWs):
        async def recv(self):
            raise TimeoutError("recv timeout")

    monkeypatch.setattr(
        "app.services.bailian_client.websockets.connect", lambda *a, **k: _TimeoutWs([]),
    )

    async def run():
        client = BailianClient()
        async for _ in client.chat_stream(app_id="app-1", prompt="你好"):
            pass

    with pytest.raises(BailianException) as ei:
        asyncio.run(run())
    assert "超时" in str(ei.value)


def test_chat_stream_connection_closed_wrapped(monkeypatch):
    """G2 回归：ws 断连（websockets.exceptions.ConnectionClosed）→ BailianException"""
    import websockets

    class _ClosedWs(_FakeWs):
        async def recv(self):
            raise websockets.exceptions.ConnectionClosed(None, None)

    monkeypatch.setattr(
        "app.services.bailian_client.websockets.connect", lambda *a, **k: _ClosedWs([]),
    )

    async def run():
        client = BailianClient()
        async for _ in client.chat_stream(app_id="app-1", prompt="你好"):
            pass

    with pytest.raises(BailianException) as ei:
        asyncio.run(run())
    assert "连接关闭" in str(ei.value)


def test_chat_stream_malformed_json_wrapped(monkeypatch):
    """G2 回归：畸形帧（非 JSON）→ BailianException，而非裸 JSONDecodeError"""
    class _BadJsonWs(_FakeWs):
        async def recv(self):
            return "not-json{{{"

    monkeypatch.setattr(
        "app.services.bailian_client.websockets.connect", lambda *a, **k: _BadJsonWs([]),
    )

    async def run():
        client = BailianClient()
        async for _ in client.chat_stream(app_id="app-1", prompt="你好"):
            pass

    with pytest.raises(BailianException) as ei:
        asyncio.run(run())
    assert "格式异常" in str(ei.value)


def test_chat_stream_malformed_frame_wrapped(monkeypatch):
    """G2 回归：JSON 合法但结构畸形（payload 非 dict → AttributeError）→ BailianException"""
    class _BadFrameWs(_FakeWs):
        async def recv(self):
            return json.dumps({"payload": "not-a-dict"})

    monkeypatch.setattr(
        "app.services.bailian_client.websockets.connect", lambda *a, **k: _BadFrameWs([]),
    )

    async def run():
        client = BailianClient()
        async for _ in client.chat_stream(app_id="app-1", prompt="你好"):
            pass

    with pytest.raises(BailianException) as ei:
        asyncio.run(run())
    assert "格式异常" in str(ei.value)
