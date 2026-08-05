"""实时转写 fail-closed：未配置 NLS_APPKEY 时拒绝降级 Mock，不落库假文本"""
import os
import pytest

from app.api.asr_ws import _get_asr_client


def test_no_appkey_raises(monkeypatch):
    monkeypatch.delenv("NLS_APPKEY", raising=False)
    monkeypatch.delenv("NLS_MOCK", raising=False)
    with pytest.raises(RuntimeError):
        _get_asr_client()


def test_explicit_mock_allowed(monkeypatch):
    monkeypatch.delenv("NLS_APPKEY", raising=False)
    monkeypatch.setenv("NLS_MOCK", "1")
    client, is_mock = _get_asr_client()
    assert is_mock is True
    assert client.__class__.__name__ == "MockRealtimeAsrClient"


def test_real_appkey_returns_real_client(monkeypatch):
    monkeypatch.setenv("NLS_APPKEY", "test-appkey")
    monkeypatch.delenv("NLS_MOCK", raising=False)
    client, is_mock = _get_asr_client()
    assert is_mock is False
    assert client.__class__.__name__ == "RealtimeAsrClient"
