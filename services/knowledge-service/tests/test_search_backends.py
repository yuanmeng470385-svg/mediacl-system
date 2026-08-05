"""检索后端链与空库处理"""
from app.api.knowledge import validate_search_request
from shared.common.response import ParamError
import pytest


def test_validate_search_request():
    with pytest.raises(ParamError):
        validate_search_request({"query": ""})
    r = validate_search_request({"query": "剂量", "top_k": 5})
    assert r == {"query": "剂量", "top_k": 5}
    with pytest.raises(ParamError):
        validate_search_request({"query": "剂量", "top_k": "abc"})
