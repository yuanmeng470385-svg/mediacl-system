# services/specialist-service/tests/test_preference_ranking.py
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", ".."))
from app.core.preference_ranking import (
    get_profile, get_profiles_batch, reorder_results, matched_interest, preference_context,
)


class FakeProfile:
    def __init__(self, areas=None, doc_type=None, style=None, closed=False):
        self.interest_areas = areas
        self.preferred_doc_type = doc_type
        self.preferred_style = style
        self.closed = closed


def test_reorder_results_matches_interest_first():
    prof = FakeProfile(areas=["肿瘤"])
    results = [
        {"title": "高血压管理指南", "content": "血压控制..."},
        {"title": "肿瘤免疫治疗进展", "content": "肺癌治疗..."},
    ]
    out = reorder_results(results, prof)
    assert out[0]["title"] == "肿瘤免疫治疗进展"


def test_reorder_results_stable_when_equal_score():
    prof = FakeProfile(areas=["肿瘤"])
    results = [
        {"title": "普通文献A", "content": "x"},
        {"title": "普通文献B", "content": "y"},
    ]
    assert reorder_results(results, prof) == results  # 无命中保持原序


def test_reorder_results_closed_returns_original():
    results = [{"title": "A", "content": "x"}, {"title": "B", "content": "y"}]
    assert reorder_results(results, FakeProfile(areas=["肿瘤"], closed=True)) == results


def test_reorder_results_none_profile_returns_original():
    results = [{"title": "A", "content": "x"}]
    assert reorder_results(results, None) == results


def test_matched_interest_true_when_title_has_area():
    assert matched_interest("肿瘤免疫治疗方案", FakeProfile(areas=["肿瘤"])) is True
    assert matched_interest("高血压管理", FakeProfile(areas=["肿瘤"])) is False
    assert matched_interest("任何", FakeProfile(areas=["肿瘤"], closed=True)) is False


def test_preference_context_includes_areas_and_constraint():
    ctx = preference_context(FakeProfile(areas=["肿瘤", "心血管"], style="简洁"))
    assert "肿瘤" in ctx and "心血管" in ctx and "简洁" in ctx
    assert "不得改变医学事实" in ctx


def test_preference_context_closed_or_none_is_empty():
    assert preference_context(FakeProfile(areas=["肿瘤"], closed=True)) == ""
    assert preference_context(None) == ""
