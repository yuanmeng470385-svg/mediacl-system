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


# ---------- F4 回归（2026-08-13）：qwen 输出畸形不抛异常、坏项跳过 ----------

class FakeQwenPayload:
    """返回任意畸形 payload 的语义层桩"""
    def __init__(self, payload):
        self._payload = payload

    def chat(self, messages, **kwargs):
        return {"content": json.dumps(self._payload)}


def test_malformed_objection_items_skipped_not_raised():
    """F4：objections 混入坏项（非 dict/缺 text/text 为空）→ 坏项跳过，合法项保留"""
    det = ObjectionDetector(qwen=FakeQwenPayload({
        "objections": [
            {"type": "efficacy", "text": "效果不如文献"},
            "裸字符串",
            None,
            123,
            {"type": "price"},                    # 缺 text 键
            {"type": "safety", "text": ""},       # 空 text
            {"type": "competition", "text": "   "},  # 空白 text
        ],
        "interests": ["长期安全性", 123, None, {"nested": 1}, "  ", "适应症扩展"],
        "sentiment": {"bad": True},
    }))
    result = det.detect("今天天气不错")  # 无规则命中的中性文本
    assert result["method"] == "rules+semantic"
    assert result["objections"] == [{"type": "efficacy", "text": "效果不如文献"}]
    assert result["interests"] == ["长期安全性", "适应症扩展"]
    assert result["sentiment"] == "neutral"


def test_objections_as_string_not_raised():
    """F4：objections 为字符串（旧实现逐个字符取 ["text"] 抛 TypeError）→ 不抛异常"""
    det = ObjectionDetector(qwen=FakeQwenPayload({
        "objections": "这是一个字符串而不是数组",
        "interests": [],
        "sentiment": "neutral",
    }))
    result = det.detect("今天天气不错")
    assert result["method"] == "rules+semantic"
    assert result["objections"] == []


def test_objections_as_dict_or_none_not_raised():
    """F4：objections 为 dict / None → 不抛异常，按坏项跳过"""
    for bad in ({"oops": 1}, None):
        det = ObjectionDetector(qwen=FakeQwenPayload({
            "objections": bad,
            "interests": "兴趣字符串而非数组",   # interests 类型钳制
            "sentiment": 42,                    # sentiment 类型钳制
        }))
        result = det.detect("今天天气不错")
        assert result["method"] == "rules+semantic"
        assert result["objections"] == []
        assert result["interests"] == []
        assert result["sentiment"] == "neutral"


def test_objection_text_number_coerced_to_string():
    """F4：text 为数字 → 经 str() 钳制后保留（不因类型逃出异常）"""
    det = ObjectionDetector(qwen=FakeQwenPayload({
        "objections": [{"type": "other", "text": 12345}],
        "interests": [],
        "sentiment": "neutral",
    }))
    result = det.detect("今天天气不错")
    assert result["objections"] == [{"type": "other", "text": "12345"}]
