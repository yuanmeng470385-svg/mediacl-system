"""网关 WS 代理测试（注入 fake 上游，不真连 specialist）"""
import asyncio
import json
import queue as thread_queue
import threading

import pytest
import websockets
import websockets.frames as ws_frames
from fastapi.testclient import TestClient

from app.main import app, set_upstream_factory


class FakeUpstream:
    """模拟 specialist 上游：线程安全队列驱动

    - 代理把客户端消息发给上游（send_text/send_bytes）→ 记入 received（不回显）
    - 测试模拟上游主动下发 → to_client.put(...)，代理转发给客户端
    - 注意：TestClient 的 portal 在独立线程跑 app，跨线程直接对
      asyncio.Queue put_nowait 不会可靠唤醒 getter，故改用线程安全
      queue.Queue + 可取消的轮询桥接
    """
    def __init__(self):
        self.closed = False
        self.to_client = thread_queue.Queue()      # 上游→客户端
        self.received = []                          # 客户端→上游
        self.received_event = threading.Event()     # 代理送达上游时置位（防竞态）

    async def send_text(self, text):
        self.received.append(text)
        self.received_event.set()

    async def send_bytes(self, data):
        self.received.append(data)
        self.received_event.set()

    async def receive_text(self):
        kind, payload = await self._take_from_client()
        return payload

    async def receive_bytes(self):
        kind, payload = await self._take_from_client()
        return payload

    async def _take_from_client(self):
        while True:
            try:
                return self.to_client.get_nowait()
            except thread_queue.Empty:
                await asyncio.sleep(0.01)

    async def close(self):
        self.closed = True


@pytest.fixture(autouse=True)
def reset_factory():
    yield
    set_upstream_factory(None)


def test_ws_proxy_双向透传():
    """B5 首帧鉴权：客户端首帧发 auth 帧（真 token）→ 网关验过后透传；后续帧正常转发"""
    import os
    from shared.common.auth import create_token
    fake = FakeUpstream()
    set_upstream_factory(lambda url: fake)
    token = create_token(user_id=1, username="rep1", role="rep")

    with TestClient(app) as client:
        with client.websocket_connect("/api/v1/specialists/1/chat/ws") as ws:
            # 客户端 → 上游：auth 帧（网关验证 + 透传）+ question 帧
            ws.send_text(json.dumps({"type": "auth", "token": token}))
            ws.send_text(json.dumps({"type": "question", "text": "你好"}))
            assert fake.received_event.wait(2.0), "代理未把客户端消息转发给上游"
            frames = [json.loads(x) for x in fake.received if isinstance(x, str)]
            assert frames[0]["type"] == "auth"
            assert frames[1]["type"] == "question"
            # 上游 → 客户端（测试直接向队列投递，模拟上游主动下发）
            fake.to_client.put(("text", json.dumps({"type": "delta", "text": "你"})))
            assert json.loads(ws.receive_text())["type"] == "delta"
            fake.to_client.put(("text", json.dumps({"type": "done", "text": "你好", "conversation_id": 1})))
            assert json.loads(ws.receive_text())["type"] == "done"


def test_ws_proxy_rejects_invalid_token():
    """B5：网关对 WS 零鉴权修复 —— 无效 token 首帧 → 4401 拒绝（不再透传上游）"""
    fake = FakeUpstream()
    set_upstream_factory(lambda url: fake)

    with TestClient(app) as client:
        with client.websocket_connect("/api/v1/specialists/1/chat/ws") as ws:
            ws.send_text(json.dumps({"type": "auth", "token": "not-a-real-token"}))
            msg = ws.receive()
            assert msg["type"] == "websocket.close"
            assert msg["code"] == 4401


def _record_url_factory(seen, fake):
    """记录上游 URL 的工厂（工厂调用先于首帧转发，收到帧时 seen 必已就绪）"""

    def _factory(url):
        seen["url"] = url
        return fake

    return _factory


def test_ws_proxy_auth_frame_token_not_in_upstream_url():
    """E1（2026-08-13）：首帧 auth 协议时 token 不拼进上游 URL query
    —— JWT 不进 specialist uvicorn 访问日志；仅旧客户端 query 兜底才附带"""
    from shared.common.auth import create_token
    seen = {}
    fake = FakeUpstream()
    set_upstream_factory(_record_url_factory(seen, fake))
    token = create_token(user_id=1, username="rep1", role="rep")

    with TestClient(app) as client:
        with client.websocket_connect("/api/v1/specialists/1/chat/ws") as ws:
            ws.send_text(json.dumps({"type": "auth", "token": token}))
            assert fake.received_event.wait(2.0), "代理未把首帧转发给上游"
            assert "token=" not in seen["url"]
            assert seen["url"].endswith("/ws/specialists/1/chat")


def test_ws_proxy_query_token_kept_in_upstream_url():
    """E1：旧客户端（query token 兜底）—— 上游 URL 保留 query token"""
    from shared.common.auth import create_token
    seen = {}
    fake = FakeUpstream()
    set_upstream_factory(_record_url_factory(seen, fake))
    token = create_token(user_id=1, username="rep1", role="rep")

    with TestClient(app) as client:
        with client.websocket_connect(f"/api/v1/specialists/1/chat/ws?token={token}") as ws:
            ws.send_text(json.dumps({"type": "question", "text": "你好"}))
            assert fake.received_event.wait(2.0)
            assert f"?token={token}" in seen["url"]


class FakeUpstreamClosing(FakeUpstream):
    """receive_text 立即抛 ConnectionClosed(close_code)，模拟上游主动带码关闭"""

    def __init__(self, close_code: int):
        super().__init__()
        self.close_code = close_code

    async def receive_text(self):
        raise websockets.exceptions.ConnectionClosed(
            ws_frames.Close(self.close_code, ""),
            ws_frames.Close(self.close_code, ""),
            rcvd_then_sent=False,
        )


@pytest.mark.parametrize("close_code", [4401, 4404, 4500])
def test_ws_proxy_透传上游关闭码(close_code):
    """M46：上游 4401/4404/4500 关闭码原样透传给下游，不再被吞成 1000"""
    import os
    from shared.common.auth import create_token
    fake = FakeUpstreamClosing(close_code)
    set_upstream_factory(lambda url: fake)
    token = create_token(user_id=1, username="rep1", role="rep")

    with TestClient(app) as client:
        with client.websocket_connect("/api/v1/specialists/1/chat/ws") as ws:
            ws.send_text(json.dumps({"type": "auth", "token": token}))
            msg = ws.receive()
            assert msg["type"] == "websocket.close"
            assert msg["code"] == close_code
