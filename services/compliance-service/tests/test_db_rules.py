"""合规规则 DB 加载单测（monkeypatch SessionLocal，不连真库）"""
import time
from app.core.checker import ComplianceChecker


class _FakeRow:
    def __init__(self, code, name, rtype, content, severity="high", action="reject", enabled=True):
        self.rule_code = code
        self.rule_name = name
        self.rule_type = rtype
        self.content = content
        self.severity = severity
        self.action = action
        self.enabled = enabled


class _FakeDb:
    def __init__(self, rows):
        self._rows = rows

    def query(self, *a, **kw):
        return self

    def filter(self, *a, **kw):
        return self

    def all(self):
        # 2026-08-13 D1 后 checker 不在 SQL 层过滤 enabled（禁用行也要加载，
        # 最终过滤在 checker._reload_rules 里做），fake 与修复后口径对齐
        return list(self._rows)

    def close(self):
        pass


def test_db_rules_override_yaml(monkeypatch):
    # DB 提供 R001（关键词，DB 版 patterns 覆盖 YAML）
    rows = [_FakeRow("R001", "禁止承诺疗效(DB版)", "keyword", {"patterns": ["包治百病"]})]
    monkeypatch.setattr(
        "shared.common.db_session.SessionLocal",
        lambda: _FakeDb(rows),
    )
    checker = ComplianceChecker()
    r001 = next(r for r in checker.rules if r["id"] == "R001")
    assert r001["patterns"] == ["包治百病"]  # DB 覆盖 YAML
    assert any(r["id"] == "R005" for r in checker.rules)  # YAML 补位仍在


def test_db_unavailable_falls_back_to_yaml(monkeypatch):
    def boom():
        raise RuntimeError("db down")
    monkeypatch.setattr("shared.common.db_session.SessionLocal", boom)
    checker = ComplianceChecker()
    assert len(checker.rules) >= 4  # YAML 兜底仍加载


def test_bad_regex_rule_isolated(monkeypatch):
    # 一条坏正则不拖垮整个引擎
    rows = [_FakeRow("R999", "坏正则", "regex", {"patterns": ["([unclosed"]})]
    monkeypatch.setattr("shared.common.db_session.SessionLocal", lambda: _FakeDb(rows))
    checker = ComplianceChecker()
    bad = [r for r in checker.rules if r["id"] == "R999"]
    assert bad == []  # 坏正则规则被剔除
    assert any(r["id"] == "R001" for r in checker.rules)  # 其余规则正常


def test_ttl_auto_reload(monkeypatch):
    rows = [_FakeRow("R001", "旧", "keyword", {"patterns": ["旧词"]})]
    monkeypatch.setattr("shared.common.db_session.SessionLocal", lambda: _FakeDb(rows))
    checker = ComplianceChecker()
    # 新规则出现 + 手动拨快 TTL
    rows2 = [_FakeRow("R001", "旧", "keyword", {"patterns": ["旧词"]}),
             _FakeRow("R010", "新规则", "keyword", {"patterns": ["新词"]})]
    monkeypatch.setattr("shared.common.db_session.SessionLocal", lambda: _FakeDb(rows2))
    checker.rules_ttl = 0.01
    time.sleep(0.02)
    result = checker.check("这里有新词", {})
    assert any(v["rule_code"] == "R010" for v in result["violations"])


# ==================== D1：禁用规则（2026-08-13） ====================

def test_disabled_db_rule_overrides_yaml(monkeypatch):
    """D1：DB 中禁用 YAML 源规则 R001（enabled=False）→ check 不再命中 R001"""
    rows = [_FakeRow("R001", "禁止承诺疗效(已禁用)", "keyword",
                     {"patterns": ["保证治好"]}, enabled=False)]
    monkeypatch.setattr("shared.common.db_session.SessionLocal", lambda: _FakeDb(rows))
    checker = ComplianceChecker()
    result = checker.check("保证治好", {"type": "chat"})
    assert not any(v["rule_code"] == "R001" for v in result["violations"])
    assert result["blocked"] is False
    # 其他 YAML 规则不受影响
    result2 = checker.check("这个药有返点吗", {"type": "chat"})
    assert any(v["rule_code"] == "R002" for v in result2["violations"])


def test_disabled_custom_db_rule_not_hit(monkeypatch):
    """D1：禁用的自定义 DB 规则（YAML 无此 id）→ check 不再命中"""
    rows = [_FakeRow("R900", "自定义规则(已禁用)", "keyword",
                     {"patterns": ["自定义违禁词"]}, enabled=False)]
    monkeypatch.setattr("shared.common.db_session.SessionLocal", lambda: _FakeDb(rows))
    checker = ComplianceChecker()
    result = checker.check("这里出现自定义违禁词", {"type": "chat"})
    assert not any(v["rule_code"] == "R900" for v in result["violations"])


def test_disabled_then_enabled_rule_recovers(monkeypatch):
    """D1：禁用后重新启用（TTL 自动重载）→ 恢复命中"""
    rows_disabled = [_FakeRow("R001", "已禁用", "keyword",
                              {"patterns": ["保证治好"]}, enabled=False)]
    monkeypatch.setattr("shared.common.db_session.SessionLocal", lambda: _FakeDb(rows_disabled))
    checker = ComplianceChecker()
    assert not any(v["rule_code"] == "R001"
                   for v in checker.check("保证治好", {})["violations"])

    rows_enabled = [_FakeRow("R001", "已启用", "keyword",
                             {"patterns": ["保证治好"]}, enabled=True)]
    monkeypatch.setattr("shared.common.db_session.SessionLocal", lambda: _FakeDb(rows_enabled))
    checker.rules_ttl = 0.01
    time.sleep(0.02)
    result = checker.check("保证治好", {})
    assert any(v["rule_code"] == "R001" for v in result["violations"])


# ==================== D2：坏 content 行隔离（2026-08-13） ====================

def test_non_dict_content_row_skipped_not_poisoning(monkeypatch):
    """D2：单行 content 非 dict（字符串）被跳过 + warning，不毒化全部 DB 规则加载"""
    rows = [
        _FakeRow("R010", "坏数据规则", "semantic", "这是一段字符串 content"),
        _FakeRow("R011", "正常规则", "keyword", {"patterns": ["正常词"]}),
    ]
    monkeypatch.setattr("shared.common.db_session.SessionLocal", lambda: _FakeDb(rows))
    checker = ComplianceChecker()
    assert not any(r["id"] == "R010" for r in checker.rules)  # 坏行被剔除
    assert any(r["id"] == "R011" for r in checker.rules)      # 其余 DB 规则正常
    result = checker.check("出现正常词", {})
    assert any(v["rule_code"] == "R011" for v in result["violations"])
