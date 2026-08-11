"""2026-08-11：指标口径对齐 + 语义层漏检可观测 回归测试

覆盖：
- 指标口径：compliance_blocks_total 只计 reject（warn/log 不再虚增"拦截"数），
  全量命中记 compliance_violations_total
- 语义层：LLM 返回未知 rule_code 不再静默丢弃（warning 日志 + SEMANTIC_DROPS 指标）
- _compile_rules：语义规则缺必填字段单条剔除（对齐坏正则隔离），不再拖垮引擎/500
"""
import logging
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", ".."))

from prometheus_client import REGISTRY

from app.core.checker import ComplianceChecker


def _sample(name, labels):
    """读当前 counter 值（无样本返回 0）"""
    try:
        return REGISTRY.get_sample_value(name, labels) or 0.0
    except Exception:
        return 0.0


class TestMetricActionScope:
    """warn/log 命中不再计入"拦截"计数（blocks 只计 reject）"""

    def setup_method(self):
        self.checker = ComplianceChecker()

    def test_count_violations_reject_only_blocks(self):
        blocks_reject_before = _sample("compliance_blocks_total", {"action": "reject", "severity": "high"})
        blocks_warn_before = _sample("compliance_blocks_total", {"action": "warn", "severity": "medium"})
        hits_warn_before = _sample("compliance_violations_total", {"action": "warn", "severity": "medium"})

        ComplianceChecker._count_violations([
            {"action": "reject", "severity": "high"},
            {"action": "warn", "severity": "medium"},
            {"action": "log", "severity": "low"},
        ])

        # 拦截指标只增 reject
        assert _sample("compliance_blocks_total", {"action": "reject", "severity": "high"}) == blocks_reject_before + 1
        # warn 命中不虚增拦截数
        assert _sample("compliance_blocks_total", {"action": "warn", "severity": "medium"}) == blocks_warn_before
        # 全量命中指标含 warn/log
        assert _sample("compliance_violations_total", {"action": "warn", "severity": "medium"}) == hits_warn_before + 1

    def test_check_reject_hit_counts_block(self):
        """check() 端到端：R001（reject/high）命中 → blocks_total 增 1"""
        before = _sample("compliance_blocks_total", {"action": "reject", "severity": "high"})
        result = self.checker.check("我们这个药保证治好", {"type": "chat"})
        assert result["blocked"] is True
        assert _sample("compliance_blocks_total", {"action": "reject", "severity": "high"}) == before + 1


class TestSemanticDrops:
    """语义层未知 rule_code 不再静默丢弃（告警 + 指标，漏检可观测）"""

    @staticmethod
    def _fake_qwen(raw_text):
        import types
        choices = types.SimpleNamespace(
            choices=[types.SimpleNamespace(message=types.SimpleNamespace(content=raw_text))]
        )
        return types.SimpleNamespace(
            chat=types.SimpleNamespace(completions=types.SimpleNamespace(create=lambda **kw: choices))
        )

    def setup_method(self):
        self.checker = ComplianceChecker()
        self.safe_content = "今天天气不错，适合开会讨论"

    def test_unknown_rule_code_warns_and_counts(self, caplog):
        """LLM 返回幻觉 rule_code → 违规被忽略（不误拦截）但必须告警 + 计数"""
        self.checker.qwen_client = self._fake_qwen(
            '{"violations": [{"rule_code": "R9999", "matched_text": "x", "reason": "幻觉"}]}'
        )
        before = _sample("compliance_semantic_drops_total", {"reason": "unknown_rule_code"})
        with caplog.at_level(logging.WARNING, logger="app.core.checker"):
            result = self.checker.check(self.safe_content, {"type": "chat"})
        assert result["blocked"] is False
        assert result["violations"] == []
        assert any("未知 rule_code" in r.message for r in caplog.records)
        assert _sample("compliance_semantic_drops_total", {"reason": "unknown_rule_code"}) == before + 1

    def test_known_rule_code_no_drop(self):
        """正常语义违规（R003）不触发 drop 指标"""
        self.checker.qwen_client = self._fake_qwen(
            '{"violations": [{"rule_code": "R003", "matched_text": "统计处方", "reason": "统方风险"}]}'
        )
        before = _sample("compliance_semantic_drops_total", {"reason": "unknown_rule_code"})
        result = self.checker.check(self.safe_content, {"type": "chat"})
        assert any(v["rule_code"] == "R003" for v in result["violations"])
        assert _sample("compliance_semantic_drops_total", {"reason": "unknown_rule_code"}) == before


class TestCompileSemanticValidation:
    """_compile_rules：语义规则缺必填字段被单条剔除（对齐坏正则隔离）"""

    def test_missing_fields_rule_isolated(self, caplog):
        checker = ComplianceChecker()
        checker.rules = [
            {"id": "S1", "type": "semantic", "name": "好规则", "action": "reject", "severity": "high"},
            {"id": "S2", "type": "semantic", "name": "缺 action/severity"},
            {"type": "semantic", "name": "缺 id", "action": "warn", "severity": "medium"},
            {"id": "K1", "type": "keyword", "name": "关键词", "action": "reject", "severity": "high",
             "patterns": ["保证治好"]},
        ]
        with caplog.at_level(logging.ERROR, logger="app.core.checker"):
            checker._compile_rules()
        ids = [r["id"] for r in checker.rules]
        assert "S1" in ids and "K1" in ids
        assert "S2" not in ids and "S3" not in ids
        assert any("缺少必填字段" in r.message for r in caplog.records)

    def test_valid_rules_untouched(self):
        """合法语义/关键词规则全保留"""
        checker = ComplianceChecker()
        checker.rules = [
            {"id": "S1", "type": "semantic", "name": "好规则", "action": "reject", "severity": "high"},
            {"id": "R001", "type": "keyword", "name": "疗效承诺", "action": "reject",
             "severity": "high", "patterns": ["保证治好"]},
        ]
        checker._compile_rules()
        assert [r["id"] for r in checker.rules] == ["S1", "R001"]
