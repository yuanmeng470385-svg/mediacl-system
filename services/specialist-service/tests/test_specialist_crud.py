"""专员 CRUD 权限与字段校验（monkeypatch DB，测校验逻辑）"""
import pytest

from app.api.specialists import _validate_specialist_fields, _normalize_status
from shared.common.response import ParamError


def test_validate_create_requires_name():
    with pytest.raises(ParamError):
        _validate_specialist_fields({"product_id": 1}, creating=True)


def test_validate_update_rejects_unknown_fields():
    with pytest.raises(ParamError):
        _validate_specialist_fields({"name": "新", "hack": True}, creating=False)


def test_normalize_status():
    assert _normalize_status("active") == "active"
    assert _normalize_status("DRAFT") == "draft"
    with pytest.raises(ParamError):
        _normalize_status("banned")


def test_validate_create_accepts_whitelist_fields():
    _validate_specialist_fields({"name": "A", "product_id": 1, "persona": {"style": "专业"}}, creating=True)


def test_validate_rejects_non_whitelist_on_create():
    with pytest.raises(ParamError):
        _validate_specialist_fields({"name": "A", "product_id": 1, "hack": True}, creating=True)
