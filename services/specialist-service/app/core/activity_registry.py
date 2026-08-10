"""进程内活动注册表 — 数字专员实时工作状态（瞬态，重启即失）

设计要点：
- 单事件循环内读写，无需锁
- 重启后注册表为空 → live-status 接口按 conversations 最近活跃降级推断
- 与 lifecycle（draft/active/disabled）区分：这里只存运行时瞬态
- 同一专员并发多轮对话时 last-writer-wins，覆盖上一快照
"""
from dataclasses import dataclass
from datetime import datetime
from typing import Optional

PHASE_COMPLIANCE_PRECHECK = "compliance_precheck"
PHASE_GENERATING = "generating"
PHASE_COMPLIANCE_REVIEW = "compliance_review"

PHASE_TEXT = {
    PHASE_COMPLIANCE_PRECHECK: "正在核查问题合规性",
    PHASE_GENERATING: "正在检索知识库并生成回答",
    PHASE_COMPLIANCE_REVIEW: "正在审核回答合规性",
}

QUESTION_SNIPPET_LEN = 20


def _now() -> datetime:
    return datetime.utcnow()


@dataclass
class ActivitySnapshot:
    specialist_id: int
    phase: str
    question_snippet: str
    phase_since: datetime


class ActivityRegistry:
    def __init__(self):
        self._states: dict[int, ActivitySnapshot] = {}

    def set_working(self, specialist_id: int, phase: str, question: str) -> None:
        self._states[specialist_id] = ActivitySnapshot(
            specialist_id=specialist_id,
            phase=phase,
            question_snippet=question[:QUESTION_SNIPPET_LEN],
            phase_since=_now(),
        )

    def set_idle(self, specialist_id: int) -> None:
        self._states.pop(specialist_id, None)

    def get(self, specialist_id: int) -> Optional[ActivitySnapshot]:
        return self._states.get(specialist_id)

    def all(self) -> dict[int, ActivitySnapshot]:
        return dict(self._states)


registry = ActivityRegistry()
