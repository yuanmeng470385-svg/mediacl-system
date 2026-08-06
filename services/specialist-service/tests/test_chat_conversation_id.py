"""chat 必须返回 conversation_id（assistant 行 id），前端反馈/收藏依赖它。

沿用本服务既有风格：不起真实 DB，用假 session 验证落库逻辑与返回值。
"""
import pytest

from app.api.specialists import _persist_conversation


class FakeSession:
    """最小 Session 替身：add 时给对象补 id，模拟 commit 后主键回填"""

    def __init__(self, fail_on_commit=False):
        self.added = []
        self.fail_on_commit = fail_on_commit
        self.committed = False

    def add(self, obj):
        self.added.append(obj)

    def commit(self):
        if self.fail_on_commit:
            raise RuntimeError("db down")
        self.committed = True
        for i, obj in enumerate(self.added, start=1):
            obj.id = i

    def rollback(self):
        pass


RESULT = {
    "answer": "答案内容",
    "citations": [{"title": "文献A"}],
    "session_id": "sess-1",
    "latency_ms": 120,
    "blocked": False,
}


def test_persist_returns_assistant_row_id():
    db = FakeSession()
    conv_id = _persist_conversation(db, user_id=3, specialist_id=1,
                                    question="你好", result=RESULT)
    # 两条：user 行 id=1，assistant 行 id=2 —— 必须返回 assistant 行
    assert len(db.added) == 2
    assert db.added[0].role == "user"
    assert db.added[1].role == "assistant"
    assert conv_id == 2


def test_persist_assistant_row_carries_answer_and_citations():
    db = FakeSession()
    _persist_conversation(db, user_id=3, specialist_id=1,
                          question="你好", result=RESULT)
    ai_row = db.added[1]
    assert ai_row.content == "答案内容"
    assert ai_row.citations == [{"title": "文献A"}]
    assert ai_row.latency_ms == 120


def test_persist_returns_none_on_db_failure():
    """入库失败不能让整个 chat 挂掉 —— 返回 None，前端据此禁用反馈按钮"""
    db = FakeSession(fail_on_commit=True)
    conv_id = _persist_conversation(db, user_id=3, specialist_id=1,
                                    question="你好", result=RESULT)
    assert conv_id is None
