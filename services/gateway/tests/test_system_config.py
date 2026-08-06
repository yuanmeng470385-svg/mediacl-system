"""网关系统配置只读端点（admin 限定）

GET /api/v1/system/config：
    - 未登录 → 401（AuthMiddleware 统一拦截）
    - 非 admin 角色 → 403 {code:3000}
    - admin → 200 {code:0, data:{items:[{key,label,configured}], info:{...}}}
    - 只返回"是否已配置"布尔值，绝不返回密钥值本身
"""
import time

import jwt as pyjwt
import pytest
from fastapi.testclient import TestClient

from app.main import app, SYSTEM_CONFIG_ITEMS
from app.core.auth_middleware import settings as middleware_settings

client = TestClient(app)


def _token(role: str) -> str:
    now = int(time.time())
    payload = {"sub": "2", "username": "u", "role": role, "iat": now, "exp": now + 3600}
    return pyjwt.encode(payload, middleware_settings.JWT_SECRET, algorithm="HS256")


def test_requires_login():
    resp = client.get("/api/v1/system/config")
    assert resp.status_code == 401


def test_rejects_non_admin_roles():
    for role in ("manager", "rep", "medical", "compliance", "finance"):
        resp = client.get("/api/v1/system/config", headers={"Authorization": f"Bearer {_token(role)}"})
        assert resp.status_code == 403, role
        assert resp.json() == {"code": 3000, "message": "无权限：需要角色 admin", "data": None}


def test_admin_gets_config_status(monkeypatch):
    monkeypatch.setenv("DASHSCOPE_API_KEY", "sk-real-secret-value")
    monkeypatch.setenv("ES_URL", "your_es_host")  # 模板占位值 = 未配置
    monkeypatch.delenv("NLS_APPKEY", raising=False)

    resp = client.get("/api/v1/system/config", headers={"Authorization": f"Bearer {_token('admin')}"})
    assert resp.status_code == 200
    body = resp.json()
    assert body["code"] == 0

    items = {it["key"]: it for it in body["data"]["items"]}
    assert items["DASHSCOPE_API_KEY"]["configured"] is True
    assert items["NLS_APPKEY"]["configured"] is False
    assert items["ES_URL"]["configured"] is False  # 占位值视为未配置

    # 形状与覆盖
    keys = {it["key"] for it in body["data"]["items"]}
    assert keys == {env for env, _ in SYSTEM_CONFIG_ITEMS}
    for it in body["data"]["items"]:
        assert set(it) == {"key", "label", "configured"}
        assert it["configured"] in (True, False)

    # 绝不返回密钥值
    assert "sk-real-secret-value" not in resp.text


def test_response_never_contains_secret_values(monkeypatch):
    """响应全文不得出现任何密钥值（如占位符之外的样例值也不应有）"""
    monkeypatch.setenv("ALIYUN_ACCESS_KEY_ID", "LTAI-secret-id-xxx")
    monkeypatch.setenv("ALIYUN_ACCESS_KEY_SECRET", "very-secret-secret-value")
    resp = client.get("/api/v1/system/config", headers={"Authorization": f"Bearer {_token('admin')}"})
    assert resp.status_code == 200
    assert "LTAI-secret-id-xxx" not in resp.text
    assert "very-secret-secret-value" not in resp.text
