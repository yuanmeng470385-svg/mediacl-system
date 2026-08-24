"""反馈/收藏落库 + 满意度统计"""
import pytest
from fastapi.testclient import TestClient
from types import SimpleNamespace

from app.api.conversations import compute_satisfaction, get_current_user, get_db
from app.main import app


def test_compute_satisfaction_empty():
    assert compute_satisfaction(0, 0) == {"total_feedback": 0, "satisfaction_rate": None}


def test_compute_satisfaction_rates():
    r = compute_satisfaction(3, 1)  # 3 赞 1 踩 → 75%
    assert r["total_feedback"] == 4
    assert r["satisfaction_rate"] == 75


def test_compute_satisfaction_all_negative():
    assert compute_satisfaction(0, 2)["satisfaction_rate"] == 0


class FakeConv:
    """最小对话替身：满足 toggle_favorite 读取的字段"""

    def __init__(self, id=16, user_id=3, specialist_id=1, session_id="sess-1",
                 role="user", content="问题", citations=None):
        self.id = id
        self.user_id = user_id
        self.specialist_id = specialist_id
        self.session_id = session_id
        self.role = role
        self.content = content
        self.citations = citations


class QueryStub:
    """链式 query().filter().first()/all() 替身"""

    def __init__(self, first_result=None):
        self._first = first_result

    def filter(self, *a, **k):
        return self

    def order_by(self, *a, **k):
        return self

    def first(self):
        return self._first

    def all(self):
        return [FakeConv()]


class MsgStub:
    """会话消息查询替身：解析 Conversation.id == X / id <= X 条件后过滤。

    需支持 _get_conv_or_404（主键等值）与 toggle_favorite 快照（id <= 锚点）。
    """

    def __init__(self, msgs):
        self._msgs = list(msgs)

    def filter(self, *a, **k):
        for cond in a:
            col = getattr(getattr(cond, "left", None), "key", None)
            # SQLAlchemy 2.x 的右值是 BindParameter（:id_1），取 .value 才是字面量
            right = getattr(getattr(cond, "right", None), "value", None)
            if right is None:
                right = getattr(cond, "right", None)
            op_name = getattr(cond.operator, "__name__", "")
            if col == "id" and op_name == "eq":
                self._msgs = [m for m in self._msgs if m.id == right]
            elif col == "id" and op_name == "le":
                self._msgs = [m for m in self._msgs if m.id <= right]
        return self

    def order_by(self, *a, **k):
        return self

    def first(self):
        return self._msgs[0] if self._msgs else None

    def all(self):
        return self._msgs


class FakeDb:
    """已收藏（added 非空）后 query(ConversationFavorite) 返回 existing"""

    def __init__(self, msgs=None):
        self.added = []
        self.deleted = []
        self.msgs = msgs  # None → 单条 FakeConv（与旧行为一致）

    def query(self, model):
        if model.__name__ == "Conversation":
            return MsgStub(self.msgs if self.msgs is not None else [FakeConv()])
        return QueryStub(first_result=SimpleNamespace() if self.added else None)

    def add(self, obj):
        self.added.append(obj)

    def delete(self, obj):
        self.deleted.append(obj)

    def commit(self):
        pass


def _client(db: FakeDb):
    app.dependency_overrides[get_db] = lambda: db
    app.dependency_overrides[get_current_user] = lambda: {"id": 3, "role": "rep"}
    return TestClient(app)


# M-4 批次顺手修（2026-08-24）：本文件 _client 设置的 dependency_overrides
# 此前不清理，同进程后续文件（test_monitor_specialists 等 require_roles 用例）
# 拿到假 rep 身份 7 例假红。autouse 每用例后清空，恢复隔离。
@pytest.fixture(autouse=True)
def _clear_overrides():
    yield
    app.dependency_overrides.clear()


def test_toggle_favorite_no_body_returns_200():
    """无 body 的 toggle（前端契约：POST 无 body）不得 422 —— 回归 2026-08-06 实测 422"""
    db = FakeDb()
    resp = _client(db).post("/api/v1/conversations/16/favorite")
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["data"]["is_favorite"] is True
    assert len(db.added) == 1
    assert db.added[0].conversation_id == 16
    assert db.added[0].question == "问题"
    assert db.added[0].answer == ""  # 快照里无 assistant 行 → answer 兜底空串

def test_toggle_favorite_twice_unfavorites():
    """第二次调用走 existing 分支 → is_favorite False 且 delete"""
    db = FakeDb()
    client = _client(db)
    r1 = client.post("/api/v1/conversations/16/favorite")
    r2 = client.post("/api/v1/conversations/16/favorite")
    assert r1.status_code == 200
    assert r1.json()["data"]["is_favorite"] is True
    assert r2.json()["data"]["is_favorite"] is False
    assert len(db.deleted) == 1


# ==================== 多轮快照回归（收藏取同轮，不再错配第一轮） ====================

def _conv(id_, role, content, citations=None):
    return FakeConv(id=id_, role=role, content=content, citations=citations)


def test_toggle_favorite_multi_turn_snapshot_same_round():
    """收藏第 2 轮 assistant 答案 → 快照第 2 轮的问题+答案（旧实现错配成第 1 轮）"""
    msgs = [
        _conv(1, "user", "第一轮问题"),
        _conv(2, "assistant", "第一轮回答", citations=[{"id": "c1"}]),
        _conv(3, "user", "第二轮问题"),
        _conv(4, "assistant", "第二轮回答", citations=[{"id": "c2"}]),
    ]
    db = FakeDb(msgs=msgs)
    resp = _client(db).post("/api/v1/conversations/4/favorite")
    assert resp.status_code == 200
    fav = db.added[0]
    assert fav.question == "第二轮问题"
    assert fav.answer == "第二轮回答"
    assert fav.citations == [{"id": "c2"}]


def test_toggle_favorite_multi_turn_snapshot_no_future_rows():
    """收藏 user 行 → question=该行，answer=该行之前最后一条 assistant
    （id <= 锚点 过滤：快照不得取到后续轮次）"""
    msgs = [
        _conv(1, "user", "第一轮问题"),
        _conv(2, "assistant", "第一轮回答"),
        _conv(3, "user", "第二轮问题"),
        _conv(4, "assistant", "第二轮回答"),
    ]
    db = FakeDb(msgs=msgs)
    resp = _client(db).post("/api/v1/conversations/3/favorite")
    assert resp.status_code == 200
    fav = db.added[0]
    assert fav.question == "第二轮问题"
    assert fav.answer == "第一轮回答"  # 锚点之前最后一条 assistant，而非下一轮的回答


def test_toggle_favorite_multi_turn_snapshot_first_round():
    """收藏第 1 轮 answer → question=第一轮问题（边界：之前无 user 行时兜底自身）"""
    msgs = [
        _conv(1, "user", "第一轮问题"),
        _conv(2, "assistant", "第一轮回答"),
        _conv(3, "user", "第二轮问题"),
        _conv(4, "assistant", "第二轮回答"),
    ]
    db = FakeDb(msgs=msgs)
    resp = _client(db).post("/api/v1/conversations/2/favorite")
    assert resp.status_code == 200
    fav = db.added[0]
    assert fav.question == "第一轮问题"
    assert fav.answer == "第一轮回答"
