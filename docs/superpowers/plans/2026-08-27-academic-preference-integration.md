# 学术偏好接入 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 把医生的学术偏好（interest_areas / preferred_doc_type / closed）接入医学问答（检索排序）、分身对话（prompt 注入）、学术卡片推送（兴趣匹配标记），守住"医学事实零扰动"红线。

**Architecture:** 新增 `preference_ranking.py` 共享工具模块（get_profile / get_profiles_batch / reorder_results / matched_interest / preference_context），三条链路各自调用；`closed=true` 或偏好为空统一回退基线。加迁移 026 给 `card_push_records` 补 `matched_interest` 列。

**Tech Stack:** Python / FastAPI / SQLAlchemy / PostgreSQL / pytest（specialist-service 既有测试体系）

**Spec:** `docs/superpowers/specs/2026-08-27-academic-preference-integration-design.md`

## Global Constraints

- **事实零扰动**：re-rank 不改结果集合、prompt 注入必带「不得改变医学事实、不得省略关键信息」约束
- **基线回退**：`closed=true` / 偏好为空 / 读取异常 → 一律回退（原序 / false / 空串），不得阻塞业务
- **合规保留**：既有 `check_compliance` fail-closed、流式门禁、审计全部不动
- **测试目录**：specialist-service 测试必须在 `services/specialist-service` 目录下运行（sys.path 依赖 cwd）
- **迁移格式**：沿用 `scripts/migrations/0XX_*.sql` 的 `\set ON_ERROR_STOP on` + 注释头风格，并同步 `scripts/init_db.sql`

---

### Task 1: preference_ranking 共享模块

**Files:**
- Create: `services/specialist-service/app/core/preference_ranking.py`
- Test: `services/specialist-service/tests/test_preference_ranking.py`

**Interfaces:**
- Consumes: `shared/models/doctor_profile.py` 的 `DoctorProfile`（doctor_id / interest_areas JSONB / preferred_doc_type / preferred_style / closed）
- Produces（后续任务依赖）:
  - `get_profile(db: Session, doctor_id: int) -> Optional[DoctorProfile]`
  - `get_profiles_batch(db: Session, doctor_ids: List[int]) -> Dict[int, Optional[DoctorProfile]]`
  - `reorder_results(results: List[Dict], profile: Optional[DoctorProfile]) -> List[Dict]`
  - `matched_interest(card_title: str, profile: Optional[DoctorProfile]) -> bool`
  - `preference_context(profile: Optional[DoctorProfile]) -> str`

- [ ] **Step 1: 写失败测试**

```python
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
```

- [ ] **Step 2: 运行确认失败**

Run: `cd services/specialist-service && python -m pytest tests/test_preference_ranking.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'app.core.preference_ranking'`

- [ ] **Step 3: 实现核心模块**

```python
# services/specialist-service/app/core/preference_ranking.py
"""医生学术偏好 → 个性化排序/提示的共享工具（spec 2026-08-27）。

红线：医学事实零扰动。reorder_results 只改顺序不改集合；
preference_context 必带「不得改变医学事实」硬约束。
closed=true / 偏好为空 / 读取异常 → 一律回退基线。
"""
from typing import Dict, List, Optional

from sqlalchemy.orm import Session

from shared.models.doctor_profile import DoctorProfile


def get_profile(db: Session, doctor_id: int) -> Optional[DoctorProfile]:
    """读医生偏好画像；closed 或空兴趣 → None（调用方回退基线）。"""
    p = db.query(DoctorProfile).filter(DoctorProfile.doctor_id == doctor_id).first()
    return p if (p and not p.closed and p.interest_areas) else None


def get_profiles_batch(db: Session, doctor_ids: List[int]) -> Dict[int, Optional[DoctorProfile]]:
    """批量读（IN 一次查询），未查到的医生不在 dict（调用方按无偏好处理）。"""
    if not doctor_ids:
        return {}
    rows = db.query(DoctorProfile).filter(DoctorProfile.doctor_id.in_(doctor_ids)).all()
    return {r.doctor_id: r for r in rows if r and not r.closed and r.interest_areas}


def _areas(profile) -> List[str]:
    return [str(a).lower() for a in (profile.interest_areas or []) if a]


def reorder_results(results: List[Dict], profile: Optional[DoctorProfile]) -> List[Dict]:
    """按偏好稳定重排（集合不变只变顺序）；closed/空/无 profile 原序返回。"""
    if not profile or not results:
        return results
    areas = _areas(profile)

    def score(r: Dict) -> int:
        text = f"{r.get('title', '')} {r.get('content', '')}".lower()
        s = sum(1 for a in areas if a and a in text)
        dt = str(r.get("doc_type") or "")
        if profile.preferred_doc_type and dt and dt == profile.preferred_doc_type:
            s += 1
        return s

    return sorted(results, key=lambda r: -score(r))  # sorted 稳定：同权重保持原序


def matched_interest(card_title: str, profile: Optional[DoctorProfile]) -> bool:
    """卡片标题是否命中医生兴趣领域；closed/无 profile → False。"""
    if not profile or not card_title:
        return False
    areas = _areas(profile)
    t = str(card_title).lower()
    return any(a and a in t for a in areas)


def preference_context(profile: Optional[DoctorProfile]) -> str:
    """偏好 → prompt 注入片段（含事实约束）；closed/空 → 空串。"""
    if not profile:
        return ""
    parts = []
    areas = [str(a) for a in (profile.interest_areas or []) if a]
    if areas:
        parts.append(f"该医生主要关注领域：{'、'.join(areas)}")
    if profile.preferred_style:
        parts.append(f"回答风格偏好：{profile.preferred_style}")
    if not parts:
        return ""
    return (
        "（医生学术偏好上下文——仅供组织回答侧重，"
        "不得改变医学事实、不得省略关键信息：" + "；".join(parts) + "）"
    )
```

- [ ] **Step 4: 运行确认通过**

Run: `cd services/specialist-service && python -m pytest tests/test_preference_ranking.py -v`
Expected: 7 passed

- [ ] **Step 5: Commit**

```bash
git add services/specialist-service/app/core/preference_ranking.py services/specialist-service/tests/test_preference_ranking.py
git commit -m "feat(specialist): 学术偏好排序共享模块（reorder/matched/context，closed 回退基线）"
```

---

### Task 2: 迁移 026 + CardPushRecord 模型加列

**Files:**
- Create: `scripts/migrations/026_card_push_matched_interest.sql`
- Modify: `shared/models/academic.py`（CardPushRecord 加 `matched_interest`）
- Modify: `scripts/init_db.sql`（card_push_records 建表加列）
- Test: `services/specialist-service/tests/test_card_pushes.py`（不新增，用既有用例确认无回归）

**Interfaces:**
- Consumes: 无（前置 Task 1 的模型不依赖）
- Produces: `CardPushRecord.matched_interest: Optional[bool]`（Task 5 写入）

- [ ] **Step 1: 写迁移文件**

```sql
-- 026_card_push_matched_interest.sql
-- 学术偏好接入（2026-08-27 spec）：推送记录标兴趣匹配（matched_interest）
-- 可空：历史推送不填充，仅新推送写入；不改变推送行为、不丢触达。
-- 用法：docker exec -i medagent-postgres psql -U medagent medagent < scripts/migrations/026_card_push_matched_interest.sql

\set ON_ERROR_STOP on

ALTER TABLE card_push_records ADD COLUMN matched_interest BOOLEAN NULL;
```

- [ ] **Step 2: 模型加列**

`shared/models/academic.py` 的 `CardPushRecord` 加（在 `feedback = Column(String(500))` 之后）：

```python
    # 学术偏好接入（2026-08-27）：该医生兴趣是否匹配卡片主题；可空（历史推送不填充）
    matched_interest = Column(Boolean)
```

- [ ] **Step 3: init_db.sql 同步**

在 `scripts/init_db.sql` 的 `card_push_records` 建表里（`feedback VARCHAR(500)` 行附近）加：

```sql
    matched_interest BOOLEAN,  -- 学术偏好接入（2026-08-27）：医生兴趣是否匹配卡片主题；可空
```

- [ ] **Step 4: 确认既有卡片测试无回归**

Run: `cd services/specialist-service && python -m pytest tests/test_card_pushes.py -q`
Expected: 全部通过（matched_interest 可空，历史用例不引用它）

- [ ] **Step 5: Commit**

```bash
git add scripts/migrations/026_card_push_matched_interest.sql shared/models/academic.py scripts/init_db.sql
git commit -m "feat(specialist): 迁移 026 card_push_records 加 matched_interest（兴趣匹配标记）"
```

---

### Task 3: 医学问答 re-rank

**Files:**
- Modify: `services/specialist-service/app/api/medical.py`（`medical_qa` 内 `_retrieve` 后）
- Test: `services/specialist-service/tests/test_medical_qa.py`

**Interfaces:**
- Consumes: `preference_ranking.get_profile(db, doctor_id)`、`preference_ranking.reorder_results(results, profile)`
- Produces: 无（内部行为：引用片段顺序随偏好，回答/qwen/JSON 契约不变）

- [ ] **Step 1: 写失败测试**

在 `tests/test_medical_qa.py` 加（mock `reorder_results` 断言被调用且传入当前医生 id）：

```python
def test_medical_qa_reranks_by_profile(monkeypatch, fresh_state):
    from app.core import preference_ranking
    captured = {}
    def fake_get_profile(db, doctor_id):
        captured["doctor_id"] = doctor_id
        return None  # 无偏好 → reorder 原序（仍走 reorder 调用）
    def fake_reorder(results, profile):
        captured["called"] = True
        return results
    monkeypatch.setattr(preference_ranking, "get_profile", fake_get_profile)
    monkeypatch.setattr(preference_ranking, "reorder_results", fake_reorder)
    resp = client.post("/api/v1/medical/qa", json={"question": "肿瘤治疗"}, headers=_token(2, "doctor"))
    assert resp.status_code == 200
    assert captured.get("called") is True
    assert captured.get("doctor_id") == 2
```

- [ ] **Step 2: 运行确认失败**

Run: `cd services/specialist-service && python -m pytest tests/test_medical_qa.py -k rerank -v`
Expected: FAIL（`_retrieve` 后未调用 reorder_results）

- [ ] **Step 3: 实现**

`medical_qa` 里 `retrieved = await _retrieve(question)` 之后加：

```python
    # 学术偏好接入（2026-08-27 spec）：按医生偏好 re-rank 检索片段（只变顺序，
    # 回答/JSON 契约不变；closed/无偏好由 reorder_results 内部回退原序）
    from app.core import preference_ranking
    profile = preference_ranking.get_profile(db, current_user["id"])
    results = preference_ranking.reorder_results(retrieved.get("results") or [], profile)
```

（把原有 `results = retrieved.get("results") or []` 替换为上面两行；后续 `_build_prompt(question, results)` 不变。）

- [ ] **Step 4: 运行确认通过 + 既有用例无回归**

Run: `cd services/specialist-service && python -m pytest tests/test_medical_qa.py -q`
Expected: 全部通过（含新 rerank 用例）

- [ ] **Step 5: Commit**

```bash
git add services/specialist-service/app/api/medical.py services/specialist-service/tests/test_medical_qa.py
git commit -m "feat(specialist): 医学问答按医生学术偏好 re-rank 检索片段"
```

---

### Task 4: 分身对话 prompt 注入

**Files:**
- Modify: `services/specialist-service/app/core/answer_generator.py`（`generate_stream` 开头）
- Test: `services/specialist-service/tests/test_answer_generator_phases.py`（既有生成器测试文件）

**Interfaces:**
- Consumes: `preference_ranking.get_profile(db, user_id)`、`preference_ranking.preference_context(profile)`
- Produces: 无（注入后的 prompt 同时喂给百炼 chat_stream 与降级 qwen）

- [ ] **Step 1: 写失败测试**

在生成器测试文件加（mock `bailian.chat_stream` 断言收到的 prompt 含偏好上下文）：

```python
def test_generate_stream_injects_preference_context(monkeypatch):
    from app.core import preference_ranking
    from app.core.answer_generator import AnswerGenerator
    captured = {}
    def fake_get_profile(db, user_id):
        class P:
            interest_areas = ["肿瘤"]
            preferred_doc_type = None
            preferred_style = "简洁"
            closed = False
        return P()
    class FakeBailian:
        async def chat_stream(self, app_id, prompt, session_id=None):
            captured["prompt"] = prompt
            yield {"type": "delta", "text": "好的"}
            yield {"type": "done", "text": "好的"}
    monkeypatch.setattr(preference_ranking, "get_profile", fake_get_profile)
    gen = AnswerGenerator()
    gen.bailian = FakeBailian()
    async def run():
        frames = [f async for f in gen.generate_stream(
            question="肿瘤怎么治疗", specialist=_SPEC, user_id=2, db=None)]
    import asyncio
    asyncio.run(run())
    assert "不得改变医学事实" in captured["prompt"]
    assert "肿瘤" in captured["prompt"]
```

（`_SPEC` 用测试文件既有的 `Specialist` 桩；无既有桩则用 `types.SimpleNamespace(id=1, bailian_app_id="x")`。）

- [ ] **Step 2: 运行确认失败**

Run: `cd services/specialist-service && python -m pytest tests/test_answer_generator_phases.py -k preference -v`
Expected: FAIL（prompt 未含偏好上下文）

- [ ] **Step 3: 实现**

`generate_stream` 方法体开头（`request_id = str(uuid.uuid4())` 之前或之后）注入：

```python
        # 学术偏好接入（2026-08-27 spec）：偏好作为 prompt 上下文注入（带事实约束）。
        # 百炼路径与降级 qwen 路径共用此 question；closed/无偏好 → 空片段不注入。
        from app.core import preference_ranking
        pref = preference_ranking.preference_context(
            preference_ranking.get_profile(db, user_id) if db else None
        )
        if pref:
            question = f"{question}\n{pref}"
```

（`db` 在 generate_stream 已作参数；`_fallback_generate` 内部用注入后的 question 字符串——传入参数即可。）

- [ ] **Step 4: 运行确认通过 + 既有生成器用例无回归**

Run: `cd services/specialist-service && python -m pytest tests/ -q -k "stream or generate or preference"`
Expected: 全部通过

- [ ] **Step 5: Commit**

```bash
git add services/specialist-service/app/core/answer_generator.py services/specialist-service/tests/test_answer_generator_phases.py
git commit -m "feat(specialist): 分身对话 prompt 注入医生学术偏好（含事实约束）"
```

---

### Task 5: 学术卡片推送 matched_interest 标记

**Files:**
- Modify: `services/specialist-service/app/api/academic_cards.py`（`push_card` 循环）
- Modify: `services/specialist-service/tests/test_card_pushes.py`
- Modify: `services/specialist-service/tests/test_academic_cards.py`（如需）

**Interfaces:**
- Consumes: `preference_ranking.get_profiles_batch(db, doctor_ids)`、`preference_ranking.matched_interest(card_title, profile)`、`CardPushRecord.matched_interest`（Task 2）
- Produces: 无（推送行为不变，仅写入标记）

- [ ] **Step 1: 写失败测试**

在 `tests/test_card_pushes.py` 加：

```python
def test_push_records_matched_interest_by_doctor(monkeypatch, fresh_state):
    from app.core import preference_ranking
    class FakeProf:
        def __init__(self, areas):
            self.interest_areas = areas
            self.preferred_doc_type = None
            self.preferred_style = None
            self.closed = False
    # doctor 2 兴趣含"肿瘤"、doctor 4 不含 → 各自 matched_interest 正确
    monkeypatch.setattr(
        preference_ranking, "get_profiles_batch",
        lambda db, ids: {2: FakeProf(["肿瘤"]), 4: FakeProf(["心血管"])},
    )
    # 推送卡片（title 含"肿瘤"）给 doctor 2 与 4（需先建订阅/卡片，参照既有用例）
    ...
    push = db.query(CardPushRecord).filter_by(card_id=card.id).all()
    by_doc = {r.doctor_id: r.matched_interest for r in push}
    assert by_doc[2] is True
    assert by_doc[4] is False
```

（订阅/卡片构造参照该文件既有 `test_push_...` 用例的 `fresh_state` 模式。）

- [ ] **Step 2: 运行确认失败**

Run: `cd services/specialist-service && python -m pytest tests/test_card_pushes.py -k matched -v`
Expected: FAIL（`matched_interest` 未写入）

- [ ] **Step 3: 实现**

`push_card` 里 `pushed = 0` 之前（`doctor_ids` 校验后）批量读偏好：

```python
    # 学术偏好接入（2026-08-27 spec）：批量读目标医生偏好，循环内标 matched_interest
    from app.core import preference_ranking
    profiles = preference_ranking.get_profiles_batch(db, doctor_ids)
```

循环内 `db.add(CardPushRecord(...))` 加：

```python
            matched_interest=preference_ranking.matched_interest(card.title, profiles.get(doctor_id)),
```

（其余字段不变；`skipped` 分支不写标记。）

- [ ] **Step 4: 运行确认通过 + 既有用例无回归**

Run: `cd services/specialist-service && python -m pytest tests/test_card_pushes.py tests/test_academic_cards.py -q`
Expected: 全部通过（含新 matched_interest 用例）

- [ ] **Step 5: Commit**

```bash
git add services/specialist-service/app/api/academic_cards.py services/specialist-service/tests/test_card_pushes.py
git commit -m "feat(specialist): 学术卡片推送按医生兴趣写 matched_interest 标记"
```

---

## 收尾：全量回归

全部 5 个 Task 完成后：

- [ ] Run: `cd services/specialist-service && python -m pytest tests/ -q`
  Expected: 全部通过（含新增用例）

- [ ] Run: `cd services/audit-service && python -m pytest tests/ -q`（确认 shared/models 改动无影响）
- [ ] 如有新迁移：`docker exec -i medagent-postgres psql -U medagent medagent < scripts/migrations/026_card_push_matched_interest.sql`
- [ ] Commit（若迁移实跑后有改动）：`git add -A && git commit -m "chore: 实跑迁移 026"`（仅当有改动）
- [ ] 推送：`git push origin master`

## Self-Review 记录

- Spec 覆盖：问答 re-rank（Task 3）/ 分身注入（Task 4）/ 卡片标记（Task 5）/ 迁移（Task 2）/ 共享模块（Task 1）—— spec「不做」项（简报、内容定制、卡片过滤）无对应 Task ✅
- 无占位符；类型一致性：`reorder_results`/`matched_interest`/`preference_context` 签名在 Task 1 定义、Task 3-5 按签名调用 ✅
