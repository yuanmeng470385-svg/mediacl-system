"""privacy-requests 路由（三期 L）：转发到 auth-service，且必须带 JWT

照 test_doctor_routes.py 模式：打桩 httpx，断言转发目标 URL + 方法。
"""
import asyncio
import time
import types

import httpx
import jwt as pyjwt

import app.main as main
from app.main import app
from app.core.auth_middleware import settings as middleware_settings


class _StubResponse:
    status_code = 200
    headers = {"content-type": "application/json"}
    content = b'{"code":0,"message":"success","data":null}'

    def json(self):
        return {"code": 0, "message": "success", "data": None}


class _RecordingClient:
    def __init__(self, log: list):
        self._log = log

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        pass

    async def request(self, method, url, **kwargs):
        self._log.append((method, str(url)))
        return _StubResponse()


def _record_forwarding(monkeypatch) -> list:
    log: list = []
    fake_httpx = types.SimpleNamespace(
        AsyncClient=lambda *a, **k: _RecordingClient(log),
        ConnectError=httpx.ConnectError,
        TimeoutException=httpx.TimeoutException,
        HTTPError=httpx.HTTPError,
    )
    monkeypatch.setattr(main, "httpx", fake_httpx)
    return log


def _auth_headers() -> dict:
    now = int(time.time())
    payload = {"sub": "1", "username": "u", "role": "doctor", "iat": now, "exp": now + 3600}
    token = pyjwt.encode(payload, middleware_settings.JWT_SECRET, algorithm="HS256")
    return {"Authorization": f"Bearer {token}"}


def test_privacy_requests_routes_to_auth_service(monkeypatch):
    log = _record_forwarding(monkeypatch)

    async def _run():
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as c:
            return await c.post(
                "/api/v1/privacy-requests",
                json={"request_type": "export", "detail": "导出"},
                headers=_auth_headers(),
            )

    resp = asyncio.run(_run())
    assert resp.status_code == 200
    assert len(log) == 1
    method, url = log[0]
    assert method == "POST"
    assert url == f"{main.settings.AUTH_SERVICE_URL}/api/v1/privacy-requests"


def test_privacy_requests_requires_jwt():
    async def _run():
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as c:
            return await c.get("/api/v1/privacy-requests/me")

    resp = asyncio.run(_run())
    assert resp.status_code == 401
