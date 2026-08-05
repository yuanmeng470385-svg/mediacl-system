"""百炼流式响应引用溯源解析（mock websocket 收包序列）"""
import asyncio
import json
import pytest

from app.services.bailian_client import BailianClient


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


def test_parse_citations_from_responding_content(monkeypatch):
    frames = [
        _frame("Started", dialog_id="d1"),
        _frame("DialogStateChanged", state="Listening"),
        _frame("RespondingContent", text="根据说明书，该药…", finished=False,
               extra_info={"docs": [{"doc_name": "说明书.pdf", "doc_url": "https://oss/1.pdf", "doc_id": "f1"}]}),
        _frame("RespondingContent", text="根据说明书，该药…", finished=True,
               extra_info={"docs": [{"doc_name": "说明书.pdf", "doc_url": "https://oss/1.pdf", "doc_id": "f1"}]}),
    ]
    monkeypatch.setattr("websockets.connect", lambda *a, **kw: _FakeWs(frames))
    client = BailianClient()
    result = __import__("asyncio").get_event_loop_policy().new_event_loop().run_until_complete(
        client.chat(app_id="app1", prompt="问题")
    )
    assert len(result["citations"]) == 1
    assert result["citations"][0]["title"] == "说明书.pdf"
    assert result["citations"][0]["url"] == "https://oss/1.pdf"


def test_citations_missing_is_empty(monkeypatch):
    frames = [
        _frame("Started", dialog_id="d1"),
        _frame("DialogStateChanged", state="Listening"),
        _frame("RespondingContent", text="没有引用", finished=True),
    ]
    monkeypatch.setattr("websockets.connect", lambda *a, **kw: _FakeWs(frames))
    client = BailianClient()
    result = __import__("asyncio").get_event_loop_policy().new_event_loop().run_until_complete(
        client.chat(app_id="app1", prompt="问题")
    )
    assert result["citations"] == []


def test_recv_timeout_raises_bailian_exception(monkeypatch):
    from app.services.bailian_client import BailianException

    class _HungWs(_FakeWs):
        async def recv(self):
            await asyncio.sleep(3600)  # 真正挂起：无 wait_for 时测试将永久挂住（回归必现）

    frames = [_frame("Started", dialog_id="d1")]
    monkeypatch.setattr("websockets.connect", lambda *a, **kw: _HungWs(frames))
    client = BailianClient()
    client.timeout = 0.1  # 缩短超时便于测试
    with pytest.raises(BailianException):
        __import__("asyncio").get_event_loop_policy().new_event_loop().run_until_complete(
            client.chat(app_id="app1", prompt="问题")
        )
