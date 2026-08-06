"""网关 X-Request-ID 链路（需求 7.1：每个请求带 X-Request-ID（UUID））

- 请求头无 X-Request-ID：网关生成 uuid4，转发上游时注入
- 有 X-Request-ID：沿用（原样透传上游，同链关联）
- 超长/恶意值：校验拦截，重新生成（防滥用，原始值不透传）
- OPTIONS 预检：CORS 短路，不因新中间件引入额外逻辑
"""
import time
import uuid

import httpx
import jwt as pyjwt
from fastapi.testclient import TestClient

import app.main as main
from app.main import app
from app.core.auth_middleware import settings as middleware_settings

client = TestClient(app)


def _token(role: str = "admin") -> str:
    now = int(time.time())
    payload = {"sub": "1", "username": "u", "role": role, "iat": now, "exp": now + 3600}
    return pyjwt.encode(payload, middleware_settings.JWT_SECRET, algorithm="HS256")


def _headers() -> dict:
    return {"Authorization": f"Bearer {_token()}"}


class _StubResponse:
    """模拟 httpx 上游响应（JSON 分支）"""
    status_code = 200
    headers = {"content-type": "application/json"}
    content = b'{"code":0,"message":"success","data":null}'

    def json(self):
        return {"code": 0, "message": "success", "data": None}


class _CapturingClient:
    """模拟 httpx.AsyncClient：记录转发上游的请求头，返回固定 200"""

    def __init__(self):
        self.captured_headers = None

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        pass

    async def request(self, *args, **kwargs):
        self.captured_headers = kwargs.get("headers") or {}
        return _StubResponse()


def _proxy_client(monkeypatch) -> _CapturingClient:
    stub = _CapturingClient()
    monkeypatch.setattr(main.httpx, "AsyncClient", lambda *a, **k: stub)
    return stub


def test_generates_request_id_when_missing(monkeypatch):
    """请求未带 X-Request-ID：网关生成 uuid4 并注入转发头"""
    stub = _proxy_client(monkeypatch)
    resp = client.get("/api/v1/visits/x", headers=_headers())
    assert resp.status_code == 200
    rid = stub.captured_headers.get("x-request-id")
    assert rid
    uuid.UUID(rid)  # 必须是合法 UUID 格式


def test_reuses_client_request_id(monkeypatch):
    """请求已带 X-Request-ID：沿用，原样透传上游"""
    stub = _proxy_client(monkeypatch)
    rid = str(uuid.uuid4())
    resp = client.get("/api/v1/visits/x", headers={**_headers(), "X-Request-ID": rid})
    assert resp.status_code == 200
    assert stub.captured_headers.get("x-request-id") == rid


def test_oversized_request_id_is_regenerated(monkeypatch):
    """超长 X-Request-ID（>100 字符，与审计库列长对齐）：视为滥用重新生成"""
    stub = _proxy_client(monkeypatch)
    resp = client.get(
        "/api/v1/visits/x",
        headers={**_headers(), "X-Request-ID": "A" * 200},
    )
    assert resp.status_code == 200
    rid = stub.captured_headers.get("x-request-id")
    assert rid
    assert len(rid) <= 100
    assert rid != "A" * 200
    uuid.UUID(rid)


def test_preflight_passes_through():
    """OPTIONS 预检：CORS 短路返回，不触发链路/转发逻辑"""
    resp = client.options(
        "/api/v1/visits/x",
        headers={
            "Origin": "http://example.com",
            "Access-Control-Request-Method": "POST",
            "X-Request-ID": "A" * 200,  # 预检即使带恶意头也不落任何逻辑
        },
    )
    assert resp.status_code == 200
    assert resp.headers.get("access-control-allow-origin")
