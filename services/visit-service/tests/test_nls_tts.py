"""NLS TTS token 端点测试"""
import asyncio
import sys
import os
from unittest.mock import AsyncMock

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", ".."))

import pytest

from shared.common.response import BusinessError
import app.api.nls as nls_mod


def _call(user=None):
    user = user or {"id": 1, "role": "rep"}
    # 端点返回 success() 标准信封，测试断言解包到 data
    return asyncio.run(nls_mod.get_tts_token(user))["data"]


def test_tts_token_missing_appkey_raises(monkeypatch):
    """未配 NLS_APPKEY → BusinessError（移动端据此禁用朗读按钮）"""
    monkeypatch.delenv("NLS_APPKEY", raising=False)
    with pytest.raises(BusinessError) as ei:
        _call()
    assert "NLS_APPKEY" in str(ei.value)


def test_tts_token_ok(monkeypatch):
    """已配 NLS_APPKEY → 返回 {token, appkey, expires_at}"""
    monkeypatch.setenv("NLS_APPKEY", "appkey-123")
    monkeypatch.setattr(nls_mod, "get_nls_token", AsyncMock(return_value="tok-abc"))
    monkeypatch.setattr(nls_mod, "nls_token_expire_at", lambda: 1234567890.0)
    data = _call()
    assert data["token"] == "tok-abc"
    assert data["appkey"] == "appkey-123"
    assert data["expires_at"] == 1234567890.0
