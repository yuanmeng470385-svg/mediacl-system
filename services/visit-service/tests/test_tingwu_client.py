"""听悟客户端 _parse_result 解析测试（合规硬伤回归：旧实现找不存在的 transcripts 字段）"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", ".."))

from app.services.tingwu_client import TingwuClient


class FakeResult:
    """模拟 SDK to_map() 返回听悟 GetTaskInfo 真实结构（tingwu20230930）"""

    def __init__(self, data: dict):
        self._data = data

    def to_map(self) -> dict:
        return self._data


def _parse(data: dict):
    return TingwuClient()._parse_result(FakeResult(data))


def test_parse_real_tingwu_structure():
    """听悟真实结构：result.text 全文 + result.sentences 句级（含 speaker_id）"""
    out = _parse({
        "text": "医生您好，这是新款降压药。",
        "sentences": [
            {"sentence": {"speaker_id": 0, "text": "医生您好，", "begin_time": 0, "end_time": 500}},
            {"sentence": {"speaker_id": 1, "text": "这是新款降压药。", "begin_time": 500, "end_time": 1200}},
        ],
    })
    assert out["text"] == "医生您好，这是新款降压药。", out["text"]
    assert len(out["sentences"]) == 2
    assert out["sentences"][0] == {"speaker_id": 0, "text": "医生您好，"}, out["sentences"][0]
    assert out["sentences"][1]["speaker_id"] == 1
    assert out["speakers"] == [0, 1]


def test_parse_flat_sentences():
    """平铺句元素（无 sentence 嵌套）也能解析"""
    out = _parse({
        "text": "全文",
        "sentences": [{"speaker_id": "speaker_1", "text": "全文"}],
    })
    assert out["text"] == "全文"
    assert out["speakers"] == ["speaker_1"]


def test_parse_empty_result_returns_empty():
    """空 result 不抛异常，返回空结构"""
    out = _parse({})
    assert out == {"text": "", "sentences": [], "speakers": []}


def test_parse_legacy_transcripts_nested():
    """旧 transcripts 嵌套结构仍兼容（不回归）"""
    out = _parse({
        "transcripts": [
            {"sentences": [{"sentence": {"speaker_id": 0, "text": "旧结构"}}]},
        ],
    })
    assert out["text"] == "旧结构"
    assert len(out["sentences"]) == 1
