"""拜访后任务创建与任务接口"""
from datetime import date

from app.db.repositories.task_repo import TaskRepo
from app.core.visit_manager import _parse_follow_up_items


class _FakeTask:
    def __init__(self, **kw):
        for k, v in kw.items():
            setattr(self, k, v)


class _FakeDb:
    def __init__(self):
        self.tasks = []

    def add(self, obj):
        self.tasks.append(obj)

    def commit(self):
        pass

    def refresh(self, obj):
        obj.id = len(self.tasks)


def test_parse_follow_up_items():
    items = [
        {"action": "发送 XX 说明书", "due": "2026-08-10", "channel": "微信"},
        {"action": "预约下次拜访", "due": "", "channel": "下次拜访"},
        "坏格式",
    ]
    parsed = _parse_follow_up_items(items, visit_id=1, user_id=2)
    assert len(parsed) == 2
    assert parsed[0]["title"] == "发送 XX 说明书"
    assert parsed[0]["due_date"] == date(2026, 8, 10)
    assert parsed[0]["task_type"] == "send_material"
    assert parsed[1]["task_type"] == "book_appointment"


def test_repo_create_assigns_fields():
    db = _FakeDb()
    task = TaskRepo.create(db, visit_id=1, user_id=2, item={
        "title": "打电话跟进", "task_type": "call", "due_date": None, "channel": "电话",
    })
    assert task.visit_id == 1 and task.user_id == 2
    assert task.status == "open"
    assert db.tasks[0].title == "打电话跟进"
