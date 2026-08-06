"""网关 WS 代理测试（注入 fake 上游，不真连 specialist）"""
import asyncio
import json
import queue as thread_queue
import threading

import pytest
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
    fake = FakeUpstream()
    set_upstream_factory(lambda url: fake)

    with TestClient(app) as client:
        with client.websocket_connect("/api/v1/specialists/1/chat/ws?token=abc") as ws:
            # 客户端 → 上游
            ws.send_text(json.dumps({"type": "question", "text": "你好"}))
            assert fake.received_event.wait(2.0), "代理未把客户端消息转发给上游"
            assert json.loads(fake.received.pop(0))["type"] == "question"
            # 上游 → 客户端（测试直接向队列投递，模拟上游主动下发）
            fake.to_client.put(("text", json.dumps({"type": "delta", "text": "你"})))
            assert json.loads(ws.receive_text())["type"] == "delta"
            fake.to_client.put(("text", json.dumps({"type": "done", "text": "你好", "conversation_id": 1})))
            assert json.loads(ws.receive_text())["type"] == "done"
