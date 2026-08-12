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
    _mgr.end_visit = AsyncMock(return_value={"id": 46, "ai_summary": "mock"})
    yield
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
