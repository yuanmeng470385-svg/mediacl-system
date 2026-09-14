"""auth/register 网关转发（部署挂账 §5）

医生自助注册端点必须免认证可达（未注册的人没有 token）：
  - POST /api/v1/auth/register 无 token → 200（打桩转发到 auth-service）
  - 对照：同前缀下需认证的 /api/v1/auth/profile 无 token 仍 401（白名单只放 register）

照 test_doctor_routes.py 模式：打桩 httpx，断言转发目标 URL + 方法。
"""
import asyncio
import types

import httpx

import app.main as main
from app.main import app


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


def test_register_routes_to_auth_service_without_token(monkeypatch):
    log = _record_forwarding(monkeypatch)

    async def _run():
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as c:
            return await c.post("/api/v1/auth/register", json={
                "phone": "13900009931", "full_name": "测试注册", "password": "Test@2026a",
            })

    resp = asyncio.run(_run())
    assert resp.status_code == 200
    assert len(log) == 1
    method, url = log[0]
    assert method == "POST"
    assert url == f"{main.settings.AUTH_SERVICE_URL}/api/v1/auth/register"


def test_auth_profile_still_requires_bearer_token(monkeypatch):
    """白名单只放开 register：同前缀的 profile 无 token 依旧 401（不转发）"""
    log = _record_forwarding(monkeypatch)

    async def _run():
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as c:
            return await c.get("/api/v1/auth/profile")

    resp = asyncio.run(_run())
    assert resp.status_code == 401
    assert log == []
