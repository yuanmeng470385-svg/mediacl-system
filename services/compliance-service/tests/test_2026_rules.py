"""2026《医药代表管理办法》映射新增规则测试（R008-R011 + R006 新口径）

文本层（keyword/regex）用 fast=True 断言命中 —— fast 只跑文本层，
语义层不执行，测试不依赖 DASHSCOPE_API_KEY、不烧 token。
"""
import pytest

from app.core.checker import ComplianceChecker


class _FakeDb:
    """空 DB：只吃 YAML 种子（新增规则已在 Task 1 写入 rules.yaml）"""

    def query(self, *a, **kw):
        return self

    def filter(self, *a, **kw):
        return self

    def all(self):
        return []

    def close(self):
        pass


@pytest.fixture()
def checker(monkeypatch):
    monkeypatch.setattr("shared.common.db_session.SessionLocal", lambda: _FakeDb())
    return ComplianceChecker()


def test_new_rules_loaded_from_yaml(checker):
    ids = {r["id"] for r in checker.rules}
    assert {"R008", "R009", "R010", "R011"} <= ids
    r006 = next(r for r in checker.rules if r["id"] == "R006")
    assert "非法收集" in r006["description"]


def test_r008_regex_hits_sales_condition_sponsor(checker):
    result = checker.check("只要销量达到100盒，我们就给科室赞助", fast=True)
    codes = [v["rule_code"] for v in result["violations"]]
    assert "R008" in codes


def test_r008_regex_hits_sponsor_first_order(checker):
    result = checker.check("公司赞助的前提是按销售额返点", fast=True)
    codes = [v["rule_code"] for v in result["violations"]]
    assert "R008" in codes


def test_r009_keyword_hits_gift(checker):
    result = checker.check("下次拜访给您带点礼品", fast=True)
    codes = [v["rule_code"] for v in result["violations"]]
    assert "R009" in codes


def test_r010_keyword_hits_hidden_adverse_effect(checker):
    result = checker.check("我们这个药没有副作用，绝对安全", fast=True)
    codes = [v["rule_code"] for v in result["violations"]]
    assert "R010" in codes


def test_r011_semantic_not_executed_in_fast_mode(checker):
    result = checker.check("按说明书用药即可", fast=True)
    # 语义规则在 fast 模式不执行：checked_rules 不含 R011
    assert "R011" not in result["checked_rules"]
    # R011 已注册（normal 模式会执行）
    assert any(r["id"] == "R011" and r["type"] == "semantic" for r in checker.rules)


def test_existing_r002_still_hits_regression(checker):
    result = checker.check("这个药有返点吗", fast=True)
    codes = [v["rule_code"] for v in result["violations"]]
    assert "R002" in codes
