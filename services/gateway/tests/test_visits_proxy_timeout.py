"""visits AI 路由（pre-visit / end / follow-up）的网关代理超时 carve-out

拜访结束/跟进是同步 AI 生成链：end_visit 直调 qwen（60s 读超时 × 重试 1 次）+
三次合规检查（10s ×3）+ 审计写入，最坏 ~150s。网关默认 30s 会先于后端掐断 ——
客户端看到 504/超时但后端 handler 继续跑完并持有 FOR UPDATE 行锁，用户重试
end 只能排在行锁后再超时一次，表现为"结束拜访卡死几分钟"。照 F3
（qualifications）/ B9（doctors）先例，仅这两个 AI 重路由放宽到 120s；
visits 其余路由（列表/详情/转写/取消）维持 30s。

超时链修复补遗（2026-08-28）：pre-visit 是同款问题 —— prepare_visit 走专员链路
（specialist_client 60s 超时）生成推荐，网关 30s 先掐断，客户端拿到 504 但
后端继续跑完，重试再等一轮。pre-visit 一并放宽到 120s。

三期 P（2026-08-31）：skill-packages/extract-draft（LLM 同步生成风格草稿）与
practices/{id}/complete（收尾 LLM 深度评分）同款放宽到 120s —— 独立精确匹配，
不并入 knowledge/qualifications/doctors 前缀分支（否则 release / turn 等
非 AI 路由也被误伤到 120s）。
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
    def __init__(self):
        pass

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        pass

    async def request(self, method, url, **kwargs):
        return _StubResponse()


def _record_timeouts(monkeypatch) -> list:
    timeouts: list = []

    def _fake_async_client(*a, **k):
        timeouts.append(k.get("timeout"))
        return _RecordingClient()

    fake_httpx = types.SimpleNamespace(
        AsyncClient=_fake_async_client,
        ConnectError=httpx.ConnectError,
        TimeoutException=httpx.TimeoutException,
        HTTPError=httpx.HTTPError,
    )
    monkeypatch.setattr(main, "httpx", fake_httpx)
    return timeouts


def _auth_headers(sub: str = "1") -> dict:
    now = int(time.time())
    payload = {"sub": sub, "username": "u", "role": "rep", "iat": now, "exp": now + 3600}
    token = pyjwt.encode(payload, middleware_settings.JWT_SECRET, algorithm="HS256")
    return {"Authorization": f"Bearer {token}"}


def test_visits_ai_routes_timeout_carve_out(monkeypatch):
    """pre-visit / end / follow-up（同步 AI 生成链）走 120s；visits 其他路由维持 30s"""
    timeouts = _record_timeouts(monkeypatch)

    async def _run():
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as c:
            await c.post("/api/v1/visits/pre-visit", headers=_auth_headers())
            await c.post("/api/v1/visits/123/end", headers=_auth_headers())
            await c.post("/api/v1/visits/123/follow-up", headers=_auth_headers())
            await c.get("/api/v1/visits", headers=_auth_headers())

    asyncio.run(_run())
    assert timeouts == [120.0, 120.0, 120.0, 30.0]


def test_skill_practices_ai_routes_timeout_carve_out(monkeypatch):
    """extract-draft / practices complete / 异议话术 AI 草稿两路由（同步 LLM 慢链）
    走 120s，其余维持 30s

    红线：精确匹配 —— release 与 practices turn 等非 LLM 轻路由不得被顺带放宽；
    objection-scripts 的 create/review 同理维持 30s（2026-09-10 异议话术批补入断言）。
    sub=3：独立限流窗口，避免与本文件及其他用例的 u:1 请求在 60/min 内存
    窗口里累计顶限。
    """
    timeouts = _record_timeouts(monkeypatch)

    async def _run():
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as c:
            await c.post("/api/v1/skill-packages/extract-draft", headers=_auth_headers("3"))
            await c.post("/api/v1/skill-packages/release", headers=_auth_headers("3"))
            await c.post("/api/v1/practices/1/complete", headers=_auth_headers("3"))
            await c.post("/api/v1/practices/1/turn", headers=_auth_headers("3"))
            await c.post("/api/v1/practices/objection-scripts/ai-generate", headers=_auth_headers("3"))
            await c.post("/api/v1/practices/objection-scripts", headers=_auth_headers("3"))
            await c.post("/api/v1/practices/objection-scripts/extract-draft", headers=_auth_headers("3"))

    asyncio.run(_run())
    assert timeouts == [120.0, 30.0, 120.0, 30.0, 120.0, 30.0, 120.0]
