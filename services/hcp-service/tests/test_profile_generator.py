"""画像生成器测试 — LLM 成功 / LLM 失败降级 / 互动历史查询异常降级"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", ".."))

from app.models.hcp import Hcp  # noqa: E402
from app.services.profile_generator import ProfileGenerator  # noqa: E402


class FakeQwenOk:
    """返回固定 JSON 的假千问客户端"""

    def chat(self, messages, **kwargs):
        return {"content": '{"academic_profile": "学术型KOL", "communication_advice": "多谈指南", "next_step_suggestion": "预约下次拜访", "prescription_preference": "偏好联合方案", "risk_alert": "无"}'}


class FakeQwenFail:
    """调用即抛错的假千问客户端"""

    def chat(self, messages, **kwargs):
        raise Exception("DASHSCOPE_API_KEY 未配置")


class FakeDbEmptyInteractions:
    """execute 抛错的假 session — 模拟 visit_records 表不存在"""

    def execute(self, *args, **kwargs):
        raise Exception('relation "visit_records" does not exist')


def _make_hcp(**kwargs):
    defaults = dict(id=1, name="张伟", hospital="协和医院", title="主任医师", tags=["KOL"])
    defaults.update(kwargs)
    return Hcp(**defaults)


def test_profile_ok_with_valid_json():
    gen = ProfileGenerator(qwen=FakeQwenOk())
    result = gen.generate(FakeDbEmptyInteractions(), _make_hcp())
    assert result["degraded"] is False
    assert result["ai_profile"]["academic_profile"] == "学术型KOL"
    assert result["ai_profile"]["next_step_suggestion"] == "预约下次拜访"
    assert result["interactions"] == []  # 表缺失时降级为空列表


def test_profile_degraded_when_llm_fails():
    gen = ProfileGenerator(qwen=FakeQwenFail())
    result = gen.generate(FakeDbEmptyInteractions(), _make_hcp())
    assert result["degraded"] is True
    assert "ai_profile" in result
    assert "base_info" in result["ai_profile"]
    # 降级时基础信息仍可用
    assert result["ai_profile"]["base_info"]["title"] == "主任医师"
