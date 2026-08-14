"""M11 回归：含 dot-segment（../、/./、结尾 /..）的路径在网关层被 400 拒绝

根因（2026-08-14 确认）：网关鉴权/路由用未归一化的原始路径 —— starlette
Request.url.path 原样保留 ASGI scope 的 raw path（实测 '/api/v1/auth/login/../../docs'
不被归一化），PUBLIC_PATHS 是前缀匹配；而 httpx 建连时会把 /a/../b 归一化为
/b（实测 httpx 0.28.1: URL('/api/v1/auth/login/../../docs').path == '/api/v1/docs'）。
于是 /api/v1/auth/login/../../docs 可借 '/api/v1/auth/login' 前缀免 JWT，转发时
被归一化成 /api/v1/docs，未认证拉取后端 /docs、/openapi.json、/metrics。

修复：AuthMiddleware.dispatch 在任何 PUBLIC/INTERNAL 匹配之前，用标准库
urlsplit + split("/") 逐段检测 dot-segment（不写正则），命中返回
400 {code:1000}，proxy 不实例化 httpx 客户端、不转发。

测试构造说明（两形态都要覆盖）：
- 字面形态（../）：无法经 httpx 客户端发送 —— httpx 解析 URL 时就归一化，
  到不了 app 已不是原始路径。uvicorn/h11 对 request-target 不做归一化，故
  按 ASGI 协议手工构造 scope（path 含字面 ../）直达 app，精确复现真实攻击请求。
- 编码形态（%2e%2e / %2e）：httpx 不归一化、ASGI 层解码后恢复为 ../，
  用 httpx.AsyncClient + ASGITransport 走完整客户端→传输→app 链路。
- 零转发断言：monkeypatch main.httpx，记录 AsyncClient 的 request(url) 调用；
  dot-segment 用例必须 400 且转发记录为空。
"""
import asyncio
import json
import time
import types

import httpx
import jwt as pyjwt
import pytest

import app.main as main
from app.main import app
from app.core.auth_middleware import settings as middleware_settings

REJECT_BODY = {"code": 1000, "message": "路径包含非法 .. 段", "data": None}


# ---- 转发记录桩（只替换 main 模块的 httpx 属性，测试自身仍用真 httpx 发 ASGI 请求）----

class _StubResponse:
    """模拟 httpx 上游响应（JSON 分支）"""
    status_code = 200
    headers = {"content-type": "application/json"}
    content = b'{"code":0,"message":"success","data":null}'

    def json(self):
        return {"code": 0, "message": "success", "data": None}


class _RecordingClient:
    """模拟 httpx.AsyncClient：记录每次 request 的目标 url，返回固定 200"""

    def __init__(self, log: list):
        self._log = log

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        pass

    async def request(self, method, url, **kwargs):
        self._log.append(str(url))
        return _StubResponse()


def _record_forwarding(monkeypatch) -> list:
    """把 proxy()/health probe 里的 httpx.AsyncClient 换成记录桩，返回转发 url 日志。

    参照 test_proxy_ip.py 的 _capture：只替换 main 模块的 httpx 属性
    （SimpleNamespace），本测试自身仍可用真 httpx.AsyncClient 发起 ASGI 请求。
    """
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
    payload = {"sub": "1", "username": "u", "role": "admin", "iat": now, "exp": now + 3600}
    token = pyjwt.encode(payload, middleware_settings.JWT_SECRET, algorithm="HS256")
    return {"Authorization": f"Bearer {token}"}


def _get_asgi(path: str, headers: dict | None = None) -> httpx.Response:
    """httpx.AsyncClient + ASGITransport 走完整链路（同 test_proxy_ip.py 写法）"""
    async def _run():
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as c:
            return await c.get(path, headers=headers)

    return asyncio.run(_run())


def _send_raw_path(path: str, headers: dict | None = None) -> tuple[int, dict]:
    """以含字面 dot-segment 的原始路径调用网关 ASGI app，返回 (status, body)。

    不经过 httpx 客户端 —— httpx 0.28 解析 URL 时把 /a/../b 归一化为 /b
    （与本漏洞转发侧同一行为），会掩盖攻击路径；uvicorn 收到 request-target
    不做归一化。这里按 ASGI 协议手工构造 scope，path 原样交给 app，
    等价于 uvicorn 收到的请求。
    """
    state = {}

    async def receive():
        return {"type": "http.request", "body": b"", "more_body": False}

    async def send(message):
        if message["type"] == "http.response.start":
            state["status"] = message["status"]
        elif message["type"] == "http.response.body":
            state.setdefault("body", b"")
            state["body"] += message.get("body", b"")

    scope = {
        "type": "http",
        "asgi": {"version": "3.0"},
        "http_version": "1.1",
        "method": "GET",
        "scheme": "http",
        "path": path,
        "raw_path": path.encode("utf-8"),
        "query_string": b"",
        "root_path": "",
        "headers": [
            (k.lower().encode("utf-8"), v.encode("utf-8"))
            for k, v in (headers or {}).items()
        ],
        "client": ("203.0.113.66", 12345),
        "server": ("testserver", 80),
    }
    asyncio.run(app(scope, receive, send))
    return state["status"], json.loads(state.get("body", b"") or b"{}")


# ---- 字面形态：../、/./、结尾 /.. 一律 400 且零转发 ----

@pytest.mark.parametrize("path", [
    "/api/v1/auth/login/../../docs",   # M11 原始 PoC：借 login 前缀免 JWT
    "/api/v1/../docs",
    "/api/v1/a/./b",
    "/api/v1/auth/login/..",           # 结尾 /..
    "/api/v1/auth/login/.",
    "/api/v1/auth/../..",              # 连续 .. 到根
])
def test_literal_dot_segment_400_and_zero_forward(monkeypatch, path):
    log = _record_forwarding(monkeypatch)
    status, body = _send_raw_path(path)
    assert status == 400
    assert body == REJECT_BODY
    assert log == [], "dot-segment 请求必须在网关被拒绝，不得转发到任何后端"


def test_dot_segment_rejected_before_public_path_match(monkeypatch):
    """检查先于 PUBLIC_PATHS 前缀匹配生效：
    原始路径以 /api/v1/auth/login 开头（白名单前缀），未带 token —— 若检查
    在 PUBLIC 匹配之后，此请求会 200 并转发到后端；现在必须 400 零转发。"""
    log = _record_forwarding(monkeypatch)
    status, body = _send_raw_path("/api/v1/auth/login/../../docs")
    assert status == 400
    assert body == REJECT_BODY
    assert log == []


def test_dot_segment_rejected_before_internal_key_check(monkeypatch):
    """检查先于 INTERNAL_PATHS/X-Internal-Key 校验生效：
    带合法 X-Internal-Key 的内部路径缀上 /../ 同样 400 零转发
    （无此检查会通过内部鉴权并转发到后端）。"""
    log = _record_forwarding(monkeypatch)
    status, body = _send_raw_path(
        "/api/v1/audit/log/../docs",
        headers={"X-Internal-Key": "test-internal-key-not-a-default"},
    )
    assert status == 400
    assert body == REJECT_BODY
    assert log == []


def test_dot_segment_rejected_even_with_valid_jwt(monkeypatch):
    """检查与 JWT 无关：带合法 token 的 dot-segment 路径同样 400（零转发）"""
    log = _record_forwarding(monkeypatch)
    status, body = _send_raw_path(
        "/api/v1/visits/../docs", headers=_auth_headers(),
    )
    assert status == 400
    assert body == REJECT_BODY
    assert log == []


# ---- 编码形态（%2e%2e / %2e）：ASGITransport 完整链路 ----

@pytest.mark.parametrize("encoded_path", [
    "/api/v1/auth/login/%2e%2e/docs",
    "/api/v1/%2e%2e/docs",
    "/api/v1/a/%2e/b",
    "/api/v1/auth/login/%2e%2e",      # 编码的结尾 /..
])
def test_encoded_dot_segment_400_and_zero_forward(monkeypatch, encoded_path):
    """percent-encoded dot-segment：httpx 不归一化，ASGI 解码后中间件看到 ../"""
    log = _record_forwarding(monkeypatch)
    resp = _get_asgi(encoded_path)
    assert resp.status_code == 400
    assert resp.json() == REJECT_BODY
    assert log == []


# ---- 正常路径不受影响 ----

def test_public_login_path_unaffected(monkeypatch):
    """正常 public 路径照常放行并转发到后端（中间件不误伤）"""
    log = _record_forwarding(monkeypatch)
    resp = _get_asgi("/api/v1/auth/login")
    assert resp.status_code == 200
    assert any("api/v1/auth/login" in u for u in log), "login 应正常转发到 auth 后端"


def test_health_path_unaffected(monkeypatch):
    """网关自身 /health 不受影响"""
    _record_forwarding(monkeypatch)
    resp = _get_asgi("/health")
    assert resp.status_code == 200
    assert resp.json()["status"] == "ok"


def test_authenticated_path_unaffected(monkeypatch):
    """需 JWT 的路径带合法 token 照常转发（dot-segment 检查不影响正常鉴权链）"""
    log = _record_forwarding(monkeypatch)
    resp = _get_asgi("/api/v1/auth/profile", headers=_auth_headers())
    assert resp.status_code == 200
    assert any("api/v1/auth/profile" in u for u in log)


def test_similar_but_legal_segment_not_rejected(monkeypatch):
    """形似但不等于 .. 的段（'b..'）不误拒：未带 token 应走到 JWT 关卡返回 401，
    而不是被 dot-segment 检查 400 拦下"""
    _record_forwarding(monkeypatch)
    resp = _get_asgi("/api/v1/visits/b..")
    assert resp.status_code == 401
    assert resp.json()["code"] == 2000
