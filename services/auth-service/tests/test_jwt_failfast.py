"""H1 回归（2026-08-11）：JWT_SECRET fail-fast 守卫

背景：shared 层原实现 `os.getenv("JWT_SECRET", "dev-secret-change-me")` 静默默认回退
——任何服务漏配 JWT_SECRET 时都用公开默认密钥签验，攻击者可伪造任意角色 token
直连服务。修复：默认值为空，_jwt_secret() 校验弱值/空值直接 RuntimeError，
服务在启动守卫（各服务 main.py validate_jwt_secret）处拒绝启动。

本文件直接测 shared 层函数（不 import app.main，避开服务启动守卫本身）：
- validate_jwt_secret：空值/已知弱值抛 RuntimeError，强值放行
- 无 JWT_SECRET 环境：create_token / verify_token 抛 RuntimeError（不再回退）
- 强密钥：签发/验签 roundtrip 正常
"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", ".."))

import pytest

from shared.common.auth import (
    WEAK_JWT_SECRETS,
    validate_jwt_secret,
    create_token,
    verify_token,
)

STRONG = "s3cret-key-that-is-long-and-random-20260811"


def test_weak_values_raise_runtime_error():
    """空值与已知弱值一律拒绝（含 gateway/auth 已有守卫的同一名单）"""
    for weak in WEAK_JWT_SECRETS:
        with pytest.raises(RuntimeError, match="JWT_SECRET"):
            validate_jwt_secret(weak)


def test_strong_secret_passes():
    assert validate_jwt_secret(STRONG) == STRONG


def test_missing_env_create_token_raises(monkeypatch):
    """无 JWT_SECRET 环境：create_token 抛 RuntimeError（原实现回退公开默认密钥）"""
    monkeypatch.delenv("JWT_SECRET", raising=False)
    with pytest.raises(RuntimeError, match="JWT_SECRET"):
        create_token(user_id=1, username="rep1", role="rep")


def test_missing_env_verify_token_raises(monkeypatch):
    """无 JWT_SECRET 环境：verify_token 抛 RuntimeError（不可验签，无回退）"""
    monkeypatch.delenv("JWT_SECRET", raising=False)
    with pytest.raises(RuntimeError, match="JWT_SECRET"):
        verify_token("eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiIxIn0.fake")


def test_weak_env_create_token_raises(monkeypatch):
    """JWT_SECRET 配成默认值：签发拒绝（部署时漏改 .env 立即暴露）"""
    monkeypatch.setenv("JWT_SECRET", "dev-secret-change-me")
    with pytest.raises(RuntimeError, match="JWT_SECRET"):
        create_token(user_id=1, username="rep1", role="rep")


def test_strong_secret_roundtrip(monkeypatch):
    """强密钥：签发 → 验签 roundtrip（签名与 sub/role 完整）"""
    monkeypatch.setenv("JWT_SECRET", STRONG)
    token = create_token(user_id=7, username="rep7", role="rep")
    payload = verify_token(token)
    assert payload["sub"] == "7"
    assert payload["role"] == "rep"
    assert payload["username"] == "rep7"
