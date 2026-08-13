"""E4/E5/E7 硬化测试（2026-08-13 低危批）

- E4：404/422 统一 —— 缺档案 BusinessError code 4001（HTTP 422，统一形状）；
  hcp_id 非 int 显式 ParamError（HTTP 400，替代 FastAPI 默认 422）
- E5：create/update/tags/profile-update 请求体非 dict → ParamError（不再 500）
- E7：create/update/tags 增删/batch-import 写审计（before/after 值、action 语义）
"""
import asyncio
import io
import os
import sys
from types import SimpleNamespace

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", ".."))

import pytest  # noqa: E402
from fastapi import UploadFile  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from app.main import app  # noqa: E402
from app.api import hcps as hcps_api  # noqa: E402
from shared.common.db_session import get_db  # noqa: E402
from shared.common.auth import get_current_user  # noqa: E402
from shared.common.internal_auth import require_internal_key  # noqa: E402
from shared.common.response import ParamError  # noqa: E402


# ==================== E4：404/422 统一（API 层 4xx 形状） ====================

class _HcpQuery:
    def __init__(self, hcp=None):
        self._hcp = hcp

    def filter(self, *a, **k):
        return self

    def first(self):
        return self._hcp


class _FakeDb:
    """hcp 查询返回 None（缺档案场景）；User 查询不被本文件用例触发"""

    def query(self, model):
        return _HcpQuery(None)


async def _fake_current_user():
    return {"id": 1, "username": "admin", "role": "admin"}


async def _fake_internal_key():
    return None


@pytest.fixture
def client(monkeypatch):
    app.dependency_overrides[get_db] = lambda: _FakeDb()
    app.dependency_overrides[get_current_user] = _fake_current_user
    app.dependency_overrides[require_internal_key] = _fake_internal_key
    monkeypatch.setattr(hcps_api.hcp_cache, "get", lambda *a, **k: None)  # 恒 miss
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()


def test_get_hcp_non_int_id_returns_400_param_error(client):
    """E4：hcp_id 非数字 → ParamError 400 code 1000（不再是 FastAPI 默认 422 形状）"""
    resp = client.get("/api/v1/hcps/abc")
    assert resp.status_code == 400
    body = resp.json()
    assert body["code"] == 1000
    assert body["message"] == "hcp_id 必须为整数"


def test_get_hcp_missing_returns_422_business_error(client):
    """E4：缺档案 → BusinessError 422 {code:4001, message, data} 统一形状"""
    resp = client.get("/api/v1/hcps/999")
    assert resp.status_code == 422
    assert resp.json() == {"code": 4001, "message": "医生档案不存在", "data": None}


def test_profile_update_non_int_hcp_id_returns_400(client):
    """E4：profile-update 请求体 hcp_id 非 int → ParamError 400（替代默认 422）"""
    resp = client.post("/api/v1/hcps/profile-update", json={"hcp_id": "abc"})
    assert resp.status_code == 400
    assert resp.json()["code"] == 1000


def test_profile_update_missing_hcp_returns_422(client):
    """E4：profile-update 缺档案 → BusinessError 422 code 4001（原裸 404）"""
    resp = client.post(
        "/api/v1/hcps/profile-update",
        json={"hcp_id": 999, "source": "visit"},
    )
    assert resp.status_code == 422
    assert resp.json() == {"code": 4001, "message": "医生档案不存在", "data": None}


# ==================== E5：请求体非 dict → ParamError ====================

_ADMIN = {"id": 1, "username": "admin", "role": "admin"}


def test_create_request_not_dict_raises_param_error():
    with pytest.raises(ParamError):
        asyncio.run(hcps_api.create_hcp(None, _ADMIN, None))


def test_update_request_not_dict_raises_param_error():
    with pytest.raises(ParamError):
        asyncio.run(hcps_api.update_hcp("1", None, _ADMIN, None))


def test_add_tags_request_not_dict_raises_param_error():
    with pytest.raises(ParamError):
        asyncio.run(hcps_api.add_hcp_tags("1", None, _ADMIN, None))


def test_remove_tags_request_not_dict_raises_param_error():
    with pytest.raises(ParamError):
        asyncio.run(hcps_api.remove_hcp_tags("1", None, _ADMIN, None))


def test_profile_update_request_not_dict_raises_param_error():
    with pytest.raises(ParamError):
        asyncio.run(hcps_api.update_hcp_profile_from_visit(None, None, True))


# ==================== E7：写路径审计 ====================

@pytest.fixture
def audit_calls(monkeypatch):
    calls = []

    async def _fake_audit(**kwargs):
        calls.append(kwargs)
        return 1

    monkeypatch.setattr(hcps_api, "write_audit_log", _fake_audit)
    monkeypatch.setattr(hcps_api, "_invalidate_hcp_cache", lambda hcp_id: None)
    return calls


def test_create_writes_audit(audit_calls, monkeypatch):
    created = SimpleNamespace(id=42, to_dict=lambda: {"id": 42, "name": "张伟"})
    monkeypatch.setattr(hcps_api.HcpRepo, "create", staticmethod(lambda db, data: created))
    asyncio.run(hcps_api.create_hcp(
        {"name": "张伟", "hospital": "协和医院"}, _ADMIN, None,
    ))
    assert len(audit_calls) == 1
    call = audit_calls[0]
    assert call["action"] == "hcp_create"
    assert call["user_id"] == 1
    assert call["resource_type"] == "hcp"
    assert call["resource_id"] == "42"
    assert call["after_value"] == {"name": "张伟", "hospital": "协和医院"}


def test_update_writes_audit_before_after(audit_calls, monkeypatch):
    """E7：update 审计 before（改前档案）/after（本次变更字段）"""
    fake = SimpleNamespace(
        id=7, tags=["KOL"],
        to_dict=lambda: {"id": 7, "name": "张伟", "tags": ["KOL"]},
    )
    monkeypatch.setattr(hcps_api, "_get_hcp_or_404", lambda db, hcp_id: fake)
    updated = SimpleNamespace(id=7, to_dict=lambda: {"id": 7, "name": "张伟"})
    monkeypatch.setattr(hcps_api.HcpRepo, "update", staticmethod(lambda db, hcp, data: updated))
    asyncio.run(hcps_api.update_hcp(
        "7", {"hospital": "仁济医院"}, _ADMIN, None,
    ))
    call = audit_calls[0]
    assert call["action"] == "hcp_update"
    assert call["resource_id"] == "7"
    assert call["before_value"] == {"id": 7, "name": "张伟", "tags": ["KOL"]}
    assert call["after_value"] == {"hospital": "仁济医院"}


def test_add_tags_writes_audit(audit_calls, monkeypatch):
    fake = SimpleNamespace(id=7, tags=["KOL"], to_dict=lambda: {"id": 7, "tags": ["KOL"]})
    monkeypatch.setattr(hcps_api, "_get_hcp_or_404", lambda db, hcp_id: fake)
    after_tags = ["KOL", "学术型"]
    after = SimpleNamespace(tags=after_tags, to_dict=lambda: {"id": 7, "tags": after_tags})
    monkeypatch.setattr(hcps_api.HcpRepo, "add_tags", staticmethod(lambda db, hcp, tags: after))
    asyncio.run(hcps_api.add_hcp_tags("7", {"tags": ["学术型"]}, _ADMIN, None))
    call = audit_calls[0]
    assert call["action"] == "hcp_tags_add"
    assert call["before_value"] == {"tags": ["KOL"]}
    assert call["after_value"] == {"tags": ["KOL", "学术型"]}


def test_remove_tags_writes_audit(audit_calls, monkeypatch):
    fake = SimpleNamespace(id=7, tags=["KOL", "学术型"], to_dict=lambda: {"id": 7, "tags": ["KOL", "学术型"]})
    monkeypatch.setattr(hcps_api, "_get_hcp_or_404", lambda db, hcp_id: fake)
    after_tags = ["学术型"]
    after = SimpleNamespace(tags=after_tags, to_dict=lambda: {"id": 7, "tags": after_tags})
    monkeypatch.setattr(hcps_api.HcpRepo, "remove_tags", staticmethod(lambda db, hcp, tags: after))
    asyncio.run(hcps_api.remove_hcp_tags("7", {"tags": ["KOL"]}, _ADMIN, None))
    call = audit_calls[0]
    assert call["action"] == "hcp_tags_remove"
    assert call["before_value"] == {"tags": ["KOL", "学术型"]}
    assert call["after_value"] == {"tags": ["学术型"]}


def test_batch_import_writes_audit(audit_calls, monkeypatch):
    """E7：批量导入审计（after 记汇总数字，明细由 request_id 关联）"""
    monkeypatch.setattr(
        hcps_api, "parse_hcp_excel",
        lambda f: [{"name": "张伟"}, {"name": "李娜"}],
    )
    monkeypatch.setattr(hcps_api.HcpRepo, "batch_create", staticmethod(lambda db, rows: (2, [])))
    file = UploadFile(filename="hcps.xlsx", file=io.BytesIO(b"fake"))
    asyncio.run(hcps_api.batch_import_hcps(file, _ADMIN, None))
    assert len(audit_calls) == 1
    call = audit_calls[0]
    assert call["action"] == "hcp_batch_import"
    assert call["user_id"] == 1
    assert call["after_value"] == {"total": 2, "imported": 2, "failed": 0}
