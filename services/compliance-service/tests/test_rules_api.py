"""合规规则 API 字段校验单测（monkeypatch DB，不连真库）

回归背景（审计 M29/M30）：
- rule_type 拼错（keywrod）被静默当语义规则 → 规则永不生效，必须 400；
- action/severity 任意值被 checker 静默接受，必须 400；
- patterns 传字符串被逐字符展开成单字符匹配 → 全量误拦，必须 400；
- 合法创建 → 成功，且 response 字段与模型 to_dict 对齐（rule_code/rule_name/...）。
"""
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", ".."))

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from app.main import app  # noqa: E402
from app.api import rules as rules_api  # noqa: E402
from shared.common.db_session import get_db  # noqa: E402
from shared.common.auth import get_current_user  # noqa: E402


class _FakeRule:
    """与 ComplianceRule 同构的假行（update/列表用）"""

    def __init__(self, id=1, rule_code="R101", rule_name="测试规则", rule_type="keyword",
                 content=None, severity="high", action="reject",
                 description="", enabled=True, version=1):
        self.id = id
        self.rule_code = rule_code
        self.rule_name = rule_name
        self.rule_type = rule_type
        self.content = content if content is not None else {"patterns": ["违禁词A"]}
        self.severity = severity
        self.action = action
        self.description = description
        self.enabled = enabled
        self.version = version

    def to_dict(self):
        return {
            "id": self.id,
            "rule_code": self.rule_code,
            "rule_name": self.rule_name,
            "rule_type": self.rule_type,
            "content": self.content,
            "severity": self.severity,
            "action": self.action,
            "description": self.description,
            "enabled": self.enabled,
            "version": self.version,
        }


class _FakeDb:
    """假 session：add/commit/query 全在内存，不连真库"""

    def __init__(self, rows=None):
        self.rows = list(rows or [])
        self.added = []
        self.committed = False

    def query(self, *a, **kw):
        return self

    def filter(self, *a, **kw):
        return self

    def order_by(self, *a, **kw):
        return self

    def offset(self, *a, **kw):
        return self

    def limit(self, *a, **kw):
        return self

    def first(self):
        return self.rows[0] if self.rows else None

    def all(self):
        return self.rows

    def count(self):
        return len(self.rows)

    def add(self, obj):
        self.added.append(obj)

    def commit(self):
        self.committed = True

    def refresh(self, obj):
        if getattr(obj, "id", None) is None:
            obj.id = 1

    def rollback(self):
        pass

    def close(self):
        pass


async def _fake_current_user():
    return {"id": 1, "username": "tester", "role": "admin"}


async def _fake_audit_log(**kwargs):
    return None


@pytest.fixture
def client(monkeypatch):
    """TestClient：假 DB + 假登录 + 假审计，只测规则校验与响应契约"""
    monkeypatch.setattr(rules_api, "write_audit_log", _fake_audit_log)
    # checker.reload() 走 _load_db_rules（SessionLocal），置空表避免连真库
    monkeypatch.setattr("shared.common.db_session.SessionLocal", lambda: _FakeDb())

    app.dependency_overrides[get_db] = lambda: _FakeDb()
    app.dependency_overrides[get_current_user] = _fake_current_user
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()


def _valid_payload(**overrides):
    payload = {
        "rule_code": "R900",
        "rule_name": "测试新规则",
        "rule_type": "keyword",
        "content": {"patterns": ["包治百病"]},
        "severity": "high",
        "action": "reject",
        "description": "单测规则",
        "enabled": True,
    }
    payload.update(overrides)
    return payload


# ==================== 新增校验 ====================

def test_create_rule_invalid_rule_type_400(client):
    """拼错 rule_type（keywrod）→ 400，不允许静默当语义规则落库"""
    resp = client.post("/api/v1/compliance/rules", json=_valid_payload(rule_type="keywrod"))
    assert resp.status_code == 400
    body = resp.json()
    assert body["code"] == 1000
    assert "rule_type" in body["message"]


def test_create_rule_patterns_string_400(client):
    """patterns 传字符串 → 400，不允许逐字符展开成单字符匹配"""
    resp = client.post(
        "/api/v1/compliance/rules",
        json=_valid_payload(content={"patterns": "包治百病"}),
    )
    assert resp.status_code == 400
    assert "patterns" in resp.json()["message"]


def test_create_rule_patterns_empty_400(client):
    """keyword 规则 patterns 为空列表 → 400"""
    resp = client.post(
        "/api/v1/compliance/rules",
        json=_valid_payload(content={"patterns": []}),
    )
    assert resp.status_code == 400
    assert "patterns" in resp.json()["message"]


def test_create_rule_invalid_action_400(client):
    """action 任意值 → 400（否则永不拦截）"""
    resp = client.post("/api/v1/compliance/rules", json=_valid_payload(action="delete"))
    assert resp.status_code == 400
    assert "action" in resp.json()["message"]


def test_create_rule_invalid_severity_400(client):
    """severity 任意值 → 400（否则风险分级错乱）"""
    resp = client.post("/api/v1/compliance/rules", json=_valid_payload(severity="critical"))
    assert resp.status_code == 400
    assert "severity" in resp.json()["message"]


def test_create_rule_bad_regex_400(client):
    """regex 规则 pattern 编译失败 → 400（否则 checker 静默剔除该条）"""
    resp = client.post(
        "/api/v1/compliance/rules",
        json=_valid_payload(rule_type="regex", content={"patterns": ["([unclosed"]}),
    )
    assert resp.status_code == 400
    assert "编译失败" in resp.json()["message"]


def test_create_rule_missing_patterns_400(client):
    """keyword 规则不带 patterns → 400"""
    resp = client.post("/api/v1/compliance/rules", json=_valid_payload(content={}))
    assert resp.status_code == 400


def test_create_rule_valid_success(client):
    """合法创建 → 成功，返回字段与模型 to_dict 对齐"""
    resp = client.post("/api/v1/compliance/rules", json=_valid_payload())
    assert resp.status_code == 200
    body = resp.json()
    assert body["code"] == 0
    data = body["data"]
    assert data["rule_code"] == "R900"
    assert data["rule_name"] == "测试新规则"
    assert data["rule_type"] == "keyword"
    assert data["content"] == {"patterns": ["包治百病"]}
    assert data["severity"] == "high"
    assert data["action"] == "reject"
    assert data["description"] == "单测规则"
    assert data["enabled"] is True


# ==================== 编辑校验 ====================

def test_update_rule_invalid_fields_400(client, monkeypatch):
    """编辑提交非法 severity / patterns 字符串 → 400 且不提交"""
    fake = _FakeDb(rows=[_FakeRule()])
    monkeypatch.setattr("shared.common.db_session.SessionLocal", lambda: _FakeDb())
    app.dependency_overrides[get_db] = lambda: fake

    resp = client.put(
        "/api/v1/compliance/rules/1",
        json={"severity": "critical", "content": {"patterns": "abc"}},
    )
    assert resp.status_code == 400
    assert not fake.committed  # 校验失败不落库


def test_update_rule_bad_regex_400(client, monkeypatch):
    """编辑把 keyword 改成 regex 但 pattern 编译失败 → 400"""
    fake = _FakeDb(rows=[_FakeRule()])
    monkeypatch.setattr("shared.common.db_session.SessionLocal", lambda: _FakeDb())
    app.dependency_overrides[get_db] = lambda: fake

    resp = client.put(
        "/api/v1/compliance/rules/1",
        json={"rule_type": "regex", "content": {"patterns": ["(bad"]}},
    )
    assert resp.status_code == 400
    assert not fake.committed


def test_update_rule_valid_success(client, monkeypatch):
    """合法编辑 → 200，字段真实更新（不再是"成功"但无效果）"""
    fake = _FakeDb(rows=[_FakeRule()])
    monkeypatch.setattr("shared.common.db_session.SessionLocal", lambda: _FakeDb())
    app.dependency_overrides[get_db] = lambda: fake

    resp = client.put(
        "/api/v1/compliance/rules/1",
        json={
            "severity": "low",
            "action": "warn",
            "content": {"patterns": ["新的词"]},
            "description": "已更新",
            "enabled": False,
        },
    )
    assert resp.status_code == 200
    assert resp.json()["code"] == 0
    rule = fake.rows[0]
    assert rule.severity == "low"
    assert rule.action == "warn"
    assert rule.content == {"patterns": ["新的词"]}
    assert rule.description == "已更新"
    assert rule.enabled is False
    assert rule.version == 2


def test_update_rule_not_found_404(client):
    """编辑不存在的规则 → 404"""
    resp = client.put("/api/v1/compliance/rules/999", json={"severity": "low"})
    assert resp.status_code == 404


# ==================== 列表（仅需登录，无角色限制） ====================

def test_list_rules_login_only(client):
    """GET /rules 仅需登录（移动端合规手册页依赖），不要求 admin 角色"""
    resp = client.get("/api/v1/compliance/rules")
    assert resp.status_code == 200
    body = resp.json()
    assert body["code"] == 0
    assert isinstance(body["data"]["items"], list)
