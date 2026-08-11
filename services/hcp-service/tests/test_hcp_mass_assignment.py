"""hcp create/update 白名单（防 mass assignment）API 契约测试

回归背景：旧实现把请求 dict 原样传入 HcpRepo.create（Hcp(**data)）/update
（setattr 循环）—— 客户端可传 id/created_at/updated_at 覆盖系统字段，
任意未知 key 也会被写进模型。现在 API 层白名单外字段一律 400（与
specialist-service 契约一致），repo 层再做兜底过滤。
"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", ".."))

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from app.main import app  # noqa: E402
from app.models.hcp import Hcp  # noqa: E402
from shared.common.db_session import get_db  # noqa: E402
from shared.common.auth import get_current_user  # noqa: E402


class _FakeUser:
    id = 1
    status = "active"
    role = "admin"


class _UserQuery:
    """require_roles 库查（S6 修复）：主键查 User 返回 active admin 用户"""

    def filter(self, *a, **k):
        return self

    def first(self):
        return _FakeUser()


class _HcpQuery:
    def __init__(self, hcp=None):
        self._hcp = hcp

    def filter(self, *a, **k):
        return self

    def first(self):
        return self._hcp


class FakeDb:
    def __init__(self, existing_hcp=None):
        self.existing_hcp = existing_hcp or Hcp(id=1, name="张伟", hospital="协和医院")
        self.added = []

    def query(self, model):
        name = getattr(model, "__name__", "")
        if name == "User":
            return _UserQuery()
        return _HcpQuery(self.existing_hcp)

    def add(self, obj):
        self.added.append(obj)

    def commit(self):
        pass

    def refresh(self, obj):
        pass


async def _fake_current_user():
    return {"id": 1, "username": "tester", "role": "admin"}


@pytest.fixture
def client():
    db = FakeDb()

    def _override_db():
        yield db

    app.dependency_overrides[get_db] = _override_db
    app.dependency_overrides[get_current_user] = _fake_current_user
    with TestClient(app) as c:
        yield c, db
    app.dependency_overrides.clear()


# ==================== create ====================

def test_create_rejects_system_fields(client):
    """id/created_at/updated_at 等系统字段 → 400，不落库"""
    c, db = client
    resp = c.post("/api/v1/hcps", json={
        "name": "张伟", "id": 999, "created_at": "2099-01-01T00:00:00",
    })
    assert resp.status_code == 400
    msg = resp.json()["message"]
    assert "id" in msg and "created_at" in msg
    assert db.added == []


def test_create_rejects_unknown_fields(client):
    """未知 key → 400（否则被静默写进模型）"""
    c, db = client
    resp = c.post("/api/v1/hcps", json={"name": "张伟", "hack": "x"})
    assert resp.status_code == 400
    assert "hack" in resp.json()["message"]
    assert db.added == []


def test_create_valid_whitelist_only(client):
    """白名单字段正常创建"""
    c, db = client
    resp = c.post("/api/v1/hcps", json={
        "name": "张伟", "hospital": "协和医院", "title": "主任医师", "tags": ["KOL"],
    })
    assert resp.status_code == 200
    assert resp.json()["code"] == 0
    created = db.added[0]
    assert created.name == "张伟"
    assert created.tags == ["KOL"]


# ==================== update ====================

def test_update_rejects_system_fields(client):
    c, _ = client
    resp = c.put("/api/v1/hcps/1", json={"hospital": "仁济医院", "id": 99})
    assert resp.status_code == 400
    assert "id" in resp.json()["message"]


def test_update_rejects_unknown_fields(client):
    c, _ = client
    resp = c.put("/api/v1/hcps/1", json={"hospital": "仁济医院", "hack": "x"})
    assert resp.status_code == 400
    assert "hack" in resp.json()["message"]


def test_update_valid_whitelist_only(client):
    c, _ = client
    resp = c.put("/api/v1/hcps/1", json={"hospital": "仁济医院", "title": "副主任医师"})
    assert resp.status_code == 200
    assert resp.json()["data"]["hospital"] == "仁济医院"
    assert resp.json()["data"]["title"] == "副主任医师"
