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


# ==================== L-4（2026-08-24 审查修复）：官方分身不变式合并判定 ====================

def test_update_official_invariant_merged_not_payload_only():
    """partial update 只带其中一个键也能查出冲突（此前两键须同时出现才触发）"""
    # 场景 A：已绑代表的普通分身，只传 is_official=true → 拒绝
    try:
        _validate_specialist_fields(
            {"is_official": True}, creating=False,
            existing={"is_official": False, "representative_id": 1},
        )
        raise AssertionError("场景 A 应被拒绝")
    except Exception as e:
        assert "官方" in str(e)

    # 场景 B：官方分身，只传 representative_id → 拒绝
    try:
        _validate_specialist_fields(
            {"representative_id": 5}, creating=False,
            existing={"is_official": True, "representative_id": None},
        )
        raise AssertionError("场景 B 应被拒绝")
    except Exception as e:
        assert "官方" in str(e)

    # 场景 C：官方分身显式置 representative_id=null 清空绑定 → 合法（data 未变，两键均空/独立）
    data = _validate_specialist_fields(
        {"representative_id": None}, creating=False,
        existing={"is_official": True, "representative_id": 5},
    )
    assert data["representative_id"] is None

    # 场景 D：已绑代表分身转官方前先解绑（显式 null + is_official 同批）→ 合法
    data = _validate_specialist_fields(
        {"is_official": True, "representative_id": None}, creating=False,
        existing={"is_official": False, "representative_id": 1},
    )
    assert data["is_official"] is True and data["representative_id"] is None
