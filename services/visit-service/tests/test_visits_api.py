"""拜访 API 端点回归测试（FastAPI 校验层：真机 422 回归）

真机联调发现：移动端 endVisit 不带 body 调 POST /visits/{id}/end，
旧签名 request: dict 被 FastAPI 校验层 422 拒绝（full_transcript 本身是可选
契约，body 不应必填）→ 移动端弹"请求失败"。本测试从校验层验证：
  - 不带 body → 200（regression）
  - 带 body（full_transcript）→ 透传给 manager（契约不回退）
"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", ".."))

from unittest.mock import AsyncMock

import pytest
from fastapi.testclient import TestClient

from shared.common.auth import get_current_user
from shared.common.db_session import get_db

import app.api.visits as visits_mod
from app.main import app

# 依赖覆盖：端点到 manager 为止（真实 DB/鉴权不参与）
FAKE_USER = {"id": 1, "role": "rep"}


@pytest.fixture(autouse=True)
def _override_deps():
    def _fake_db():
        yield object()

    app.dependency_overrides[get_db] = _fake_db
    app.dependency_overrides[get_current_user] = lambda: FAKE_USER
    # 归属校验与 manager 全部打桩
    visits_mod._assert_visit_owner = lambda *a, **k: None
    _mgr = visits_mod._visit_manager
    # B7（2026-08-13）：保存原函数，teardown 还原 —— 直接替换不还原会让
    # 后续用到真实 end_visit 的用例（跨模块顺序敏感）拿到 AsyncMock
    _orig_end_visit = _mgr.end_visit
    _mgr.end_visit = AsyncMock(return_value={"id": 46, "ai_summary": "mock"})
    yield
    _mgr.end_visit = _orig_end_visit
    app.dependency_overrides.clear()


def test_end_visit_without_body_ok():
    """移动端 endVisit 不带 body → 必须 200（regression：曾经 422）"""
    client = TestClient(app)
    resp = client.post("/api/v1/visits/46/end")
    assert resp.status_code == 200
    body = resp.json()
    assert body["code"] == 0
    assert body["data"]["id"] == 46
    # 无 body → full_transcript=None → 用已累积转写
    assert visits_mod._visit_manager.end_visit.call_args.kwargs["full_transcript"] is None


def test_end_visit_with_full_transcript_passthrough():
    """带 body（full_transcript）→ 原样透传 manager，契约不回退"""
    client = TestClient(app)
    resp = client.post("/api/v1/visits/46/end", json={"full_transcript": "你好"})
    assert resp.status_code == 200
    assert visits_mod._visit_manager.end_visit.call_args.kwargs["full_transcript"] == "你好"


def test_end_visit_empty_object_ok():
    """空对象 {} 同样合法（老客户端可能发空 body）"""
    client = TestClient(app)
    resp = client.post("/api/v1/visits/46/end", json={})
    assert resp.status_code == 200
    assert visits_mod._visit_manager.end_visit.call_args.kwargs["full_transcript"] is None


def test_end_visit_full_transcript_not_str_400():
    """B6：full_transcript 非字符串（数字/数组/对象）→ 400，不把垃圾拼进转写证据"""
    client = TestClient(app)
    for bad in (123, ["你好"], {"text": "你好"}, True):
        resp = client.post("/api/v1/visits/46/end", json={"full_transcript": bad})
        assert resp.status_code == 400, f"full_transcript={bad!r} 应 400"
        assert resp.json()["code"] == 1000


def test_list_visits_invalid_status_400():
    """B3：列表 status 白名单 —— 非法值 400，不再静默忽略返回全量"""
    client = TestClient(app)
    resp = client.get("/api/v1/visits?status=hacked")
    assert resp.status_code == 400
    assert resp.json()["code"] == 1000


def test_list_visits_valid_statuses_passthrough(monkeypatch):
    """B3 反例：三种合法状态放行进入 repo（白名单不误伤正常筛选）"""
    def _fake_list(db, **kwargs):
        return [], 0

    monkeypatch.setattr(visits_mod.VisitRepo, "list", staticmethod(_fake_list))
    client = TestClient(app)
    for status in ("in_progress", "completed", "cancelled"):
        resp = client.get(f"/api/v1/visits?status={status}")
        assert resp.status_code == 200, f"status={status} 应放行"
