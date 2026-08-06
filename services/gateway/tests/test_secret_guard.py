"""
网关 JWT_SECRET 密钥守卫测试（C21 修复）

守卫要求：JWT_SECRET 未配置 / 等于代码旧默认值 "dev-secret-change-me" /
等于 .env.example 模板占位值 "change_me_to_a_random_secret_string" → 导入
app.config（即网关启动路径）即抛 RuntimeError。

此前网关是静默回退（os.getenv("JWT_SECRET", "dev-secret-change-me")）——
漏配时任何人可用公开默认密钥伪造任意角色 token 通过网关。现在必须 fail-fast。

测试方式：importlib.reload 重载 app.config 模拟"重新启动"；重载时 patch 掉
dotenv.load_dotenv，避免根目录 .env 回填密钥，让 os.environ 完全由测试控制。
"""
import importlib

import pytest

import dotenv

import app.config


def _reload_config(monkeypatch, jwt_secret=None, set_secret=True):
    """以给定环境重载 app.config。jwt_secret=None 且 set_secret=False 表示未配置。"""
    monkeypatch.setattr(dotenv, "load_dotenv", lambda *a, **k: None)
    if set_secret:
        monkeypatch.setenv("JWT_SECRET", jwt_secret)
    else:
        monkeypatch.delenv("JWT_SECRET", raising=False)
    return importlib.reload(app.config)


def test_rejects_unset_jwt_secret(monkeypatch):
    """JWT_SECRET 未配置 → RuntimeError（不能再静默回退到公开默认值）"""
    with pytest.raises(RuntimeError, match="JWT_SECRET"):
        _reload_config(monkeypatch, set_secret=False)


def test_rejects_old_code_default(monkeypatch):
    """JWT_SECRET 等于旧默认值 dev-secret-change-me → RuntimeError"""
    with pytest.raises(RuntimeError, match="JWT_SECRET"):
        _reload_config(monkeypatch, jwt_secret="dev-secret-change-me")


def test_rejects_template_placeholder(monkeypatch):
    """JWT_SECRET 等于 .env.example 模板占位值 → RuntimeError"""
    with pytest.raises(RuntimeError, match="JWT_SECRET"):
        _reload_config(monkeypatch, jwt_secret="change_me_to_a_random_secret_string")


def test_accepts_strong_secret(monkeypatch):
    """JWT_SECRET 配置强随机值 → 正常加载，且无默认回退残留"""
    mod = _reload_config(monkeypatch, jwt_secret="strong-test-secret-123")
    assert mod.settings.JWT_SECRET == "strong-test-secret-123"
    # validate_jwt_secret 对强值原样放行
    assert mod.validate_jwt_secret("strong-test-secret-123") == "strong-test-secret-123"


def test_validate_jwt_secret_rejects_each_weak_value():
    """validate_jwt_secret 单独校验：三个弱值全被拒绝"""
    for weak in ("", "dev-secret-change-me", "change_me_to_a_random_secret_string"):
        with pytest.raises(RuntimeError, match="JWT_SECRET"):
            app.config.validate_jwt_secret(weak)


def test_middleware_decodes_with_settings_secret():
    """中间件校验密钥来自 settings（唯一读取点，C21 收敛）。

    用中间件实际绑定那份 settings 的 JWT_SECRET 签的 token 能通过认证走到路由
    （未匹配路由 → 404）；用别的密钥签的 token 在中间件被拒（401）。
    如果中间件偷偷回退到 os.getenv 的公开默认值，这条测试会失败。
    """
    import time

    import jwt as pyjwt
    from fastapi.testclient import TestClient

    from app.main import app
    # 中间件在 import 时绑定了 settings —— 用同一个对象签 token，与实现保持一致
    from app.core.auth_middleware import settings as middleware_settings

    client = TestClient(app)
    now = int(time.time())
    payload = {"sub": "1", "username": "u", "role": "admin", "iat": now, "exp": now + 3600}

    good = pyjwt.encode(payload, middleware_settings.JWT_SECRET, algorithm="HS256")
    r = client.get("/api/v1/definitely-not-a-route", headers={"Authorization": f"Bearer {good}"})
    # 走到 404 说明通过了中间件认证（未匹配路由由 proxy 兜底返回 404，不会连后端）
    assert r.status_code == 404

    bad = pyjwt.encode(payload, "some-other-public-secret", algorithm="HS256")
    r2 = client.get("/api/v1/definitely-not-a-route", headers={"Authorization": f"Bearer {bad}"})
    assert r2.status_code == 401
    assert r2.json()["code"] == 2002
