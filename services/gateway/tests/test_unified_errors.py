"""网关统一错误格式（M44/M45/E3）

404/503/504/502 必须返回顶层 {code, message, data}，与 auth_middleware 和
rate_limiter 一致 —— 此前 404/503/504 是 {"detail": ...}，前端 resp.data.code
拿不到 code；上游断连（非 ConnectError/TimeoutException）会冒泡成 500 纯文本。
E3：上游声称 JSON 但 body 无法解析 → 502 {code:5005}（5001=连不上 503、
5002=超时 504、5003=限流 429、5004=协议异常 502）。
"""
import json
import time

import httpx
import jwt as pyjwt
import pytest
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


def test_404_uses_unified_shape():
    """未匹配路由 → 404 {code:1004,...}，不是 {"detail":...}"""
    resp = client.get("/api/v1/definitely-not-a-route", headers=_headers())
    assert resp.status_code == 404
    assert resp.json() == {"code": 1004, "message": "路由不存在", "data": None}


def test_503_connect_error_uses_unified_shape(monkeypatch):
    """连接被拒（ConnectError）→ 503 {code:5001,...}"""
    monkeypatch.setattr(
        main.httpx, "AsyncClient",
        lambda *a, **k: _BoomClient(httpx.ConnectError("connection refused")),
    )
    resp = client.get("/api/v1/visits/x", headers=_headers())
    assert resp.status_code == 503
    assert resp.json() == {"code": 5001, "message": "后端服务不可用", "data": None}


class _BoomClient:
    """模拟 httpx.AsyncClient：request 抛指定异常"""

    def __init__(self, exc):
        self.exc = exc

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        pass

    async def request(self, *args, **kwargs):
        raise self.exc


def test_504_timeout_uses_unified_shape(monkeypatch):
    """上游超时 → 504 {code:5002,...}"""
    monkeypatch.setattr(
        main.httpx, "AsyncClient",
        lambda *a, **k: _BoomClient(httpx.TimeoutException("slow backend")),
    )
    resp = client.get("/api/v1/visits/x", headers=_headers())
    assert resp.status_code == 504
    assert resp.json() == {"code": 5002, "message": "后端服务超时", "data": None}


def test_502_http_error_uses_unified_shape(monkeypatch):
    """上游断连/协议异常（非 ConnectError/TimeoutException）→ 502 {code:5004,...}"""
    monkeypatch.setattr(
        main.httpx, "AsyncClient",
        lambda *a, **k: _BoomClient(httpx.RemoteProtocolError("peer closed connection")),
    )
    resp = client.get("/api/v1/visits/x", headers=_headers())
    assert resp.status_code == 502
    assert resp.json() == {"code": 5004, "message": "后端服务连接中断", "data": None}


def test_json_branch_drops_content_length_headers(monkeypatch):
    """JSON 分支不透传上游 content-length/content-encoding（M46 失配）"""

    class _StubResponse:
        status_code = 200
        headers = {
            "content-type": "application/json",
            "content-length": "12345",           # 与重序列化后的实际长度失配
            "content-encoding": "gzip",          # 字节已被 JSONResponse 改写
            "transfer-encoding": "chunked",
            "x-custom": "keep-me",
        }

        def json(self):
            return {"code": 0, "message": "success", "data": None}

    class _StubClient(_BoomClient):
        async def request(self, *args, **kwargs):
            return _StubResponse()

    monkeypatch.setattr(
        main.httpx, "AsyncClient",
        lambda *a, **k: _StubClient(None),
    )
    resp = client.get("/api/v1/visits/x", headers=_headers())
    assert resp.status_code == 200
    lowered = {k.lower(): v for k, v in resp.headers.items()}
    assert "content-length" not in lowered or lowered["content-length"] != "12345"
    assert "content-encoding" not in lowered
    assert lowered.get("x-custom") == "keep-me"


def test_502_json_decode_error_uses_unified_shape(monkeypatch):
    """E3（2026-08-13）：上游 content-type 声明 JSON 但 body 无法解析
    （响应截断/代理层返回 HTML）→ 502 {code:5005,...}，不再冒泡 500 纯文本"""

    class _StubResponse:
        status_code = 200
        headers = {"content-type": "application/json"}

        def json(self):
            raise json.JSONDecodeError("Expecting value", "not-json", 0)

    class _StubClient(_BoomClient):
        async def request(self, *args, **kwargs):
            return _StubResponse()

    monkeypatch.setattr(
        main.httpx, "AsyncClient",
        lambda *a, **k: _StubClient(None),
    )
    resp = client.get("/api/v1/visits/x", headers=_headers())
    assert resp.status_code == 502
    assert resp.json() == {"code": 5005, "message": "上游响应解析失败", "data": None}
