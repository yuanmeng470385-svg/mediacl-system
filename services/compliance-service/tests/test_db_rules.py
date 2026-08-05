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
        return [r for r in self._rows if r.enabled]

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
