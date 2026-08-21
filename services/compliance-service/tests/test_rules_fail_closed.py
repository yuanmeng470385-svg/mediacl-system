"""规则库降级 fail-closed 回归（2026-08-21 审计遗留：加载失败静默全放行 + /health 无信号）

设计（分两档）：
- 0 条有效规则（YAML 缺失 + DB 挂 / DB 空表）→ RULES_FAIL_MODE=closed（默认）下
  check() 返回 blocked=True + 合成违规 R998 —— 合规门禁不能静默失效；
- DB 挂但 YAML 兜底规则仍生效 → 不硬拦（DB 抖动不该瘫掉全站对话），但
  result.degraded / /health / prometheus 指标必须暴露降级状态；
- RULES_FAIL_MODE=open 为显式逃生口（恢复旧行为，仅故障排查临时使用）。
"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", ".."))

import pytest  # noqa: E402
import yaml as yaml_mod  # noqa: E402

from app.core import checker as checker_mod  # noqa: E402
from app.core.checker import ComplianceChecker  # noqa: E402

R001 = {"id": "R001", "name": "禁止承诺疗效", "type": "keyword",
        "patterns": ["保证治好"], "severity": "high", "action": "reject", "enabled": True}


def _raising(exc):
    def f():
        raise exc
    return f


def _mk_checker(monkeypatch, tmp_path, yaml_rules=None, db_rules=None, db_error=None,
                mode="closed"):
    """构造不连真库/真 YAML 的 checker：yaml_rules=None 表示 YAML 文件不存在"""
    monkeypatch.setattr(checker_mod.settings, "RULES_FAIL_MODE", mode)
    if yaml_rules is None:
        monkeypatch.setattr(checker_mod.settings, "RULES_YAML_PATH",
                            str(tmp_path / "不存在.yaml"))
    else:
        p = tmp_path / "rules.yaml"
        p.write_text(yaml_mod.safe_dump({"rules": yaml_rules}, allow_unicode=True),
                     encoding="utf-8")
        monkeypatch.setattr(checker_mod.settings, "RULES_YAML_PATH", str(p))
    if db_error is not None:
        monkeypatch.setattr(ComplianceChecker, "_load_db_rules",
                            staticmethod(_raising(db_error)))
    else:
        monkeypatch.setattr(ComplianceChecker, "_load_db_rules",
                            staticmethod(lambda: list(db_rules or [])))
    return ComplianceChecker()


def test_zero_rules_blocks_closed(monkeypatch, tmp_path):
    """YAML 缺失 + DB 挂 → 0 条规则：closed 模式必须 R998 拦截（修复前静默放行）"""
    c = _mk_checker(monkeypatch, tmp_path, yaml_rules=None,
                    db_error=RuntimeError("connection refused"))
    r = c.check("今天天气不错，适合学术会议")
    assert r["blocked"] is True
    assert r["violations"][0]["rule_code"] == "R998"
    assert r["risk_level"] == "high"
    assert "规则库" in r["violations"][0]["reason"]


def test_db_empty_and_no_yaml_blocks(monkeypatch, tmp_path):
    """YAML 缺失 + DB 空表（加载成功但 0 行）→ 同样 0 条规则，必须拦截"""
    c = _mk_checker(monkeypatch, tmp_path, yaml_rules=None, db_rules=[])
    r = c.check("随便聊聊")
    assert r["blocked"] is True
    assert r["violations"][0]["rule_code"] == "R998"


def test_yaml_protection_with_db_fail_flagged_not_hardblocked(monkeypatch, tmp_path):
    """DB 挂 + YAML 兜底：YAML 规则照常拦截（命中归因仍是 R001 不是 R998），
    干净内容不硬拦（DB 抖动不瘫全站对话），但 degraded 标志必须暴露"""
    c = _mk_checker(monkeypatch, tmp_path, yaml_rules=[R001],
                    db_error=RuntimeError("db down"))
    r1 = c.check("这个药保证治好")
    assert r1["blocked"] is True
    assert any(v["rule_code"] == "R001" for v in r1["violations"])   # 归因保持
    r2 = c.check("III期临床试验显示良好的安全性")
    assert r2["blocked"] is False                                     # 不硬拦
    assert r2["degraded"] is True                                     # 但必须可观测


def test_open_mode_zero_rules_allows(monkeypatch, tmp_path):
    """RULES_FAIL_MODE=open 显式逃生口：0 条规则放行（恢复旧行为），degraded 仍暴露"""
    c = _mk_checker(monkeypatch, tmp_path, yaml_rules=None,
                    db_error=RuntimeError("db down"), mode="open")
    r = c.check("今天天气不错")
    assert r["blocked"] is False
    assert r["degraded"] is True


def test_empty_content_never_blocked_even_degraded(monkeypatch, tmp_path):
    """空内容永远放行（守卫：降级拦截只针对非空内容）"""
    c = _mk_checker(monkeypatch, tmp_path, yaml_rules=None,
                    db_error=RuntimeError("db down"))
    r = c.check("")
    assert r["blocked"] is False


def test_health_exposes_rules_state():
    """/health 必须暴露 rules_count / rules_degraded（修复前无任何信号）"""
    from fastapi.testclient import TestClient
    from app.main import app
    from app.core.checker import get_checker

    c = get_checker()
    old = c._load_error
    c._load_error = "测试注入的错误"
    try:
        with TestClient(app) as client:
            resp = client.get("/health")
        assert resp.status_code == 200
        body = resp.json()
        assert body["rules_degraded"] is True
        assert body["rules_error"] == "测试注入的错误"
        assert body["rules_count"] == len(c.rules)
    finally:
        c._load_error = old
