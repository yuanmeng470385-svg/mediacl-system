"""反馈/收藏落库 + 满意度统计"""
from app.api.conversations import compute_satisfaction


def test_compute_satisfaction_empty():
    assert compute_satisfaction(0, 0) == {"total_feedback": 0, "satisfaction_rate": None}


def test_compute_satisfaction_rates():
    r = compute_satisfaction(3, 1)  # 3 赞 1 踩
    assert r["total_feedback"] == 4
    assert r["satisfaction_rate"] == 0.75


def test_compute_satisfaction_all_negative():
    assert compute_satisfaction(0, 2)["satisfaction_rate"] == 0.0
