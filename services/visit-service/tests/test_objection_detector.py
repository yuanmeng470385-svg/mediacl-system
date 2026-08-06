"""异议识别器测试 — 规则层 / 语义层降级 / 合并去重"""
import os
import sys
import json

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", ".."))

from app.core.objection_detector import ObjectionDetector  # noqa: E402


class FakeQwenOk:
    """返回固定语义分析结果"""
    def chat(self, messages, **kwargs):
        return {"content": json.dumps({
            "objections": [{"type": "efficacy", "text": "但效果好像没文献说得那么好"}],
            "interests": ["长期用药安全性", "适应症扩展"],
            "sentiment": "neutral",
        })}


class FakeQwenFail:
    """语义层不可用，降级为仅规则层"""
    def chat(self, messages, **kwargs):
        raise Exception("DASHSCOPE_API_KEY 未配置")


def test_rule_price_objection():
    det = ObjectionDetector(qwen=FakeQwenFail())
    result = det.detect("这个药价格有点贵啊，患者负担不起")
    assert result["method"] == "rules"  # 语义降级
    assert any(o["type"] == "price" for o in result["objections"])


def test_rule_safety_objection():
    det = ObjectionDetector(qwen=FakeQwenFail())
    result = det.detect("我担心副作用比较大，患者用了会投诉")
    assert any(o["type"] == "safety" for o in result["objections"])


def test_rule_deferral_objection():
    det = ObjectionDetector(qwen=FakeQwenFail())
    result = det.detect("我再考虑考虑，下次再说吧")
    assert any(o["type"] == "deferral" for o in result["objections"])


def test_rule_competition_objection():
    det = ObjectionDetector(qwen=FakeQwenFail())
    result = det.detect("别家竞品的替代方案好像也不错")
    assert any(o["type"] == "competition" for o in result["objections"])


def test_rule_competition_no_false_positive_on_usage_phrases():
    """'患者用药后'等高频短语不再误报竞品异议（需比较语境）"""
    det = ObjectionDetector(qwen=FakeQwenFail())
    result = det.detect("患者用药后应观察不良反应，定期复查肝功能")
    types = {o["type"] for o in result["objections"]}
    assert "competition" not in types
    # 另一个高频误报场景：比如/比索洛尔（裸"比"不参与匹配）
    result2 = det.detect("比如用这个药做联合治疗，比索洛尔也能联用")
    types2 = {o["type"] for o in result2["objections"]}
    assert "competition" not in types2


def test_rule_competition_comparison_context_still_detected():
    """带比较语境的竞品异议仍能命中"""
    det = ObjectionDetector(qwen=FakeQwenFail())
    result = det.detect("这个药不如别家的，患者反馈差别明显")
    types = {o["type"] for o in result["objections"]}
    assert "competition" in types
    # 用药 + 比较词（正向顺序）
    result2 = det.detect("用药效果和另一家差不多，患者更认可那边的数据")
    types2 = {o["type"] for o in result2["objections"]}
    assert "competition" in types2


def test_rule_efficacy_objection():
    det = ObjectionDetector(qwen=FakeQwenFail())
    result = det.detect("这个药不太有效果，病人反馈一般")
    assert any(o["type"] == "efficacy" for o in result["objections"])


def test_no_objection_clean_text():
    det = ObjectionDetector(qwen=FakeQwenFail())
    result = det.detect("好的，这个信息很有用，下次再聊")
    assert result["objections"] == []


def test_semantic_merge_with_rules():
    """语义层补充规则层未覆盖的异议"""
    det = ObjectionDetector(qwen=FakeQwenOk())
    # 文本触发规则匹配 + 语义层返回新异议
    result = det.detect("价格有点贵，不过效果还行")
    assert result["method"] == "rules+semantic"
    # 规则层命中 price + 语义层返回 efficacy，两者合并
    types = {o["type"] for o in result["objections"]}
    assert "price" in types  # 规则层
    assert "efficacy" in types  # 语义层
    assert result["sentiment"] == "neutral"


def test_empty_text():
    det = ObjectionDetector()
    result = det.detect("")
    assert result["objections"] == []
    assert result["sentiment"] == "neutral"
