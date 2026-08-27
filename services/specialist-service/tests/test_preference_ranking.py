# services/specialist-service/tests/test_preference_ranking.py
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", ".."))
from app.core.preference_ranking import (
    get_profile, get_profiles_batch, reorder_results, matched_interest, preference_context,
)


class FakeProfile:
    def __init__(self, areas=None, doc_type=None, style=None, closed=False, doctor_id=None):
        self.interest_areas = areas
        self.preferred_doc_type = doc_type
        self.preferred_style = style
        self.closed = closed
        self.doctor_id = doctor_id


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


# --- get_profile / get_profiles_batch 读取侧覆盖（评审 Issue-1/Issue-2 补测） ---

class QueryStub:
    """链式 query().filter().first()/all() 替身（本模块只用到这两条链）"""

    def __init__(self, first_result=None, all_results=None):
        self._first = first_result
        if all_results is None:
            all_results = [first_result] if first_result is not None else []
        self._all = all_results

    def filter(self, *a, **k):
        return self

    def first(self):
        return self._first

    def all(self):
        return self._all


class FakeDb:
    def __init__(self, first=None, all_rows=None, raise_on_query=False):
        self._first = first
        self._all_rows = all_rows
        self._raise_on_query = raise_on_query

    def query(self, model):
        if self._raise_on_query:
            raise RuntimeError("db down")
        return QueryStub(first_result=self._first, all_results=self._all_rows)


def test_get_profile_normal_returns_profile():
    prof = FakeProfile(areas=["肿瘤"], doctor_id=7)
    assert get_profile(FakeDb(first=prof), 7) is prof


def test_get_profile_closed_returns_none():
    assert get_profile(FakeDb(first=FakeProfile(areas=["肿瘤"], closed=True, doctor_id=7)), 7) is None


def test_get_profile_empty_areas_returns_none():
    assert get_profile(FakeDb(first=FakeProfile(areas=[], doctor_id=7)), 7) is None


def test_get_profile_db_error_returns_none():
    assert get_profile(FakeDb(raise_on_query=True), 7) is None


def test_get_profile_malformed_row_returns_none():
    """读取异常（含畸形行）→ None：查询返回无 closed/interest_areas 字段的对象时不得抛异常"""
    assert get_profile(FakeDb(first=object()), 7) is None


def test_get_profiles_batch_filters_closed_and_empty():
    p1 = FakeProfile(areas=["肿瘤"], doctor_id=1)
    p2 = FakeProfile(areas=["心血管"], closed=True, doctor_id=2)
    p3 = FakeProfile(areas=[], doctor_id=3)
    out = get_profiles_batch(FakeDb(all_rows=[p1, p2, p3]), [1, 2, 3])
    assert out == {1: p1}


def test_get_profiles_batch_empty_ids_returns_empty():
    assert get_profiles_batch(FakeDb(), []) == {}


def test_get_profiles_batch_db_error_returns_empty():
    assert get_profiles_batch(FakeDb(raise_on_query=True), [1, 2]) == {}
