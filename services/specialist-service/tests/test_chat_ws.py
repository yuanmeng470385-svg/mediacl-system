"""chat_ws 端点测试：帧协议 + 鉴权（mock generate_stream）"""
import json
import os
import pytest
from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

os.environ.setdefault("JWT_SECRET", "test-secret")
from shared.common.auth import create_token
from app.main import app
from app.api.chat_ws import get_generator_factory, set_generator_factory
from app.models.specialist import Specialist


@pytest.fixture(autouse=True)
def reset_factory():
    """每个用例后清掉注入的生成器工厂"""
    yield
    set_generator_factory(None)


class FakeGenerator:
    """模拟 AnswerGenerator：generate_stream 逐帧 yield 预置帧"""

    def __init__(self, frames):
        self._frames = frames

    async def generate_stream(self, question, specialist, user_id, session_id=None):
        for f in self._frames:
            yield f


def _fake_specialist(specialist_id: int) -> Specialist:
    """与 test_generate_stream._spec 同风格：内存构造 Specialist，不碰 DB"""
    return Specialist(
        id=specialist_id, name="测试专员", bailian_app_id="app-1",
        persona="", knowledge_scope="", compliance_level="internal",
    )


def test_ws_无token关4401():
    """无 token：握手被服务端拒绝，关闭码 4401（与 asr_ws 语义一致）"""
    with TestClient(app) as client:
        with pytest.raises(WebSocketDisconnect) as exc:
            with client.websocket_connect("/ws/specialists/1/chat"):
                pass  # 不应成功；TestClient 在握手被拒时抛 WebSocketDisconnect
        assert exc.value.code == 4401


def test_ws_question_delta_done_流程(monkeypatch):
    # 存在性校验与落库都避开真实 DB（沿用本服务纯逻辑测试风格）
    monkeypatch.setattr(
        "app.api.chat_ws._get_specialist",
        lambda db, specialist_id: _fake_specialist(specialist_id),
    )
    monkeypatch.setattr(
        "app.api.specialists._persist_conversation",
        lambda db, user_id, specialist_id, question, result: 42,
    )

    token = create_token(user_id=1, username="rep1", role="rep")
    done = {
        "type": "done", "answer": "最终答案", "citations": [],
        "evidence_level": "B", "session_id": "dlg-1", "request_id": "req-1",
        "latency_ms": 100, "blocked": False, "violations": [],
    }
    frames = [{"type": "delta", "text": "你"}, {"type": "delta", "text": "你好"}, done]
    set_generator_factory(lambda: FakeGenerator(frames))

    with TestClient(app) as client:
        with client.websocket_connect(
            f"/ws/specialists/1/chat?token={token}"
        ) as ws:
            ws.send_text(json.dumps({"type": "question", "text": "你好"}))
            start = json.loads(ws.receive_text())
            assert start["type"] == "start"
            d1 = json.loads(ws.receive_text())
            d2 = json.loads(ws.receive_text())
            assert (d1["type"], d2["type"]) == ("delta", "delta")
            fin = json.loads(ws.receive_text())
            assert fin["type"] == "done"
            assert fin["answer"] == "最终答案"
            # 落库在 done 帧前完成：conversation_id 由 _persist_conversation 返回填入
            assert fin["conversation_id"] == 42
