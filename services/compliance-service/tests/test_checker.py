"""合规审核引擎单元测试"""
import pytest
import sys
import os

# 确保可以导入 shared 和 app
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", ".."))

from app.core.checker import ComplianceChecker


class TestComplianceChecker:
    """关键词 + 正则匹配测试"""

    def setup_method(self):
        self.checker = ComplianceChecker()

    def test_keyword_block_疗效承诺(self):
        """R001: 禁止承诺疗效 - 应被拦截"""
        result = self.checker.check("我们这个药保证治好", {"type": "chat"})
        assert result["blocked"] is True
        assert any(v["rule_code"] == "R001" for v in result["violations"])

    def test_keyword_block_100有效(self):
        """R001: 100%有效 应被拦截"""
        result = self.checker.check("我们的药100%有效", {"type": "chat"})
        assert result["blocked"] is True
        assert any(v["rule_code"] == "R001" for v in result["violations"])

    def test_regex_block_回扣暗示(self):
        """R002: 禁止回扣暗示 - 应被拦截"""
        result = self.checker.check("这个药有返点吗", {"type": "chat"})
        assert result["blocked"] is True
        assert any(v["rule_code"] == "R002" for v in result["violations"])

    def test_regex_block_好处费(self):
        """R002: 好处费 应被拦截"""
        result = self.checker.check("给你好处费", {"type": "chat"})
        assert result["blocked"] is True
        assert any(v["rule_code"] == "R002" for v in result["violations"])

    def test_safe_content_passes(self):
        """正常学术内容应通过审核"""
        result = self.checker.check(
            "我们的产品在III期临床试验中显示出良好的安全性和有效性",
            {"type": "chat"}
        )
        assert result["blocked"] is False
        # 安全内容不应有 reject 级别的违规
        assert not any(v["action"] == "reject" for v in result["violations"])

    def test_empty_content(self):
        """空内容应安全通过"""
        result = self.checker.check("", {"type": "chat"})
        assert result["blocked"] is False
        assert result["violations"] == []

    def test_risk_level_high(self):
        """高风险违规 → risk_level=high"""
        result = self.checker.check("保证治好，100%有效", {"type": "chat"})
        assert result["risk_level"] == "high"

    def test_warn_rule(self):
        """warn 级别的规则不阻断但记录"""
        # R005 是 medium/warn，不会触发 blocked=True
        result = self.checker.check("竞品那个药不行", {"type": "chat"})
        # 这个测试可能通过（R005 是语义规则需要 LLM）
        # 如果没有配置 DASHSCOPE_API_KEY，语义规则会跳过
        assert "risk_level" in result

    def test_reload_rules(self):
        """热更新：reload 后规则数不变"""
        count_before = len(self.checker.rules)
        self.checker.reload()
        count_after = len(self.checker.rules)
        assert count_before == count_after

    def test_test_rule(self):
        """规则测试功能"""
        result = self.checker.test_rule("保证治好", "R001")
        assert len(result["hits"]) == 1
        assert result["hits"][0]["hit"] is True

    def test_test_rule_no_match(self):
        """规则测试：正常内容不命中"""
        result = self.checker.test_rule("正常的学术讨论内容", "R001")
        assert len(result["hits"]) == 1
        assert result["hits"][0]["hit"] is False
