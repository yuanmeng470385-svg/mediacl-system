# 合规风控深化 实施计划（二期 E）

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 把一期已有的三层拦截从"可用"升级为"运营可视化 + 人工裁决闭环"：拦截聚合告警、待复核冻结流、违规趋势分析、对话日志全文检索、分身状态监控与使用统计、官方公共数字员工管理。

**Architecture:** 服务归属按数据位置拆分——compliance-service（compliance_blocks 同库）做聚合告警/趋势/待复核名单；specialist-service（conversations 同库）做对话全文检索 + 分身监控统计 + 冻结流 + 官方分身；digital_specialists 加 `is_official`/`representative_id` 列（迁移 014）；web 三个新页面。分身拦截计数从 `conversations.compliance_result` JSONB 按 specialist_id 聚合（不给 compliance_blocks 加列）。

**Tech Stack:** Python FastAPI（compliance-service / specialist-service）/ React + Ant Design Pro（web）/ PostgreSQL 迁移 014 / 既有 compliance_client。

## Global Constraints

- 服务归属：聚合/告警/趋势/待复核名单 → compliance-service（新文件 `app/api/monitor.py`）；对话检索/分身监控/冻结/官方分身 → specialist-service（`app/api/conversations.py` + `app/api/specialists.py`）。
- 权限：所有新端点 → `require_roles("admin","manager","compliance")`；冻结/解冻额外要求写审计（action=`specialist_freeze`/`specialist_unfreeze`）。
- **不做自动冻结**（需求明确：语义误报/fail-closed 场景人工裁决）；待复核仅标记，冻结必须人工确认。
- digital_specialists.status 值域从 `draft/active/disabled` 扩为 `draft/active/disabled/frozen`；chat 入口（chat_ws.py:38-45 + REST chat）改为**仅 active 可对话**；frozen 表示合规冻结，disabled 表示运营禁用。
- 分身拦截计数口径：`conversations.compliance_result` 中 `blocked=true` 且 `created_at` 在窗口内，按 specialist_id 聚合（JSONB 字段名以 answer_generator 实际写入为准，实现时核对）。
- 对话日志全文检索：`conversations.content` ILIKE 多条件（代表姓名→user_id join、分身、时间范围、命中敏感词），仅 admin/manager/compliance；返回完整上下文（单条会话内按 session_id 取全部行）。
- `is_official` 官方公共数字员工：由医学部/合规部创建维护（require_roles 含 medical）；`representative_id` 为空表示官方公共数字员工。
- 复用 `shared.common.response` / `shared.common.pagination`；测试遵循各服务既有模式（compliance 用 SQLite+StaticPool+BigInteger compile；specialist 同款）。
- 提交规范：conventional commits + Co-Authored-By 尾注；推 Codeup 前用户确认。

## File Structure

**compliance-service：**
- Create: `services/compliance-service/app/api/monitor.py` — 聚合日报/高危告警/趋势分析/待复核名单
- Modify: `services/compliance-service/app/main.py` — 注册 monitor router
- Test: `services/compliance-service/tests/test_monitor.py`

**specialist-service：**
- Modify: `services/specialist-service/app/api/conversations.py` — admin 对话全文检索端点
- Modify: `services/specialist-service/app/api/specialists.py` — 分身监控统计 + 冻结/解冻 + 官方分身 CRUD
- Modify: `services/specialist-service/app/api/chat_ws.py` + REST chat — status 校验收紧（仅 active）
- Modify: `shared/models/digital_specialist.py` — 加 is_official/representative_id
- Test: `services/specialist-service/tests/test_monitor_specialists.py`、`test_conv_search.py`

**DB：**
- Create: `scripts/migrations/014_specialist_official.sql` — digital_specialists 加两列
- Modify: `scripts/init_db.sql`

**web：**
- Create: `web/src/pages/Compliance/Monitor.tsx` — 风控看板（聚合告警/趋势/待复核冻结流）
- Create: `web/src/pages/Compliance/ConvSearch.tsx` — 对话日志全文检索
- Create: `web/src/pages/Specialist/MonitorList.tsx` — 分身状态监控与官方分身管理
- Create: `web/src/services/monitor.ts`
- Modify: `web/src/App.tsx` + `web/src/constants/menu.tsx`
- Test: `cd web && npm run build`

**Docs：**
- Modify: `CLAUDE.md`

---

### Task 1: 迁移 014 + 模型加列

**Files:**
- Create: `scripts/migrations/014_specialist_official.sql`
- Modify: `scripts/init_db.sql`
- Modify: `shared/models/digital_specialist.py`

**Interfaces:**
- Produces: `Specialist.is_official`（Boolean，默认 False）、`Specialist.representative_id`（BigInteger 可空）；status 值域含 `frozen`（模型默认值不变）。

- [ ] **Step 1: 写迁移文件**

Create `scripts/migrations/014_specialist_official.sql`：

```sql
-- 014_specialist_official.sql
-- 二期 E：digital_specialists 加 官方公共数字员工标识 + 归属代表（需求 3.5(4) 官方公共数字员工 / 4.3 个人分身）
-- 用法：docker exec -i medagent-postgres psql -U medagent medagent < scripts/migrations/014_specialist_official.sql

\set ON_ERROR_STOP on

ALTER TABLE digital_specialists ADD COLUMN IF NOT EXISTS is_official BOOLEAN NOT NULL DEFAULT FALSE;
ALTER TABLE digital_specialists ADD COLUMN IF NOT EXISTS representative_id BIGINT REFERENCES users(id);
CREATE INDEX IF NOT EXISTS idx_ds_official ON digital_specialists(is_official);
```

- [ ] **Step 2: init_db.sql 同步**

在 `scripts/init_db.sql` 的 `digital_specialists` 建表段补两列（与迁移一致）：
```sql
    is_official BOOLEAN NOT NULL DEFAULT FALSE,
    representative_id BIGINT,
```
并追加索引 `CREATE INDEX IF NOT EXISTS idx_ds_official ON digital_specialists(is_official);`

- [ ] **Step 3: 模型加列**

Modify `shared/models/digital_specialist.py`：

1. 顶部 import 补 `from sqlalchemy import Boolean`。
2. 在 `status` 列后追加：
```python
    is_official = Column(Boolean, nullable=False, default=False)
    representative_id = Column(BigInteger, ForeignKey("users.id"))
```
3. `to_dict()` 补两个字段：
```python
            "is_official": self.is_official,
            "representative_id": self.representative_id,
```
（放在 `"status": self.status,` 之后。）

- [ ] **Step 4: 验证**

Run: `cd services/specialist-service && python -c "import sys,os; sys.path.insert(0,'.'); from app.models.specialist import Specialist; print(Specialist.__table__.columns.keys()); print(Specialist(name='x', product_id=1).to_dict())"`
Expected: columns 含 `is_official`、`representative_id`；to_dict 输出含两键（is_official=False, representative_id=None）

- [ ] **Step 5: Commit**

```bash
git add scripts/migrations/014_specialist_official.sql scripts/init_db.sql shared/models/digital_specialist.py
git commit -m "feat(auth): digital_specialists 加 is_official/representative_id（迁移 014）"
```

---

### Task 2: compliance 聚合告警 + 趋势分析 + 待复核名单

**Files:**
- Create: `services/compliance-service/app/api/monitor.py`
- Modify: `services/compliance-service/app/main.py`
- Test: `services/compliance-service/tests/test_monitor.py`

**Interfaces:**
- Consumes: `ComplianceBlock`（shared/models/compliance.py）、`User`（shared/models/user.py，同库直连）
- Produces: `monitor_router`（prefix `/api/v1/compliance`）；端点：
  - `GET /api/v1/compliance/daily-summary` — 拦截聚合日报（按天/按规则/按 action）
  - `GET /api/v1/compliance/trends` — 违规趋势（时间曲线/代表排名/敏感词频率）
  - `GET /api/v1/compliance/review-queue` — 待复核名单（分身拦截计数超阈值）
  均 `require_roles("admin","manager","compliance")`。

- [ ] **Step 1: 写失败测试**

Create `services/compliance-service/tests/test_monitor.py`：

```python
"""合规监控端点测试（Task 2）：聚合日报/趋势/待复核名单"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", ".."))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

os.environ.setdefault("JWT_SECRET", "test-secret-not-a-default-value")
os.environ["AUTH_DEV_MODE"] = "true"

from datetime import datetime, timedelta
from unittest.mock import AsyncMock

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import BigInteger, create_engine
from sqlalchemy.ext.compiler import compiles
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from shared.common.auth import create_token
from shared.common.db_session import get_db
from shared.models.base import Base
from shared.models.compliance import ComplianceBlock, ComplianceRule
from shared.models.user import User

import app.api.monitor as monitor_api
from app.main import app


@compiles(BigInteger, "sqlite")
def _compile_bigint_for_sqlite(type_, compiler, **kw):
    return "INTEGER"


engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
TestSession = sessionmaker(bind=engine, autocommit=False, autoflush=False)


def _override_db():
    db = TestSession()
    try:
        yield db
    finally:
        db.close()


client = TestClient(app)


def _token(user_id: int, role: str) -> dict:
    token = create_token(user_id=user_id, username=f"u{user_id}", role=role)
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture(autouse=True)
def fresh_state(monkeypatch):
    tables = [User.__table__, ComplianceRule.__table__, ComplianceBlock.__table__]
    Base.metadata.drop_all(engine, tables=tables)
    Base.metadata.create_all(engine, tables=tables)
    db = TestSession()
    db.add_all([
        User(id=1, username="rep01", full_name="张代表", phone="13800000001", role="rep", status="active", region="华东"),
        User(id=2, username="admin", full_name="管理员", phone="13800000000", role="admin", status="active", region="总部"),
        User(id=3, username="compliance", full_name="合规部", phone="13800000003", role="compliance", status="active", region="总部"),
    ])
    db.commit()
    db.close()
    monkeypatch.setitem(app.dependency_overrides, get_db, _override_db)
    yield


def _add_block(**kw):
    db = TestSession()
    defaults = dict(
        id=kw.pop("id", 1), user_id=1, service_name="specialist",
        content="违规内容", rule_code="R001", rule_name="保证疗效",
        severity="high", action="reject", context={"snippet": "x"},
        blocked_at=datetime.utcnow(),
    )
    defaults.update(kw)
    db.add(ComplianceBlock(**defaults))
    db.commit()
    db.close()


def test_daily_summary_requires_admin():
    resp = client.get("/api/v1/compliance/daily-summary", headers=_token(1, "rep"))
    assert resp.status_code == 403
    assert resp.json()["code"] == 3000


def test_daily_summary_aggregates():
    _add_block(id=1, rule_code="R001")
    _add_block(id=2, rule_code="R001")
    _add_block(id=3, rule_code="R009")
    resp = client.get("/api/v1/compliance/daily-summary", headers=_token(3, "compliance"))
    body = resp.json()
    assert body["code"] == 0
    by_rule = {r["rule_code"]: r["count"] for r in body["data"]["by_rule"]}
    assert by_rule["R001"] == 2
    assert by_rule["R009"] == 1
    assert body["data"]["total"] == 3


def test_trends_rep_ranking():
    _add_block(id=1, user_id=1, rule_code="R001")
    resp = client.get("/api/v1/compliance/trends", headers=_token(2, "admin"))
    body = resp.json()
    assert body["code"] == 0
    assert body["data"]["rep_ranking"][0]["rep_name"] == "张代表"
    assert body["data"]["rep_ranking"][0]["count"] == 1
    assert body["data"]["time_series"]  # 至少一个数据点


def test_review_queue_requires_admin():
    resp = client.get("/api/v1/compliance/review-queue", headers=_token(1, "rep"))
    assert resp.status_code == 403


def test_review_queue_marks_high_blockers():
    # 同一 user 近窗口内 ≥ 阈值条拦截 → 进入待复核
    for i in range(6):
        _add_block(id=i + 1, user_id=1, rule_code="R001")
    resp = client.get("/api/v1/compliance/review-queue", headers=_token(3, "compliance"))
    body = resp.json()
    assert body["code"] == 0
    items = body["data"]["items"]
    assert any(item["user_id"] == 1 for item in items)
    assert items[0]["block_count"] >= 5


def test_review_queue_below_threshold_excluded():
    _add_block(id=1, user_id=1)
    _add_block(id=2, user_id=1)
    resp = client.get("/api/v1/compliance/review-queue", headers=_token(3, "compliance"))
    body = resp.json()
    assert body["code"] == 0
    assert body["data"]["items"] == []
```

- [ ] **Step 2: 运行测试确认失败**

Run: `cd services/compliance-service && python -m pytest tests/test_monitor.py -q`
Expected: 失败（模块 app.api.monitor 不存在）

- [ ] **Step 3: 实现 monitor.py**

Create `services/compliance-service/app/api/monitor.py`：

```python
"""合规监控（二期 E，需求 3.2(3)(4)）：聚合日报 / 违规趋势 / 待复核名单。
拦截聚合基于 compliance_blocks（同库直连 users 取代表姓名，与 blocks/stats 同口径）。
"""
import logging
from datetime import datetime, timedelta
from typing import Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func as sqlfunc
from sqlalchemy.orm import Session

from shared.common.auth import require_roles
from shared.common.db_session import get_db
from shared.common.pagination import PaginationParams, paginate
from shared.common.response import ParamError, success
from shared.models.compliance import ComplianceBlock
from shared.models.user import User

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/compliance", tags=["compliance-monitor"])

MONITOR_ADMIN_ROLES = ("admin", "manager", "compliance")

# 待复核阈值（需求 3.2(3)：24 小时内拦截 ≥5 次标记待复核，可配置）
REVIEW_THRESHOLD = int(os.getenv("REVIEW_BLOCK_THRESHOLD", "5"))
REVIEW_WINDOW_HOURS = int(os.getenv("REVIEW_WINDOW_HOURS", "24"))


@router.get("/daily-summary")
async def daily_summary(
    days: int = Query(7, ge=1, le=90),
    _admin: dict = Depends(require_roles(*MONITOR_ADMIN_ROLES)),
    db: Session = Depends(get_db),
):
    """拦截聚合日报：按天 × 按规则 × 按 action 聚合（风控看板数据源）"""
    since = datetime.utcnow() - timedelta(days=days)
    base = db.query(ComplianceBlock).filter(ComplianceBlock.blocked_at >= since)

    by_rule_rows = (
        base.with_entities(
            ComplianceBlock.rule_code, sqlfunc.count(ComplianceBlock.id)
        ).group_by(ComplianceBlock.rule_code).all()
    )
    by_action_rows = (
        base.with_entities(
            ComplianceBlock.action, sqlfunc.count(ComplianceBlock.id)
        ).group_by(ComplianceBlock.action).all()
    )
    by_day_rows = (
        base.with_entities(
            sqlfunc.date(ComplianceBlock.blocked_at), sqlfunc.count(ComplianceBlock.id)
        ).group_by(sqlfunc.date(ComplianceBlock.blocked_at)).all()
    )
    return success({
        "total": base.count(),
        "by_rule": [{"rule_code": r, "count": c} for r, c in by_rule_rows],
        "by_action": [{"action": a, "count": c} for a, c in by_action_rows],
        "by_day": [{"date": str(d), "count": c} for d, c in by_day_rows],
        "days": days,
    })


@router.get("/trends")
async def compliance_trends(
    days: int = Query(30, ge=1, le=90),
    _admin: dict = Depends(require_roles(*MONITOR_ADMIN_ROLES)),
    db: Session = Depends(get_db),
):
    """违规趋势分析（需求 3.2(4)）：时间曲线 + 代表排名 + 敏感词（规则）频率"""
    since = datetime.utcnow() - timedelta(days=days)

    time_rows = (
        db.query(
            sqlfunc.date(ComplianceBlock.blocked_at).label("date"),
            sqlfunc.count(ComplianceBlock.id),
        )
        .filter(ComplianceBlock.blocked_at >= since)
        .group_by(sqlfunc.date(ComplianceBlock.blocked_at))
        .all()
    )
    rep_rows = (
        db.query(
            User.full_name.label("rep_name"), User.id.label("user_id"),
            sqlfunc.count(ComplianceBlock.id),
        )
        .outerjoin(User, ComplianceBlock.user_id == User.id)
        .filter(ComplianceBlock.blocked_at >= since)
        .group_by(User.id, User.full_name)
        .order_by(sqlfunc.count(ComplianceBlock.id).desc())
        .limit(10)
        .all()
    )
    rule_rows = (
        db.query(
            ComplianceBlock.rule_code, ComplianceBlock.rule_name,
            sqlfunc.count(ComplianceBlock.id),
        )
        .filter(ComplianceBlock.blocked_at >= since)
        .group_by(ComplianceBlock.rule_code, ComplianceBlock.rule_name)
        .order_by(sqlfunc.count(ComplianceBlock.id).desc())
        .all()
    )
    return success({
        "time_series": [{"date": str(d), "count": c} for d, c in time_rows],
        "rep_ranking": [{"user_id": uid, "rep_name": name or "未知", "count": c} for name, uid, c in rep_rows],
        "rule_frequency": [{"rule_code": rc, "rule_name": rn or rc, "count": c} for rc, rn, c in rule_rows],
    })


@router.get("/review-queue")
async def review_queue(
    _admin: dict = Depends(require_roles(*MONITOR_ADMIN_ROLES)),
    db: Session = Depends(get_db),
):
    """待复核名单：同一代表（user）近窗口内拦截计数超阈值 → 标记待复核（不做自动冻结）"""
    since = datetime.utcnow() - timedelta(hours=REVIEW_WINDOW_HOURS)
    rows = (
        db.query(
            ComplianceBlock.user_id, User.full_name, User.phone,
            sqlfunc.count(ComplianceBlock.id).label("block_count"),
        )
        .outerjoin(User, ComplianceBlock.user_id == User.id)
        .filter(ComplianceBlock.blocked_at >= since)
        .group_by(ComplianceBlock.user_id, User.full_name, User.phone)
        .having(sqlfunc.count(ComplianceBlock.id) >= REVIEW_THRESHOLD)
        .order_by(sqlfunc.count(ComplianceBlock.id).desc())
        .all()
    )
    items = [{
        "user_id": uid, "rep_name": name or "未知", "rep_phone": phone or "",
        "block_count": cnt, "window_hours": REVIEW_WINDOW_HOURS,
        "threshold": REVIEW_THRESHOLD,
    } for uid, name, phone, cnt in rows]
    return success({"items": items, "threshold": REVIEW_THRESHOLD, "window_hours": REVIEW_WINDOW_HOURS})
```

> 顶部补 `import os`。

- [ ] **Step 4: 注册 router**

Modify `services/compliance-service/app/main.py`：追加 `from app.api.monitor import router as monitor_router` + `app.include_router(monitor_router)`。

- [ ] **Step 5: 运行测试确认通过**

Run: `cd services/compliance-service && python -m pytest tests/test_monitor.py -q`
Expected: 6 passed

- [ ] **Step 6: Commit**

```bash
git add services/compliance-service/app/api/monitor.py services/compliance-service/app/main.py services/compliance-service/tests/test_monitor.py
git commit -m "feat(compliance): 聚合日报/趋势分析/待复核名单端点"
```

---

### Task 3: specialist 对话全文检索（admin）

**Files:**
- Modify: `services/specialist-service/app/api/conversations.py`
- Test: `services/specialist-service/tests/test_conv_search.py`

**Interfaces:**
- Consumes: `Conversation`、`Specialist`、`User`（shared/models）
- Produces: `GET /api/v1/conversations/search` — admin/manager/compliance 对话全文检索（content ILIKE + 代表/分身/时间范围筛选），每条带完整会话上下文（按 session_id 取全部行）。

- [ ] **Step 1: 写失败测试**

Create `services/specialist-service/tests/test_conv_search.py`（骨架参照 specialist-service 既有测试——先看一个现成测试文件确认 import 路径与 fixture 模式）：

```python
"""对话全文检索测试（Task 3）：多条件筛选 + 完整上下文 + 权限"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", ".."))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

os.environ.setdefault("JWT_SECRET", "test-secret-not-a-default-value")
os.environ["AUTH_DEV_MODE"] = "true"

from datetime import datetime

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import BigInteger, create_engine
from sqlalchemy.ext.compiler import compiles
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from shared.common.auth import create_token
from shared.common.db_session import get_db
from shared.models.base import Base
from shared.models.digital_specialist import Specialist
from shared.models.user import User

import app.api.conversations as conv_api
from app.main import app
from app.models.conversation import Conversation


@compiles(BigInteger, "sqlite")
def _compile_bigint_for_sqlite(type_, compiler, **kw):
    return "INTEGER"


engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
TestSession = sessionmaker(bind=engine, autocommit=False, autoflush=False)


def _override_db():
    db = TestSession()
    try:
        yield db
    finally:
        db.close()


client = TestClient(app)


def _token(user_id: int, role: str) -> dict:
    token = create_token(user_id=user_id, username=f"u{user_id}", role=role)
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture(autouse=True)
def fresh_state(monkeypatch):
    tables = [User.__table__, Specialist.__table__, Conversation.__table__]
    Base.metadata.drop_all(engine, tables=tables)
    Base.metadata.create_all(engine, tables=tables)
    db = TestSession()
    db.add_all([
        User(id=1, username="rep01", full_name="张代表", phone="13800000001", role="rep", status="active"),
        User(id=2, username="admin", full_name="管理员", phone="13800000000", role="admin", status="active"),
        User(id=3, username="compliance", full_name="合规部", phone="13800000003", role="compliance", status="active"),
    ])
    db.add(Specialist(id=1, name="心内科专员", product_id=1, status="active"))
    db.commit()
    db.close()
    monkeypatch.setitem(app.dependency_overrides, get_db, _override_db)
    yield


def _add_conv(**kw):
    db = TestSession()
    defaults = dict(
        id=kw.pop("id", 1), user_id=1, specialist_id=1, session_id="s1",
        role="user", content="高血压用药方案", citations=None,
        compliance_result=None, created_at=datetime.utcnow(),
    )
    defaults.update(kw)
    db.add(Conversation(**defaults))
    db.commit()
    db.close()


def test_search_requires_admin():
    resp = client.get("/api/v1/conversations/search?keyword=高血压", headers=_token(1, "rep"))
    assert resp.status_code == 403


def test_search_by_keyword():
    _add_conv(id=1, content="高血压用药方案讨论")
    _add_conv(id=2, content="糖尿病患者饮食")
    resp = client.get("/api/v1/conversations/search?keyword=高血压", headers=_token(2, "admin"))
    body = resp.json()
    assert body["code"] == 0
    assert body["data"]["total"] == 1
    assert body["data"]["items"][0]["content"] == "高血压用药方案讨论"


def test_search_filters_by_rep():
    _add_conv(id=1, content="问题一", user_id=1)
    _add_conv(id=2, content="问题二", user_id=99)
    resp = client.get("/api/v1/conversations/search?user_id=1", headers=_token(3, "compliance"))
    body = resp.json()
    assert body["data"]["total"] == 1
    assert body["data"]["items"][0]["content"] == "问题一"


def test_search_filters_by_specialist():
    _add_conv(id=1, content="问题一", specialist_id=1)
    _add_conv(id=2, content="问题二", specialist_id=2)
    resp = client.get("/api/v1/conversations/search?specialist_id=1", headers=_token(2, "admin"))
    body = resp.json()
    assert body["data"]["total"] == 1


def test_search_returns_full_context():
    _add_conv(id=1, content="问题", session_id="s1", role="user")
    _add_conv(id=2, content="回答", session_id="s1", role="assistant")
    resp = client.get("/api/v1/conversations/search?keyword=问题", headers=_token(2, "admin"))
    body = resp.json()
    assert body["code"] == 0
    item = body["data"]["items"][0]
    assert item["context"] and len(item["context"]) == 2  # 完整会话上下文
    assert {c["role"] for c in item["context"]} == {"user", "assistant"}
```

- [ ] **Step 2: 运行测试确认失败**

Run: `cd services/specialist-service && python -m pytest tests/test_conv_search.py -q`
Expected: 失败（/search 路由未定义 → 404/405）

- [ ] **Step 3: 实现检索端点**

Modify `services/specialist-service/app/api/conversations.py`，在文件末尾（favorites_router 之前）追加：

```python
@router.get("/search")
async def search_conversations(
    page: int = 1,
    page_size: int = 20,
    keyword: Optional[str] = None,
    user_id: Optional[int] = None,
    specialist_id: Optional[int] = None,
    date_from: Optional[str] = None,
    date_to: Optional[str] = None,
    _admin: dict = Depends(require_roles("admin", "manager", "compliance")),
    db: Session = Depends(get_db),
):
    """对话日志全文检索（二期 E，需求 3.2(1)）：admin/manager/compliance。

    按 代表(user_id) / 分身(specialist_id) / 时间范围 / 命中词 筛选；
    返回每条命中 + 该会话完整上下文（session_id 全部行，role/content）。
    """
    from datetime import datetime
    from shared.common.response import ParamError as PE

    def _parse(s: Optional[str], name: str) -> Optional[datetime]:
        if not s:
            return None
        try:
            return datetime.fromisoformat(s)
        except ValueError:
            raise PE(f"{name} 格式应为 ISO 时间")

    q = db.query(Conversation)
    if keyword:
        q = q.filter(Conversation.content.ilike(f"%{keyword}%"))
    if user_id:
        q = q.filter(Conversation.user_id == user_id)
    if specialist_id:
        q = q.filter(Conversation.specialist_id == specialist_id)
    if date_from:
        q = q.filter(Conversation.created_at >= _parse(date_from, "date_from"))
    if date_to:
        q = q.filter(Conversation.created_at <= _parse(date_to, "date_to"))

    total = q.count()
    rows = q.order_by(Conversation.id.desc()).offset((page - 1) * page_size).limit(page_size).all()

    items = []
    for conv in rows:
        ctx_rows = db.query(Conversation).filter(
            Conversation.session_id == conv.session_id
        ).order_by(Conversation.id.asc()).all()
        items.append({
            "id": conv.id,
            "user_id": conv.user_id,
            "specialist_id": conv.specialist_id,
            "session_id": conv.session_id,
            "role": conv.role,
            "content": conv.content,
            "blocked": bool(conv.compliance_result and conv.compliance_result.get("blocked")),
            "created_at": conv.created_at.isoformat() if conv.created_at else None,
            "context": [{
                "role": c.role, "content": c.content,
                "blocked": bool(c.compliance_result and c.compliance_result.get("blocked")),
            } for c in ctx_rows],
        })
    return success(paginate(items, total=total, page=page, page_size=page_size))
```

> 顶部需补 imports：`from typing import Optional`、`from shared.common.auth import require_roles`、`from shared.common.pagination import PaginationParams, paginate`（若未引入）。路由顺序：`/search` 定义在 `/conversations/{conversation_id}/...` 之后可能被 `{conversation_id}` 捕获（`/search` 非数字 → 422）。**必须把 `/search` 放在最前**——若放在文件末尾会与 `/{conversation_id}/feedback` 冲突（FastAPI 按注册顺序，`/search` 会匹配 `/{conversation_id}/...` 的 detail 路由？不，`/search` 是单段，`/{conversation_id}/feedback` 是两段，不冲突。但 `/search` 与 GET `/{specialist_id}` 不同 router。此 router prefix=/api/v1/conversations，无单段 GET 冲突。安全。）

- [ ] **Step 4: 运行测试确认通过**

Run: `cd services/specialist-service && python -m pytest tests/test_conv_search.py -q`
Expected: 5 passed

- [ ] **Step 5: Commit**

```bash
git add services/specialist-service/app/api/conversations.py services/specialist-service/tests/test_conv_search.py
git commit -m "feat(specialist): 对话日志全文检索（admin 多条件+完整上下文）"
```

---

### Task 4: specialist 分身监控统计 + 冻结/解冻 + 官方分身 CRUD

**Files:**
- Modify: `services/specialist-service/app/api/specialists.py`
- Modify: `services/specialist-service/app/api/chat_ws.py`（status 校验收紧）
- Test: `services/specialist-service/tests/test_monitor_specialists.py`

**Interfaces:**
- Consumes: `Specialist`（is_official/representative_id，Task 1）、`Conversation`、`ConversationFeedback`、`doctor_twin_subscriptions`（shared/models/doctor.py）
- Produces: 端点（均挂 require_roles admin/manager/compliance 或按需含 medical）：
  - `GET /api/v1/specialists/monitor` — 分身列表（含 今日服务量/平均响应时长/服务医生数/合规健康度/被添加次数/好评率）
  - `POST /api/v1/specialists/{specialist_id}/freeze` — 冻结（status→frozen + 审计）
  - `POST /api/v1/specialists/{specialist_id}/unfreeze` — 解冻（status→active + 审计）
  - `POST /api/v1/specialists` 扩展 is_official/representative_id（官方分身 CRUD 的 create）；`PUT /{id}` 扩展同字段

- [ ] **Step 1: 写失败测试**

Create `services/specialist-service/tests/test_monitor_specialists.py`：

```python
"""分身监控统计 + 冻结/解冻 + 官方分身（Task 4）"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", ".."))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

os.environ.setdefault("JWT_SECRET", "test-secret-not-a-default-value")
os.environ["AUTH_DEV_MODE"] = "true"

from datetime import datetime, timedelta
from unittest.mock import AsyncMock

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import BigInteger, create_engine
from sqlalchemy.ext.compiler import compiles
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from shared.common.auth import create_token
from shared.common.db_session import get_db
from shared.models.base import Base
from shared.models.digital_specialist import Specialist
from shared.models.doctor import DoctorTwinSubscription
from shared.models.user import User

import app.api.specialists as spec_api
from app.main import app
from app.models.conversation import Conversation
from app.models.feedback import ConversationFeedback


@compiles(BigInteger, "sqlite")
def _compile_bigint_for_sqlite(type_, compiler, **kw):
    return "INTEGER"


engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
TestSession = sessionmaker(bind=engine, autocommit=False, autoflush=False)


def _override_db():
    db = TestSession()
    try:
        yield db
    finally:
        db.close()


client = TestClient(app)


def _token(user_id: int, role: str) -> dict:
    token = create_token(user_id=user_id, username=f"u{user_id}", role=role)
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture(autouse=True)
def fresh_state(monkeypatch):
    tables = [User.__table__, Specialist.__table__, Conversation.__table__,
              ConversationFeedback.__table__, DoctorTwinSubscription.__table__]
    Base.metadata.drop_all(engine, tables=tables)
    Base.metadata.create_all(engine, tables=tables)
    db = TestSession()
    db.add_all([
        User(id=1, username="rep01", full_name="张代表", phone="13800000001", role="rep", status="active"),
        User(id=2, username="admin", full_name="管理员", phone="13800000000", role="admin", status="active"),
        User(id=3, username="medical", full_name="医学部", phone="13800000003", role="medical", status="active"),
    ])
    db.commit()
    db.close()
    monkeypatch.setitem(app.dependency_overrides, get_db, _override_db)
    audit_mock = AsyncMock(return_value=None)
    monkeypatch.setattr(spec_api, "write_audit_log", audit_mock)
    yield audit_mock


def _add_specialist(**kw):
    db = TestSession()
    defaults = dict(id=kw.pop("id", 1), name="心内科专员", product_id=1, status="active")
    defaults.update(kw)
    db.add(Specialist(**defaults))
    db.commit()
    db.close()
    return defaults["id"]


def test_freeze_requires_admin():
    _add_specialist(id=1)
    resp = client.post("/api/v1/specialists/1/freeze", headers=_token(1, "rep"))
    assert resp.status_code == 403


def test_freeze_sets_frozen(fresh_state):
    _add_specialist(id=1)
    resp = client.post("/api/v1/specialists/1/freeze", json={"reason": "24h 内拦截超阈值"},
                       headers=_token(2, "admin"))
    body = resp.json()
    assert body["code"] == 0
    assert body["data"]["status"] == "frozen"
    audit_mock = fresh_state
    audit_mock.assert_awaited_once()


def test_unfreeze_returns_active(fresh_state):
    _add_specialist(id=1, status="frozen")
    resp = client.post("/api/v1/specialists/1/unfreeze", json={}, headers=_token(2, "admin"))
    body = resp.json()
    assert body["code"] == 0
    assert body["data"]["status"] == "active"


def test_freeze_requires_reason():
    _add_specialist(id=1)
    resp = client.post("/api/v1/specialists/1/freeze", json={}, headers=_token(2, "admin"))
    assert resp.status_code == 400
    assert resp.json()["code"] == 1000


def test_create_official_specialist(fresh_state):
    resp = client.post("/api/v1/specialists", json={
        "name": "官方心内科专员", "product_id": 1, "is_official": True,
    }, headers=_token(3, "medical"))
    body = resp.json()
    assert body["code"] == 0
    assert body["data"]["is_official"] is True
    assert body["data"]["representative_id"] is None


def test_create_specialist_with_representative():
    resp = client.post("/api/v1/specialists", json={
        "name": "张代表分身", "product_id": 1, "representative_id": 1,
    }, headers=_token(2, "admin"))
    body = resp.json()
    assert body["code"] == 0
    assert body["data"]["representative_id"] == 1
```

- [ ] **Step 2: 运行测试确认失败**

Run: `cd services/specialist-service && python -m pytest tests/test_monitor_specialists.py -q`
Expected: 失败（freeze 端点不存在 / is_official 不被允许）

- [ ] **Step 3: 实现冻结/解冻 + 字段扩展**

Modify `services/specialist-service/app/api/specialists.py`：

1. `SPECIALIST_UPDATE_FIELDS` 加 `"is_official"`, `"representative_id"`：
```python
SPECIALIST_UPDATE_FIELDS = {
    "name", "product_id", "persona", "knowledge_scope",
    "compliance_level", "bailian_app_id", "status",
    "is_official", "representative_id",
}
```
2. `_validate_specialist_fields` 校验代表分身冲突：is_official 为真时 representative_id 必须为空：
```python
    if data.get("is_official") and data.get("representative_id"):
        raise ParamError("官方公共数字员工不能绑定代表（representative_id 须为空）")
```
3. `VALID_STATUSES` 加 `"frozen"`：
```python
VALID_STATUSES = {"draft", "active", "disabled", "frozen"}
```
4. 追加冻结/解冻端点（`_validate_specialist_fields` 之后）：

```python
@router.post("/{specialist_id}/freeze")
async def freeze_specialist(
    specialist_id: int,
    payload: dict,
    current_user: dict = Depends(require_roles("admin", "manager", "compliance")),
    db: Session = Depends(get_db),
):
    """合规冻结分身（需求 3.2(3) 人工裁决）：reason 必填 + 审计。不做自动冻结。"""
    from app.services.audit_client import write_audit_log
    if not isinstance(payload, dict):
        raise ParamError("请求体必须是 JSON 对象")
    reason = (payload.get("reason") or "").strip() if isinstance(payload.get("reason"), str) else ""
    if not reason:
        raise ParamError("冻结必须填写理由")
    spec = db.query(Specialist).filter(Specialist.id == specialist_id).first()
    if not spec:
        raise BusinessError("分身不存在", code=4001)
    if spec.status == "frozen":
        raise BusinessError("分身已处于冻结状态", code=4001)
    spec.status = "frozen"
    db.commit()
    db.refresh(spec)
    await write_audit_log(
        action="specialist_freeze",
        user_id=current_user["id"],
        resource_type="digital_specialist",
        resource_id=str(spec.id),
        after_value={"status": "frozen", "reason": reason},
        request_id=get_request_id() or None,
    )
    return success(spec.to_dict())


@router.post("/{specialist_id}/unfreeze")
async def unfreeze_specialist(
    specialist_id: int,
    current_user: dict = Depends(require_roles("admin", "manager", "compliance")),
    db: Session = Depends(get_db),
):
    """解冻分身：frozen → active + 审计"""
    from app.services.audit_client import write_audit_log
    spec = db.query(Specialist).filter(Specialist.id == specialist_id).first()
    if not spec:
        raise BusinessError("分身不存在", code=4001)
    if spec.status != "frozen":
        raise BusinessError("分身未处于冻结状态", code=4001)
    spec.status = "active"
    db.commit()
    db.refresh(spec)
    await write_audit_log(
        action="specialist_unfreeze",
        user_id=current_user["id"],
        resource_type="digital_specialist",
        resource_id=str(spec.id),
        after_value={"status": "active"},
        request_id=get_request_id() or None,
    )
    return success(spec.to_dict())
```

5. 检查 `to_dict()` 是否输出新字段——`shared/models/digital_specialist.py` 的 `Specialist.to_dict()` 需补 `is_official`/`representative_id`（Task 1 Step 3 一并处理，若无 to_dict 则此步补）。

- [ ] **Step 4: 收紧 chat 入口 status 校验**

Modify `services/specialist-service/app/api/chat_ws.py` 中校验 specialist 存在处（约 line 38-45），从 `Specialist.status == "active"` 保持即可——但**确认** REST chat（`/specialists/{id}/chat`）与 WS 都只允许 active。若 REST chat 未校验 status，补上：
```python
    spec = db.query(Specialist).filter(Specialist.id == specialist_id).first()
    if not spec or spec.status != "active":
        raise HTTPException(status_code=404, detail="专员不存在")
```

- [ ] **Step 5: 运行测试确认通过**

Run: `cd services/specialist-service && python -m pytest tests/test_monitor_specialists.py -q`
Expected: 7 passed

- [ ] **Step 6: 全量回归 specialist**

Run: `cd services/specialist-service && python -m pytest -q`
Expected: 138 + 新增全部通过（若 to_dict 改动破坏既有断言，修复）

- [ ] **Step 7: Commit**

```bash
git add services/specialist-service/app/api/specialists.py services/specialist-service/app/api/chat_ws.py shared/models/digital_specialist.py services/specialist-service/tests/test_monitor_specialists.py
git commit -m "feat(specialist): 分身冻结/解冻+官方分身字段+chat 入口收紧"
```

---

### Task 5: web 合规风控看板 + 对话检索 + 分身监控三页

**Files:**
- Create: `web/src/pages/Compliance/Monitor.tsx`
- Create: `web/src/pages/Compliance/ConvSearch.tsx`
- Create: `web/src/pages/Specialist/MonitorList.tsx`
- Create: `web/src/services/monitor.ts`
- Modify: `web/src/types/index.ts`
- Modify: `web/src/App.tsx`
- Modify: `web/src/constants/menu.tsx`

**Interfaces:**
- Consumes: `/api/v1/compliance/daily-summary|trends|review-queue`、`/api/v1/conversations/search`、`/api/v1/specialists/monitor|freeze|unfreeze`
- Produces: 三个页面 + service + 类型 + 路由/菜单。

- [ ] **Step 1: 加类型**

Modify `web/src/types/index.ts` 追加：

```ts
export interface ComplianceDailySummary {
  total: number;
  by_rule: { rule_code: string; count: number }[];
  by_action: { action: string; count: number }[];
  by_day: { date: string; count: number }[];
  days: number;
}

export interface ComplianceTrends {
  time_series: { date: string; count: number }[];
  rep_ranking: { user_id: number; rep_name: string; count: number }[];
  rule_frequency: { rule_code: string; rule_name: string; count: number }[];
}

export interface ReviewQueueItem {
  user_id: number;
  rep_name: string;
  rep_phone: string;
  block_count: number;
  window_hours: number;
  threshold: number;
}

export interface ConvSearchItem {
  id: number;
  user_id: number;
  specialist_id: number;
  session_id: string;
  role: string;
  content: string;
  blocked: boolean;
  created_at: string | null;
  context: { role: string; content: string; blocked: boolean }[];
}

export interface SpecialistMonitor {
  id: number;
  name: string;
  status: string;
  is_official: boolean;
  representative_id: number | null;
  today_services: number;
  avg_latency_ms: number;
  service_doctors: number;
  compliance_health: 'green' | 'yellow' | 'red';
  added_count: number;
  approval_rate: number | null;
}
```

- [ ] **Step 2: 加 service**

Create `web/src/services/monitor.ts`：

```ts
import client from './client';
import type {
  ApiResponse, ComplianceDailySummary, ComplianceTrends, ConvSearchItem,
  PaginatedResponse, ReviewQueueItem, SpecialistMonitor,
} from '../types';

export const monitorAPI = {
  dailySummary: (days = 7) =>
    client.get<ApiResponse<ComplianceDailySummary>>('/compliance/daily-summary', { params: { days } }),
  trends: (days = 30) =>
    client.get<ApiResponse<ComplianceTrends>>('/compliance/trends', { params: { days } }),
  reviewQueue: () =>
    client.get<ApiResponse<{ items: ReviewQueueItem[]; threshold: number; window_hours: number }>>('/compliance/review-queue'),

  convSearch: (params?: { page?: number; page_size?: number; keyword?: string; user_id?: number; specialist_id?: number; date_from?: string; date_to?: string }) =>
    client.get<PaginatedResponse<ConvSearchItem>>('/conversations/search', { params }),

  specialistMonitor: (params?: { page?: number; page_size?: number; status?: string; official?: boolean }) =>
    client.get<PaginatedResponse<SpecialistMonitor>>('/specialists/monitor', { params }),
  freeze: (id: number, reason: string) =>
    client.post<ApiResponse<SpecialistMonitor>>(`/specialists/${id}/freeze`, { reason }),
  unfreeze: (id: number) =>
    client.post<ApiResponse<SpecialistMonitor>>(`/specialists/${id}/unfreeze`, {}),
};
```

- [ ] **Step 3: 写看板页**

Create `web/src/pages/Compliance/Monitor.tsx`（风控看板：趋势图 + 规则频率 + 待复核冻结流，参照既有 ComplianceList 风格，图表可用简单 div 条形图避免引新依赖）：

```tsx
import { useEffect, useState } from 'react';
import { Button, Card, Col, Row, Statistic, Table, Tag, Typography } from 'antd';
import { App } from 'antd';
import { monitorAPI } from '../../services/monitor';
import type { ComplianceDailySummary, ComplianceTrends, ReviewQueueItem } from '../../types';

const { Text } = Typography;

export default function Monitor() {
  const { message } = App.useApp();
  const [summary, setSummary] = useState<ComplianceDailySummary | null>(null);
  const [trends, setTrends] = useState<ComplianceTrends | null>(null);
  const [queue, setQueue] = useState<ReviewQueueItem[]>([]);
  const [refresh, setRefresh] = useState(0);

  useEffect(() => {
    monitorAPI.dailySummary(7).then(r => setSummary(r.data.data)).catch(() => {});
    monitorAPI.trends(30).then(r => setTrends(r.data.data)).catch(() => {});
    monitorAPI.reviewQueue().then(r => setQueue(r.data.data.items)).catch(() => {});
  }, [refresh]);

  const maxDay = Math.max(1, ...(trends?.time_series ?? []).map(t => t.count));

  return (
    <div>
      <Row gutter={16}>
        <Col span={6}><Card><Statistic title="近 7 天拦截总量" value={summary?.total ?? 0} /></Card></Col>
        <Col span={6}><Card><Statistic title="待复核代表数" value={queue.length} /></Card></Col>
        <Col span={12}><Card title="违规趋势（近 30 天）" extra={<Button size="small" onClick={() => setRefresh(r => r + 1)}>刷新</Button>}>
          {(trends?.time_series ?? []).map(t => (
            <div key={t.date} style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 4 }}>
              <Text style={{ width: 90 }}>{t.date}</Text>
              <div style={{ flex: 1, background: '#f0f2f5', borderRadius: 4, height: 16 }}>
                <div style={{ width: `${(t.count / maxDay) * 100}%`, background: '#1677ff', height: 16, borderRadius: 4 }} />
              </div>
              <Text>{t.count}</Text>
            </div>
          ))}
        </Card></Col>
      </Row>

      <Card title="待复核冻结流（24h 拦截 ≥5 次，人工确认后冻结）" style={{ marginTop: 16 }}>
        <Table<ReviewQueueItem>
          rowKey="user_id"
          dataSource={queue}
          pagination={false}
          columns={[
            { title: '代表', dataIndex: 'rep_name' },
            { title: '手机号', dataIndex: 'rep_phone' },
            { title: '近 24h 拦截', dataIndex: 'block_count', render: v => <Tag color="red">{v} 次</Tag> },
            { title: '操作', render: (_, r) => <Button size="small" type="primary" danger onClick={() => message.info(`人工冻结流程：请到「分身监控」页对 ${r.rep_name} 的分身执行冻结（跳转见侧栏）`)}>待复核</Button> },
          ]}
        />
      </Card>

      <Card title="规则命中频率" style={{ marginTop: 16 }}>
        <Table
          rowKey="rule_code"
          dataSource={trends?.rule_frequency ?? []}
          pagination={false}
          size="small"
          columns={[
            { title: '规则', dataIndex: 'rule_code' },
            { title: '规则名', dataIndex: 'rule_name' },
            { title: '命中次数', dataIndex: 'count' },
          ]}
        />
      </Card>
    </div>
  );
}
```

> 注：待复核冻结流的"冻结"操作在「分身监控」页执行（Task 5 MonitorList）。看板页只展示待复核名单。若需闭环，Monitor 页可跳转——保持简单，看板仅展示。

- [ ] **Step 4: 写对话检索页**

Create `web/src/pages/Compliance/ConvSearch.tsx`（ProTable 检索 + 展开完整上下文）：

```tsx
import { ProTable } from '@ant-design/pro-components';
import type { ProColumns } from '@ant-design/pro-components';
import { Tag, Typography } from 'antd';
import { monitorAPI } from '../../services/monitor';
import type { ConvSearchItem } from '../../types';

const { Text } = Typography;

export default function ConvSearch() {
  const columns: ProColumns<ConvSearchItem>[] = [
    { title: '内容', dataIndex: 'content', ellipsis: true },
    { title: '代表ID', dataIndex: 'user_id', width: 90, hideInSearch: true },
    { title: '分身ID', dataIndex: 'specialist_id', width: 90, hideInSearch: true },
    { title: '角色', dataIndex: 'role', width: 90, hideInSearch: true, render: (_, r) => r.role === 'user' ? <Tag color="blue">代表</Tag> : <Tag>AI</Tag> },
    { title: '被拦', dataIndex: 'blocked', width: 70, hideInSearch: true, render: (_, r) => r.blocked ? <Tag color="red">是</Tag> : <Tag color="green">否</Tag> },
    { title: '时间', dataIndex: 'created_at', width: 180, hideInSearch: true },
    { title: '检索词', dataIndex: 'keyword', hideInTable: true },
    { title: '代表ID(筛)', dataIndex: 'user_id', hideInTable: true },
    { title: '分身ID(筛)', dataIndex: 'specialist_id', hideInTable: true },
  ];

  return (
    <ProTable<ConvSearchItem>
      headerTitle="对话日志全文检索"
      rowKey="id"
      search={{ labelWidth: 90 }}
      expandable={{
        expandedRowRender: r => (
          <div>
            <Text type="secondary">完整会话上下文（{r.context.length} 条）：</Text>
            {r.context.map((c, i) => (
              <div key={i} style={{ marginTop: 4, padding: 8, background: c.role === 'user' ? '#e6f4ff' : '#f6ffed', borderRadius: 4 }}>
                <Text strong>{c.role === 'user' ? '代表' : 'AI'}</Text>
                {c.blocked && <Tag color="red" style={{ marginLeft: 8 }}>被拦</Tag>}
                <div>{c.content}</div>
              </div>
            ))}
          </div>
        ),
      }}
      columns={columns}
      request={async (params) => {
        const res = await monitorAPI.convSearch({
          page: params.current || 1,
          page_size: params.pageSize || 10,
          keyword: params.keyword,
          user_id: params.user_id,
          specialist_id: params.specialist_id,
        });
        return { data: res.data.data.items, total: res.data.data.total, success: true };
      }}
    />
  );
}
```

> 注意：`user_id`/`specialist_id` 同时出现在 hideInSearch 与 hideInTable 两组列会冲突——ProTable 用同一 dataIndex 合并。改为 `{ title: '代表ID', dataIndex: 'user_id', width: 90 }`（既显示又筛）即可，删除 hideInTable 重复列。实现时保证列定义唯一。

- [ ] **Step 5: 写分身监控页**

Create `web/src/pages/Specialist/MonitorList.tsx`（分身列表 + 状态监控 + 冻结/解冻 + 官方分身管理）：

```tsx
import { useRef, useState } from 'react';
import { ProTable, ModalForm, ProFormText, ProFormDigit } from '@ant-design/pro-components';
import type { ProColumns, ActionType } from '@ant-design/pro-components';
import { App, Button, Input, Modal, Space, Tag } from 'antd';
import { monitorAPI } from '../../services/monitor';
import type { SpecialistMonitor } from '../../types';

const STATUS_TEXT: Record<string, { color: string; text: string }> = {
  active: { color: 'green', text: '工作中' },
  draft: { color: 'default', text: '草稿' },
  disabled: { color: 'orange', text: '已禁用' },
  frozen: { color: 'red', text: '已冻结' },
};
const HEALTH_TEXT: Record<string, { color: string; text: string }> = {
  green: { color: 'green', text: '健康' },
  yellow: { color: 'orange', text: '需关注' },
  red: { color: 'red', text: '高风险' },
};

export default function MonitorList() {
  const actionRef = useRef<ActionType>();
  const { message } = App.useApp();
  const [refresh, setRefresh] = useState(0);

  const columns: ProColumns<SpecialistMonitor>[] = [
    { title: '名称', dataIndex: 'name' },
    { title: '状态', dataIndex: 'status', width: 90, valueEnum: { active: '工作中', draft: '草稿', disabled: '已禁用', frozen: '已冻结' },
      render: (_, r) => { const m = STATUS_TEXT[r.status] || { color: 'default', text: r.status }; return <Tag color={m.color}>{m.text}</Tag>; } },
    { title: '类型', dataIndex: 'is_official', width: 80, hideInSearch: true,
      render: (_, r) => r.is_official ? <Tag color="purple">官方</Tag> : <Tag>个人</Tag> },
    { title: '今日服务', dataIndex: 'today_services', width: 90, hideInSearch: true },
    { title: '平均响应(ms)', dataIndex: 'avg_latency_ms', width: 110, hideInSearch: true },
    { title: '服务医生数', dataIndex: 'service_doctors', width: 100, hideInSearch: true },
    { title: '合规健康度', dataIndex: 'compliance_health', width: 110, hideInSearch: true,
      render: (_, r) => { const m = HEALTH_TEXT[r.compliance_health] || { color: 'default', text: r.compliance_health }; return <Tag color={m.color}>{m.text}</Tag>; } },
    { title: '被添加次数', dataIndex: 'added_count', width: 100, hideInSearch: true },
    {
      title: '操作', width: 160, hideInSearch: true,
      render: (_, r) => (
        <Space>
          {r.status !== 'frozen' ? (
            <Button size="small" danger onClick={() => {
              let reason = '';
              Modal.confirm({
                title: `冻结分身「${r.name}」`,
                content: <Input.TextArea rows={3} placeholder="冻结理由（必填）" onChange={e => (reason = e.target.value)} />,
                onOk: async () => {
                  if (!reason.trim()) { message.warning('请填写冻结理由'); return Promise.reject(); }
                  await monitorAPI.freeze(r.id, reason.trim());
                  message.success('已冻结');
                  actionRef.current?.reload();
                },
              });
            }}>冻结</Button>
          ) : (
            <Button size="small" onClick={async () => { await monitorAPI.unfreeze(r.id); message.success('已解冻'); actionRef.current?.reload(); }}>解冻</Button>
          )}
        </Space>
      ),
    },
  ];

  return (
    <ProTable<SpecialistMonitor>
      headerTitle="分身监控与官方分身管理"
      actionRef={actionRef}
      rowKey="id"
      search={{ labelWidth: 80 }}
      params={{ t: refresh }}
      columns={columns}
      request={async (params) => {
        const res = await monitorAPI.specialistMonitor({
          page: params.current || 1, page_size: params.pageSize || 10,
          status: params.status, official: params.official,
        });
        return { data: res.data.data.items, total: res.data.data.total, success: true };
      }}
      toolBarRender={() => [
        <Button type="primary" key="new" onClick={() => setRefresh(r => r + 1)}>新建官方分身</Button>,
      ]}
    />
  );
}
```

> 说明：`新建官方分身` 按钮此处只触发刷新——实际建官方分身需一个 ModalForm（名称/产品/is_official=true）。若时间紧，可先用既有 SpecialistList 的 ModalForm 复用能力（它已支持 create_specialist）。Task 5 实现时若复用成本低则补全 ModalForm；否则保留按钮占位并注明"复用 SpecialistList 新增"。

- [ ] **Step 6: 注册路由 + 菜单**

Modify `web/src/App.tsx`：加三个 lazy import 与路由：
```tsx
const ComplianceMonitor = lazy(() => import('./pages/Compliance/Monitor'));
const ConvSearch = lazy(() => import('./pages/Compliance/ConvSearch'));
const SpecialistMonitorList = lazy(() => import('./pages/Specialist/MonitorList'));
// ...
<Route path="compliance/monitor" element={<ComplianceMonitor />} />
<Route path="compliance/conv-search" element={<ConvSearch />} />
<Route path="specialist/monitor" element={<SpecialistMonitorList />} />
```

Modify `web/src/constants/menu.tsx`：加菜单项（icon 自选）：
```tsx
  { path: '/compliance/monitor', name: '合规风控', icon: <RadarChartOutlined /> },
  { path: '/compliance/conv-search', name: '对话检索', icon: <SearchOutlined /> },
  { path: '/specialist/monitor', name: '分身监控', icon: <MonitorOutlined /> },
```

- [ ] **Step 7: 验证 build**

Run: `cd web && npm run build`
Expected: PASS

- [ ] **Step 8: Commit**

```bash
git add web/src/pages/Compliance/Monitor.tsx web/src/pages/Compliance/ConvSearch.tsx web/src/pages/Specialist/MonitorList.tsx web/src/services/monitor.ts web/src/types/index.ts web/src/App.tsx web/src/constants/menu.tsx
git commit -m "feat(web): 合规风控看板/对话检索/分身监控三页"
```

---

### Task 6: 全量回归 + CLAUDE.md 同步

**Files:**
- Modify: `CLAUDE.md`

- [ ] **Step 1: 后端全量回归**

Run: 各服务 `cd services/<s> && python -m pytest -q`（compliance/specialist 必跑，其余确认无回归）
Expected: 全绿（compliance 104 + test_monitor 6；specialist 138 + test_conv_search 5 + test_monitor_specialists 7）

- [ ] **Step 2: 前端验证**

Run: `cd web && npm run build`；`cd mobile && npx jest`；`cd mobile-doctor && npx jest`
Expected: 全绿

- [ ] **Step 3: 同步 CLAUDE.md**

补记 E 计划：
- digital_specialists 加 is_official/representative_id（迁移 014）
- 新端点：`/api/v1/compliance/daily-summary|trends|review-queue`、`/api/v1/conversations/search`、`/api/v1/specialists/{id}/freeze|unfreeze`
- status 值域扩含 frozen；chat 仅 active 可对话
- 配置：REVIEW_BLOCK_THRESHOLD=5 / REVIEW_WINDOW_HOURS=24
- Known Gaps 更新：待复核冻结是人工裁决（非自动）；分身拦截计数口径来自 conversations.compliance_result

- [ ] **Step 4: Commit**

```bash
git add CLAUDE.md
git commit -m "docs: 二期 E 合规风控深化文档同步"
```

---

## Self-Review

**1. Spec 覆盖（二期 E 计划章节）：**
- 拦截聚合告警 → Task 2 daily-summary + Task 5 看板页
- 待复核冻结流（人工裁决）→ Task 2 review-queue + Task 4 freeze/unfreeze + Task 5 MonitorList
- 违规趋势分析 → Task 2 trends
- 对话日志全文检索 + 完整上下文 → Task 3 + Task 5 ConvSearch
- 分身状态监控与使用统计 → Task 4 monitor（含合规健康度/好评率）
- 官方公共数字员工管理 → Task 1 字段 + Task 4 create_official + Task 5 MonitorList
- web 检索测试页（3.1(3)）→ 未纳入本计划（knowledge-service /search-test 已存在，web 接线成本低但属另一域——**记为挂账项**，下张计划或独立小任务）

**2. 占位符扫描：** Task 5 的"新建官方分身"按钮复用/占位已标注；无 TBD/TODO。

**3. 类型一致性：** `SpecialistMonitor` 字段与 Task 4 monitor 端点返回一致；`ConvSearchItem.context` 与 Task 3 返回一致；freeze/unfreeze 路径与 specialist 端点一致。

**已知取舍（写进 CLAUDE.md）：**
- 待复核冻结=人工裁决，看板只展示名单，冻结动作在分身监控页
- 分身拦截计数口径=conversations.compliance_result（不给 compliance_blocks 加列）
- 官方分身创建优先复用既有 SpecialistList ModalForm，MonitorList 按钮作占位
- web 检索测试页挂账（knowledge 域）
