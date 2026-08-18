"""doctor 路由（一期 B）：medical/qa 与 share-links 转发到 specialist-service，且必须带 JWT

照 test_qualifications_route.py 模式：打桩 httpx，断言转发目标 URL + 方法。
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


def test_medical_qa_routes_to_specialist_service(monkeypatch):
    log = _record_forwarding(monkeypatch)

    async def _run():
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as c:
            return await c.post("/api/v1/medical/qa", json={"question": "测试"},
                                headers=_auth_headers())

    resp = asyncio.run(_run())
    assert resp.status_code == 200
    assert len(log) == 1
    method, url = log[0]
    assert method == "POST"
    assert url == f"{main.settings.SPECIALIST_SERVICE_URL}/api/v1/medical/qa"


def test_share_links_activate_routes_to_specialist_service(monkeypatch):
    log = _record_forwarding(monkeypatch)

    async def _run():
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as c:
            return await c.post("/api/v1/share-links/abc/activate", headers=_auth_headers())

    resp = asyncio.run(_run())
    assert resp.status_code == 200
    assert len(log) == 1
    method, url = log[0]
    assert method == "POST"
    assert url == f"{main.settings.SPECIALIST_SERVICE_URL}/api/v1/share-links/abc/activate"


def test_doctors_certs_me_routes_to_auth_service(monkeypatch):
    """B9：/api/v1/doctors/certs/me（医生端 submitCert/getMyCert）转发到 auth-service，
    且必须带 JWT —— Task 2 计划遗漏，此前经网关 404。"""
    log = _record_forwarding(monkeypatch)

    async def _run():
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as c:
            return await c.get("/api/v1/doctors/certs/me", headers=_auth_headers())

    resp = asyncio.run(_run())
    assert resp.status_code == 200
    assert len(log) == 1
    method, url = log[0]
    assert method == "GET"
    assert url == f"{main.settings.AUTH_SERVICE_URL}/api/v1/doctors/certs/me"


def test_doctors_requires_bearer_token(monkeypatch):
    log = _record_forwarding(monkeypatch)

    async def _run():
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as c:
            return await c.get("/api/v1/doctors/certs/me")

    resp = asyncio.run(_run())
    assert resp.status_code == 401
    assert log == []


def test_doctors_proxy_timeout_carve_out(monkeypatch):
    """B9：/api/v1/doctors/* 走 120s 超时 carve-out（证书 OSS 上传慢时防 30s 网关
    先断）—— 照 qualifications 路由先例，其他路由维持 30s。"""
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
            await c.get("/api/v1/doctors/certs/me", headers=_auth_headers())
            await c.get("/api/v1/visits/tasks", headers=_auth_headers())

    asyncio.run(_run())
    assert timeouts == [120.0, 30.0]
