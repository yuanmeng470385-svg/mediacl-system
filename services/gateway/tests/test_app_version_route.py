"""App 版本检查走网关（2026-09-15 挂账落地）

两端 App 冷启动第一屏是登录页，此时没有 token —— /api/v1/app/version 必须免认证可达；
同前缀下的管理端配置 /api/v1/app/config 必须仍要 JWT（防「前缀白名单顺手放开」）。

照 test_register_route.py 模式：打桩 httpx，断言转发目标 URL + 方法。
"""
import asyncio
import types

import httpx

import app.main as main
from app.main import app


class _StubResponse:
    status_code = 200
    headers = {"content-type": "application/json"}
    content = b'{"code":0,"message":"success","data":{"latest_version":"1.0.0"}}'

    def json(self):
        return {"code": 0, "message": "success", "data": {"latest_version": "1.0.0"}}


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


def _get(path, **kwargs):
    async def _run():
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as c:
            return await c.get(path, **kwargs)
    return asyncio.run(_run())


def test_version_public_and_forwarded_to_auth(monkeypatch):
    log = _record_forwarding(monkeypatch)
    resp = _get("/api/v1/app/version?platform=rep")
    assert resp.status_code == 200
    assert log, "应转发到 auth-service"
    method, url = log[-1]
    assert method == "GET"
    assert url.startswith(main.settings.AUTH_SERVICE_URL)
    assert "/api/v1/app/version" in url


def test_admin_config_still_requires_token():
    """白名单只放 /version；/config 是它的兄弟不是子路径，不能被顺带放开"""
    resp = _get("/api/v1/app/config")
    assert resp.status_code == 401
    assert resp.json()["code"] == 2000
