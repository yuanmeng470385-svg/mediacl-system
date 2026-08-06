"""反馈/收藏落库 + 满意度统计"""
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

    def __init__(self):
        self.id = 16
        self.user_id = 3
        self.specialist_id = 1
        self.session_id = "sess-1"
        self.content = "问题"
        self.citations = None
        self.role = "user"


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


class FakeDb:
    """已收藏（added 非空）后 query(ConversationFavorite) 返回 existing"""

    def __init__(self):
        self.added = []
        self.deleted = []

    def query(self, model):
        if model.__name__ == "Conversation":
            return QueryStub(first_result=FakeConv())
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
