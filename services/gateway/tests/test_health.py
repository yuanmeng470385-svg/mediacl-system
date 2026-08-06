"""网关健康检查端点（M46：真探活）"""
import pytest
from fastapi.testclient import TestClient

from app.main import app, set_health_probe

client = TestClient(app)

BACKEND_NAMES = {
    "auth", "specialist", "visit", "knowledge",
    "compliance", "audit", "hcp",
}


@pytest.fixture(autouse=True)
def _inject_fake_probe():
    """默认注入 fake 探测（全部 up），避免测试真连本地后端；用例可自行覆盖。"""
    async def _probe(url: str) -> bool:
        return True

    set_health_probe(_probe)
    yield
    set_health_probe(None)


def test_health_returns_ok():
    resp = client.get("/health")
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "ok"
    # 保留原有返回结构
    assert set(body["backends"]) == BACKEND_NAMES
    assert body["service"] == "gateway"
    # 新增：每个服务 up/down 状态
    assert set(body["services"]) == BACKEND_NAMES
    assert all(s in ("up", "down") for s in body["services"].values())


def test_health_reports_down_service():
    async def _probe(url: str) -> bool:
        return "8002" not in url  # visit-service（默认端口 8002）探测失败

    set_health_probe(_probe)
    resp = client.get("/health")
    body = resp.json()
    assert body["services"]["visit"] == "down"
    assert body["services"]["auth"] == "up"
    # 网关自身仍存活
    assert body["status"] == "ok"


def test_health_probe_exception_counts_as_down():
    async def _probe(url: str) -> bool:
        raise RuntimeError("probe 内部异常")

    set_health_probe(_probe)
    resp = client.get("/health")
    assert resp.status_code == 200
    assert all(v == "down" for v in resp.json()["services"].values())
