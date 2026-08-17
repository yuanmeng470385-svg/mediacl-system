"""qualifications 路由：网关转发到 auth-service，且必须带 JWT"""
import asyncio
import time
import types

import httpx
import jwt as pyjwt
import pytest

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
    payload = {"sub": "1", "username": "u", "role": "rep", "iat": now, "exp": now + 3600}
    token = pyjwt.encode(payload, middleware_settings.JWT_SECRET, algorithm="HS256")
    return {"Authorization": f"Bearer {token}"}


def test_me_routes_to_auth_service(monkeypatch):
    log = _record_forwarding(monkeypatch)

    async def _run():
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as c:
            return await c.get("/api/v1/qualifications/me", headers=_auth_headers())

    resp = asyncio.run(_run())
    assert resp.status_code == 200
    assert len(log) == 1
    method, url = log[0]
    assert method == "GET"
    assert url == f"{main.settings.AUTH_SERVICE_URL}/api/v1/qualifications/me"


def test_requires_bearer_token(monkeypatch):
    log = _record_forwarding(monkeypatch)

    async def _run():
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as c:
            return await c.get("/api/v1/qualifications/me")

    resp = asyncio.run(_run())
    assert resp.status_code == 401
    assert log == []


def test_qualifications_proxy_timeout_carve_out(monkeypatch):
    """F3：/api/v1/qualifications/* 走 120s 超时 carve-out（移动端 60s 客户端超时，
    网关 30s 默认超时会先掐断）—— 照 knowledge 路由先例，其他路由维持 30s。"""
    timeouts: list = []

    def _fake_async_client(*a, **k):
        timeouts.append(k.get("timeout"))
        return _RecordingClient([])

    fake_httpx = types.SimpleNamespace(
        AsyncClient=_fake_async_client,
        ConnectError=httpx.ConnectError,
        TimeoutException=httpx.TimeoutException,
        HTTPError=httpx.HTTPError,
    )
    monkeypatch.setattr(main, "httpx", fake_httpx)

    async def _run():
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as c:
            await c.get("/api/v1/qualifications/me", headers=_auth_headers())
            await c.get("/api/v1/visits/tasks", headers=_auth_headers())

    asyncio.run(_run())
    assert timeouts == [120.0, 30.0]
