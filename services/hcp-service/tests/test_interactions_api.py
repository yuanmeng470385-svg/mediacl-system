"""API 契约测试 — /api/v1/hcps/{id}/interactions 必须返回裸数组

回归背景：曾返回 {"items": [...]}，而 web 端 DoctorDetail.tsx 与 mobile 端
hcp.ts/HCPDetailScreen.tsx 均按裸数组解包（直接 .map），导致两端必崩。
契约：响应 data 字段必须是数组，不能是 {"items": ...} 包装。
"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", ".."))

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from app.main import app  # noqa: E402
from app.models.hcp import Hcp  # noqa: E402
from app.api import hcps as hcps_api  # noqa: E402
from shared.common.db_session import get_db  # noqa: E402
from shared.common.auth import get_current_user  # noqa: E402


class FakeDb:
    """假 session：不该被真正查询（list_interactions 已被 mock）"""

    def execute(self, *args, **kwargs):
        raise AssertionError("不应真正执行 SQL")


async def _fake_current_user():
    return {"id": 1, "username": "tester", "role": "admin"}


_FAKE_INTERACTIONS = [
    {
        "id": 1,
        "visit_time": "2026-08-01T10:00:00",
        "duration_minutes": 30,
        "sentiment": "positive",
        "ai_summary": "交流良好，认可产品",
        "key_points": ["学术认可"],
        "interests": ["免疫治疗"],
        "objections": [],
        "follow_up_suggestions": "跟进临床数据",
        "next_visit_plan": "2026-09-01",
    },
    {
        "id": 2,
        "visit_time": "2026-07-20T14:00:00",
        "ai_summary": "首次拜访",
        "key_points": ["建立联系"],
    },
]


@pytest.fixture
def client(monkeypatch):
    """TestClient：mock 掉 DB 依赖与数据查询，只验证响应形状契约"""
    monkeypatch.setattr(
        hcps_api.HcpRepo, "get",
        staticmethod(lambda db, hcp_id: Hcp(id=hcp_id, name="张伟", hospital="协和医院")),
    )
    monkeypatch.setattr(hcps_api, "list_interactions", lambda db, hcp_id: _FAKE_INTERACTIONS)

    app.dependency_overrides[get_db] = lambda: FakeDb()
    app.dependency_overrides[get_current_user] = _fake_current_user
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()


def test_interactions_returns_bare_array(client):
    resp = client.get("/api/v1/hcps/1/interactions")
    assert resp.status_code == 200
    body = resp.json()
    assert body["code"] == 0
    data = body["data"]
    # 契约：裸数组（两端直接 .map，禁止 {items: [...]} 包装）
    assert isinstance(data, list), f"data 必须是裸数组，实际为 {type(data).__name__}"
    assert len(data) == 2
    assert data[0]["ai_summary"] == "交流良好，认可产品"
    assert data[1]["visit_time"] == "2026-07-20T14:00:00"


def test_interactions_404_when_hcp_missing(client, monkeypatch):
    monkeypatch.setattr(
        hcps_api.HcpRepo, "get", staticmethod(lambda db, hcp_id: None),
    )
    resp = client.get("/api/v1/hcps/999/interactions")
    assert resp.status_code == 404
