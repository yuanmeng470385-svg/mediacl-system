# MAH 合规全景 + 数据治理（三期 K）Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 管理后台补 MAH 合规全景视图（备案/培训/合规通过率）、数据分类分级清单、敏感数据导出审批流（对话明细 xlsx）。

**Architecture:** MAH 全景（`/api/v1/specialists/mah-overview`）在 **specialist-service**——conversations 模型只在 specialist（spec §6 K 已修正，遵循 review-queue 先例），同库直读 users/representative_qualifications/conversations；数据分类分级（`/api/v1/compliance/data-assets`）在 compliance-service（静态清单）；数据导出审批（`/api/v1/data-exports/*`）在 specialist-service（对话明细同库）+ 迁移 022 `export_requests` 表，审批人=admin/manager/compliance，对话明细 xlsx 用 openpyxl（specialist requirements 需补该依赖），网关加 `/api/v1/data-exports` 前缀。下载端点经网关非 JSON 原样透传（网关已有字节透传分支）。

**Tech Stack:** FastAPI + SQLAlchemy（specialist:8001 / compliance:8004）+ openpyxl（新增到 specialist requirements）+ React web + SQLite 单测（StaticPool + JSONB compile shim）。

## Global Constraints

- MAH 合规通过率口径 = 1 − conversations.compliance_result.blocked=true / 总对话数（与 review-queue 同口径）；备案状态按 `_filing_status()` + audit_status 派生。
- 数据导出审批：申请人 admin/manager，审批人 admin/manager/compliance；SLA = created_at + 3 自然日（仅高亮提醒，**不自动放行**）；导出物一期仅 `conversations` 对话明细。
- 对话明细导出列：id/user_id/specialist_id/session_id/role/content/blocked/created_at；**绝不含患者诊断信息**；上限 50000 行。
- 权限：`require_roles` 实时查库；`EXPORT_ROLES = ("admin","manager","compliance")`；写审计 action=export_request_create/export_request_review。
- 下载端点：approved 且 expires_at（approve + 7 天）未过期；文件 `logs/exports/export_<id>.xlsx`（gitignored）。
- 测试约定：SQLite + StaticPool；`monkeypatch.setitem(app.dependency_overrides, get_db, _override_db)`；`write_audit_log` AsyncMock。
- 验证门：`cd services/specialist-service && python -m pytest tests/ -q` + `cd services/compliance-service && python -m pytest tests/ -q`；`cd web && npm run build`。
- **禁止子代理 push 任何远程**——推 Codeup 由主会话在用户确认后执行。

---

### Task 1: 迁移 022 + ExportRequest 模型 + init_db

**Files:**
- Create: `scripts/migrations/022_export_requests.sql`
- Create: `services/specialist-service/app/models/export_request.py`
- Modify: `scripts/init_db.sql`
- Test: `services/specialist-service/tests/test_data_exports.py`（新建，含 fixture）

**Interfaces:**
- Produces: `ExportRequest(requester_id, export_type, reason, status, approver_id, approve_reason, file_url, expires_at, responded_at)` + `to_dict()`。Task 2 依赖。

- [ ] **Step 1: 写迁移 SQL**

Create `scripts/migrations/022_export_requests.sql`:

```sql
-- 022_export_requests.sql
-- 三期 K：敏感数据导出审批（需求 3.8(3)）
-- 用法：docker exec -i medagent-postgres psql -U medagent medagent < scripts/migrations/022_export_requests.sql

\set ON_ERROR_STOP on

CREATE TABLE IF NOT EXISTS export_requests (
    id BIGSERIAL PRIMARY KEY,
    requester_id BIGINT NOT NULL REFERENCES users(id),
    export_type VARCHAR(50) NOT NULL DEFAULT 'conversations',  -- conversations（一期唯一敏感导出物）
    reason VARCHAR(500),                                      -- 导出目的
    status VARCHAR(20) NOT NULL DEFAULT 'pending',            -- pending/approved/rejected
    approver_id BIGINT REFERENCES users(id),
    approve_reason VARCHAR(500),
    file_url VARCHAR(500),
    expires_at TIMESTAMP,
    responded_at TIMESTAMP,
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_er_status ON export_requests(status);
CREATE INDEX IF NOT EXISTS idx_er_requester ON export_requests(requester_id);
```

- [ ] **Step 2: 模型**

Create `services/specialist-service/app/models/export_request.py`:

```python
"""数据导出审批记录模型（三期 K，需求 3.8(3)）"""
from sqlalchemy import BigInteger, Column, DateTime, ForeignKey, String

from shared.models.base import Base, TimestampMixin


class ExportRequest(Base, TimestampMixin):
    __tablename__ = "export_requests"

    requester_id = Column(BigInteger, ForeignKey("users.id"), nullable=False)
    export_type = Column(String(50), nullable=False, default="conversations")
    reason = Column(String(500))
    status = Column(String(20), nullable=False, default="pending")  # pending/approved/rejected
    approver_id = Column(BigInteger, ForeignKey("users.id"))
    approve_reason = Column(String(500))
    file_url = Column(String(500))
    expires_at = Column(DateTime)
    responded_at = Column(DateTime)

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "requester_id": self.requester_id,
            "export_type": self.export_type,
            "reason": self.reason,
            "status": self.status,
            "approver_id": self.approver_id,
            "approve_reason": self.approve_reason,
            "file_url": self.file_url,
            "expires_at": self.expires_at.isoformat() if self.expires_at else None,
            "responded_at": self.responded_at.isoformat() if self.responded_at else None,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }
```

- [ ] **Step 3: 同步 init_db.sql**

在 `conversations` 相关建表后追加 `export_requests` 建表 + 两个索引（与迁移 022 一致）。

- [ ] **Step 4: 写失败测试（fixture + 模型级）**

Create `services/specialist-service/tests/test_data_exports.py`（骨架参照 test_practices.py：`BigInteger`/`JSONB` compile shim + StaticPool + `fresh_state`）：

```python
"""数据导出审批测试（三期 K）"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", ".."))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

os.environ.setdefault("JWT_SECRET", "test-secret-not-a-default-value")
os.environ["AUTH_DEV_MODE"] = "true"

from unittest.mock import AsyncMock

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import BigInteger, create_engine
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.ext.compiler import compiles
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from shared.common.auth import create_token
from shared.common.db_session import get_db
from shared.models.base import Base
from shared.models.user import User

from app.main import app
from app.models.export_request import ExportRequest


@compiles(BigInteger, "sqlite")
def _compile_bigint_for_sqlite(type_, compiler, **kw):
    return "INTEGER"


@compiles(JSONB, "sqlite")
def _compile_jsonb_for_sqlite(type_, compiler, **kw):
    return "JSON"


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
    tables = [User.__table__, ExportRequest.__table__]
    Base.metadata.drop_all(engine, tables=tables)
    Base.metadata.create_all(engine, tables=tables)
    db = TestSession()
    db.add_all([
        User(id=1, username="rep01", full_name="张代表", phone="13800000001", role="rep", status="active"),
        User(id=2, username="admin", full_name="管理员", phone="13800000000", role="admin", status="active"),
        User(id=3, username="compliance", full_name="合规部", phone="13800000003", role="compliance", status="active"),
    ])
    db.commit()
    db.close()
    monkeypatch.setitem(app.dependency_overrides, get_db, _override_db)
    yield None
```

> **Task 1 注意**：`data_exports` 模块 Task 2 才创建，本 Task 的 `fresh_state` **不要** import 它。Task 2 Step 1 会把 monkeypatch 加回来（`from app.api import data_exports as de_api; audit_mock = AsyncMock(...); monkeypatch.setattr(de_api, "write_audit_log", audit_mock); yield audit_mock`）。本 Task 的模型级测试不依赖 audit mock。

追加模型级测试：

```python
def test_export_request_to_dict(fresh_state):
    db = TestSession()
    er = ExportRequest(id=1, requester_id=2, export_type="conversations", reason="监管自查", status="pending")
    db.add(er)
    db.commit()
    d = er.to_dict()
    assert d["export_type"] == "conversations"
    assert d["status"] == "pending"
    assert d["reason"] == "监管自查"
    db.close()
```

- [ ] **Step 5: 运行确认失败**

Run: `cd services/specialist-service && python -m pytest tests/test_data_exports.py -v`
Expected: FAIL（`test_export_request_to_dict` —— 模型未建）。**注意**：`from app.main import app` 会加载 main.py，`from app.api.data_exports import router` 需在 Task 2 才注册——因此本文件先只放模型级测试，不要 import `data_exports` 模块。`fresh_state` 的 `import app.api.data_exports as de_api` 会失败——改为在 fresh_state 里直接 `monkeypatch.setattr("app.api.data_exports.write_audit_log", audit_mock)`？——**简化**：本 Task fresh_state 不 import data_exports，只在 Task 2 补该 import 与 monkeypatch（届时该文件已存在）。现将 fresh_state 的 import 行去掉，Task 2 再加回。

- [ ] **Step 6: 实现并确认通过**

应用 Step 2 模型 + Step 3 init_db。重跑 Step 5。Expected: PASS。

- [ ] **Step 7: 全量确认**

Run: `cd services/specialist-service && python -m pytest tests/ -q`
Expected: 既有 257 不降（+1）。

- [ ] **Step 8: Commit**

```bash
git add scripts/migrations/022_export_requests.sql services/specialist-service/app/models/export_request.py scripts/init_db.sql services/specialist-service/tests/test_data_exports.py
git commit -m "feat(data-export): 迁移 022 + ExportRequest 模型"
```

---

### Task 2: 数据导出审批端点（申请/列表/审批/下载 + 对话明细 xlsx）

**Files:**
- Create: `services/specialist-service/app/api/data_exports.py`
- Modify: `services/specialist-service/app/main.py`（include_router）
- Modify: `services/specialist-service/requirements.txt`（加 openpyxl）
- Modify: `services/gateway/app/main.py`（ROUTE_MAP 加 `/api/v1/data-exports`）
- Modify: `services/specialist-service/tests/test_data_exports.py`（补 import/monkeypatch + 端点测试）

**Interfaces:**
- Consumes: Task 1 的 `ExportRequest`；`Conversation`（`from app.models.conversation import Conversation`）。
- Produces: `POST /api/v1/data-exports/requests`、`GET /api/v1/data-exports/requests`、`POST /api/v1/data-exports/requests/{id}/review`、`GET /api/v1/data-exports/requests/{id}/download`。Task 5 web 依赖。

- [ ] **Step 1: 写失败测试**

在 `test_data_exports.py` 的 `fresh_state` 中补回 data_exports monkeypatch（`from app.api import data_exports as de_api; audit_mock = AsyncMock(...); monkeypatch.setattr(de_api, "write_audit_log", audit_mock)`），并追加端点测试：

```python
def test_create_export_requires_admin_or_manager():
    resp = client.post("/api/v1/data-exports/requests", json={"export_type": "conversations", "reason": "监管自查"},
                       headers=_token(3, "compliance"))
    assert resp.status_code == 403
    assert resp.json()["code"] == 3000


def test_create_export_sets_pending(fresh_state):
    resp = client.post("/api/v1/data-exports/requests", json={"export_type": "conversations", "reason": "监管自查"},
                       headers=_token(2, "admin"))
    body = resp.json()
    assert body["code"] == 0
    assert body["data"]["status"] == "pending"
    assert body["data"]["export_type"] == "conversations"
    fresh_state.assert_awaited_once()


def test_create_export_requires_reason():
    resp = client.post("/api/v1/data-exports/requests", json={"export_type": "conversations"},
                       headers=_token(2, "admin"))
    assert resp.status_code == 400
    assert resp.json()["code"] == 1000


def test_list_exports_filters_status(fresh_state):
    db = TestSession()
    db.add_all([
        ExportRequest(id=1, requester_id=2, export_type="conversations", reason="a", status="pending"),
        ExportRequest(id=2, requester_id=2, export_type="conversations", reason="b", status="approved"),
    ])
    db.commit()
    db.close()
    resp = client.get("/api/v1/data-exports/requests", params={"status": "approved"}, headers=_token(3, "compliance"))
    body = resp.json()
    assert body["data"]["total"] == 1
    assert body["data"]["items"][0]["id"] == 2
    assert body["data"]["items"][0]["requester_name"] == "管理员"


def test_review_approve_generates_xlsx(fresh_state, monkeypatch, tmp_path):
    db = TestSession()
    db.add(ExportRequest(id=1, requester_id=2, export_type="conversations", reason="监管自查", status="pending"))
    db.commit()
    db.close()
    fake_path = str(tmp_path / "export_1.xlsx")
    monkeypatch.setattr("app.api.data_exports._build_conversations_xlsx", lambda request_id, rows, out_dir: fake_path)
    resp = client.post("/api/v1/data-exports/requests/1/review", json={"verdict": "approve"},
                       headers=_token(3, "compliance"))
    body = resp.json()
    assert body["code"] == 0
    assert body["data"]["status"] == "approved"
    assert body["data"]["file_url"] == fake_path
    assert body["data"]["approver_id"] == 3
    assert body["data"]["expires_at"] is not None
    fresh_state.assert_awaited_once()


def test_review_reject_requires_reason(fresh_state):
    db = TestSession()
    db.add(ExportRequest(id=1, requester_id=2, export_type="conversations", reason="a", status="pending"))
    db.commit()
    db.close()
    resp = client.post("/api/v1/data-exports/requests/1/review", json={"verdict": "reject"},
                       headers=_token(3, "compliance"))
    assert resp.status_code == 400
    assert resp.json()["code"] == 1000


def test_download_requires_approved(fresh_state):
    db = TestSession()
    db.add(ExportRequest(id=1, requester_id=2, export_type="conversations", reason="a", status="pending"))
    db.commit()
    db.close()
    resp = client.get("/api/v1/data-exports/requests/1/download", headers=_token(3, "compliance"))
    assert resp.status_code == 422
    assert resp.json()["code"] == 4001
```

- [ ] **Step 2: 运行确认失败**

Run: `cd services/specialist-service && python -m pytest tests/test_data_exports.py -v`
Expected: 端点测试 FAIL（404）。

- [ ] **Step 3: 实现 data_exports.py**

Create `services/specialist-service/app/api/data_exports.py`：

```python
"""数据导出审批（三期 K，需求 3.8(3)）：敏感数据导出须经合规部审批。
一期导出物仅 conversations 对话明细；SLA=3 自然日（仅高亮提醒，不自动放行）。"""
import asyncio
import logging
import os
from datetime import datetime, timedelta
from typing import Optional

from fastapi import APIRouter, Depends
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from shared.common.auth import require_roles
from shared.common.context import get_request_id
from shared.common.db_session import get_db
from shared.common.pagination import PaginationParams, paginate
from shared.common.response import BusinessError, ParamError, success
from shared.models.user import User

from app.models.conversation import Conversation
from app.models.export_request import ExportRequest
from app.services.audit_client import write_audit_log

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/data-exports", tags=["data-exports"])

EXPORT_ROLES = ("admin", "manager", "compliance")
VALID_EXPORT_TYPES = ("conversations",)
SLA_DAYS = 3
DOWNLOAD_EXPIRE_DAYS = 7
ROW_CAP = 50000


def _build_conversations_xlsx(request_id: int, rows: list, out_dir: str = os.path.join("logs", "exports")) -> str:
    """把对话明细行写入 xlsx，返回文件路径。rows 为 dict 列表（已脱敏/受限字段）。"""
    from openpyxl import Workbook
    os.makedirs(out_dir, exist_ok=True)
    wb = Workbook()
    ws = wb.active
    ws.title = "对话明细"
    ws.append(["id", "user_id", "specialist_id", "session_id", "role", "content", "blocked", "created_at"])
    for r in rows:
        ws.append([
            r.get("id"), r.get("user_id"), r.get("specialist_id"), r.get("session_id"),
            r.get("role"), r.get("content"), r.get("blocked"), r.get("created_at"),
        ])
    path = os.path.join(out_dir, f"export_{request_id}.xlsx")
    wb.save(path)
    return path


@router.post("/requests")
async def create_export_request(
    payload: dict,
    current_user: dict = Depends(require_roles("admin", "manager")),
    db: Session = Depends(get_db),
):
    """申请人 admin/manager：提交敏感数据导出申请 → pending。"""
    if not isinstance(payload, dict):
        raise ParamError("请求体必须是 JSON 对象")
    export_type = payload.get("export_type") or "conversations"
    if export_type not in VALID_EXPORT_TYPES:
        raise ParamError("export_type 不合法（一期仅 conversations）")
    reason = (payload.get("reason") or "").strip() if isinstance(payload.get("reason"), str) else ""
    if not reason:
        raise ParamError("导出目的必填")
    if len(reason) > 500:
        raise ParamError("原因长度不能超过 500 字符")
    req = ExportRequest(requester_id=current_user["id"], export_type=export_type, reason=reason, status="pending")
    db.add(req)
    db.commit()
    db.refresh(req)
    await write_audit_log(
        action="export_request_create", user_id=current_user["id"],
        resource_type="export_request", resource_id=str(req.id),
        after_value={"export_type": export_type, "reason": reason},
        request_id=get_request_id() or None,
    )
    return success(req.to_dict())


@router.get("/requests")
async def list_export_requests(
    page: int = 1,
    page_size: int = 20,
    status: Optional[str] = None,
    current_user: dict = Depends(require_roles(*EXPORT_ROLES)),
    db: Session = Depends(get_db),
):
    """审批人列表：分页 + status 过滤 + SLA 超时（pending 且 created_at+3 天 < now）高亮。"""
    if status and status not in ("pending", "approved", "rejected"):
        raise ParamError("status 不合法")
    p = PaginationParams(page=page, page_size=page_size)
    q = db.query(ExportRequest).outerjoin(User, ExportRequest.requester_id == User.id)
    if status:
        q = q.filter(ExportRequest.status == status)
    total = q.count()
    rows = (
        q.order_by(ExportRequest.id.desc())
        .offset(p.offset).limit(p.limit)
        .with_entities(ExportRequest, User.full_name)
        .all()
    )
    now = datetime.utcnow()
    items = []
    for req, requester_name in rows:
        d = req.to_dict()
        d["requester_name"] = requester_name
        d["sla_overdue"] = bool(
            req.status == "pending"
            and req.created_at
            and req.created_at + timedelta(days=SLA_DAYS) < now
        )
        items.append(d)
    return success(paginate(items, total, p.page, p.page_size))


@router.post("/requests/{request_id}/review")
async def review_export_request(
    request_id: int,
    payload: dict,
    current_user: dict = Depends(require_roles(*EXPORT_ROLES)),
    db: Session = Depends(get_db),
):
    """合规部审批：approve → 生成对话明细 xlsx + expires_at；reject 必填 reason。"""
    req = db.query(ExportRequest).filter(ExportRequest.id == request_id).first()
    if not req:
        raise BusinessError("导出申请不存在", code=4001)
    if req.status != "pending":
        raise BusinessError("当前状态不可审批（仅待审批可审）", code=4001)
    if not isinstance(payload, dict):
        raise ParamError("请求体必须是 JSON 对象")
    verdict = payload.get("verdict")
    if verdict not in ("approve", "reject"):
        raise ParamError("verdict 必须是 approve 或 reject")
    reason = (payload.get("reason") or "").strip() if isinstance(payload.get("reason"), str) else ""
    if verdict == "reject" and not reason:
        raise ParamError("驳回必须填写原因")
    if len(reason) > 500:
        raise ParamError("原因长度不能超过 500 字符")
    if verdict == "approve":
        rows = [
            {
                "id": c.id, "user_id": c.user_id, "specialist_id": c.specialist_id,
                "session_id": c.session_id, "role": c.role, "content": c.content,
                "blocked": bool((c.compliance_result or {}).get("blocked")) if c.compliance_result else False,
                "created_at": c.created_at.isoformat() if c.created_at else None,
            }
            for c in db.query(Conversation).order_by(Conversation.id).limit(ROW_CAP).all()
        ]
        path = await asyncio.to_thread(_build_conversations_xlsx, req.id, rows)
        req.file_url = path
        req.expires_at = datetime.utcnow() + timedelta(days=DOWNLOAD_EXPIRE_DAYS)
    req.status = "approved" if verdict == "approve" else "rejected"
    req.approve_reason = reason if verdict == "reject" else None
    req.approver_id = current_user["id"]
    req.responded_at = datetime.utcnow()
    db.commit()
    db.refresh(req)
    await write_audit_log(
        action="export_request_review", user_id=current_user["id"],
        resource_type="export_request", resource_id=str(req.id),
        after_value={"status": req.status, "approve_reason": req.approve_reason},
        request_id=get_request_id() or None,
    )
    return success(req.to_dict())


@router.get("/requests/{request_id}/download")
async def download_export(
    request_id: int,
    current_user: dict = Depends(require_roles(*EXPORT_ROLES)),
    db: Session = Depends(get_db),
):
    """审批通过后下载对话明细 xlsx（expires_at 未过期）。"""
    req = db.query(ExportRequest).filter(ExportRequest.id == request_id).first()
    if not req or req.status != "approved":
        raise BusinessError("导出申请不存在或未通过审批", code=4001)
    if req.expires_at and req.expires_at < datetime.utcnow():
        raise BusinessError("导出文件已过期，请重新申请", code=4001)
    if not req.file_url or not os.path.exists(req.file_url):
        raise BusinessError("导出文件不存在", code=4001)
    return FileResponse(req.file_url, filename=f"conversations_export_{req.id}.xlsx")
```

- [ ] **Step 4: 接线**

- `main.py`：`from app.api.data_exports import router as data_exports_router; app.include_router(data_exports_router)`。
- `requirements.txt`：追加 `openpyxl>=3.1.0`（与 compliance/audit/hcp 一致）。
- `gateway/app/main.py` ROUTE_MAP：`"/api/v1/data-exports": settings.SPECIALIST_SERVICE_URL,  # 数据导出审批（三期 K）`。

- [ ] **Step 5: 运行确认通过**

Run: `cd services/specialist-service && python -m pytest tests/test_data_exports.py -v`
Expected: 6 端点测试 + 1 模型测试 PASS。全量 `python -m pytest tests/ -q` 不降。

- [ ] **Step 6: Commit**

```bash
git add services/specialist-service/app/api/data_exports.py services/specialist-service/app/main.py services/specialist-service/requirements.txt services/gateway/app/main.py services/specialist-service/tests/test_data_exports.py
git commit -m "feat(data-export): 敏感数据导出审批流 + 对话明细 xlsx"
```

---

### Task 3: MAH 合规全景视图端点

**Files:**
- Create: `services/specialist-service/app/api/mah_overview.py`
- Modify: `services/specialist-service/app/main.py`（include_router）
- Modify: `services/specialist-service/tests/test_data_exports.py`（或新建 test_mah_overview.py——用既有 test_data_exports.py 的 fixture 追加）

**Interfaces:**
- Produces: `GET /api/v1/specialists/mah-overview`（admin/manager/compliance）。Task 5 web 依赖。

- [ ] **Step 1: 写失败测试**

追加到 `test_data_exports.py`（`fresh_state` tables 加 `Conversation` 与 `RepresentativeQualification`；需 `from shared.models.qualification import RepresentativeQualification` 与 `from app.models.conversation import Conversation`；Conversation 无 TimestampMixin，SQLite create 需要其 FK 表 digital_specialists？Conversation 有 FK 到 digital_specialists，SQLite 建表需先有 digital_specialists 表——把 `DigitalSpecialist.__table__` 也加进 tables）：

```python
def test_mah_overview_requires_admin():
    resp = client.get("/api/v1/specialists/mah-overview", headers=_token(1, "rep"))
    assert resp.status_code == 403
    assert resp.json()["code"] == 3000


def test_mah_overview_aggregates(fresh_state):
    db = TestSession()
    # 2 个 rep：一个有效备案+培训完成，一个未备案
    db.add(User(id=4, username="rep02", full_name="李代表", phone="13800000004", role="rep", status="active"))
    db.add(RepresentativeQualification(id=1, representative_id=1, education_cert="u1", filing_number="MAH-1",
                                       audit_status="approved", filing_expire_date=None,
                                       compliance_training_completed=True, commitment_signed=True))
    db.add(RepresentativeQualification(id=2, representative_id=4, education_cert="u4", audit_status="pending"))
    # 对话：1 条 blocked，3 条正常 → 通过率 0.75
    db.add_all([
        Conversation(id=1, user_id=1, specialist_id=1, session_id="s1", role="user", content="a", compliance_result=None),
        Conversation(id=2, user_id=1, specialist_id=1, session_id="s1", role="assistant", content="b", compliance_result={"blocked": False}),
        Conversation(id=3, user_id=1, specialist_id=1, session_id="s2", role="user", content="c", compliance_result={"blocked": False}),
        Conversation(id=4, user_id=4, specialist_id=1, session_id="s2", role="assistant", content="d", compliance_result={"blocked": True}),
    ])
    db.commit()
    db.close()
    resp = client.get("/api/v1/specialists/mah-overview", headers=_token(2, "admin"))
    body = resp.json()
    assert body["code"] == 0
    data = body["data"]
    assert data["total_reps"] == 2
    assert data["filing"]["valid"] == 1
    assert data["filing"]["pending_review"] == 1
    assert data["filing"]["not_filed"] == 0
    assert data["training_completed_rate"] == 0.5
    assert data["commitment_signed_rate"] == 0.5
    assert data["compliance_pass_rate"] == 0.75
```

- [ ] **Step 2: 运行确认失败**

Run: `cd services/specialist-service && python -m pytest tests/test_data_exports.py -k mah_overview -v`
Expected: FAIL（404）。

- [ ] **Step 3: 实现 mah_overview.py**

Create `services/specialist-service/app/api/mah_overview.py`：

```python
"""MAH 合规全景视图（三期 K，需求 3.7(4)）：备案状态分布 / 培训完成率 / 合规通过率。

口径：合规通过率 = 1 − conversations.compliance_result.blocked=true / 总对话数（同 review-queue）。
备案状态按 representative_qualifications 派生：无记录/无备案号 → not_filed；
audit_status=pending → pending_review；rejected → rejected；approved 且 filing 有效 → valid / 过期 → expired。"""
from datetime import date
from typing import Optional

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from shared.common.auth import require_roles
from shared.common.db_session import get_db
from shared.common.response import success
from shared.models.qualification import RepresentativeQualification
from shared.models.user import User

from app.models.conversation import Conversation

router = APIRouter(prefix="/api/v1/specialists", tags=["mah-overview"])


def _filing_bucket(rep_id: int, qual: Optional[RepresentativeQualification]) -> str:
    """判序：审核状态（pending/rejected）优先于备案号有无——待审/被驳的资质即使无备案号也归对应桶。"""
    if not qual:
        return "not_filed"
    if qual.audit_status == "pending":
        return "pending_review"
    if qual.audit_status == "rejected":
        return "rejected"
    if not (qual.filing_number or "").strip():
        return "not_filed"
    if qual.filing_expire_date and qual.filing_expire_date < date.today():
        return "expired"
    return "valid"


@router.get("/mah-overview")
async def mah_overview(
    _admin: dict = Depends(require_roles("admin", "manager", "compliance")),
    db: Session = Depends(get_db),
):
    reps = db.query(User).filter(User.role == "rep").all()
    quals = db.query(RepresentativeQualification).all()
    qual_map = {q.representative_id: q for q in quals}

    filing = {"not_filed": 0, "valid": 0, "expired": 0, "pending_review": 0, "rejected": 0}
    for rep in reps:
        filing[_filing_bucket(rep.id, qual_map.get(rep.id))] += 1

    approved_quals = [q for q in quals if q.audit_status == "approved"]
    total_reps = len(reps) or 1
    training_completed = sum(1 for q in approved_quals if q.compliance_training_completed)
    commitment_signed = sum(1 for q in approved_quals if q.commitment_signed)

    conv_rows = db.query(Conversation.compliance_result).all()
    total_conv = len(conv_rows)
    blocked = sum(1 for (cr,) in conv_rows if cr and cr.get("blocked"))
    compliance_pass_rate = round(1 - (blocked / total_conv), 4) if total_conv else 1.0

    return success({
        "total_reps": len(reps),
        "filing": filing,
        "training_completed_rate": round(training_completed / total_reps, 4),
        "commitment_signed_rate": round(commitment_signed / total_reps, 4),
        "compliance_pass_rate": compliance_pass_rate,
    })
```

`main.py` 加 `from app.api.mah_overview import router as mah_overview_router; app.include_router(mah_overview_router)`。

- [ ] **Step 4: 运行确认通过**

Run: `cd services/specialist-service && python -m pytest tests/test_data_exports.py -k mah_overview -v`
Expected: 2 PASS。全量不降。

- [ ] **Step 5: Commit**

```bash
git add services/specialist-service/app/api/mah_overview.py services/specialist-service/app/main.py services/specialist-service/tests/test_data_exports.py
git commit -m "feat(mah): MAH 合规全景视图（备案/培训/合规通过率）"
```

---

### Task 4: 数据分类分级端点

**Files:**
- Create: `services/compliance-service/app/api/data_assets.py`
- Modify: `services/compliance-service/app/main.py`（include_router）
- Modify: `services/compliance-service/tests/test_data_assets.py`（新建）

**Interfaces:**
- Produces: `GET /api/v1/compliance/data-assets`（admin/manager/compliance）。Task 5 web 依赖。

- [ ] **Step 1: 写失败测试**

Create `services/compliance-service/tests/test_data_assets.py`（骨架参照 monitor 测试的 fixture 模式；compliance 测试在服务目录跑）：

```python
def test_data_assets_requires_admin():
    resp = client.get("/api/v1/compliance/data-assets", headers=_token(1, "rep"))
    assert resp.status_code == 403
    assert resp.json()["code"] == 3000


def test_data_assets_returns_three_categories(fresh_state):
    resp = client.get("/api/v1/compliance/data-assets", headers=_token(2, "admin"))
    body = resp.json()
    assert body["code"] == 0
    cats = {c["category"] for c in body["data"]}
    assert {"个人信息", "业务数据", "合规留存数据"} <= cats
    personal = next(c for c in body["data"] if c["category"] == "个人信息")
    assert "users" in personal["tables"]
    assert personal["level"] == "敏感"
```

- [ ] **Step 2: 运行确认失败**

Run: `cd services/compliance-service && python -m pytest tests/test_data_assets.py -v`
Expected: FAIL（404）。

- [ ] **Step 3: 实现 data_assets.py**

Create `services/compliance-service/app/api/data_assets.py`：

```python
"""数据分类分级清单（三期 K，需求 3.8(1)）：只读配置，三类数据资产映射实际表。
敏感类别（个人信息/对话明细）导出必走数据导出审批流（/data-exports）。"""
from fastapi import APIRouter, Depends

from shared.common.auth import require_roles
from shared.common.response import success

router = APIRouter(prefix="/api/v1/compliance", tags=["data-assets"])

ASSETS = [
    {"category": "个人信息", "level": "敏感", "tables": ["users", "doctor_profiles", "doctor_twin_subscriptions", "doctor_consents"]},
    {"category": "业务数据", "level": "内部", "tables": ["conversations", "academic_cards", "card_push_records", "edu_content_records", "visit_records"]},
    {"category": "合规留存数据", "level": "审计留存", "tables": ["audit_logs", "compliance_blocks", "compliance_rules", "skill_audits"]},
]


@router.get("/data-assets")
async def data_assets(
    _admin: dict = Depends(require_roles("admin", "manager", "compliance")),
):
    return success(ASSETS)
```

`main.py` 加 include_router。

- [ ] **Step 4: 运行确认通过**

Run: `cd services/compliance-service && python -m pytest tests/test_data_assets.py -v`
Expected: 2 PASS。全量 `python -m pytest tests/ -q` 不降。

- [ ] **Step 5: Commit**

```bash
git add services/compliance-service/app/api/data_assets.py services/compliance-service/app/main.py services/compliance-service/tests/test_data_assets.py
git commit -m "feat(data-assets): 数据分类分级清单端点"
```

---

### Task 5: web — MAH 全景 + 数据治理 + 导出审批三页

**Files:**
- Modify: `web/src/types/index.ts`
- Modify: `web/src/services/specialist.ts`（mahOverview）、`web/src/services/compliance.ts`（dataAssets）
- Create: `web/src/services/dataExports.ts`
- Create: `web/src/pages/Compliance/MahOverview.tsx`、`web/src/pages/Compliance/DataAssets.tsx`、`web/src/pages/Compliance/DataExports.tsx`
- Modify: `web/src/App.tsx`、`web/src/constants/menu.tsx`
- Test: 无 jest；验证门 = `cd web && npm run build`

**Interfaces:**
- Consumes: `GET /api/v1/specialists/mah-overview`（Task 3）、`GET /api/v1/compliance/data-assets`（Task 4）、`/api/v1/data-exports/requests`（Task 2）。

- [ ] **Step 1: 类型 + API**

`web/src/types/index.ts` 加：

```ts
// ========== 三期 K：MAH 全景 / 数据分类 / 导出审批 ==========
export interface MahOverview {
  total_reps: number;
  filing: { not_filed: number; valid: number; expired: number; pending_review: number; rejected: number };
  training_completed_rate: number;
  commitment_signed_rate: number;
  compliance_pass_rate: number;
}

export interface DataAssetCategory {
  category: string;
  level: string;
  tables: string[];
}

export interface ExportRequest {
  id: number;
  requester_id: number;
  requester_name?: string | null;
  export_type: string;
  reason: string | null;
  status: 'pending' | 'approved' | 'rejected';
  approver_id: number | null;
  approve_reason: string | null;
  file_url: string | null;
  expires_at: string | null;
  responded_at: string | null;
  created_at: string | null;
  sla_overdue?: boolean;
}
```

`web/src/services/specialist.ts` 加：

```ts
  mahOverview: () =>
    client.get<ApiResponse<MahOverview>>('/specialists/mah-overview'),
```

`web/src/services/compliance.ts` 加：

```ts
  dataAssets: () =>
    client.get<ApiResponse<DataAssetCategory[]>>('/compliance/data-assets'),
```

Create `web/src/services/dataExports.ts`：

```ts
import client from './client';
import type { ApiResponse, PaginatedResponse, ExportRequest } from '../types';

export const dataExportAPI = {
  list: (params?: { page?: number; page_size?: number; status?: string }) =>
    client.get<PaginatedResponse<ExportRequest>>('/data-exports/requests', { params }),
  create: (data: { export_type: string; reason: string }) =>
    client.post<ApiResponse<ExportRequest>>('/data-exports/requests', data),
  review: (id: number, data: { verdict: 'approve' | 'reject'; reason?: string }) =>
    client.post<ApiResponse<ExportRequest>>(`/data-exports/requests/${id}/review`, data),
  downloadUrl: (id: number) => `/api/v1/data-exports/requests/${id}/download`,
};
```

（download 用浏览器直开 URL 下载，不经过 axios。）

- [ ] **Step 2: 三页**

- `MahOverview.tsx`：进入 `specialistAPI.mahOverview()`；展示 5 张卡片（总代表数/合规通过率/培训完成率/承诺签署率）+ 备案分布（valid/expired/not_filed/pending_review/rejected 计数与 Tag）。参照 `Compliance/Monitor.tsx` 的统计卡风格。
- `DataAssets.tsx`：`complianceAPI.dataAssets()`；三类清单表格（类别/级别/表清单），顶部说明"敏感类别（个人信息/对话明细）导出必走数据导出审批流"。
- `DataExports.tsx`：`dataExportAPI.list()` ProTable；列：申请单号/申请人/类型/目的/状态（pending 橙+`sla_overdue` 红 Tag「超 SLA」/approved 绿/rejected 红）/申请时间/操作（pending → 「审批」Drawer verdict+reason；approved → 「下载」`window.open(dataExportAPI.downloadUrl(id))`）；头部「发起导出申请」ModalForm（export_type 固定 conversations + reason 必填）→ `dataExportAPI.create`。

- [ ] **Step 3: 路由 + 菜单**

`web/src/App.tsx` 加懒加载路由：`compliance/mah-overview` → `MahOverview`、`data/assets` → `DataAssets`、`data/exports` → `DataExports`。`menu.tsx` 在「合规风控」后加 `{ path: '/compliance/mah-overview', name: 'MAH 全景', icon: <RadarChartOutlined /> }`、在「审计查询」前加 `{ path: '/data/assets', name: '数据治理', icon: <SafetyOutlined /> }` 与 `{ path: '/data/exports', name: '导出审批', icon: <SnippetsOutlined /> }`。

- [ ] **Step 4: 构建验证**

Run: `cd web && npm run build`
Expected: 零错误。

- [ ] **Step 5: Commit**

```bash
git add web/src/types/index.ts web/src/services/specialist.ts web/src/services/compliance.ts web/src/services/dataExports.ts web/src/pages/Compliance/MahOverview.tsx web/src/pages/Compliance/DataAssets.tsx web/src/pages/Compliance/DataExports.tsx web/src/App.tsx web/src/constants/menu.tsx
git commit -m "feat(web): MAH 全景 + 数据治理 + 导出审批三页"
```

---

### Task 6: 全量回归 + 文档同步

**Files:**
- Modify: `CLAUDE.md`、`README.md`
- Test: 全量回归

- [ ] **Step 1: 全量后端回归**

Run: `cd services/specialist-service && python -m pytest tests/ -q`（预计 257 + Task1 1 + Task2 6 + Task3 2 = ~266）；`cd services/compliance-service && python -m pytest tests/ -q`（107 + 2 = ~109）。

- [ ] **Step 2: 前端验证**

Run: `cd web && npm run build`；`cd mobile && npx jest`（96 不变）。

- [ ] **Step 3: 同步 CLAUDE.md**

网关 ROUTE_MAP 加 `/api/v1/data-exports` → specialist；三期 K 补记段（`/specialists/mah-overview` 口径 + `/compliance/data-assets` + `/data-exports/requests` 申请/审批/下载 + SLA 3 日 + 下载 7 天过期 + openpyxl 依赖）；Database 段迁移 022（export_requests 表，已并入 init_db.sql）；specialist/compliance 基线改实测；Known Gaps 补「对话明细导出上限 50000 行」。

- [ ] **Step 4: 同步 README**

功能矩阵加三期 K 行（管理后台 MAH 全景/数据治理/导出审批）。

- [ ] **Step 5: Commit**

```bash
git add CLAUDE.md README.md
git commit -m "docs: 三期 K MAH 全景+数据治理文档同步"
```
