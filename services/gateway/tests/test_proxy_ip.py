"""网关 XFF 信任代理回归（I2，2026-08-13）

B5 修复无条件用 request.client.host 覆盖 X-Forwarded-For/X-Real-IP —— 防客户端
伪造是对的，但反代/LB 部署下把部署层注入的真实客户端 IP 也覆盖掉了（审计
client_ip 全记成 LB 地址）。I2：新增 TRUSTED_PROXY_CIDRS 信任代理网段（逗号
分隔 CIDR，默认空）—— 仅当对端命中信任网段时，采用部署层注入的 X-Real-IP
（取第一个）作为真实客户端 IP；未配置 / 未命中时维持原有覆盖行为，默认行为
与现状完全一致。
"""
import asyncio
import ipaddress
import time
import types

import httpx
import jwt as pyjwt
from starlette.testclient import TestClient

import app.main as main
from app.main import app
from app.core.auth_middleware import settings as middleware_settings

client = TestClient(app)  # starlette 默认 scope client 为 ("testclient", 50000)


def _token(role: str = "admin") -> str:
    now = int(time.time())
    payload = {"sub": "1", "username": "u", "role": role, "iat": now, "exp": now + 3600}
    return pyjwt.encode(payload, middleware_settings.JWT_SECRET, algorithm="HS256")


def _auth_headers() -> dict:
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


def _capture(monkeypatch) -> _CapturingClient:
    """把 proxy() 里的 httpx.AsyncClient 换成记录桩。

    只替换 main 模块的 httpx 属性（不污染全局 httpx 模块），
    本测试自身仍可用真 httpx.AsyncClient 发起 ASGI 请求。
    """
    stub = _CapturingClient()
    fake_httpx = types.SimpleNamespace(
        AsyncClient=lambda *a, **k: stub,
        ConnectError=httpx.ConnectError,
        TimeoutException=httpx.TimeoutException,
        HTTPError=httpx.HTTPError,
    )
    monkeypatch.setattr(main, "httpx", fake_httpx)
    return stub


def _get_with_peer(peer_ip: str, path: str, headers: dict) -> httpx.Response:
    """以指定对端 IP 发起一次网关请求（ASGITransport 指定 scope client）"""
    async def _run():
        transport = httpx.ASGITransport(app=app, client=(peer_ip, 1234))
        async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as c:
            return await c.get(path, headers=headers)

    return asyncio.run(_run())


def _trust(monkeypatch, cidrs):
    """注入信任代理网段（模块级 _trusted_proxy_nets 由启动时解析，测试用 monkeypatch 替换）"""
    monkeypatch.setattr(
        main, "_trusted_proxy_nets", [ipaddress.ip_network(c, strict=False) for c in cidrs]
    )


def test_default_unconfigured_forged_headers_overwritten(monkeypatch):
    """默认（未配置 TRUSTED_PROXY_CIDRS）：客户端伪造的 X-Real-IP/X-Forwarded-For
    仍被对端地址覆盖（B5 行为不变）"""
    stub = _capture(monkeypatch)
    resp = _get_with_peer(
        "198.51.100.7", "/api/v1/visits/x",
        {**_auth_headers(), "X-Real-IP": "203.0.113.9", "X-Forwarded-For": "6.6.6.6"},
    )
    assert resp.status_code == 200
    assert stub.captured_headers["x-forwarded-for"] == "198.51.100.7"
    assert stub.captured_headers["x-real-ip"] == "198.51.100.7"


def test_untrusted_peer_outside_cidr_still_overwritten(monkeypatch):
    """配置了信任网段但对端不在网段内：维持覆盖行为（不信任自报 IP）"""
    _trust(monkeypatch, ["10.0.0.0/8"])
    stub = _capture(monkeypatch)
    resp = _get_with_peer(
        "198.51.100.7", "/api/v1/visits/x",
        {**_auth_headers(), "X-Real-IP": "203.0.113.9"},
    )
    assert resp.status_code == 200
    assert stub.captured_headers["x-forwarded-for"] == "198.51.100.7"
    assert stub.captured_headers["x-real-ip"] == "198.51.100.7"


def test_trusted_proxy_preserves_injected_real_ip(monkeypatch):
    """对端命中信任网段：保留部署层注入的 X-Real-IP（真实客户端 IP 不再被抹成 LB 地址）"""
    _trust(monkeypatch, ["10.0.0.0/8"])
    stub = _capture(monkeypatch)
    resp = _get_with_peer(
        "10.0.0.5", "/api/v1/visits/x",  # 网关对端是 LB
        {**_auth_headers(), "X-Real-IP": "203.0.113.9"},
    )
    assert resp.status_code == 200
    assert stub.captured_headers["x-forwarded-for"] == "203.0.113.9"
    assert stub.captured_headers["x-real-ip"] == "203.0.113.9"


def test_trusted_proxy_takes_first_x_real_ip_value(monkeypatch):
    """X-Real-IP 为逗号列表时取第一个（多级代理场景首段为真实客户端）"""
    _trust(monkeypatch, ["10.0.0.0/8"])
    stub = _capture(monkeypatch)
    resp = _get_with_peer(
        "10.0.0.5", "/api/v1/visits/x",
        {**_auth_headers(), "X-Real-IP": "203.0.113.9, 198.51.100.4"},
    )
    assert resp.status_code == 200
    assert stub.captured_headers["x-forwarded-for"] == "203.0.113.9"
    assert stub.captured_headers["x-real-ip"] == "203.0.113.9"


def test_trusted_proxy_without_injected_header_falls_back_to_peer(monkeypatch):
    """信任代理未注入 X-Real-IP：回退用对端地址（不传空值上游）"""
    _trust(monkeypatch, ["10.0.0.0/8"])
    stub = _capture(monkeypatch)
    resp = _get_with_peer("10.0.0.5", "/api/v1/visits/x", _auth_headers())
    assert resp.status_code == 200
    assert stub.captured_headers["x-forwarded-for"] == "10.0.0.5"
    assert stub.captured_headers["x-real-ip"] == "10.0.0.5"


def test_parse_trusted_proxy_cidrs_skips_invalid(monkeypatch):
    """CIDR 解析：非法项告警跳过，不拖垮启动"""
    monkeypatch.setattr(main, "_trusted_proxy_cidrs", ["10.0.0.0/8", "not-a-cidr", "192.168.0.0/16"])
    nets = main._parse_trusted_proxy_cidrs()
    assert [str(n) for n in nets] == ["10.0.0.0/8", "192.168.0.0/16"]
