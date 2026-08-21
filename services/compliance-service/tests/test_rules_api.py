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


class _FakeUser:
    """require_roles 库查（S6 修复）：主键查 User 返回的 active admin 用户（本文件 token 恒为 admin）"""

    def __init__(self):
        self.id = 1
        self.status = "active"
        self.role = "admin"


class _UserQuery:
    """users 表查询 stub：first() 返回 active admin 用户"""

    def filter(self, *a, **kw):
        return self

    def first(self):
        return _FakeUser()


class _FakeDb:
    """假 session：add/commit/query 全在内存，不连真库"""

    def __init__(self, rows=None):
        self.rows = list(rows or [])
        self.added = []
        self.committed = False

    def query(self, *a, **kw):
        # require_roles 库查（S6 修复）：User 走独立 stub；规则表查询仍走自身链式
        model = a[0] if a else None
        if model is not None and getattr(model, "__name__", "") == "User":
            return _UserQuery()
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


def test_update_rule_content_non_dict_400(client, monkeypatch):
    """D2：semantic 规则 content 传字符串 → 400 且不落库（否则字符串 content 落库后
    checker 60s TTL 重载时 content.get() 崩溃，单行坏数据毒化全部 DB 规则加载）"""
    fake = _FakeDb(rows=[_FakeRule(rule_code="R201", rule_type="semantic",
                                   content={"description": "语义规则"})])
    monkeypatch.setattr("shared.common.db_session.SessionLocal", lambda: _FakeDb())
    app.dependency_overrides[get_db] = lambda: fake

    resp = client.put("/api/v1/compliance/rules/1", json={"content": "非对象字符串"})
    assert resp.status_code == 400
    assert "content" in resp.json()["message"]
    assert not fake.committed  # 校验失败不落库


def test_update_rule_not_found_404(client):
    """编辑不存在的规则 → 404"""
    resp = client.put("/api/v1/compliance/rules/999", json={"severity": "low"})
    assert resp.status_code == 404


# ==================== /check 快速模式（流式逐帧门禁） ====================

def test_check_fast_flag_passthrough(client, monkeypatch):
    """/check 透传 fast 标志：fast=True → checker 收 fast=True；不传 → False"""
    monkeypatch.setenv("INTERNAL_API_KEY", "test-internal-key")
    monkeypatch.setattr("shared.common.internal_auth._INTERNAL_KEY", None)
    calls = []

    class _FakeChecker:
        def check(self, content, context=None, fast=False):
            calls.append((content, fast))
            return {"blocked": False, "violations": [], "risk_level": "none", "checked_rules": []}

    import app.api.rules as rules_api
    monkeypatch.setattr(rules_api, "checker", _FakeChecker())
    headers = {"X-Internal-Key": "test-internal-key"}

    resp = client.post("/api/v1/compliance/check", headers=headers,
                       json={"content": "测试", "context": {"type": "ai_output"}, "fast": True})
    assert resp.status_code == 200
    assert resp.json()["code"] == 0
    assert calls[0][1] is True

    client.post("/api/v1/compliance/check", headers=headers, json={"content": "测试"})
    assert calls[1][1] is False  # 默认全量检查


# ==================== C1/C6: /check 参数健壮性 ====================

def _check_headers(monkeypatch):
    """/check 需要 X-Internal-Key（require_internal_key）"""
    monkeypatch.setenv("INTERNAL_API_KEY", "test-internal-key")
    monkeypatch.setattr("shared.common.internal_auth._INTERNAL_KEY", None)
    return {"X-Internal-Key": "test-internal-key"}


def test_check_content_non_str_400(client, monkeypatch):
    """C1：content 非字符串（int/list/dict）→ 400，而非 checker 里
    content.strip() 的 AttributeError 500"""
    headers = _check_headers(monkeypatch)
    for bad in (123, ["a"], {"text": "x"}):
        resp = client.post("/api/v1/compliance/check", headers=headers, json={"content": bad})
        assert resp.status_code == 400
        assert "content" in resp.json()["message"]


def test_check_context_non_dict_400(client, monkeypatch):
    """C1：context 非对象（字符串/数组）→ 400，而非违规落库时
    context.get() 崩溃 + JSONB 写入非对象"""
    headers = _check_headers(monkeypatch)
    for bad in ("user_input", [1, 2]):
        resp = client.post("/api/v1/compliance/check", headers=headers,
                           json={"content": "测试", "context": bad})
        assert resp.status_code == 400
        assert "context" in resp.json()["message"]


def test_check_fast_string_false_is_false(client, monkeypatch):
    """C1：fast="false" 必须解析为 False —— bool("false") == True 会让调用方
    意外跳过 LLM 语义层（合规硬伤）；"true" 同理解析为 True"""
    headers = _check_headers(monkeypatch)
    calls = []

    class _FakeChecker:
        def check(self, content, context=None, fast=False):
            calls.append(fast)
            return {"blocked": False, "violations": [], "risk_level": "none", "checked_rules": []}

    import app.api.rules as rules_api
    monkeypatch.setattr(rules_api, "checker", _FakeChecker())

    client.post("/api/v1/compliance/check", headers=headers, json={"content": "测试", "fast": "false"})
    assert calls == [False]
    client.post("/api/v1/compliance/check", headers=headers, json={"content": "测试", "fast": "true"})
    assert calls == [False, True]


def test_check_fast_invalid_400(client, monkeypatch):
    """C1：fast 取值非法（"maybe"/2）→ 400 显式提示"""
    headers = _check_headers(monkeypatch)
    for bad in ("maybe", 2):
        resp = client.post("/api/v1/compliance/check", headers=headers,
                           json={"content": "测试", "fast": bad})
        assert resp.status_code == 400
        assert "fast" in resp.json()["message"]


def test_check_content_too_long_400(client, monkeypatch):
    """C6：content 超过 10000 字符 → 400（防超大文本放大 ReDoS 与 LLM 成本）"""
    headers = _check_headers(monkeypatch)
    resp = client.post("/api/v1/compliance/check", headers=headers,
                       json={"content": "x" * 10001})
    assert resp.status_code == 400
    assert "10000" in resp.json()["message"]


# ==================== 列表（仅需登录，无角色限制） ====================

def test_list_rules_login_only(client):
    """GET /rules 仅需登录（移动端合规手册页依赖），不要求 admin 角色"""
    resp = client.get("/api/v1/compliance/rules")
    assert resp.status_code == 200
    body = resp.json()
    assert body["code"] == 0
    assert isinstance(body["data"]["items"], list)


def test_create_rule_duplicate_rule_code_4001(monkeypatch):
    """重复 rule_code → 422 code 4001（修复前：假库无唯一约束 → 直接 200；
    真实 PG 唯一索引 → IntegrityError → 500）。修法对齐 auth users.py 撞号 A2。"""
    async def _fake_audit_log(**kwargs):
        return None

    monkeypatch.setattr(rules_api, "write_audit_log", _fake_audit_log)
    monkeypatch.setattr("shared.common.db_session.SessionLocal", lambda: _FakeDb())
    app.dependency_overrides[get_db] = lambda: _FakeDb(rows=[_FakeRule(rule_code="R900")])
    app.dependency_overrides[get_current_user] = _fake_current_user
    try:
        with TestClient(app) as c:
            resp = c.post("/api/v1/compliance/rules", json={
                "rule_code": "R900", "rule_name": "重复规则", "rule_type": "keyword",
                "content": {"patterns": ["违禁词"]}, "severity": "high",
                "action": "reject", "description": "", "enabled": True,
            })
        assert resp.status_code == 422, resp.text
        assert resp.json()["code"] == 4001
    finally:
        app.dependency_overrides.clear()
