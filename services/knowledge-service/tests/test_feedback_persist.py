"""检索反馈落库（参数校验纯函数）"""
import pytest

from app.api.knowledge import validate_feedback_request
from shared.common.response import ParamError


def test_feedback_requires_query_and_rating():
    with pytest.raises(ParamError):
        validate_feedback_request({"rating": 1})
    with pytest.raises(ParamError):
        validate_feedback_request({"query": "q"})
    with pytest.raises(ParamError):
        validate_feedback_request({"query": "q", "rating": 0})
    r = validate_feedback_request({"query": "剂量", "rating": -1, "doc_id": "3", "comment": "不准"})
    assert r["rating"] == -1
