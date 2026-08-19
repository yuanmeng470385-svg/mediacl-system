# 学术触达 实施计划（二期 G）

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 上线学术卡片从生成到回流闭环：代表端 AI 生成学术卡片 → 推送已添加分身的医生 → 医生端接收/阅读/反馈 → 反馈回流代表简报 + 触达统计。

**Architecture:** 服务归属 specialist-service（与 share_links/nightly_briefings 同域，复用 qwen 客户端与 OSS）。两张新表：academic_cards / card_push_records。卡片生成走 qwen 辅助 + 三层合规预检（复用 compliance_client）；推送对象 = doctor_twin_subscriptions 中订阅了该代表分身且 status='subscribed' 的 doctor 用户（已建立关联 + 知情同意）；阅读追踪用 tracked_seconds 秒数；反馈（有用/无用/追问）回流；触达统计聚合。简报真实通知渠道（一期 C 挂账）并入本计划。

**Tech Stack:** Python FastAPI（specialist-service）/ React Native 0.75（mobile 代表端 + mobile-doctor 医生端）/ React + Ant Design Pro（web 运营）/ PostgreSQL 迁移 015 / 既有 qwen_client + compliance_client。

## Global Constraints

- 服务归属 specialist-service；新端点前缀 `/api/v1/academic-cards`、`/api/v1/card-pushes`；网关 ROUTE_MAP 加两行 → SPECIALIST_SERVICE_URL。
- 权限：卡片生成/推送/追踪 → rep；卡片接收/反馈 → doctor；触达统计 → admin/manager/compliance/medical。
- 推送对象限定 = `doctor_twin_subscriptions`（doctor_id, twin_id, status='subscribed'）中该代表名下的分身（digital_specialists.representative_id=当前 rep）所关联的 doctor 用户；不推给 hcps 档案（无 app 接收能力）。
- 卡片内容必须过三层合规预检（compliance_client），命中拦截 → fail-closed 拒绝生成（不落库）。
- AI 生成内容标注 `is_ai_generated=true`；卡片含引用（citations 复用 medical.py 的 `_retrieve` + 引用口径：文档名/版本/章节，无页码）。
- 阅读追踪：read_status（unread/read/favorited/forwarded）+ read_at + tracked_seconds（医生端停留秒数）；反馈：feedback（useful/useless/追问文本）。
- 简报通知渠道：夜间简报生成后写一条代表端通知（本计划建 `notifications` 表做站内信，代表端简报列表拉取）。
- 复用 `shared.common.response` / `shared.common.pagination`；测试遵循 specialist-service 既有模式（SQLite+StaticPool+BigInteger compile+dependency_overrides+qwen/compliance monkeypatch）。
- 提交规范：conventional commits + Co-Authored-By；推 Codeup 前用户确认。

## File Structure

**specialist-service：**
- Create: `services/specialist-service/app/api/academic_cards.py` — 卡片生成（rep）/ 列表 / 推送（rep）/ 触达统计
- Create: `services/specialist-service/app/api/card_pushes.py` — 医生端接收列表 / 阅读追踪 / 反馈 / 简报通知查询
- Modify: `services/specialist-service/app/main.py` — 注册两个 router
- Modify: `services/specialist-service/app/services/qwen_client.py` — 加卡片生成方法（或复用 medical 的 `_qwen_json` 模式）
- Modify: `services/gateway/app/main.py` — ROUTE_MAP 两行
- Test: `services/specialist-service/tests/test_academic_cards.py`、`test_card_pushes.py`

**DB：**
- Create: `scripts/migrations/015_academic_cards.sql`
- Modify: `scripts/init_db.sql`
- Create: `shared/models/academic.py`

**mobile 代表端：**
- Create: `mobile/src/screens/Academic/CardCreateScreen.tsx` — 卡片生成 + 推送对象选择
- Create: `mobile/src/screens/Academic/CardListScreen.tsx` — 我的卡片 + 阅读追踪
- Create: `mobile/src/api/academic.ts`
- Modify: `mobile/src/navigation/types.ts` + `AppNavigator.tsx` + `ProfileScreen.tsx`（入口）
- Test: `mobile/src/api/__tests__/academic-contract.test.ts`

**mobile-doctor 医生端：**
- Create: `mobile-doctor/src/screens/Inbox/InboxScreen.tsx` — 学术卡片接收列表
- Create: `mobile-doctor/src/screens/Inbox/CardDetailScreen.tsx` — 卡片详情 + 反馈
- Create: `mobile-doctor/src/api/inbox.ts`
- Modify: `mobile-doctor/src/navigation/types.ts` + `AppNavigator.tsx` + `ProfileScreen.tsx`（入口）
- Test: `mobile-doctor/src/api/__tests__/inbox-contract.test.ts`

**web：**
- Create: `web/src/pages/Compliance/CardStats.tsx` — 学术内容触达统计
- Create: `web/src/services/cardStats.ts`
- Modify: `web/src/types/index.ts`、`web/src/App.tsx`、`web/src/constants/menu.tsx`
- Test: `cd web && npm run build`

**Docs：**
- Modify: `CLAUDE.md`

---

### Task 1: 迁移 015 + 模型（academic_cards / card_push_records / notifications）

**Files:**
- Create: `scripts/migrations/015_academic_cards.sql`
- Modify: `scripts/init_db.sql`
- Create: `shared/models/academic.py`

**Interfaces:**
- Produces: `AcademicCard` / `CardPushRecord` / `Notification`（shared/models/academic.py，继承 `shared.models.base.Base` + `TimestampMixin`），字段名供 Task 2-6 使用。

- [ ] **Step 1: 写迁移文件**

Create `scripts/migrations/015_academic_cards.sql`：

```sql
-- 015_academic_cards.sql
-- 二期 G：学术卡片 / 卡片推送记录 / 站内通知（需求 4.6/5.3/6.3/3.7(1)）
-- 用法：docker exec -i medagent-postgres psql -U medagent medagent < scripts/migrations/015_academic_cards.sql

\set ON_ERROR_STOP on

CREATE TABLE IF NOT EXISTS academic_cards (
    id BIGSERIAL PRIMARY KEY,
    representative_id BIGINT NOT NULL REFERENCES users(id),
    title VARCHAR(200) NOT NULL,
    content JSONB NOT NULL,              -- {conclusion, key_points[], summary, citations[]}
    is_ai_generated BOOLEAN NOT NULL DEFAULT TRUE,
    compliance_status VARCHAR(20) NOT NULL DEFAULT 'passed',  -- passed/blocked
    status VARCHAR(20) NOT NULL DEFAULT 'active',             -- active/archived
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_ac_rep ON academic_cards(representative_id);

CREATE TABLE IF NOT EXISTS card_push_records (
    id BIGSERIAL PRIMARY KEY,
    representative_id BIGINT NOT NULL REFERENCES users(id),
    card_id BIGINT NOT NULL REFERENCES academic_cards(id),
    doctor_id BIGINT NOT NULL REFERENCES users(id),
    read_status VARCHAR(20) NOT NULL DEFAULT 'unread',  -- unread/read/favorited/forwarded
    read_at TIMESTAMP,
    tracked_seconds INTEGER NOT NULL DEFAULT 0,
    feedback VARCHAR(500),                                -- useful/useless/追问文本
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW(),
    CONSTRAINT uq_push UNIQUE (card_id, doctor_id)
);
CREATE INDEX IF NOT EXISTS idx_cpr_doctor ON card_push_records(doctor_id);
CREATE INDEX IF NOT EXISTS idx_cpr_rep ON card_push_records(representative_id);

CREATE TABLE IF NOT EXISTS notifications (
    id BIGSERIAL PRIMARY KEY,
    user_id BIGINT NOT NULL REFERENCES users(id),
    type VARCHAR(20) NOT NULL,            -- briefing_ready/card_feedback/card_question
    title VARCHAR(200) NOT NULL,
    content VARCHAR(1000),
    link VARCHAR(200),
    is_read BOOLEAN NOT NULL DEFAULT FALSE,
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_notif_user ON notifications(user_id, is_read);
```

- [ ] **Step 2: init_db.sql 同步**

在 `scripts/init_db.sql` 末尾追加与迁移 015 完全一致的三段 `CREATE TABLE IF NOT EXISTS` + 索引（copy Step 1，去掉 `\set ON_ERROR_STOP` 与注释头两行）。

- [ ] **Step 3: 写模型**

Create `shared/models/academic.py`：

```python
"""学术触达模型（需求 4.6/5.3/6.3/附录A push_records + 站内通知）"""
from datetime import datetime

from sqlalchemy import BigInteger, Boolean, Column, DateTime, ForeignKey, Integer, String
from sqlalchemy.dialects.postgresql import JSONB

from shared.models.base import Base, TimestampMixin


class AcademicCard(Base, TimestampMixin):
    __tablename__ = "academic_cards"

    representative_id = Column(BigInteger, ForeignKey("users.id"), nullable=False)
    title = Column(String(200), nullable=False)
    content = Column(JSONB, nullable=False)
    is_ai_generated = Column(Boolean, nullable=False, default=True)
    compliance_status = Column(String(20), default="passed")
    status = Column(String(20), default="active")

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "representative_id": self.representative_id,
            "title": self.title,
            "content": self.content,
            "is_ai_generated": self.is_ai_generated,
            "compliance_status": self.compliance_status,
            "status": self.status,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }


class CardPushRecord(Base, TimestampMixin):
    __tablename__ = "card_push_records"
    __table_args__ = (__import__("sqlalchemy").UniqueConstraint("card_id", "doctor_id", name="uq_push"),)

    representative_id = Column(BigInteger, ForeignKey("users.id"), nullable=False)
    card_id = Column(BigInteger, ForeignKey("academic_cards.id"), nullable=False)
    doctor_id = Column(BigInteger, ForeignKey("users.id"), nullable=False)
    read_status = Column(String(20), default="unread")
    read_at = Column(DateTime)
    tracked_seconds = Column(Integer, default=0)
    feedback = Column(String(500))

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "representative_id": self.representative_id,
            "card_id": self.card_id,
            "doctor_id": self.doctor_id,
            "read_status": self.read_status,
            "read_at": self.read_at.isoformat() if self.read_at else None,
            "tracked_seconds": self.tracked_seconds,
            "feedback": self.feedback,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }


class Notification(Base, TimestampMixin):
    __tablename__ = "notifications"

    user_id = Column(BigInteger, ForeignKey("users.id"), nullable=False)
    type = Column(String(20), nullable=False)   # briefing_ready / card_feedback / card_question
    title = Column(String(200), nullable=False)
    content = Column(String(1000))
    link = Column(String(200))
    is_read = Column(Boolean, nullable=False, default=False)

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "user_id": self.user_id,
            "type": self.type,
            "title": self.title,
            "content": self.content,
            "link": self.link,
            "is_read": self.is_read,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }
```

> 注意：`CardPushRecord` 用 `__table_args__` 定义唯一约束；SQLite 测试无需特殊处理（unique 约束在 SQLite 生效）。

- [ ] **Step 4: 验证模型可建表**

Run: `cd services/specialist-service && python -c "import sys,os; sys.path.insert(0,'.'); from shared.models.academic import AcademicCard, CardPushRecord, Notification; print('ok')"`
Expected: `ok`

- [ ] **Step 5: Commit**

```bash
git add scripts/migrations/015_academic_cards.sql scripts/init_db.sql shared/models/academic.py
git commit -m "feat(auth): 学术触达三表迁移+模型（academic_cards/card_push_records/notifications）"
```

---

### Task 2: 卡片生成端点（rep）+ 合规预检

**Files:**
- Create: `services/specialist-service/app/api/academic_cards.py`
- Modify: `services/specialist-service/app/main.py`
- Test: `services/specialist-service/tests/test_academic_cards.py`

**Interfaces:**
- Consumes: `AcademicCard`、`_qwen_json`（medical.py 模式）、`compliance_client`、`_retrieve`
- Produces: `academic_cards_router`（prefix `/api/v1/academic-cards`）；`POST ""`（rep 生成卡片：AI 生成 + 合规预检 + 落库）、`GET ""`（rep 我的卡片分页）。

- [ ] **Step 1: 写失败测试**

Create `services/specialist-service/tests/test_academic_cards.py`（骨架参照现有 specialist 测试，SQLite+StaticPool+BigInteger compile+dependency_overrides）：

```python
"""学术卡片生成测试（Task 2）：rep 生成 + 合规预检 + 权限"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", ".."))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

os.environ.setdefault("JWT_SECRET", "test-secret-not-a-default-value")
os.environ["AUTH_DEV_MODE"] = "true"

from unittest.mock import AsyncMock, patch

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import BigInteger, create_engine
from sqlalchemy.ext.compiler import compiles
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from shared.common.auth import create_token
from shared.common.db_session import get_db
from shared.models.base import Base
from shared.models.academic import AcademicCard, CardPushRecord, Notification
from shared.models.digital_specialist import Specialist
from shared.models.user import User

import app.api.academic_cards as ac_api
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
    tables = [User.__table__, Specialist.__table__, AcademicCard.__table__,
              CardPushRecord.__table__, Notification.__table__]
    Base.metadata.drop_all(engine, tables=tables)
    Base.metadata.create_all(engine, tables=tables)
    db = TestSession()
    db.add_all([
        User(id=1, username="rep01", full_name="张代表", phone="13800000001", role="rep", status="active"),
        User(id=2, username="doctor1", full_name="王医生", phone="13800000002", role="doctor", status="active"),
        User(id=3, username="admin", full_name="管理员", phone="13800000000", role="admin", status="active"),
    ])
    db.commit()
    db.close()
    monkeypatch.setitem(app.dependency_overrides, get_db, _override_db)
    yield


def test_create_card_requires_rep():
    resp = client.post("/api/v1/academic-cards", json={"title": "高血压指南", "topic": "高血压"},
                       headers=_token(3, "admin"))
    assert resp.status_code == 403
    assert resp.json()["code"] == 3000


def test_create_card_ai_generate_and_pass(fresh_state, monkeypatch):
    fake_card = {
        "conclusion": "高血压患者应限盐。",
        "key_points": ["限盐≤5g/日", "定期监测"],
        "summary": "一句话：控盐降压。",
        "citations": [{"doc_name": "高血压防治指南", "version": "2024版", "section": "生活方式干预"}],
    }
    monkeypatch.setattr(ac_api, "_generate_card_content", AsyncMock(return_value=fake_card))
    monkeypatch.setattr(ac_api, "check_compliance", AsyncMock(return_value={"blocked": False}))

    resp = client.post("/api/v1/academic-cards", json={"title": "高血压指南", "topic": "高血压"},
                       headers=_token(1, "rep"))
    body = resp.json()
    assert body["code"] == 0
    data = body["data"]
    assert data["title"] == "高血压指南"
    assert data["is_ai_generated"] is True
    assert data["compliance_status"] == "passed"
    assert data["content"]["conclusion"] == "高血压患者应限盐。"


def test_create_card_blocked_fails_closed(fresh_state, monkeypatch):
    fake_card = {
        "conclusion": "保证治好。",
        "key_points": [], "summary": "x",
        "citations": [],
    }
    monkeypatch.setattr(ac_api, "_generate_card_content", AsyncMock(return_value=fake_card))
    monkeypatch.setattr(ac_api, "check_compliance", AsyncMock(return_value={"blocked": True, "rule_code": "R001"}))

    resp = client.post("/api/v1/academic-cards", json={"title": "违规卡", "topic": "疗效"},
                       headers=_token(1, "rep"))
    assert resp.status_code == 400
    assert resp.json()["code"] == 1000
    assert "合规" in resp.json()["message"]


def test_list_my_cards():
    db = TestSession()
    db.add(AcademicCard(id=1, representative_id=1, title="卡1", content={"conclusion": "x"}, is_ai_generated=True))
    db.add(AcademicCard(id=2, representative_id=99, title="别人的卡", content={"conclusion": "y"}, is_ai_generated=True))
    db.commit()
    db.close()

    resp = client.get("/api/v1/academic-cards", headers=_token(1, "rep"))
    body = resp.json()
    assert body["code"] == 0
    assert body["data"]["total"] == 1
    assert body["data"]["items"][0]["title"] == "卡1"
```

- [ ] **Step 2: 运行测试确认失败**

Run: `cd services/specialist-service && python -m pytest tests/test_academic_cards.py -q`
Expected: 失败（模块不存在）

- [ ] **Step 3: 实现卡片生成端点**

Create `services/specialist-service/app/api/academic_cards.py`：

```python
"""学术卡片（二期 G，需求 4.6(1)(3)）：rep 生成卡片 → 三层合规预检 → 落库 → 推送医生"""
import asyncio
import logging
from typing import Optional

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from shared.common.auth import get_current_user, require_roles
from shared.common.context import get_request_id
from shared.common.db_session import get_db
from shared.common.pagination import PaginationParams, paginate
from shared.common.response import BusinessError, ParamError, PermissionError, success
from shared.models.academic import AcademicCard

from app.api.medical import _qwen_json, _retrieve
from app.services.audit_client import write_audit_log
from app.services.compliance_client import check_compliance

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/academic-cards", tags=["academic-cards"])


async def _generate_card_content(topic: str, title: str) -> dict:
    """AI 生成学术卡片内容（qwen 辅助，返回结构化内容；引用来自知识库检索）"""
    retrieved = await _retrieve(topic, top_k=3)
    citations = [{
        "doc_name": c.get("doc_name") or c.get("title", ""),
        "version": c.get("version", ""),
        "section": c.get("section", ""),
        "file_url": c.get("file_url"),
    } for c in retrieved if c]
    prompt = (
        "你是药企医学部的学术内容助手。基于提供的知识库引用，生成学术卡片。\n"
        "只输出 JSON，格式：\n"
        '{"conclusion": "核心结论", "key_points": ["要点1", "要点2"], "summary": "一句话总结"}\n'
        "要求：内容严格来自引用，不编造；不含疗效承诺、不含具体用量指导。\n"
        f"引用来源：\n<user_content>{citations}</user_content>"
    )
    result = await asyncio.to_thread(_qwen_json, prompt)
    return {
        "conclusion": result.get("conclusion", ""),
        "key_points": result.get("key_points", []),
        "summary": result.get("summary", ""),
        "citations": citations,
    }


@router.post("")
async def create_card(
    payload: dict,
    current_user: dict = Depends(require_roles("rep")),
    db: Session = Depends(get_db),
):
    """rep 生成学术卡片：AI 生成 + 三层合规预检（fail-closed）"""
    if not isinstance(payload, dict):
        raise ParamError("请求体必须是 JSON 对象")
    title = (payload.get("title") or "").strip()
    topic = (payload.get("topic") or "").strip()
    if not title or len(title) > 200:
        raise ParamError("标题必填且不超过 200 字符")
    if not topic:
        raise ParamError("主题必填")

    try:
        content = await _generate_card_content(topic, title)
    except Exception as exc:
        logger.warning(f"卡片 AI 生成失败: {exc}")
        raise BusinessError("AI 生成失败，请稍后重试", code=6001)

    # 三层合规预检：结论 + 要点 + 总结拼接检查（fail-closed）
    text_to_check = " ".join([
        content.get("conclusion", ""),
        *content.get("key_points", []),
        content.get("summary", ""),
    ])
    try:
        comp = await check_compliance(text_to_check)
    except Exception as exc:
        logger.warning(f"卡片合规预检失败: {exc}")
        raise BusinessError("合规检查失败，请稍后重试", code=6001)
    if comp.get("blocked"):
        raise ParamError(f"内容未通过合规检查：{comp.get('rule_code', 'R999')}")

    card = AcademicCard(
        representative_id=current_user["id"],
        title=title,
        content=content,
        is_ai_generated=True,
        compliance_status="passed",
        status="active",
    )
    db.add(card)
    db.commit()
    db.refresh(card)
    await write_audit_log(
        action="academic_card_create",
        user_id=current_user["id"],
        resource_type="academic_card",
        resource_id=str(card.id),
        after_value={"title": title},
        request_id=get_request_id() or None,
    )
    return success(card.to_dict())


@router.get("")
async def list_my_cards(
    page: int = 1,
    page_size: int = 20,
    current_user: dict = Depends(require_roles("rep")),
    db: Session = Depends(get_db),
):
    p = PaginationParams(page=page, page_size=page_size)
    query = db.query(AcademicCard).filter(
        AcademicCard.representative_id == current_user["id"],
        AcademicCard.status == "active",
    )
    total = query.count()
    rows = query.order_by(AcademicCard.id.desc()).offset(p.offset).limit(p.limit).all()
    return success(paginate([c.to_dict() for c in rows], total, p.page, p.page_size))
```

> 需要确认 `check_compliance` 从 `app.services.compliance_client` 导入的签名（返回 dict 含 blocked/rule_code）。若与 brief 不同以实际为准。

- [ ] **Step 4: 注册 router**

Modify `services/specialist-service/app/main.py`：追加 `from app.api.academic_cards import router as academic_cards_router` + `app.include_router(academic_cards_router)`。

- [ ] **Step 5: 运行测试确认通过**

Run: `cd services/specialist-service && python -m pytest tests/test_academic_cards.py -q`
Expected: 4 passed

- [ ] **Step 6: Commit**

```bash
git add services/specialist-service/app/api/academic_cards.py services/specialist-service/app/main.py services/specialist-service/tests/test_academic_cards.py
git commit -m "feat(specialist): 学术卡片生成端点（AI+合规预检）"
```

---

### Task 3: 卡片推送 + 医生端接收/阅读追踪/反馈

**Files:**
- Modify: `services/specialist-service/app/api/academic_cards.py`（推送端点）
- Create: `services/specialist-service/app/api/card_pushes.py`
- Modify: `services/specialist-service/app/main.py`
- Test: `services/specialist-service/tests/test_card_pushes.py`

**Interfaces:**
- Consumes: `AcademicCard`、`CardPushRecord`、`DoctorTwinSubscription`、`Notification`、`User`
- Produces: `POST /api/v1/academic-cards/{card_id}/push`（rep 推送给订阅了其分身的医生）、`card_pushes_router`（prefix `/api/v1/card-pushes`）：`GET ""`（doctor 接收列表）、`POST /{push_id}/track`（阅读追踪）、`POST /{push_id}/feedback`（反馈）、`GET /notifications`（代表/医生通知）。

- [ ] **Step 1: 写失败测试**

Create `services/specialist-service/tests/test_card_pushes.py`（骨架同 Task 2 测试）：

```python
"""卡片推送/接收/追踪/反馈测试（Task 3）"""
# (imports 与 fixture 同 test_academic_cards.py，含 User/Specialist/AcademicCard/CardPushRecord/Notification/DoctorTwinSubscription 七表)

from shared.models.doctor import DoctorTwinSubscription


def test_push_requires_rep():
    resp = client.post("/api/v1/academic-cards/1/push", json={"doctor_ids": [2]}, headers=_token(3, "admin"))
    assert resp.status_code == 403


def test_push_creates_records(fresh_state):
    db = TestSession()
    db.add(AcademicCard(id=1, representative_id=1, title="卡", content={"conclusion": "x"}, is_ai_generated=True))
    db.add(DoctorTwinSubscription(id=1, doctor_id=2, twin_id=1, status="subscribed", consent_version="1.0"))
    db.add(Specialist(id=1, name="分身", product_id=1, status="active", representative_id=1))
    db.commit()
    db.close()

    resp = client.post("/api/v1/academic-cards/1/push", json={"doctor_ids": [2]}, headers=_token(1, "rep"))
    body = resp.json()
    assert body["code"] == 0
    assert body["data"]["pushed"] == 1
    assert body["data"]["skipped"] == 0

    db = TestSession()
    rec = db.query(CardPushRecord).filter_by(card_id=1, doctor_id=2).first()
    assert rec is not None
    assert rec.read_status == "unread"
    db.close()


def test_push_only_subscribed_doctors(fresh_state):
    # doctor 3 未订阅该代表分身 → skipped
    db = TestSession()
    db.add(AcademicCard(id=1, representative_id=1, title="卡", content={"conclusion": "x"}, is_ai_generated=True))
    db.add(Specialist(id=1, name="分身", product_id=1, status="active", representative_id=1))
    db.add(DoctorTwinSubscription(id=1, doctor_id=2, twin_id=1, status="subscribed", consent_version="1.0"))
    db.commit()
    db.close()
    # doctor 3 未建订阅

    resp = client.post("/api/v1/academic-cards/1/push", json={"doctor_ids": [2, 3]}, headers=_token(1, "rep"))
    body = resp.json()
    assert body["code"] == 0
    assert body["data"]["pushed"] == 1
    assert body["data"]["skipped"] == 1


def test_doctor_inbox_lists_pushes():
    db = TestSession()
    db.add(AcademicCard(id=1, representative_id=1, title="高血压指南", content={"conclusion": "控盐"},
                        is_ai_generated=True))
    db.add(CardPushRecord(id=1, representative_id=1, card_id=1, doctor_id=2, read_status="unread"))
    db.commit()
    db.close()

    resp = client.get("/api/v1/card-pushes", headers=_token(2, "doctor"))
    body = resp.json()
    assert body["code"] == 0
    assert body["data"]["total"] == 1
    assert body["data"]["items"][0]["card"]["title"] == "高血压指南"


def test_track_read(fresh_state):
    db = TestSession()
    db.add(CardPushRecord(id=1, representative_id=1, card_id=1, doctor_id=2, read_status="unread"))
    db.commit()
    db.close()

    resp = client.post("/api/v1/card-pushes/1/track", json={"read_status": "read", "seconds": 42},
                       headers=_token(2, "doctor"))
    body = resp.json()
    assert body["code"] == 0
    assert body["data"]["read_status"] == "read"
    assert body["data"]["tracked_seconds"] == 42


def test_feedback_useful_notifies_rep(fresh_state):
    db = TestSession()
    db.add(CardPushRecord(id=1, representative_id=1, card_id=1, doctor_id=2, read_status="read"))
    db.commit()
    db.close()

    resp = client.post("/api/v1/card-pushes/1/feedback", json={"feedback": "useful"},
                       headers=_token(2, "doctor"))
    body = resp.json()
    assert body["code"] == 0
    assert body["data"]["feedback"] == "useful"
    # 通知回流给代表
    db = TestSession()
    n = db.query(Notification).filter_by(user_id=1, type="card_feedback").first()
    assert n is not None
    db.close()


def test_doctor_inbox_rejects_rep():
    resp = client.get("/api/v1/card-pushes", headers=_token(1, "rep"))
    assert resp.status_code == 403
```

- [ ] **Step 2: 运行测试确认失败**

Run: `cd services/specialist-service && python -m pytest tests/test_card_pushes.py -q`
Expected: 失败（端点不存在）

- [ ] **Step 3: 实现推送端点**

Modify `services/specialist-service/app/api/academic_cards.py`，追加：

```python
from shared.models.academic import CardPushRecord, Notification
from shared.models.doctor import DoctorTwinSubscription


@router.post("/{card_id}/push")
async def push_card(
    card_id: int,
    payload: dict,
    current_user: dict = Depends(require_roles("rep")),
    db: Session = Depends(get_db),
):
    """rep 推送卡片给订阅了其分身且 status='subscribed' 的医生。"""
    if not isinstance(payload, dict):
        raise ParamError("请求体必须是 JSON 对象")
    doctor_ids = payload.get("doctor_ids")
    if not isinstance(doctor_ids, list) or not doctor_ids:
        raise ParamError("doctor_ids 必须是医生 ID 数组")
    if len(doctor_ids) > 50:
        raise ParamError("一次最多推送 50 位医生")

    card = db.query(AcademicCard).filter(
        AcademicCard.id == card_id,
        AcademicCard.representative_id == current_user["id"],
        AcademicCard.status == "active",
    ).first()
    if not card:
        raise BusinessError("卡片不存在", code=4001)

    # 该代表的全部分身
    my_twins = db.query(Specialist.id).filter(Specialist.representative_id == current_user["id"]).all()
    twin_ids = [t[0] for t in my_twins]
    if not twin_ids:
        raise BusinessError("请先生成分身再推送", code=4001)

    pushed = 0
    skipped = 0
    for doctor_id in doctor_ids:
        sub = db.query(DoctorTwinSubscription).filter(
            DoctorTwinSubscription.doctor_id == doctor_id,
            DoctorTwinSubscription.twin_id.in_(twin_ids),
            DoctorTwinSubscription.status == "subscribed",
        ).first()
        if not sub:
            skipped += 1
            continue
        existing = db.query(CardPushRecord).filter_by(card_id=card_id, doctor_id=doctor_id).first()
        if existing:
            skipped += 1
            continue
        db.add(CardPushRecord(
            representative_id=current_user["id"],
            card_id=card_id,
            doctor_id=doctor_id,
            read_status="unread",
        ))
        db.add(Notification(
            user_id=doctor_id,
            type="card_new",
            title=f"收到学术卡片：{card.title}",
            link=f"/card-pushes",
        ))
        pushed += 1
    db.commit()
    return success({"pushed": pushed, "skipped": skipped})
```

- [ ] **Step 4: 实现 card_pushes.py**

Create `services/specialist-service/app/api/card_pushes.py`：

```python
"""医生端学术卡片接收/阅读追踪/反馈 + 站内通知查询（二期 G）"""
import logging
from typing import Optional

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from shared.common.auth import require_roles
from shared.common.context import get_request_id
from shared.common.db_session import get_db
from shared.common.pagination import PaginationParams, paginate
from shared.common.response import BusinessError, ParamError, success
from shared.models.academic import AcademicCard, CardPushRecord, Notification

from app.services.audit_client import write_audit_log

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/card-pushes", tags=["card-pushes"])

VALID_STATUS = ("unread", "read", "favorited", "forwarded")


@router.get("")
async def doctor_inbox(
    page: int = 1,
    page_size: int = 20,
    current_user: dict = Depends(require_roles("doctor")),
    db: Session = Depends(get_db),
):
    """医生端收件箱：本人收到的学术卡片（带卡片内容）"""
    p = PaginationParams(page=page, page_size=page_size)
    q = db.query(CardPushRecord).filter(CardPushRecord.doctor_id == current_user["id"])
    total = q.count()
    rows = q.order_by(CardPushRecord.id.desc()).offset(p.offset).limit(p.limit).all()
    items = []
    for r in rows:
        card = db.query(AcademicCard).filter(AcademicCard.id == r.card_id).first()
        item = r.to_dict()
        item["card"] = card.to_dict() if card else None
        items.append(item)
    return success(paginate(items, total, p.page, p.page_size))


@router.post("/{push_id}/track")
async def track_read(
    push_id: int,
    payload: dict,
    current_user: dict = Depends(require_roles("doctor")),
    db: Session = Depends(get_db),
):
    """阅读追踪：read_status + 停留秒数（医生端离开卡片时上报）"""
    if not isinstance(payload, dict):
        raise ParamError("请求体必须是 JSON 对象")
    rec = db.query(CardPushRecord).filter(CardPushRecord.id == push_id).first()
    if not rec or rec.doctor_id != current_user["id"]:
        raise BusinessError("推送记录不存在", code=4001)
    status = payload.get("read_status")
    if status and status not in VALID_STATUS:
        raise ParamError("read_status 不合法")
    if status:
        rec.read_status = status
        rec.read_at = __import__("datetime").datetime.utcnow()
    seconds = payload.get("seconds")
    if isinstance(seconds, int) and seconds > 0:
        rec.tracked_seconds = seconds
    db.commit()
    db.refresh(rec)
    return success(rec.to_dict())


@router.post("/{push_id}/feedback")
async def submit_feedback(
    push_id: int,
    payload: dict,
    current_user: dict = Depends(require_roles("doctor")),
    db: Session = Depends(get_db),
):
    """医生反馈：useful / useless / 追问文本（回流代表简报）"""
    if not isinstance(payload, dict):
        raise ParamError("请求体必须是 JSON 对象")
    feedback = payload.get("feedback")
    if not feedback or not isinstance(feedback, str) or len(feedback) > 500:
        raise ParamError("feedback 必填且不超过 500 字符")
    rec = db.query(CardPushRecord).filter(CardPushRecord.id == push_id).first()
    if not rec or rec.doctor_id != current_user["id"]:
        raise BusinessError("推送记录不存在", code=4001)
    rec.feedback = feedback
    if feedback in ("useful", "useless"):
        rec.read_status = "favorited" if feedback == "useful" else "read"
    db.commit()
    db.refresh(rec)
    # 通知回流代表
    db.add(Notification(
        user_id=rec.representative_id,
        type="card_question" if feedback not in ("useful", "useless") else "card_feedback",
        title="医生反馈" if feedback in ("useful", "useless") else "医生追问",
        content=feedback,
        link=f"/briefings",
    ))
    db.commit()
    return success(rec.to_dict())


@router.get("/notifications")
async def list_notifications(
    page: int = 1,
    page_size: int = 20,
    current_user: dict = Depends(require_roles("rep", "doctor")),
    db: Session = Depends(get_db),
):
    """站内通知（代表端简报就绪/反馈回流，医生端新卡片）"""
    p = PaginationParams(page=page, page_size=page_size)
    q = db.query(Notification).filter(Notification.user_id == current_user["id"])
    total = q.count()
    rows = q.order_by(Notification.id.desc()).offset(p.offset).limit(p.limit).all()
    return success(paginate([n.to_dict() for n in rows], total, p.page, p.page_size))
```

- [ ] **Step 5: 注册 card_pushes router**

Modify `services/specialist-service/app/main.py`：追加 `from app.api.card_pushes import router as card_pushes_router` + `app.include_router(card_pushes_router)`。

- [ ] **Step 6: 运行测试确认通过**

Run: `cd services/specialist-service && python -m pytest tests/test_card_pushes.py -q`
Expected: 6 passed

- [ ] **Step 7: 全量 specialist 回归**

Run: `cd services/specialist-service && python -m pytest -q`
Expected: 156 + 4（Task2）+ 6（Task3）全过

- [ ] **Step 8: Commit**

```bash
git add services/specialist-service/app/api/academic_cards.py services/specialist-service/app/api/card_pushes.py services/specialist-service/app/main.py services/specialist-service/tests/test_card_pushes.py
git commit -m "feat(specialist): 卡片推送+医生接收/追踪/反馈+站内通知"
```

---

### Task 4: 触达统计端点 + 简报就绪通知接线

**Files:**
- Modify: `services/specialist-service/app/api/academic_cards.py`（统计端点）
- Modify: `services/specialist-service/app/api/briefings.py`（生成后写通知）
- Modify: `services/specialist-service/app/core/briefing_generator.py`（生成后写通知）
- Test: `services/specialist-service/tests/test_academic_cards.py`（追加统计用例）

**Interfaces:**
- Consumes: `CardPushRecord`、`Notification`
- Produces: `GET /api/v1/academic-cards/stats`（admin/manager/compliance/medical：点击人次/点击率/代表排名/领域排名）；夜间简报生成后写 `briefing_ready` 通知。

- [ ] **Step 1: 写失败测试**

Append to `services/specialist-service/tests/test_academic_cards.py`：

```python
def test_stats_requires_admin():
    resp = client.get("/api/v1/academic-cards/stats", headers=_token(1, "rep"))
    assert resp.status_code == 403


def test_stats_aggregates(fresh_state):
    db = TestSession()
    db.add(AcademicCard(id=1, representative_id=1, title="卡1", content={"conclusion": "x"}, is_ai_generated=True))
    db.add(CardPushRecord(id=1, representative_id=1, card_id=1, doctor_id=2, read_status="read", tracked_seconds=10))
    db.add(CardPushRecord(id=2, representative_id=1, card_id=1, doctor_id=3, read_status="unread"))
    db.commit()
    db.close()

    resp = client.get("/api/v1/academic-cards/stats", headers=_token(3, "admin"))
    body = resp.json()
    assert body["code"] == 0
    data = body["data"]
    assert data["total_pushes"] == 2
    assert data["total_reads"] == 1
    assert data["read_rate"] == 0.5
    assert data["rep_ranking"][0]["representative_id"] == 1
    assert data["rep_ranking"][0]["reads"] == 1
```

- [ ] **Step 2: 运行测试确认失败**

Run: `cd services/specialist-service && python -m pytest tests/test_academic_cards.py -q`
Expected: 新增 2 用例失败

- [ ] **Step 3: 实现统计端点**

Modify `services/specialist-service/app/api/academic_cards.py`，在 `list_my_cards` 之后追加：

```python
from shared.models.academic import CardPushRecord


@router.get("/stats")
async def card_stats(
    days: int = 30,
    _admin: dict = Depends(require_roles("admin", "manager", "compliance", "medical")),
    db: Session = Depends(get_db),
):
    """学术内容触达统计（需求 3.7(1)）：点击人次/点击率/代表排名"""
    from datetime import datetime, timedelta
    from sqlalchemy import func as sqlfunc

    since = datetime.utcnow() - timedelta(days=days)
    q = db.query(CardPushRecord).filter(CardPushRecord.created_at >= since)
    total_pushes = q.count()
    total_reads = q.filter(CardPushRecord.read_status != "unread").count()
    read_rate = round(total_reads / total_pushes, 4) if total_pushes else 0.0

    rep_rows = (
        db.query(
            CardPushRecord.representative_id,
            sqlfunc.count(CardPushRecord.id),
            sqlfunc.sum(sqlfunc.case((CardPushRecord.read_status != "unread", 1), else_=0)),
        )
        .filter(CardPushRecord.created_at >= since)
        .group_by(CardPushRecord.representative_id)
        .order_by(sqlfunc.count(CardPushRecord.id).desc())
        .limit(10)
        .all()
    )
    return success({
        "days": days,
        "total_pushes": total_pushes,
        "total_reads": total_reads,
        "read_rate": read_rate,
        "rep_ranking": [{
            "representative_id": rid, "pushes": p, "reads": r or 0,
        } for rid, p, r in rep_rows],
    })
```

> 路由顺序：`/stats` 是单段，定义在 `/{card_id}/push`（两段）之前不会被 `{card_id}` 捕获（`/stats` 是单段无 `/{card_id}` 前缀冲突）。但需确认 `/stats` 与 `/{card_id}/push` 注册顺序——`POST /stats` 不会匹配 `POST /{card_id}/push`（路径段数不同）。安全。

- [ ] **Step 4: 简报就绪通知接线**

Modify `services/specialist-service/app/core/briefing_generator.py`（生成简报成功后）与 `services/specialist-service/app/api/briefings.py`（若在端点生成）：在简报落库后写一条代表端通知：

```python
    db.add(Notification(
        user_id=representative_id,
        type="briefing_ready",
        title="你的夜间简报已生成",
        content="查看医生提问汇总与需跟进事项",
        link="/briefings",
    ))
```

（`Notification` 从 `shared.models.academic` 导入；在生成函数内、commit 前 add。）

- [ ] **Step 5: 运行测试确认通过**

Run: `cd services/specialist-service && python -m pytest tests/test_academic_cards.py -q`
Expected: 6 passed（原 4 + 新 2）

- [ ] **Step 6: Commit**

```bash
git add services/specialist-service/app/api/academic_cards.py services/specialist-service/app/api/briefings.py services/specialist-service/app/core/briefing_generator.py services/specialist-service/tests/test_academic_cards.py
git commit -m "feat(specialist): 触达统计端点 + 简报就绪站内通知"
```

---

### Task 5: 网关 ROUTE_MAP + mobile 代表端（卡片创建/列表/推送）

**Files:**
- Modify: `services/gateway/app/main.py`
- Create: `mobile/src/api/academic.ts`
- Create: `mobile/src/screens/Academic/CardCreateScreen.tsx`
- Create: `mobile/src/screens/Academic/CardListScreen.tsx`
- Modify: `mobile/src/navigation/types.ts`
- Modify: `mobile/src/navigation/AppNavigator.tsx`
- Modify: `mobile/src/screens/Profile/ProfileScreen.tsx`（入口）
- Test: `mobile/src/api/__tests__/academic-contract.test.ts`

**Interfaces:**
- Consumes: 后端 `/api/v1/academic-cards*`、`/api/v1/card-pushes*`
- Produces: 契约测试；代表端卡片创建/列表/推送屏。

- [ ] **Step 1: 网关 ROUTE_MAP**

Modify `services/gateway/app/main.py` ROUTE_MAP（在 `/api/v1/briefings` 附近）追加两行：
```python
    "/api/v1/academic-cards": settings.SPECIALIST_SERVICE_URL,  # 学术卡片（二期 G）
    "/api/v1/card-pushes": settings.SPECIALIST_SERVICE_URL,  # 卡片推送/通知（二期 G）
```
Run: `cd services/gateway && python -m pytest -q` 确认无回归。

- [ ] **Step 2: 契约测试**

Create `mobile/src/api/__tests__/academic-contract.test.ts`（参照 qualification-contract 模式）：

```ts
import { academicAPI } from '../academic';

const okResponse = (data: any = {}) => ({ json: async () => ({ code: 0, message: 'success', data }) });
let fetchMock: jest.Mock;
beforeEach(() => { fetchMock = jest.fn().mockResolvedValue(okResponse()); (global as any).fetch = fetchMock; });
function lastCall() { const [url, init] = fetchMock.mock.calls[fetchMock.mock.calls.length - 1]; return { url, init }; }

describe('academicAPI', () => {
  it('createCard 发 POST /api/v1/academic-cards', async () => {
    await academicAPI.createCard({ title: '高血压指南', topic: '高血压' });
    const { url, init } = lastCall();
    expect(url).toContain('/api/v1/academic-cards');
    expect(init.method).toBe('POST');
    expect(JSON.parse(init.body)).toEqual({ title: '高血压指南', topic: '高血压' });
  });

  it('listMyCards 发 GET /api/v1/academic-cards', async () => {
    await academicAPI.listMyCards();
    const { url, init } = lastCall();
    expect(url).toContain('/api/v1/academic-cards');
    expect(init.method).toBe('GET');
  });

  it('pushCard 发 POST /api/v1/academic-cards/1/push', async () => {
    await academicAPI.pushCard(1, [2]);
    const { url, init } = lastCall();
    expect(url).toContain('/api/v1/academic-cards/1/push');
    expect(JSON.parse(init.body)).toEqual({ doctor_ids: [2] });
  });
});
```

- [ ] **Step 3: API 层**

Create `mobile/src/api/academic.ts`：

```ts
import { apiClient } from './client';

export const academicAPI = {
  createCard: (payload: { title: string; topic: string }) =>
    apiClient.request<any>('POST', '/api/v1/academic-cards', payload),
  listMyCards: () =>
    apiClient.request<any>('GET', '/api/v1/academic-cards'),
  pushCard: (cardId: number, doctorIds: number[]) =>
    apiClient.request<any>('POST', `/api/v1/academic-cards/${cardId}/push`, { doctor_ids: doctorIds }),
  notifications: () =>
    apiClient.request<any>('GET', '/api/v1/card-pushes/notifications'),
};
```

- [ ] **Step 4: 代表端两屏**

Create `mobile/src/screens/Academic/CardCreateScreen.tsx`（主题输入 → 生成 → 展示 → 选择已添加医生推送）与 `CardListScreen.tsx`（我的卡片列表 + 推送状态），样式参照 ComplianceCenterScreen 与 HCPDetail 模式。医生对象列表从 `doctor_twin_subscriptions`（本代表分身已添加的医生）获取——**复用 twin_subscriptions 的反向查询**：后端需提供代表端"可推送医生列表"端点（`GET /api/v1/academic-cards/push-targets`，返回订阅了我分身的 doctor 用户 id/name）。若时间紧，代表端先用数字 doctor_id 输入占位（brief 已允许），后端在 Task 3 已校验订阅关系。

- [ ] **Step 5: 接线导航 + 入口**

Modify `mobile/src/navigation/types.ts`：RootStackParamList 加 `AcademicCardCreate`/`AcademicCardList`。
Modify `AppNavigator.tsx`：注册两屏。
Modify `ProfileScreen.tsx`：加"学术卡片"入口（导航到 CardCreateScreen）。

- [ ] **Step 6: 契约测试运行**

Run: `cd mobile && npx jest src/api/__tests__/academic-contract.test.ts`
Expected: 3 passed

- [ ] **Step 7: Commit**

```bash
git add services/gateway/app/main.py mobile/src/api/academic.ts mobile/src/api/__tests__/academic-contract.test.ts mobile/src/screens/Academic mobile/src/navigation/types.ts mobile/src/navigation/AppNavigator.tsx mobile/src/screens/Profile/ProfileScreen.tsx
git commit -m "feat(gateway+mobile): 学术卡片路由+代表端创建/列表/推送屏"
```

---

### Task 6: mobile-doctor 医生端收件箱 + 卡片详情反馈

**Files:**
- Create: `mobile-doctor/src/api/inbox.ts`
- Create: `mobile-doctor/src/screens/Inbox/InboxScreen.tsx`
- Create: `mobile-doctor/src/screens/Inbox/CardDetailScreen.tsx`
- Modify: `mobile-doctor/src/navigation/types.ts`
- Modify: `mobile-doctor/src/navigation/AppNavigator.tsx`
- Modify: `mobile-doctor/src/screens/Profile/ProfileScreen.tsx`（入口）
- Test: `mobile-doctor/src/api/__tests__/inbox-contract.test.ts`

**Interfaces:**
- Consumes: `/api/v1/card-pushes`（inbox/track/feedback/notifications）
- Produces: 医生端收件箱 + 卡片详情（阅读上报 + 反馈）+ 契约测试。

- [ ] **Step 1: 契约测试**

Create `mobile-doctor/src/api/__tests__/inbox-contract.test.ts`：

```ts
import { inboxAPI } from '../inbox';

const okResponse = (data: any = {}) => ({ json: async () => ({ code: 0, message: 'success', data }) });
let fetchMock: jest.Mock;
beforeEach(() => { fetchMock = jest.fn().mockResolvedValue(okResponse()); (global as any).fetch = fetchMock; });
function lastCall() { const [url, init] = fetchMock.mock.calls[fetchMock.mock.calls.length - 1]; return { url, init }; }

describe('inboxAPI', () => {
  it('listInbox 发 GET /api/v1/card-pushes', async () => {
    await inboxAPI.listInbox();
    const { url, init } = lastCall();
    expect(url).toContain('/api/v1/card-pushes');
    expect(init.method).toBe('GET');
  });

  it('trackRead 发 POST /api/v1/card-pushes/1/track', async () => {
    await inboxAPI.trackRead(1, 'read', 42);
    const { url, init } = lastCall();
    expect(url).toContain('/api/v1/card-pushes/1/track');
    expect(JSON.parse(init.body)).toEqual({ read_status: 'read', seconds: 42 });
  });

  it('submitFeedback 发 POST /api/v1/card-pushes/1/feedback', async () => {
    await inboxAPI.submitFeedback(1, 'useful');
    const { url, init } = lastCall();
    expect(url).toContain('/api/v1/card-pushes/1/feedback');
    expect(JSON.parse(init.body)).toEqual({ feedback: 'useful' });
  });
});
```

- [ ] **Step 2: API 层**

Create `mobile-doctor/src/api/inbox.ts`：

```ts
import { apiClient } from './client';

export const inboxAPI = {
  listInbox: () => apiClient.request<any>('GET', '/api/v1/card-pushes'),
  trackRead: (pushId: number, readStatus: string, seconds: number) =>
    apiClient.request<any>('POST', `/api/v1/card-pushes/${pushId}/track`, { read_status: readStatus, seconds }),
  submitFeedback: (pushId: number, feedback: string) =>
    apiClient.request<any>('POST', `/api/v1/card-pushes/${pushId}/feedback`, { feedback }),
};
```

> 注意：mobile-doctor 的 apiClient 签名需与 mobile/src/api/client.ts 核对（两个工程各自 client.ts，可能不同）。以实际为准。

- [ ] **Step 3: 医生端两屏**

Create `mobile-doctor/src/screens/Inbox/InboxScreen.tsx`（收件箱列表：卡片标题/代表名/状态）与 `CardDetailScreen.tsx`（卡片内容 + 阅读上报 + 有用/无用/追问输入），样式参照 MedicalQAScreen。

- [ ] **Step 4: 接线导航 + 入口**

Modify `mobile-doctor/src/navigation/types.ts`：RootStackParamList 加 `Inbox`/`CardDetail: { pushId: number }`。
Modify `AppNavigator.tsx`：注册两屏。
Modify `ProfileScreen.tsx`：加"学术卡片"入口。

- [ ] **Step 5: 契约测试运行**

Run: `cd mobile-doctor && npx jest src/api/__tests__/inbox-contract.test.ts`
Expected: 3 passed

- [ ] **Step 6: Commit**

```bash
git add mobile-doctor/src/api/inbox.ts mobile-doctor/src/api/__tests__/inbox-contract.test.ts mobile-doctor/src/screens/Inbox mobile-doctor/src/navigation/types.ts mobile-doctor/src/navigation/AppNavigator.tsx mobile-doctor/src/screens/Profile/ProfileScreen.tsx
git commit -m "feat(mobile-doctor): 学术卡片收件箱+详情反馈"
```

---

### Task 7: web 触达统计页

**Files:**
- Create: `web/src/pages/Compliance/CardStats.tsx`
- Create: `web/src/services/cardStats.ts`
- Modify: `web/src/types/index.ts`
- Modify: `web/src/App.tsx`
- Modify: `web/src/constants/menu.tsx`

**Interfaces:**
- Consumes: `GET /api/v1/academic-cards/stats`
- Produces: 运营触达统计页（总推送/已读/点击率/代表排名）。

- [ ] **Step 1: 加类型**

Modify `web/src/types/index.ts` 追加：

```ts
export interface CardStats {
  days: number;
  total_pushes: number;
  total_reads: number;
  read_rate: number;
  rep_ranking: { representative_id: number; pushes: number; reads: number }[];
}
```

- [ ] **Step 2: 加 service**

Create `web/src/services/cardStats.ts`：

```ts
import client from './client';
import type { ApiResponse, CardStats } from '../types';

export const cardStatsAPI = {
  stats: (days = 30) =>
    client.get<ApiResponse<CardStats>>('/academic-cards/stats', { params: { days } }),
};
```

- [ ] **Step 3: 页面**

Create `web/src/pages/Compliance/CardStats.tsx`（统计卡 + 代表排名表，参照 Monitor.tsx 风格）：

```tsx
import { useEffect, useState } from 'react';
import { Card, Col, Row, Statistic, Table } from 'antd';
import { cardStatsAPI } from '../../services/cardStats';
import type { CardStats } from '../../types';

export default function CardStats() {
  const [stats, setStats] = useState<CardStats | null>(null);

  useEffect(() => {
    cardStatsAPI.stats(30).then(r => setStats(r.data.data)).catch(() => {});
  }, []);

  return (
    <div>
      <Row gutter={16}>
        <Col span={6}><Card><Statistic title="总推送" value={stats?.total_pushes ?? 0} /></Card></Col>
        <Col span={6}><Card><Statistic title="已读" value={stats?.total_reads ?? 0} /></Card></Col>
        <Col span={6}><Card><Statistic title="点击率" value={stats?.read_rate ?? 0} precision={2} suffix="%" /></Card></Col>
      </Row>
      <Card title="代表触达排名（近 30 天）" style={{ marginTop: 16 }}>
        <Table
          rowKey="representative_id"
          dataSource={stats?.rep_ranking ?? []}
          pagination={false}
          size="small"
          columns={[
            { title: '代表ID', dataIndex: 'representative_id' },
            { title: '推送数', dataIndex: 'pushes' },
            { title: '已读数', dataIndex: 'reads' },
          ]}
        />
      </Card>
    </div>
  );
}
```

- [ ] **Step 4: 注册路由 + 菜单**

Modify `web/src/App.tsx`：加 lazy import + `<Route path="compliance/card-stats" element={<CardStats />} />`。
Modify `web/src/constants/menu.tsx`：加菜单项 `{ path: '/compliance/card-stats', name: '触达统计', icon: <BarChartOutlined /> }`。

- [ ] **Step 5: 验证 build**

Run: `cd web && npm run build`
Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add web/src/pages/Compliance/CardStats.tsx web/src/services/cardStats.ts web/src/types/index.ts web/src/App.tsx web/src/constants/menu.tsx
git commit -m "feat(web): 学术触达统计页"
```

---

### Task 8: 全量回归 + CLAUDE.md 同步

**Files:**
- Modify: `CLAUDE.md`

- [ ] **Step 1: 后端全量回归**

Run: 各服务 `cd services/<s> && python -m pytest -q`
Expected: 全绿（specialist 基线 156 + academic_cards ~6 + card_pushes ~6 = ~168；gateway 82 不变）

- [ ] **Step 2: 前端验证**

Run: `cd web && npm run build`；`cd mobile && npx jest`；`cd mobile-doctor && npx jest`
Expected: 全绿

- [ ] **Step 3: 同步 CLAUDE.md**

补记 G 计划：
- 新表：academic_cards / card_push_records / notifications（迁移 015）
- 新端点：`/api/v1/academic-cards`（rep 生成/列表/stats 管理角色）、`/api/v1/academic-cards/{id}/push`、`/api/v1/card-pushes`（doctor inbox/track/feedback/notifications）
- 推送对象口径：doctor_twin_subscriptions 中 subscribed 且属于该代表分身的 doctor
- 触达统计：read_rate = 已读/总推送
- 简报就绪通知：briefing_ready 站内信
- Known Gaps：推送暂为站内信（未接第三方推送 SDK）；卡片生成 AI 辅助人工确认

- [ ] **Step 4: Commit**

```bash
git add CLAUDE.md
git commit -m "docs: 二期 G 学术触达文档同步"
```

---

## Self-Review

**1. Spec 覆盖（二期 G 计划章节）：**
- 学术卡片生成 4.6(1) → Task 2（AI 生成 + 合规预检 + 标注）
- 推送与阅读追踪 4.6(2)(3) → Task 3（push + track）
- 医生端接收与反馈 5.3(1)(4) → Task 3（inbox/feedback）+ Task 6（医生端屏）
- 反馈回流 6.3 → Task 3（feedback 通知代表）
- 学术内容触达统计 3.7(1) → Task 4（stats）
- 简报真实推送/通知渠道（一期 C 挂账）→ Task 4（briefing_ready 通知）
- 追问回流简报 → feedback 通知 link 指向 briefings

**2. 占位符扫描：** Task 5 代表端推送对象用数字 doctor_id 占位（brief 已注明 push-targets 端点可选）；Task 2 check_compliance 签名"以实际为准"——实现时须核对。无 TBD/TODO 硬占位。

**3. 类型一致性：** AcademicCard/CardPushRecord/Notification 字段在模型、端点返回、web/mobile 类型全程一致；`read_status` 枚举 unread/read/favorited/forwarded 三处一致。

**已知取舍（写进 CLAUDE.md）：**
- 推送对象 = 已注册 doctor（订阅了该代表分身的），不推给 hcps 档案
- 推送渠道 = 站内信（notifications 表），未接第三方推送 SDK
- 卡片生成 = qwen 辅助 + 合规预检，AI 内容标注
- 代表端推送对象选择 = 数字 doctor_id（push-targets 端点可选补）
