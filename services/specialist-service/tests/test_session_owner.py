"""会话 IDOR 越权修复回归测试：他人 session_id 一律 404（不泄露存在性）。

覆盖：
- GET /api/v1/specialists/conversations/{session_id}：他人 session → 404，自己 → 200
- POST /{specialist_id}/chat 续传他人 session → 404
- WS question 帧带他人 session_id → 错误帧 + 4404 关闭；自己的 → 正常流式

沿用本服务风格：FakeDb + dependency_overrides，不起真实数据库。
"""
import json
import os
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

os.environ.setdefault("JWT_SECRET", "test-secret")

from shared.common.auth import create_token, get_current_user
from shared.common.db_session import get_db
from app.main import app
from app.api.chat_ws import get_generator_factory, set_generator_factory
from app.models.specialist import Specialist


class FakeConv:
    """对话行替身（满足 to_dict 读取的全部字段）"""

    def __init__(self, id=1, role="user", content="问题", session_id="dlg-1", user_id=3):
        self.id = id
        self.user_id = user_id
        self.specialist_id = 1
        self.session_id = session_id
        self.role = role
        self.content = content
        self.citations = None
        self.compliance_result = None
        self.tokens_used = None
        self.latency_ms = None
        self.created_at = None

    def to_dict(self):
        return {
            "id": self.id, "user_id": self.user_id, "specialist_id": self.specialist_id,
            "session_id": self.session_id, "role": self.role, "content": self.content,
            "citations": self.citations, "compliance_result": self.compliance_result,
            "tokens_used": self.tokens_used, "latency_ms": self.latency_ms,
            "created_at": self.created_at,
        }


class QueryStub:
    """链式替身：按 filter 条件区分三类查询（专员校验 / 会话归属校验 / 历史查询）"""

    def __init__(self, db, model_name):
        self._db = db
        self._model_name = model_name
        self._is_ownership = False

    def filter(self, *criteria):
        cols = {c.left.key for c in criteria if getattr(c, "left", None) is not None}
        self._is_ownership = self._model_name == "Conversation" and "user_id" in cols
        self._db.last_criteria = cols
        if self._is_ownership:
            self._db.ownership_checked += 1
        return self

    def order_by(self, *a, **k):
        return self

    def first(self):
        if self._model_name == "Specialist":
            return self._db.specialist
        if self._is_ownership:
            return SimpleNamespace(id=1) if self._db.owned else None
        return None

    def all(self):
        return self._db.messages


class FakeDb:
    """最小 DB 替身：owned=False 时归属校验 first() 返回 None（视为他人 session）"""

    def __init__(self, owned=False, messages=None, specialist=None):
        self.owned = owned
        self.messages = messages or []
        self.specialist = specialist
        self.last_criteria = set()
        self.ownership_checked = 0

    def query(self, model):
        return QueryStub(self, model.__name__)


@pytest.fixture(autouse=True)
def reset_factory():
    """每个用例后清掉注入的生成器工厂（与 test_chat_ws 同风格）"""
    yield
    set_generator_factory(None)


@pytest.fixture
def client_factory():
    app.dependency_overrides.clear()

    def _make(db):
        app.dependency_overrides[get_db] = lambda: db
        app.dependency_overrides[get_current_user] = lambda: {"id": 3, "role": "rep"}
        return TestClient(app)

    yield _make
    app.dependency_overrides.clear()


def _fake_specialist() -> Specialist:
    return Specialist(
        id=1, name="测试专员", bailian_app_id="app-1",
        persona="", knowledge_scope="", compliance_level="internal",
        status="active",
    )


# ==================== helper 单测 ====================

def test_assert_session_owner_他人session404_空session通过():
    from app.api.conversations import assert_session_owner
    from fastapi import HTTPException
    db = FakeDb(owned=False)
    with pytest.raises(HTTPException) as exc:
        assert_session_owner(db, "dlg-other", 3)
    assert exc.value.status_code == 404
    # 空 session（新建会话）直接通过
    assert_session_owner(db, "", 3)


def test_assert_session_owner_自己session通过_且同时按session和user过滤():
    from app.api.conversations import assert_session_owner
    db = FakeDb(owned=True)
    assert_session_owner(db, "dlg-1", 3)  # 不抛异常
    # IDOR 修复核心：过滤条件必须同时含 session_id 与 user_id
    assert "session_id" in db.last_criteria
    assert "user_id" in db.last_criteria


# ==================== 会话历史 ====================

def test_history_他人session返回404(client_factory):
    db = FakeDb(owned=False)
    resp = client_factory(db).get("/api/v1/specialists/conversations/dlg-other")
    assert resp.status_code == 404


def test_history_自己session返回200(client_factory):
    db = FakeDb(
        owned=True,
        messages=[
            FakeConv(id=1, role="user", content="问题"),
            FakeConv(id=2, role="assistant", content="答案"),
        ],
    )
    resp = client_factory(db).get("/api/v1/specialists/conversations/dlg-1")
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert len(data) == 2
    assert data[0]["role"] == "user"
    assert data[1]["role"] == "assistant"
    assert data[1]["session_id"] == "dlg-1"


# ==================== REST chat 续传 ====================

def test_chat_续传他人session返回404(client_factory):
    db = FakeDb(owned=False, specialist=_fake_specialist())
    resp = client_factory(db).post(
        "/api/v1/specialists/1/chat",
        json={"question": "你好", "session_id": "dlg-other"},
    )
    assert resp.status_code == 404


def test_chat_不带session_id_正常新建不校验(client_factory, monkeypatch):
    """不带 session_id 新建会话不受归属校验影响（不触碰 conversations 查询）"""
    db = FakeDb(owned=False, specialist=_fake_specialist())
    # 生成器与落库全部替身化，聚焦于请求可达生成步骤
    monkeypatch.setattr(
        "app.api.specialists.AnswerGenerator",
        _FakeGenerator,
    )
    monkeypatch.setattr(
        "app.api.specialists._persist_conversation",
        lambda db, user_id, specialist_id, question, result: 42,
    )
    resp = client_factory(db).post(
        "/api/v1/specialists/1/chat",
        json={"question": "你好"},
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["data"]["answer"] == "新会话答案"
    assert db.ownership_checked == 0  # 未带 session_id：不应触发归属校验查询


class _FakeGenerator:
    async def generate(self, question, specialist, user_id, session_id=None):
        return {"answer": "新会话答案", "session_id": "dlg-new", "citations": [],
                "blocked": False, "violations": []}


# ==================== WS chat 续传 ====================

class FakeGenerator:
    def __init__(self, frames):
        self._frames = frames

    async def generate_stream(self, question, specialist, user_id, session_id=None):
        for f in self._frames:
            yield f


def test_ws_question带他人session_id_错误帧并关4404(client_factory, monkeypatch):
    monkeypatch.setattr(
        "app.api.chat_ws._get_specialist",
        lambda db, specialist_id: _fake_specialist(),
    )
    db = FakeDb(owned=False)
    client_factory(db)
    token = create_token(user_id=3, username="u3", role="rep")
    with TestClient(app) as client:
        with pytest.raises(WebSocketDisconnect) as exc:
            with client.websocket_connect(f"/ws/specialists/1/chat?token={token}") as ws:
                ws.send_text(json.dumps(
                    {"type": "question", "text": "你好", "session_id": "dlg-other"},
                ))
                err = json.loads(ws.receive_text())
                assert err["type"] == "error"
                assert err["message"] == "无权访问该会话"
                ws.receive_text()  # 触发服务端 close(4404)
    assert exc.value.code == 4404


def test_ws_question带自己session_id_正常流式(client_factory, monkeypatch):
    monkeypatch.setattr(
        "app.api.chat_ws._get_specialist",
        lambda db, specialist_id: _fake_specialist(),
    )
    monkeypatch.setattr(
        "app.api.specialists._persist_conversation",
        lambda db, user_id, specialist_id, question, result: 42,
    )
    db = FakeDb(owned=True)
    client_factory(db)
    done = {
        "type": "done", "answer": "最终答案", "citations": [],
        "evidence_level": "B", "session_id": "dlg-1", "request_id": "req-1",
        "latency_ms": 100, "blocked": False, "violations": [],
    }
    set_generator_factory(lambda: FakeGenerator([done]))
    token = create_token(user_id=3, username="u3", role="rep")
    with TestClient(app) as client:
        with client.websocket_connect(f"/ws/specialists/1/chat?token={token}") as ws:
            ws.send_text(json.dumps(
                {"type": "question", "text": "你好", "session_id": "dlg-1"},
            ))
            assert json.loads(ws.receive_text())["type"] == "start"
            fin = json.loads(ws.receive_text())
            assert fin["type"] == "done"
            assert fin["session_id"] == "dlg-1"
            assert fin["conversation_id"] == 42
