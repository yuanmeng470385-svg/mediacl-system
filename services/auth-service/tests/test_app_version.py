"""App 版本检查+更新提示端点测试（2026-09-15 挂账落地）

GET  /api/v1/app/version?platform=rep|doctor  公开（无 token 可达，冷启动登录前就要查）
GET  /api/v1/app/config                       管理端读（admin）
PUT  /api/v1/app/config/{platform}            管理端改（admin）
"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", ".."))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

os.environ.setdefault("JWT_SECRET", "test-secret-not-a-default-value")
os.environ["AUTH_DEV_MODE"] = "true"

from unittest.mock import AsyncMock

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import BigInteger, create_engine
from sqlalchemy.ext.compiler import compiles
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from shared.common.auth import create_token
from shared.common.db_session import get_db
from shared.models.app_version import AppVersion
from shared.models.base import Base
from shared.models.user import User

import app.api.app_version as av_api
from app.main import app


@compiles(BigInteger, "sqlite")
def _compile_bigint_for_sqlite(type_, compiler, **kw):
    return "INTEGER"


engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
TestSession = sessionmaker(bind=engine, autocommit=False, autoflush=False)


def _override_db():
    db = TestSession()
    try:
        yield db
    finally:
        db.close()


client = TestClient(app)


def _token(user_id: int, role: str) -> dict:
    token = create_token(user_id=user_id, username=f"u{user_id}", role=role)
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture(autouse=True)
def fresh_state(monkeypatch):
    tables = [User.__table__, AppVersion.__table__]
    Base.metadata.drop_all(engine, tables=tables)
    Base.metadata.create_all(engine, tables=tables)
    db = TestSession()
    db.add_all([
        User(id=1, username="admin", full_name="管理员", phone="13800000000", role="admin", status="active"),
        User(id=2, username="rep01", full_name="李代表", phone="13800000002", role="rep", status="active"),
    ])
    db.commit()
    db.close()
    monkeypatch.setitem(app.dependency_overrides, get_db, _override_db)


def _seed(platform="rep", latest="1.2.0", minimum="1.0.0", url="/apk/medagent-rep.apk", notes="修了几个问题"):
    db = TestSession()
    db.add(AppVersion(platform=platform, latest_version=latest, min_version=minimum,
                      download_url=url, release_notes=notes))
    db.commit()
    db.close()


# ---------- 公开读：App 端 ----------

def test_version_is_public_without_token():
    """冷启动第一屏是登录页，还没有 token —— 这里必须免认证"""
    _seed()
    resp = client.get("/api/v1/app/version?platform=rep")
    assert resp.status_code == 200
    body = resp.json()
    assert body["code"] == 0
    assert body["data"] == {
        "platform": "rep",
        "platform_label": "代表端",
        "latest_version": "1.2.0",
        "min_version": "1.0.0",
        "download_url": "/apk/medagent-rep.apk",
        "release_notes": "修了几个问题",
        "updated_at": body["data"]["updated_at"],
    }
    assert body["data"]["updated_at"]  # 有值即落库行被读到


def test_version_falls_back_when_table_empty():
    """表里没有该平台行时兜底为「已是最新版」——宁可漏提示，不可误弹强制更新把人挡在门外"""
    resp = client.get("/api/v1/app/version?platform=doctor")
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert data["latest_version"] == "1.0.0"
    assert data["min_version"] == "1.0.0"
    assert data["download_url"] == "/apk/medagent-doctor.apk"
    assert data["release_notes"] is None


def test_version_rejects_unknown_platform():
    resp = client.get("/api/v1/app/version?platform=web")
    assert resp.status_code == 400
    assert resp.json()["code"] == 1000
    assert "rep" in resp.json()["message"]


def test_version_requires_platform_param():
    """漏传 platform → FastAPI 校验失败，统一 handler 渲染成 code 1000"""
    resp = client.get("/api/v1/app/version")
    assert resp.status_code == 422
    assert resp.json()["code"] == 1000


def test_version_hides_other_fields():
    """App 端只该拿到版本四件套，不该看到管理端面板字段（防契约漂移）"""
    _seed()
    data = client.get("/api/v1/app/version?platform=rep").json()["data"]
    assert set(data) == {"platform", "platform_label", "latest_version", "min_version",
                         "download_url", "release_notes", "updated_at"}


# ---------- 管理端读 ----------

def test_config_list_requires_admin():
    for role in ("rep", "doctor", "manager", "compliance", "medical"):
        resp = client.get("/api/v1/app/config", headers=_token(2, role))
        assert resp.status_code == 403, role


def test_config_list_returns_both_platforms(monkeypatch):
    _seed()
    resp = client.get("/api/v1/app/config", headers=_token(1, "admin"))
    assert resp.status_code == 200
    items = resp.json()["data"]
    assert [i["platform"] for i in items] == ["rep", "doctor"]
    assert items[0]["platform_label"] == "代表端"
    assert items[1]["latest_version"] == "1.0.0"  # 无行平台给兜底值，页面不会空白


# ---------- 管理端改 ----------

def _mock_audit(monkeypatch):
    mock = AsyncMock(return_value=1)
    monkeypatch.setattr(av_api, "write_audit_log", mock)
    return mock


def test_update_writes_row_and_audit(monkeypatch):
    audit = _mock_audit(monkeypatch)
    resp = client.put("/api/v1/app/config/rep", headers=_token(1, "admin"), json={
        "latest_version": "1.3.0", "min_version": "1.1.0",
        "download_url": "/apk/medagent-rep.apk", "release_notes": "新增 AI 助手\n修复若干问题",
    })
    assert resp.status_code == 200, resp.text
    data = resp.json()["data"]
    assert (data["latest_version"], data["min_version"]) == ("1.3.0", "1.1.0")
    assert data["release_notes"] == "新增 AI 助手\n修复若干问题"

    # 落库可见（App 端随后读到新版本）
    assert client.get("/api/v1/app/version?platform=rep").json()["data"]["latest_version"] == "1.3.0"

    audit.assert_awaited_once()
    kwargs = audit.await_args.kwargs
    assert kwargs["action"] == "app_version_update"
    assert kwargs["resource_id"] == "rep"
    assert kwargs["after_value"]["latest_version"] == "1.3.0"
    db = TestSession()
    row = db.query(AppVersion).filter(AppVersion.platform == "rep").first()
    db.close()
    assert row.updated_by == 1


def test_update_is_partial(monkeypatch):
    _mock_audit(monkeypatch)
    _seed(latest="1.2.0", minimum="1.0.0", notes="旧说明")
    resp = client.put("/api/v1/app/config/rep", headers=_token(1, "admin"),
                      json={"release_notes": "只改说明"})
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert data["release_notes"] == "只改说明"
    assert data["latest_version"] == "1.2.0"  # 未传的字段保持原值
    assert data["min_version"] == "1.0.0"
    assert data["download_url"] == "/apk/medagent-rep.apk"


def test_update_requires_admin(monkeypatch):
    _mock_audit(monkeypatch)
    resp = client.put("/api/v1/app/config/rep", headers=_token(2, "rep"),
                      json={"latest_version": "9.9.9"})
    assert resp.status_code == 403


def test_update_rejects_bad_payloads(monkeypatch):
    audit = _mock_audit(monkeypatch)
    h = _token(1, "admin")
    cases = [
        ({"latest_version": "1.2"}, "x.y.z"),                        # 版本号格式
        # min > latest（首次配置还得把 download_url 带上，否则先撞「缺下载地址」）
        ({"latest_version": "1.2.0", "min_version": "1.3.0", "download_url": "/apk/rep.apk"}, "不能高于"),
        ({"download_url": "apk/rep.apk"}, "以 / 开头"),               # 相对路径缺 /
        ({"download_url": ""}, "不能为空"),
        ({"release_notes": "x" * 2001}, "2000"),                     # 说明超长
        ({}, "没有需要更新的字段"),
        ({"release_notes": 123}, "必须是文本"),
    ]
    for payload, keyword in cases:
        resp = client.put("/api/v1/app/config/rep", headers=h, json=payload)
        assert resp.status_code == 400, (payload, resp.text)
        assert resp.json()["code"] == 1000
        assert keyword in resp.json()["message"], (payload, resp.json()["message"])
    assert audit.await_count == 0  # 校验失败不留痕、不落库


def test_update_rejects_unknown_platform(monkeypatch):
    _mock_audit(monkeypatch)
    resp = client.put("/api/v1/app/config/windows", headers=_token(1, "admin"),
                      json={"latest_version": "1.0.1"})
    assert resp.status_code == 400
    assert resp.json()["code"] == 1000


def test_update_second_write_keeps_first(monkeypatch):
    """min 与 latest 相等合法（强制更新门槛=最新版）；连续两次改 latest 不回退 min"""
    _mock_audit(monkeypatch)
    h = _token(1, "admin")
    assert client.put("/api/v1/app/config/doctor", headers=h, json={
        "latest_version": "2.0.0", "min_version": "2.0.0", "download_url": "/apk/medagent-doctor.apk",
    }).status_code == 200
    resp = client.put("/api/v1/app/config/doctor", headers=h, json={"latest_version": "2.1.0"})
    assert resp.status_code == 200
    assert resp.json()["data"]["min_version"] == "2.0.0"
