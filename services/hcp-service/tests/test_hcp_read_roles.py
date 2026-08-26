"""M-3（2026-08-24 审查修复）：医生档案读取角色收敛

背景：list/detail/profile 含手机号、邮箱等医生 PII，此前任意登录角色
（doctor/finance 等）都能拉全量档案。收敛到 HCP_READ_ROLES =
(admin, manager, rep)——web 医生管理 + rep 拜访是实际使用方，医生端
app 不调 /hcps。
"""
import os
import sys
from types import SimpleNamespace

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", ".."))

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from app.main import app  # noqa: E402
from app.api import hcps as hcps_api  # noqa: E402
from shared.common.db_session import get_db  # noqa: E402
from shared.common.auth import get_current_user  # noqa: E402


class _Query:
    def __init__(self, obj=None):
        self._obj = obj

    def filter(self, *a, **k):
        return self

    def first(self):
        return self._obj

    def all(self):
        return []

    def count(self):
        return 0

    def order_by(self, *a, **k):
        return self

    def offset(self, *a, **k):
        return self

    def limit(self, *a, **k):
        return self


class _FakeDb:
    """User 查询供 require_roles 角色复核（以库为准）；hcp 查询返回 None"""

    def __init__(self, user):
        self._user = user

    def query(self, model):
        if model.__name__ == "User":
            return _Query(self._user)
        return _Query(None)


@pytest.fixture
def make_client(monkeypatch):
    def _make(role: str) -> TestClient:
        db_user = SimpleNamespace(id=1, role=role, status="active")

        async def _fake_current_user():
            return {"id": 1, "username": "tester", "role": role}

        app.dependency_overrides[get_db] = lambda: _FakeDb(db_user)
        app.dependency_overrides[get_current_user] = _fake_current_user
        monkeypatch.setattr(hcps_api.hcp_cache, "get", lambda *a, **k: None)  # 恒 miss
        return TestClient(app)

    yield _make
    app.dependency_overrides.clear()


@pytest.mark.parametrize("role", ["doctor", "finance"])
def test_read_denied_for_non_hcp_roles(make_client, role):
    """doctor/finance 读档案列表/详情/画像 → 403 code 3000"""
    c = make_client(role)
    assert c.get("/api/v1/hcps").status_code == 403
    assert c.get("/api/v1/hcps").json()["code"] == 3000
    assert c.get("/api/v1/hcps/1").status_code == 403
    assert c.get("/api/v1/hcps/1/profile").status_code == 403


@pytest.mark.parametrize("role", hcps_api.HCP_READ_ROLES)
def test_read_allowed_for_hcp_read_roles(make_client, role):
    """admin/manager/rep 列表 200；详情/画像过角色门后走正常业务流（档案缺 → 422 code 4001）"""
    c = make_client(role)
    resp = c.get("/api/v1/hcps")
    assert resp.status_code == 200
    assert resp.json()["code"] == 0
    detail = c.get("/api/v1/hcps/999")
    assert detail.status_code == 404
    assert detail.json()["code"] == 4000  # 角色门已过，是"档案不存在"而非 403
