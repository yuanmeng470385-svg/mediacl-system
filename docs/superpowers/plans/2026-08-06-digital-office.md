# 数字员工办公室实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 在 Web 管理后台实现 Marvis 风格「数字员工办公室」——数字专员页办公室视图（每专员显示当前动作）＋仪表盘顶部状态条，后端提供实时状态接口。

**Architecture:** specialist-service 进程内活动注册表记录每个专员当前动作阶段（合规预检→生成→合规审核），在 AnswerGenerator 两条链路（REST/WS）埋点；新增 `GET /api/v1/specialists/live-status` 轮询接口，注册表为空时按 conversations 表最近活跃降级推断。前端数字专员页默认办公室视图（可切回原表格），仪表盘顶部加状态条，均为 3s/5s 轮询。

**Tech Stack:** FastAPI + SQLAlchemy（后端）；React + Vite + antd + @ant-design/pro-components（前端）。

## Global Constraints

- 后端测试必须在 `services/specialist-service/` 目录下运行（sys.path 依赖 cwd）
- 后端测试沿用 FakeDb/ChainStub 替身模式，不碰真实数据库（见 `tests/test_specialist_list_stats.py`）
- **`/live-status` 路由必须声明在 `/{specialist_id}` 路由之前**（FastAPI 按注册顺序匹配，否则 `live-status` 会被 int 参数路由拦截报 422）
- 不引新依赖（前后端都是）；前端无测试框架，验证走 `cd web && npm run build`（tsc -b && vite build）+ 手工
- 前端沿用 antd + inline style + 组件复用（SpecialistForm / SpecialistDataDrawer 原封不动）
- 阶段 phase 枚举：`compliance_precheck` / `generating` / `compliance_review`；状态 state 枚举：`working` / `idle` / `offline`
- 提交信息风格：`feat:` / `test:` / `refactor:`，尾部带 Co-Authored-By

---

### Task 1: 活动注册表（activity_registry + 单元测试）

**Files:**
- Create: `services/specialist-service/app/core/activity_registry.py`
- Test: `services/specialist-service/tests/test_activity_registry.py`

**Interfaces:**
- Consumes: 无
- Produces: `registry`（模块级单例）、`ActivitySnapshot`（dataclass）、常量 `PHASE_COMPLIANCE_PRECHECK` / `PHASE_GENERATING` / `PHASE_COMPLIANCE_REVIEW`、字典 `PHASE_TEXT: {phase: 中文文案}`；方法 `registry.set_working(specialist_id: int, phase: str, question: str) -> None`、`registry.set_idle(specialist_id: int) -> None`、`registry.get(specialist_id: int) -> ActivitySnapshot | None`、`registry.all() -> dict[int, ActivitySnapshot]`

- [ ] **Step 1: 写失败测试**

`services/specialist-service/tests/test_activity_registry.py`：

```python
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
```

- [ ] **Step 2: 运行验证失败**

Run: `cd "D:/gongsi/medical system/services/specialist-service" && python -m pytest tests/test_activity_registry.py -v`
Expected: FAIL（`ModuleNotFoundError: No module named 'app.core.activity_registry'`）

- [ ] **Step 3: 最小实现**

`services/specialist-service/app/core/activity_registry.py`：

```python
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
```

- [ ] **Step 4: 运行验证通过**

Run: `cd "D:/gongsi/medical system/services/specialist-service" && python -m pytest tests/test_activity_registry.py -v`
Expected: 5 passed

- [ ] **Step 5: 提交**

```bash
cd "D:/gongsi/medical system"
git add services/specialist-service/app/core/activity_registry.py services/specialist-service/tests/test_activity_registry.py
git commit -m "feat: 数字专员活动注册表（实时工作状态瞬态存储）

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

---

### Task 2: AnswerGenerator 埋点（阶段切换写入注册表）

**Files:**
- Modify: `services/specialist-service/app/core/answer_generator.py`（`generate` 与 `generate_stream` 两个方法包 try/finally）
- Test: `services/specialist-service/tests/test_answer_generator_phases.py`

**Interfaces:**
- Consumes: Task 1 的 `registry`、`PHASE_*` 常量
- Produces: 两条对话链路在运行中更新注册表；任何退出路径（含 early return 和异常）finally 置 idle

- [ ] **Step 1: 写失败测试**

`services/specialist-service/tests/test_answer_generator_phases.py`：

```python
"""AnswerGenerator 埋点测试：阶段切换写注册表，退出必置 idle"""
import asyncio
from app.core.answer_generator import AnswerGenerator
from app.core import activity_registry
from app.core.activity_registry import registry
from app.models.specialist import Specialist


def _spec(specialist_id=1):
    return Specialist(
        id=specialist_id, name="测试专员", bailian_app_id="app-1",
        persona="", knowledge_scope="", compliance_level="internal",
    )


async def _check_pass(content, context):
    await asyncio.sleep(0)
    return {"blocked": False, "violations": []}


async def _check_blocked(content, context):
    await asyncio.sleep(0)
    return {"blocked": True, "violations": [{"rule_code": "R001"}]}


async def _audit(**kw):
    await asyncio.sleep(0)


class RecordingBailian:
    """调用时记录注册表当前 phase（证明 generating 阶段已写入）"""
    def __init__(self):
        self.phase_at_call = None

    async def chat(self, app_id, prompt, session_id=None):
        self.phase_at_call = registry.get(1).phase if registry.get(1) else None
        return {"text": "你好", "citations": [], "dialog_id": "dlg-1"}


def _mk(monkeypatch, check):
    monkeypatch.setattr("app.core.answer_generator.check_compliance", check)
    monkeypatch.setattr("app.core.answer_generator.write_audit_log", _audit)
    g = AnswerGenerator()
    return g


def test_generate_phases_written_and_idle_after(monkeypatch):
    b = RecordingBailian()
    g = _mk(monkeypatch, _check_pass)
    g.bailian = b

    # 记录每个合规检查调用时刻的 phase（precheck 时应为 compliance_precheck，审核时应为 compliance_review）
    seen = []

    async def recording_check(content, context):
        await asyncio.sleep(0)
        seen.append(registry.get(1).phase if registry.get(1) else None)
        return {"blocked": False, "violations": []}

    monkeypatch.setattr("app.core.answer_generator.check_compliance", recording_check)

    result = asyncio.run(g.generate("肺癌用药注意事项", _spec(), user_id=1))
    assert result["answer"] == "你好"
    assert seen == ["compliance_precheck", "compliance_review"]
    assert b.phase_at_call == "generating"
    assert registry.get(1) is None  # finally 置 idle


def test_generate_blocked_precheck_still_idle(monkeypatch):
    g = _mk(monkeypatch, _check_blocked)
    result = asyncio.run(g.generate("违规问题", _spec(), user_id=1))
    assert result["blocked"] is True
    assert registry.get(1) is None


def test_generate_stream_phases_and_idle_after(monkeypatch):
    class FakeStream:
        async def chat_stream(self, app_id, prompt, session_id=None, history=None):
            yield {"type": "delta", "text": "你"}
            yield {"type": "done", "text": "你好", "dialog_id": "dlg-1", "citations": []}

    g = _mk(monkeypatch, _check_pass)
    g.bailian = FakeStream()

    async def run():
        frames = []
        async for frame in g.generate_stream("你好", _spec(), user_id=1):
            frames.append(frame)
        return frames

    frames = asyncio.run(run())
    assert frames[-1]["type"] == "done"
    assert registry.get(1) is None  # 流消费完后 finally 置 idle
```

- [ ] **Step 2: 运行验证失败**

Run: `cd "D:/gongsi/medical system/services/specialist-service" && python -m pytest tests/test_answer_generator_phases.py -v`
Expected: FAIL（phase 断言不过——注册表从未写入，`seen` 里全是 None）

- [ ] **Step 3: 实现埋点**

在 `answer_generator.py` 中：

1. 顶部 import 追加：

```python
from app.core.activity_registry import (
    registry, PHASE_COMPLIANCE_PRECHECK, PHASE_GENERATING, PHASE_COMPLIANCE_REVIEW,
)
```

2. `generate()`：`request_id = ...` 之后包一层 `try:`，方法体整体右缩进 4 格，在三个位置插入：

```python
        registry.set_working(specialist.id, PHASE_COMPLIANCE_PRECHECK, question)
```
（Step 1 合规预检前）

```python
        registry.set_working(specialist.id, PHASE_GENERATING, question)
```
（Step 2 调百炼前）

```python
        registry.set_working(specialist.id, PHASE_COMPLIANCE_REVIEW, question)
```
（Step 3 合规审核前）

在方法末尾（最后一个 return 之后）加：

```python
    finally:
        registry.set_idle(specialist.id)
```

3. `generate_stream()` 做同样三处插入 + finally 置 idle（生成器在流被消费完或被 close 时都会执行 finally，正好保证 done 帧发出后置空闲）。

- [ ] **Step 4: 运行验证通过**

Run: `cd "D:/gongsi/medical system/services/specialist-service" && python -m pytest tests/test_answer_generator_phases.py tests/test_generate_stream.py tests/test_request_id_metrics.py tests/test_bailian_stream.py -v`
Expected: 全部 PASS（既有测试不受影响）

- [ ] **Step 5: 提交**

```bash
cd "D:/gongsi/medical system"
git add services/specialist-service/app/core/answer_generator.py services/specialist-service/tests/test_answer_generator_phases.py
git commit -m "feat: 对话链路动作点埋点，阶段切换写活动注册表

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

---

### Task 3: live-status 实时状态接口

**Files:**
- Modify: `services/specialist-service/app/api/specialists.py`（在 `list_specialists` 之后、`get_specialist` 之前插入新路由）
- Test: `services/specialist-service/tests/test_live_status.py`

**Interfaces:**
- Consumes: Task 1 的 `registry` / `PHASE_TEXT` / `PHASE_GENERATING`
- Produces: `GET /api/v1/specialists/live-status` → `{items: [...], summary: {working, idle, offline}}`（响应字段见 Global Constraints 与规格第 1.3 节）

- [ ] **Step 1: 写失败测试**

`services/specialist-service/tests/test_live_status.py`（沿用 `test_specialist_list_stats.py` 的 FakeDb 风格，ChainStub 扩展 `group_by`）：

```python
"""live-status 接口：注册表 working / 降级推断 / lifecycle offline / summary"""
from datetime import datetime, timedelta

from fastapi.testclient import TestClient

from app.main import app
from app.api.specialists import get_current_user
from shared.common.db_session import get_db
from app.core.activity_registry import registry, PHASE_GENERATING
from app.models.specialist import Specialist


class FakeSpecialist:
    def __init__(self, id, name, status):
        self.id = id
        self.name = name
        self.status = status
        self.created_at = datetime(2026, 8, 1)


class ChainStub:
    def __init__(self, rows=None):
        self.rows = list(rows or [])
        self.filters = []

    def filter(self, *a, **k):
        self.filters.append((a, k))
        return self

    def group_by(self, *a, **k):
        return self

    def all(self):
        return self.rows


class FakeDb:
    def __init__(self, specialists=None, today_rows=None, active_rows=None):
        self.specialist_stub = ChainStub(specialists or [])
        self.today_stub = ChainStub(today_rows or [])
        self.active_stub = ChainStub(active_rows or [])
        self._conv_queries = 0

    def query(self, model):
        table = getattr(model, "__table__", None)
        if table is None:
            clause = next(iter(getattr(model, "clauses", ())), None)
            table = getattr(clause, "table", None)
        name = getattr(table, "name", None) or getattr(model, "__name__", None)
        if name == "digital_specialists":
            return self.specialist_stub
        if name == "conversations":
            # 两个聚合查询按调用顺序分发：第 1 次 → today 计数，第 2 次 → 最近活跃
            self._conv_queries += 1
            return self.today_stub if self._conv_queries == 1 else self.active_stub
        raise AssertionError(f"unexpected table: {name}")


def _client(db):
    app.dependency_overrides[get_db] = lambda: db
    app.dependency_overrides[get_current_user] = lambda: {"id": 1, "role": "admin"}
    return TestClient(app)


def _reset_registry():
    registry._states.clear()
```

（FakeDb.query 的 conversations 分支按顺序返回聚合 stub——更稳妥写法见下方 Step 3 的坑位提示，测试以「断言结果」为准，stub 分发实现可自行调整为 `self._conv_calls` 计数器。）

```python
def test_live_status_working_from_registry(monkeypatch):
    from app.core import activity_registry
    monkeypatch.setattr(activity_registry, "_now", lambda: datetime(2026, 8, 6, 10, 0, 0))
    _reset_registry()
    registry.set_working(1, PHASE_GENERATING, "肺癌用药注意事项")
    db = FakeDb(
        specialists=[FakeSpecialist(1, "学术专员-肺癌", "active")],
        today_rows=[(1, 12)],
        active_rows=[(1, datetime(2026, 8, 6, 10, 0, 5))],
    )
    resp = _client(db).get("/api/v1/specialists/live-status")
    assert resp.status_code == 200, resp.text
    item = resp.json()["data"]["items"][0]
    assert item["state"] == "working"
    assert item["phase"] == PHASE_GENERATING
    assert item["phase_text"] == "正在检索知识库并生成回答"
    assert item["question_snippet"] == "肺癌用药注意事项"
    assert item["today_conversations"] == 12
    assert resp.json()["data"]["summary"] == {"working": 1, "idle": 0, "offline": 0}


def test_live_status_idle_when_registry_empty_and_no_recent(monkeypatch):
    _reset_registry()
    db = FakeDb(
        specialists=[FakeSpecialist(1, "A", "active")],
        today_rows=[(1, 3)],
        active_rows=[(1, datetime(2026, 8, 5, 9, 0, 0))],  # 昨天，>5 分钟
    )
    resp = _client(db).get("/api/v1/specialists/live-status")
    item = resp.json()["data"]["items"][0]
    assert item["state"] == "idle"
    assert item["phase"] is None
    assert item["today_conversations"] == 3


def test_live_status_recent_conversation_degrades_to_working(monkeypatch):
    _reset_registry()
    db = FakeDb(
        specialists=[FakeSpecialist(1, "A", "active")],
        today_rows=[],
        active_rows=[(1, datetime.utcnow() - timedelta(minutes=1))],  # 1 分钟前
    )
    resp = _client(db).get("/api/v1/specialists/live-status")
    item = resp.json()["data"]["items"][0]
    assert item["state"] == "working"
    assert item["phase"] == PHASE_GENERATING  # 降级粗粒度
    assert item["question_snippet"] is None


def test_live_status_disabled_is_offline_even_with_registry_entry(monkeypatch):
    _reset_registry()
    registry.set_working(2, PHASE_GENERATING, "q")
    db = FakeDb(
        specialists=[
            FakeSpecialist(1, "A", "active"),
            FakeSpecialist(2, "B", "disabled"),
            FakeSpecialist(3, "C", "draft"),
        ],
        today_rows=[], active_rows=[],
    )
    resp = _client(db).get("/api/v1/specialists/live-status")
    by_id = {i["id"]: i for i in resp.json()["data"]["items"]}
    assert by_id[1]["state"] == "idle"
    assert by_id[2]["state"] == "offline"
    assert by_id[3]["state"] == "offline"
    assert resp.json()["data"]["summary"] == {"working": 0, "idle": 1, "offline": 2}


def test_live_status_requires_auth():
    resp = TestClient(app).get("/api/v1/specialists/live-status")
    assert resp.status_code == 401
```

- [ ] **Step 2: 运行验证失败**

Run: `cd "D:/gongsi/medical system/services/specialist-service" && python -m pytest tests/test_live_status.py -v`
Expected: FAIL（404 —— 路由不存在）

- [ ] **Step 3: 实现接口**

在 `specialists.py` 中 `list_specialists` 之后、`get_specialist`（`@router.get("/{specialist_id}")`）**之前**插入：

```python
@router.get("/live-status")
async def get_live_status(
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """数字员工办公室实时状态（web 后台 3s/5s 轮询）。

    状态推导：draft/disabled → offline；注册表有记录 → working（带阶段）；
    注册表空但 5 分钟内有过对话 → working（粗粒度 generating）；否则 idle。
    """
    from datetime import datetime, timedelta
    from sqlalchemy import func
    from app.models.conversation import Conversation
    from app.core.activity_registry import registry, PHASE_TEXT, PHASE_GENERATING

    specialists = db.query(Specialist).all()
    now = datetime.utcnow()
    today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    recent_cutoff = now - timedelta(minutes=5)

    # 今日对话数（role='user' 口径与 stats 一致）
    today_rows = db.query(
        Conversation.specialist_id, func.count(Conversation.id),
    ).filter(
        Conversation.role == "user",
        Conversation.created_at >= today_start,
    ).group_by(Conversation.specialist_id).all()
    today_count = {sid: cnt for sid, cnt in today_rows}

    # 最近活跃时间（任意 role 最后一条）
    active_rows = db.query(
        Conversation.specialist_id, func.max(Conversation.created_at),
    ).group_by(Conversation.specialist_id).all()
    last_active = {sid: ts for sid, ts in active_rows}

    items = []
    summary = {"working": 0, "idle": 0, "offline": 0}
    for s in specialists:
        snap = registry.get(s.id)
        if s.status in ("draft", "disabled"):
            state, phase = "offline", None
        elif snap is not None:
            state, phase = "working", snap.phase
        elif last_active.get(s.id) is not None and last_active[s.id] >= recent_cutoff:
            state, phase = "working", PHASE_GENERATING
        else:
            state, phase = "idle", None
        summary[state] += 1
        items.append({
            "id": s.id,
            "name": s.name,
            "lifecycle": s.status,
            "state": state,
            "phase": phase,
            "phase_text": PHASE_TEXT.get(phase) if phase else None,
            "phase_since": snap.phase_since.isoformat() if snap else None,
            "question_snippet": snap.question_snippet if snap else None,
            "today_conversations": today_count.get(s.id, 0),
            "last_active_at": last_active.get(s.id).isoformat() if last_active.get(s.id) else None,
        })
    return success({"items": items, "summary": summary})
```

**坑位提示**：`/live-status` 必须位于 `/{specialist_id}` 之前，否则 FastAPI 把 `live-status` 当 `specialist_id: int` 匹配 → 422。若测试中 FakeDb.query 的 conversations 分发逻辑写不顺，可改用计数器：`self._conv_queries = 0`，第 1 次调用返回 today stub、第 2 次返回 active stub（断言以「结果正确」为准，替身细节自由调整）。

- [ ] **Step 4: 运行验证通过**

Run: `cd "D:/gongsi/medical system/services/specialist-service" && python -m pytest tests/ -v`
Expected: 全部 PASS（含既有 12 个测试文件，确认路由顺序没破坏 `/{specialist_id}` 系列）

- [ ] **Step 5: 提交**

```bash
cd "D:/gongsi/medical system"
git add services/specialist-service/app/api/specialists.py services/specialist-service/tests/test_live_status.py
git commit -m "feat: 数字专员实时状态接口 live-status（注册表+降级推断）

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

---

### Task 4: 前端类型与 API 封装

**Files:**
- Modify: `web/src/types/index.ts`（专员区块后追加新类型）
- Modify: `web/src/services/specialist.ts`（加 `liveStatus`）

**Interfaces:**
- Consumes: Task 3 的响应结构
- Produces: `LiveStatusItem` / `LiveSummary` / `LiveStatus` 类型；`specialistAPI.liveStatus(): Promise<ApiResponse<LiveStatus>>`

- [ ] **Step 1: 加类型**

`web/src/types/index.ts`，`SpecialistStats` 之后追加：

```ts
// ========== 数字员工办公室（live-status）==========
export type SpecialistLiveState = 'working' | 'idle' | 'offline';
export type SpecialistPhase = 'compliance_precheck' | 'generating' | 'compliance_review';

/** 与后端 GET /specialists/live-status 对齐 */
export interface LiveStatusItem {
  id: number;
  name: string;
  lifecycle: 'draft' | 'active' | 'disabled';
  state: SpecialistLiveState;
  phase: SpecialistPhase | null;
  phase_text: string | null;
  phase_since: string | null;
  question_snippet: string | null;
  today_conversations: number;
  last_active_at: string | null;
}

export interface LiveSummary {
  working: number;
  idle: number;
  offline: number;
}

export interface LiveStatus {
  items: LiveStatusItem[];
  summary: LiveSummary;
}
```

- [ ] **Step 2: 加 API 方法**

`web/src/services/specialist.ts`，import 加 `LiveStatus`，对象里加：

```ts
  liveStatus: () =>
    client.get<ApiResponse<LiveStatus>>('/specialists/live-status'),
```

- [ ] **Step 3: 构建验证**

Run: `cd "D:/gongsi/medical system/web" && npm run build`
Expected: `tsc -b && vite build` 成功，无类型错误

- [ ] **Step 4: 提交**

```bash
cd "D:/gongsi/medical system"
git add web/src/types/index.ts web/src/services/specialist.ts
git commit -m "feat(web): live-status 类型与 API 封装

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

---

### Task 5: 状态常量 + 办公室视图组件 + 页面切换壳

**Files:**
- Create: `web/src/constants/specialist.ts`（STATUS_MAP 从 SpecialistList 迁出，两处共用）
- Create: `web/src/pages/Specialist/SpecialistOffice.tsx`（办公室视图：工位网格 + 3s 轮询 + 状态动画 + 悬停操作）
- Modify: `web/src/pages/Specialist/SpecialistList.tsx`（Segmented 切换「办公室 | 表格」，表格逻辑原封不动）

**Interfaces:**
- Consumes: Task 4 的 `LiveStatusItem` / `specialistAPI.liveStatus()`；既有 `SpecialistForm` / `SpecialistDataDrawer` / `STATUS_MAP`
- Produces: `SpecialistOffice` 组件，props：`{ onAdd: () => void; onEdit: (r: Specialist) => void; onToggleStatus: (r: Specialist) => void; onViewData: (r: Specialist) => void }`

- [ ] **Step 1: 迁出 STATUS_MAP**

`web/src/constants/specialist.ts`：

```ts
/** 专员生命周期状态 → Tag 颜色/文案（SpecialistList 与 SpecialistOffice 共用） */
export const STATUS_MAP: Record<string, { color: string; text: string }> = {
  draft: { color: 'default', text: '草稿' },
  active: { color: 'green', text: '正式' },
  disabled: { color: 'red', text: '停用' },
};
```

`SpecialistList.tsx`：删除本地 `STATUS_MAP` 定义，改为 `import { STATUS_MAP } from '../../constants/specialist';`

- [ ] **Step 2: 办公室视图组件**

`web/src/pages/Specialist/SpecialistOffice.tsx`：

```tsx
import { useEffect, useRef, useState } from 'react';
import {
  Row, Col, Card, Empty, Spin, Switch, Button, Space, Tag,
} from 'antd';
import {
  RobotOutlined, CoffeeOutlined, PoweroffOutlined,
  PlusOutlined, ReloadOutlined,
} from '@ant-design/icons';
import dayjs from 'dayjs';
import { specialistAPI } from '../../services/specialist';
import { STATUS_MAP } from '../../constants/specialist';
import type { LiveStatus, LiveStatusItem, Specialist } from '../../types';

const STATE_META: Record<LiveStatusItem['state'], { label: string; color: string }> = {
  working: { label: '工作中', color: '#1677ff' },
  idle: { label: '空闲中', color: '#faad14' },
  offline: { label: '离线', color: '#bfbfbf' },
};

const POLL_INTERVAL_MS = 3000;

/** 工位卡片：头像光晕 + 状态区 + 底部统计 + 悬停操作 */
function WorkstationCard({
  item, index, onEdit, onToggleStatus, onViewData,
}: {
  item: LiveStatusItem;
  index: number;
  onEdit: () => void;
  onToggleStatus: () => void;
  onViewData: () => void;
}) {
  const meta = STATE_META[item.state];
  const idle = item.state === 'idle';
  const offline = item.state === 'offline';
  return (
    <Card
      size="small"
      hoverable
      onClick={onViewData}
      style={{
        animationDelay: `${index * 120}ms`,
        borderColor: offline ? '#f0f0f0' : meta.color + '55',
      }}
    >
      <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
        <div
          style={{
            position: 'relative', width: 40, height: 40, borderRadius: 20, flexShrink: 0,
            display: 'flex', alignItems: 'center', justifyContent: 'center',
            background: offline ? '#f5f5f5' : meta.color + '1a',
            boxShadow: offline ? 'none' : `0 0 12px ${meta.color}66`,
            animation: offline ? 'none' : idle ? 'office-float 3s ease-in-out infinite' : 'office-breathe 2s ease-in-out infinite',
          }}
        >
          <RobotOutlined style={{ fontSize: 20, color: offline ? '#bfbfbf' : meta.color }} />
        </div>
        <div style={{ flex: 1, minWidth: 0 }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
            <span style={{ fontWeight: 600, fontSize: 14 }}>{item.name}</span>
            {STATUS_MAP[item.lifecycle] && (
              <Tag color={STATUS_MAP[item.lifecycle].color} style={{ marginInlineEnd: 0 }}>
                {STATUS_MAP[item.lifecycle].text}
              </Tag>
            )}
          </div>
          <div style={{ fontSize: 12, color: meta.color, marginTop: 4, display: 'flex', alignItems: 'center', gap: 6 }}>
            {item.state === 'working' && <Spin size="small" />}
            {item.state === 'idle' && <CoffeeOutlined />}
            {item.state === 'offline' && <PoweroffOutlined />}
            <span style={{ overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
              {item.state === 'working'
                ? item.phase_text ?? '正在工作'
                : meta.label}
            </span>
          </div>
        </div>
      </div>
      {item.state === 'working' && item.question_snippet && (
        <div style={{ marginTop: 8, fontSize: 12, color: '#8c8c8c', lineHeight: 1.5 }}>
          正在回答：{item.question_snippet}…
        </div>
      )}
      <div style={{ marginTop: 8, paddingTop: 8, borderTop: '1px solid #f5f5f5', display: 'flex', justifyContent: 'space-between', fontSize: 12, color: '#8c8c8c' }}>
        <span>今日 {item.today_conversations} 次</span>
        <span>{item.last_active_at ? dayjs(item.last_active_at).format('MM-DD HH:mm') : '从未'}</span>
      </div>
      <div style={{ marginTop: 6 }} onClick={(e) => e.stopPropagation()}>
        <Space size={12}>
          <a onClick={onViewData}>数据</a>
          <a onClick={onEdit}>编辑</a>
          <a style={{ color: item.lifecycle === 'active' ? '#ff4d4f' : '#52c41a' }} onClick={onToggleStatus}>
            {item.lifecycle === 'active' ? '停用' : '启用'}
          </a>
        </Space>
      </div>
    </Card>
  );
}

/** 数字员工办公室：3s 轮询 live-status，卡片化展示每个专员在干什么 */
export default function SpecialistOffice({
  onAdd, onEdit, onToggleStatus, onViewData,
}: {
  onAdd: () => void;
  onEdit: (r: Specialist) => void;
  onToggleStatus: (r: Specialist) => void;
  onViewData: (r: Specialist) => void;
}) {
  const [live, setLive] = useState<LiveStatus | null>(null);
  const [autoPoll, setAutoPoll] = useState(true);
  const [loading, setLoading] = useState(false);
  const timerRef = useRef<number | null>(null);

  const load = async () => {
    try {
      setLoading(true);
      const res = await specialistAPI.liveStatus();
      setLive(res.data.data);
    } catch {
      /* 轮询失败静默，保留上一次数据；卡片按 lifecycle 降级展示 */
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    load();
    if (autoPoll) {
      timerRef.current = window.setInterval(load, POLL_INTERVAL_MS);
    }
    return () => {
      if (timerRef.current !== null) window.clearInterval(timerRef.current);
    };
  }, [autoPoll]);

  const summary = live?.summary ?? { working: 0, idle: 0, offline: 0 };
  const items = live?.items ?? [];

  return (
    <div>
      <style>{`
        @keyframes office-breathe { 0%,100% { transform: scale(1); } 50% { transform: scale(1.08); } }
        @keyframes office-float { 0%,100% { transform: translateY(0); } 50% { transform: translateY(-3px); } }
      `}</style>
      <div style={{ display: 'flex', alignItems: 'center', gap: 16, marginBottom: 16, flexWrap: 'wrap' }}>
        <Space size={8}>
          <Tag color="blue" style={{ marginInlineEnd: 0 }}>工作中 {summary.working}</Tag>
          <Tag color="gold" style={{ marginInlineEnd: 0 }}>空闲 {summary.idle}</Tag>
          <Tag style={{ marginInlineEnd: 0 }}>离线 {summary.offline}</Tag>
        </Space>
        <span style={{ fontSize: 12, color: '#8c8c8c' }}>3s 自动刷新</span>
        <Switch size="small" checked={autoPoll} onChange={setAutoPoll} />
        <Button size="small" icon={<ReloadOutlined />} loading={loading} onClick={load}>刷新</Button>
        <Button type="primary" size="small" icon={<PlusOutlined />} onClick={onAdd}>新增专员</Button>
      </div>
      {items.length === 0 ? (
        <Empty description="暂无数字专员，点击右上角「新增专员」创建" style={{ padding: 60 }} />
      ) : (
        <Row gutter={[16, 16]}>
          {items.map((item, index) => (
            <Col key={item.id} xs={12} sm={8} lg={6}>
              <WorkstationCard
                item={item}
                index={index}
                onEdit={() => {
                  const sp = items.find((i) => i.id === item.id);
                  if (sp) onEdit({ ...sp, created_at: '' } as Specialist);
                }}
                onToggleStatus={() => {
                  const sp = items.find((i) => i.id === item.id);
                  if (sp) onToggleStatus({ ...sp, created_at: '' } as Specialist);
                }}
                onViewData={() => {
                  const sp = items.find((i) => i.id === item.id);
                  if (sp) onViewData({ ...sp, created_at: '' } as Specialist);
                }}
              />
            </Col>
          ))}
        </Row>
      )}
    </div>
  );
}
```

**注意**：`LiveStatusItem` 与 `Specialist` 字段不完全同构（live 的 lifecycle ↔ Specialist.status），转换时补 `created_at: ''`（类型断言用）。`onEdit`/`onToggleStatus`/`onViewData` 需要的是 `Specialist`，父组件拿到的是 live 条目，这里已做最小适配。若觉得别扭，可让回调参数直接用 `LiveStatusItem`，父组件内再映射（本计划采用「组件内映射 + 断言」，改动最小）。

- [ ] **Step 3: 页面切换壳**

`web/src/pages/Specialist/SpecialistList.tsx` 改造（原表格逻辑一行不动，只加视图状态与回调转发）：

```tsx
import { Segmented } from 'antd';  // 加 import
import SpecialistOffice from './SpecialistOffice';  // 加 import
```

组件内加：

```tsx
  const [view, setView] = useState<'office' | 'table'>('office');
```

两个 StatCard 行之后、ProTable 之前插入（ProTable 外包 `{view === 'table' && (...)}`，工具条加 Segmented）：

```tsx
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 16 }}>
        <Segmented
          value={view}
          onChange={(v) => setView(v as 'office' | 'table')}
          options={[
            { label: '数字员工办公室', value: 'office' },
            { label: '表格视图', value: 'table' },
          ]}
        />
      </div>
      {view === 'office' ? (
        <SpecialistOffice
          onAdd={() => { setEditing(null); setFormOpen(true); }}
          onEdit={(r) => { setEditing(r); setFormOpen(true); }}
          onToggleStatus={toggleStatus}
          onViewData={(r) => setDataView(r)}
        />
      ) : (
        <ProTable ...原样... />
      )}
```

（ProTable 的 `toolBarRender` 里原「新增专员」按钮保留；办公室视图的新增在 SpecialistOffice 头部。ProTable 的 JSX 本身一字不改——只把现有 `<ProTable<Specialist> ... />` 整个包进 `{view === 'table' && ( ... )}` 条件里，原 `request`/`columns`/`toolBarRender`/`actionRef` 全部保持原样。）

- [ ] **Step 4: 构建验证**

Run: `cd "D:/gongsi/medical system/web" && npm run build`
Expected: 构建通过。启动 `npm run dev` 打开 `http://localhost:3000/specialist/list`（后端需跑起来，见 Task 7），确认：默认办公室视图、切表格正常、3s 轮询有请求、无专员时空态、卡片 hover 出操作。

- [ ] **Step 5: 提交**

```bash
cd "D:/gongsi/medical system"
git add web/src/constants/specialist.ts web/src/pages/Specialist/SpecialistOffice.tsx web/src/pages/Specialist/SpecialistList.tsx
git commit -m "feat(web): 数字员工办公室视图（工位卡片+3s轮询+状态动画），可切回表格

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

---

### Task 6: 仪表盘顶部状态条

**Files:**
- Create: `web/src/components/LiveStatusStrip.tsx`
- Modify: `web/src/pages/Dashboard/index.tsx`（KPI Row 前插入组件）

**Interfaces:**
- Consumes: Task 4 的 `specialistAPI.liveStatus()` / `LiveStatusItem`
- Produces: `<LiveStatusStrip />` 自轮询组件（5s），点击跳转 `/specialist/list`

- [ ] **Step 1: 写组件**

`web/src/components/LiveStatusStrip.tsx`：

```tsx
import { useEffect, useRef, useState } from 'react';
import { Tooltip } from 'antd';
import { RobotOutlined, ArrowRightOutlined } from '@ant-design/icons';
import { useNavigate } from 'react-router-dom';
import { specialistAPI } from '../services/specialist';
import type { LiveStatus, LiveStatusItem } from '../types';

const MAX_STATIONS = 8;
const POLL_INTERVAL_MS = 5000;

const STATE_COLOR: Record<LiveStatusItem['state'], string> = {
  working: '#1677ff',
  idle: '#faad14',
  offline: '#bfbfbf',
};

/** 仪表盘顶部「数字员工实时状态」条：迷你工位 + 汇总 + 跳转 */
export default function LiveStatusStrip() {
  const [live, setLive] = useState<LiveStatus | null>(null);
  const timerRef = useRef<number | null>(null);
  const navigate = useNavigate();

  useEffect(() => {
    const load = async () => {
      try {
        const res = await specialistAPI.liveStatus();
        setLive(res.data.data);
      } catch {
        /* 静默：接口不可达时隐藏状态条 */
      }
    };
    load();
    timerRef.current = window.setInterval(load, POLL_INTERVAL_MS);
    return () => {
      if (timerRef.current !== null) window.clearInterval(timerRef.current);
    };
  }, []);

  if (!live) return null;
  const { items, summary } = live;
  const shown = items.slice(0, MAX_STATIONS);
  const rest = items.length - shown.length;

  return (
    <div style={{
      display: 'flex', alignItems: 'center', gap: 12, marginBottom: 16,
      padding: '10px 16px', background: '#fafafa', borderRadius: 8,
      border: '1px solid #f0f0f0', fontSize: 13,
    }}>
      <span style={{ fontWeight: 600, flexShrink: 0 }}>数字员工</span>
      <div style={{ display: 'flex', alignItems: 'center', gap: 6, flex: 1, flexWrap: 'wrap' }}>
        {shown.map((item) => (
          <Tooltip
            key={item.id}
            title={`${item.name} · ${item.phase_text ?? (item.state === 'working' ? '工作中' : item.state === 'idle' ? '空闲中' : '离线')}${item.question_snippet ? ` · ${item.question_snippet}` : ''}`}
          >
            <span
              onClick={() => navigate('/specialist/list')}
              style={{
                display: 'inline-flex', alignItems: 'center', gap: 5, cursor: 'pointer',
                padding: '2px 8px', borderRadius: 12, background: '#fff',
                border: `1px solid ${STATE_COLOR[item.state]}44`,
              }}
            >
              <RobotOutlined style={{ color: STATE_COLOR[item.state] }} />
              {item.name}
            </span>
          </Tooltip>
        ))}
        {rest > 0 && <span style={{ color: '#8c8c8c' }}>+{rest}</span>}
      </div>
      <span style={{ color: '#8c8c8c', flexShrink: 0 }}>
        工作中 {summary.working} · 空闲 {summary.idle} · 离线 {summary.offline}
      </span>
      <a style={{ flexShrink: 0 }} onClick={() => navigate('/specialist/list')}>
        查看全部 <ArrowRightOutlined />
      </a>
    </div>
  );
}
```

- [ ] **Step 2: 接入仪表盘**

`web/src/pages/Dashboard/index.tsx`：顶部 `import LiveStatusStrip from '../../components/LiveStatusStrip';`，`<PageContainer ...>` 开标签后、第一个 `<Row>` 前插入：

```tsx
      <LiveStatusStrip />
```

- [ ] **Step 3: 构建验证**

Run: `cd "D:/gongsi/medical system/web" && npm run build`
Expected: 构建通过。dev 打开 `/dashboard`：状态条在 KPI 卡上方，8 个以内显示工位，点击跳转专员页。

- [ ] **Step 4: 提交**

```bash
cd "D:/gongsi/medical system"
git add web/src/components/LiveStatusStrip.tsx web/src/pages/Dashboard/index.tsx
git commit -m "feat(web): 仪表盘顶部数字员工状态条（迷你工位+汇总+跳转）

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

---

### Task 7: 端到端手工验证

**Files:** 无代码改动；验证 runbook

- [ ] **Step 1: 起后端**

```bash
cd "D:/gongsi/medical system"
docker-compose up -d postgres redis
cd services/specialist-service && python -m uvicorn app.main:app --port 8001 --reload
cd services/gateway && python -m uvicorn app.main:app --port 8000
```

- [ ] **Step 2: 起前端并登录**

```bash
cd web && npm run dev   # http://localhost:3000
# 管理员账号：scripts/seed_admin.py 生成（或 --phone 指定）
```

- [ ] **Step 3: 验证办公室动态流转**

1. 打开 `/specialist/list` → 默认「数字员工办公室」视图，卡片按状态分布正确（汇总数与 summary 一致）
2. 用移动端/接口发起一轮对话（`POST /api/v1/specialists/{id}/chat` 或 WS），观察对应卡片在 3 秒内变为「工作中」且动作按 预检 → 生成 → 审核 流转
3. 对话结束后卡片回到「空闲中」
4. 停用一个专员 → 该卡片立即变「离线」
5. 打开 `/dashboard` → 顶部状态条同步显示，点击跳转回专员页
6. 重启 specialist-service（模拟注册表清空）→ 页面不闪全离线，有近期对话的专员仍显示工作中

- [ ] **Step 4: 回归确认**

```bash
cd services/specialist-service && python -m pytest tests/ -v   # 全绿
cd web && npm run build                                        # 构建通过
```

- [ ] **Step 5: 提交收尾说明**

无新提交（验证中发现的问题按 bug 修复流程处理）；在 git log 确认 6 个功能提交（Task 1-6）齐全。

---

## 自审记录

- **Spec 覆盖**：后端注册表（T1）/ 埋点（T2）/ 接口（T3）、前端类型与 API（T4）、办公室视图 + 切换（T5）、仪表盘状态条（T6）、降级与错误处理（T2 finally / T3 降级推断 / T5-T6 静默失败）、测试（T1-T3 单测 + T7 手工）——规格全项有任务对应。
- **占位符**：无 TBD；所有步骤含可粘贴代码。
- **类型一致性**：`PHASE_*` 常量名在 T1 定义、T2/T3 引用一致；`LiveStatusItem` 字段名与后端响应逐字段对齐（T3 产出 → T4 类型 → T5/T6 消费）；`registry.set_working/set_idle/get/all` 签名 T1 定义、T2 埋点、T3 读取一致。
- **已知风险**：T3 的 FakeDb 双聚合 stub 分发是本计划最易踩的坑，已注明计数器替代方案；`/live-status` 路由顺序已显式约束。
