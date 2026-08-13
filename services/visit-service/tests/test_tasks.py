"""拜访后任务创建与任务接口"""
import os
import sys
from datetime import date

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", ".."))

import pytest
from fastapi.testclient import TestClient

from shared.common.auth import get_current_user
from shared.common.db_session import get_db

from app.main import app
from app.db.repositories import task_repo
from app.db.repositories.task_repo import TaskRepo
from app.core.visit_manager import _parse_follow_up_items

# B3（2026-08-13）：任务列表 status 白名单校验 —— 端点层测试（依赖覆盖，不碰真实 DB）
FAKE_USER = {"id": 1, "role": "rep"}


@pytest.fixture(autouse=True)
def _override_deps():
    def _fake_db():
        yield object()

    app.dependency_overrides[get_db] = _fake_db
    app.dependency_overrides[get_current_user] = lambda: FAKE_USER
    yield
    app.dependency_overrides.clear()


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


def test_list_tasks_invalid_status_400():
    """B3：任务列表 status 白名单 —— 非法值 400，不再静默忽略返回全量"""
    client = TestClient(app)
    resp = client.get("/api/v1/tasks?status=hacked")
    assert resp.status_code == 400
    assert resp.json()["code"] == 1000


def test_list_tasks_valid_statuses_passthrough(monkeypatch):
    """B3 反例：open/done/cancelled 放行进入 repo（白名单不误伤正常筛选）"""
    def _fake_list(db, user_id, status=None, page=1, page_size=20):
        return [], 0

    monkeypatch.setattr(task_repo.TaskRepo, "list_by_user", staticmethod(_fake_list))
    client = TestClient(app)
    for status in ("open", "done", "cancelled"):
        resp = client.get(f"/api/v1/tasks?status={status}")
        assert resp.status_code == 200, f"status={status} 应放行"
