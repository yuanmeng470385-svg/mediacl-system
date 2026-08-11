"""chat_ws 端点测试：帧协议 + 鉴权（mock generate_stream）"""
import json
import os
import pytest
from types import SimpleNamespace
from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

os.environ.setdefault("JWT_SECRET", "test-secret")
from shared.common.auth import create_token
from shared.common.db_session import get_db
from app.main import app
from app.api.chat_ws import get_generator_factory, set_generator_factory
from app.models.specialist import Specialist


@pytest.fixture(autouse=True)
def reset_factory():
    """每个用例后清掉注入的生成器工厂"""
    yield
    set_generator_factory(None)


class _UserDb:
    """get_db 替身：chat_ws 的 H2 实时查库（CI 无真实 PG，必须隔离）。

    status 由 holder 控制，可切换 active/disabled 模拟停用账号旧 token 场景。
    filter 模拟 `User.status == "active"` 语义：非 active 时 first() 返回 None
    （真实 DB 过滤后无行可返），否则返回 active 用户。
    """

    def __init__(self, status):
        self._status = status

    def query(self, model):
        return self

    def filter(self, *a, **k):
        return self

    def first(self):
        if self._status != "active":
            return None
        return SimpleNamespace(id=1, username="tester", role="rep", status=self._status)


@pytest.fixture(autouse=True)
def fake_user_db():
    """H2（2026-08-11）：chat_ws 鉴权查库用 User stub（不连真实数据库）"""
    holder = {"status": "active"}
    app.dependency_overrides[get_db] = lambda: _UserDb(holder["status"])
    yield holder
    app.dependency_overrides.pop(get_db, None)


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
    """无 token：握手成功（101）后立即以 4401 关闭 —— 先 accept 再 close，
    关闭码可达客户端；旧实现未 accept 时 close 被吞成握手 403，网关兜底 4500。"""
    with TestClient(app) as client:
        with client.websocket_connect("/ws/specialists/1/chat") as ws:
            with pytest.raises(WebSocketDisconnect) as exc:
                ws.receive_json()
            assert exc.value.code == 4401


def test_ws_停用账号旧token关4401(fake_user_db):
    """H2：账号被停用后，旧 token（7 天有效期内）不再能发起对话（实时查库）"""
    fake_user_db["status"] = "disabled"
    token = create_token(user_id=1, username="tester", role="rep")
    with TestClient(app) as client:
        with client.websocket_connect(f"/ws/specialists/1/chat?token={token}") as ws:
            with pytest.raises(WebSocketDisconnect) as exc:
                ws.receive_json()
            assert exc.value.code == 4401


def test_ws_专员不存在关4404(monkeypatch):
    """专员不存在/非 active：握手成功后立即以 4404 关闭"""
    monkeypatch.setattr(
        "app.api.chat_ws._get_specialist",
        lambda db, specialist_id: None,
    )
    token = create_token(user_id=1, username="tester", role="rep")
    with TestClient(app) as client:
        with client.websocket_connect(f"/ws/specialists/999/chat?token={token}") as ws:
            with pytest.raises(WebSocketDisconnect) as exc:
                ws.receive_json()
            assert exc.value.code == 4404


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
