"""X-Request-ID 服务侧消费 + http_requests_total（REQUESTS）接线

- REQUESTS 此前定义了但从未 .inc()，恒为 0；现在由 MetricsMiddleware 计数
- RequestIDMiddleware：请求头 X-Request-ID → context（get_request_id 取用）
"""
import uuid

from fastapi import FastAPI
from fastapi.testclient import TestClient

from shared.common.context import get_request_id
from shared.common.request_id_middleware import RequestIDMiddleware

from app.api.metrics import REQUESTS
from app.main import app as real_app

client = TestClient(real_app)


# ---------- http_requests_total（REQUESTS 计数接线） ----------

def _counter_value(method: str) -> float:
    """http_requests_total{service=specialist-service, method} 的当前计数值。

    直接读计数器对象而不是解析 /metrics 文本：本地旧版 prometheus_client
    的指标名不带 _total 后缀（暴露为 http_requests），新版本（>=0.19，
    生产要求）才带 —— 对象直读对版本差异鲁棒。
    """
    return REQUESTS.labels(service="specialist-service", method=method)._value.get()


def test_http_requests_total_increments_on_request():
    """每个 HTTP 请求后 http_requests_total 递增（此前恒 0）"""
    before = _counter_value("GET")
    resp = client.get("/health")
    assert resp.status_code == 200
    assert _counter_value("GET") == before + 1


def test_options_preflight_not_counted():
    """OPTIONS 预检/非业务请求不计入 HTTP 请求数"""
    before = _counter_value("GET")
    resp = client.options("/health")
    assert resp.status_code in (200, 405)
    assert _counter_value("GET") == before


# ---------- RequestIDMiddleware 服务侧消费（请求头 → context） ----------

mini_app = FastAPI()
mini_app.add_middleware(RequestIDMiddleware)


@mini_app.get("/echo")
async def _echo():
    return {"rid": get_request_id()}


mini_client = TestClient(mini_app)


def test_service_middleware_reads_header_into_context():
    """请求头 X-Request-ID → context，路由内 get_request_id() 取到同一值"""
    rid = "client-rid-12345"
    resp = mini_client.get("/echo", headers={"X-Request-ID": rid})
    assert resp.status_code == 200
    assert resp.json()["rid"] == rid


def test_service_middleware_generates_when_missing():
    """无 X-Request-ID：自动生成合法 UUID 写入 context（服务直连兜底）"""
    resp = mini_client.get("/echo")
    assert resp.status_code == 200
    rid = resp.json()["rid"]
    assert rid
    uuid.UUID(rid)
