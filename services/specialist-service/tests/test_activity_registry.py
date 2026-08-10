"""活动注册表单元测试：set/get/置空闲/截断"""
from app.core.activity_registry import (
    registry, PHASE_GENERATING, PHASE_TEXT,
)

def test_set_working_and_get(monkeypatch):
    from app.core import activity_registry
    monkeypatch.setattr(activity_registry, "_now", lambda: __import__("datetime").datetime(2026, 8, 6, 10, 0, 0))
    registry.set_working(1, PHASE_GENERATING, "肺癌用药注意事项")
    snap = registry.get(1)
    assert snap is not None
    assert snap.specialist_id == 1
    assert snap.phase == PHASE_GENERATING
    assert snap.phase_since.isoformat() == "2026-08-06T10:00:00"
    assert snap.question_snippet == "肺癌用药注意事项"

def test_snippet_truncated_to_20_chars():
    registry.set_working(2, PHASE_GENERATING, "这" * 30)
    assert len(registry.get(2).question_snippet) == 20

def test_set_idle_removes_entry():
    registry.set_working(1, PHASE_GENERATING, "q")
    registry.set_idle(1)
    assert registry.get(1) is None

def test_all_returns_snapshot_of_current_state():
    registry.set_working(1, PHASE_GENERATING, "q1")
    registry.set_working(2, PHASE_GENERATING, "q2")
    assert set(registry.all().keys()) == {1, 2}
    registry.set_idle(1)
    assert set(registry.all().keys()) == {2}

def test_phase_text_maps_all_phases():
    assert PHASE_TEXT[PHASE_GENERATING] == "正在检索知识库并生成回答"
    assert set(PHASE_TEXT) == {"compliance_precheck", "generating", "compliance_review"}

def test_is_recently_started_window(monkeypatch):
    from datetime import datetime, timedelta
    from app.core import activity_registry
    base = datetime(2026, 8, 6, 10, 0, 0)
    monkeypatch.setattr(activity_registry, "_now", lambda: base + timedelta(seconds=30))
    monkeypatch.setattr(activity_registry, "STARTED_AT", base)
    assert activity_registry.is_recently_started() is True
    monkeypatch.setattr(activity_registry, "_now", lambda: base + timedelta(minutes=6))
    assert activity_registry.is_recently_started() is False
