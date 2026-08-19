# 培训考试 + 承诺书 实施计划（二期 F）

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 上线合规培训与考试系统（培训材料管理 + 题库 + 在线考试判分 + 年度承诺书签署），满足《医药代表管理办法》培训前置要求（先上线不强制）。

**Architecture:** 服务归属 auth-service（与 representative_qualifications 同域，需回写其三字段）。三张新表：training_materials / exam_questions / exam_records。管理端（医学部/合规部）建材料与题目并人工审核；代表端个人合规中心学习材料、参加考试、签署承诺书（勾选 + 短信验证码 + 审计）。AI 出题为辅助（返回草稿，管理端确认后走正常审核流），不直接入库。

**Tech Stack:** Python FastAPI + SQLAlchemy / React Native 0.75（mobile）/ React + Ant Design Pro（web）/ PostgreSQL 迁移 013 / httpx 直调 dashscope（AI 出题，不引 openai SDK）。

## Global Constraints

- 服务归属 auth-service，端点前缀 `/api/v1/training-materials`、`/api/v1/exams`、`/api/v1/qualifications/commitment`；网关 ROUTE_MAP 加 `/api/v1/training-materials` 与 `/api/v1/exams` → AUTH_SERVICE_URL。
- 权限：培训材料/题目/考试记录的写与审核 → `require_roles("admin","manager","compliance","medical")`；材料只读与考试 → rep 可用；承诺书 → 仅 rep。
- 题目答案字段 `answer` 为 JSON 索引数组：single→`[i]`、judge→`[0]`/`[1]`（options=["正确","错误"]）、multiple→`[i,j,...]`；提交 `selected` 同格式，判分按集合相等。
- 及格线 `EXAM_PASS_SCORE` 环境变量，默认 80。
- 考试只抽 `review_status='approved'` 的题；代表端任何接口不返回 `answer`。
- AI 出题内容仅返回草稿，**不落库**；管理端确认后经 `POST /exams/questions` 入库（review_status=pending）→ 人工审核。
- 承诺书：勾选 + 短信验证码（复用 code_store.consume）+ 审计留痕（action=`commitment_signed`）。
- 培训前置**先上线不强制**（已拍板）：只展示状态，不做使用门禁。
- 全部 AI 生成内容标注"AI 生成"；引用无页码；Skill 内容任何 API 不返回（本计划不涉及 Skill）。
- 复用 `shared.common.response`（success/ParamError/BusinessError/PermissionError）与 `shared.common.pagination`（paginate）。
- 审计走 `write_audit_log`（auth-service 内），所有写操作留痕。
- 测试遵循 auth-service 既有模式：SQLite `:memory:` + StaticPool + `@compiles(BigInteger)` → INTEGER、`monkeypatch.setitem(app.dependency_overrides, get_db, ...)`、`monkeypatch.setattr(module, "write_audit_log", AsyncMock)`。
- 提交规范：conventional commits + Co-Authored-By 尾注；推 Codeup 前需用户确认。

## File Structure

**Backend（auth-service + shared + gateway + scripts）：**
- Create: `scripts/migrations/013_training_exam.sql` — 三张新表（与 init_db.sql 一致）
- Modify: `scripts/init_db.sql` — 追加三张新表（对应迁移 013）
- Create: `shared/models/training_exam.py` — TrainingMaterial / ExamQuestion / ExamRecord
- Create: `services/auth-service/app/api/training_materials.py` — 培训材料 CRUD + 只读列表
- Create: `services/auth-service/app/api/exams.py` — 题库 CRUD/review/AI 出题 + 考试 start/submit/records
- Create: `services/auth-service/app/services/qwen_client.py` — dashscope 兼容接口 httpx 客户端（AI 出题）
- Modify: `services/auth-service/app/main.py` — 注册两个新 router
- Modify: `services/gateway/app/main.py` — ROUTE_MAP 两行
- Create: `scripts/seed_training_materials.py` — 内置《办法》要点 + RDPAC 要点 + 2 条已审核题目
- Test: `services/auth-service/tests/test_training_materials.py`
- Test: `services/auth-service/tests/test_exams.py`（题库 + 考试 + AI 出题）

**Frontend：**
- Create: `web/src/pages/Training/TrainingList.tsx` — 三 Tab：材料/题库/考试记录
- Create: `web/src/services/training.ts` — 前端 API
- Modify: `web/src/types/index.ts` — TrainingMaterial / ExamQuestion / ExamRecord / 草稿类型
- Modify: `web/src/App.tsx` — 路由 `/training/list`
- Modify: `web/src/constants/menu.tsx` — 菜单"合规培训"
- Create: `mobile/src/api/exam.ts` — 材料/考试/承诺书 API
- Create: `mobile/src/screens/Compliance/TrainingMaterialScreen.tsx`
- Create: `mobile/src/screens/Compliance/ExamScreen.tsx`
- Create: `mobile/src/screens/Compliance/CommitmentScreen.tsx`
- Modify: `mobile/src/screens/Compliance/ComplianceCenterScreen.tsx` — 加入口
- Modify: `mobile/src/navigation/types.ts` + `mobile/src/navigation/AppNavigator.tsx`
- Test: `mobile/src/api/__tests__/exam-contract.test.ts`

**Docs：**
- Modify: `CLAUDE.md` — 端点/表/基线/挂账

---

### Task 1: 迁移 013 + 数据模型 + init_db.sql 同步

**Files:**
- Create: `scripts/migrations/013_training_exam.sql`
- Modify: `scripts/init_db.sql`
- Create: `shared/models/training_exam.py`

**Interfaces:**
- Produces: `TrainingMaterial` / `ExamQuestion` / `ExamRecord`（shared/models/training_exam.py，继承 `shared.models.base.Base` + `TimestampMixin`），字段名供 Task 2-5 使用。

- [ ] **Step 1: 写迁移文件**

Create `scripts/migrations/013_training_exam.sql`：

```sql
-- 013_training_exam.sql
-- 二期 F：培训材料 / 题库 / 考试记录（需求文档 3.4/附录A）
-- 用法：docker exec -i medagent-postgres psql -U medagent medagent < scripts/migrations/013_training_exam.sql

\set ON_ERROR_STOP on

CREATE TABLE IF NOT EXISTS training_materials (
    id BIGSERIAL PRIMARY KEY,
    title VARCHAR(200) NOT NULL,
    material_type VARCHAR(20) NOT NULL,      -- regulation(办法) / rdpac / internal(内部政策)
    content TEXT NOT NULL,
    version VARCHAR(20) DEFAULT '1.0',
    status VARCHAR(20) NOT NULL DEFAULT 'active',  -- active / archived
    created_by BIGINT REFERENCES users(id),
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_tm_type ON training_materials(material_type);
CREATE INDEX IF NOT EXISTS idx_tm_status ON training_materials(status);

CREATE TABLE IF NOT EXISTS exam_questions (
    id BIGSERIAL PRIMARY KEY,
    material_id BIGINT REFERENCES training_materials(id),
    question_type VARCHAR(10) NOT NULL,      -- single / multiple / judge
    content TEXT NOT NULL,
    options JSONB NOT NULL,                  -- ["选项A",...]（judge 为 ["正确","错误"]）
    answer JSONB NOT NULL,                   -- [i] 或 [i,j]；任何接口不对代表端返回
    review_status VARCHAR(20) NOT NULL DEFAULT 'pending',  -- pending / approved / rejected
    review_reason VARCHAR(500),
    reviewed_by BIGINT,
    reviewed_at TIMESTAMP,
    created_by BIGINT REFERENCES users(id),
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_eq_status ON exam_questions(review_status);
CREATE INDEX IF NOT EXISTS idx_eq_material ON exam_questions(material_id);

CREATE TABLE IF NOT EXISTS exam_records (
    id BIGSERIAL PRIMARY KEY,
    representative_id BIGINT NOT NULL REFERENCES users(id),
    question_count INTEGER NOT NULL,
    correct_count INTEGER NOT NULL,
    score INTEGER NOT NULL,
    passed BOOLEAN NOT NULL,
    submitted_at TIMESTAMP DEFAULT NOW(),
    created_at TIMESTAMP DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_er_rep ON exam_records(representative_id);
```

- [ ] **Step 2: init_db.sql 追加相同三表**

在 `scripts/init_db.sql` 末尾追加与迁移 013 完全一致的三段 `CREATE TABLE IF NOT EXISTS` + 索引（copy Step 1 内容，去掉 `\set ON_ERROR_STOP` 与注释头两行）。

- [ ] **Step 3: 写模型**

Create `shared/models/training_exam.py`：

```python
"""培训考试模型（需求文档 3.4/附录A training_materials/exam_questions/exam_records）"""
from datetime import datetime

from sqlalchemy import BigInteger, Boolean, Column, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSONB

from shared.models.base import Base, TimestampMixin


class TrainingMaterial(Base, TimestampMixin):
    __tablename__ = "training_materials"

    title = Column(String(200), nullable=False)
    material_type = Column(String(20), nullable=False)   # regulation / rdpac / internal
    content = Column(Text, nullable=False)
    version = Column(String(20), default="1.0")
    status = Column(String(20), default="active")        # active / archived
    created_by = Column(BigInteger, ForeignKey("users.id"))

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "title": self.title,
            "material_type": self.material_type,
            "content": self.content,
            "version": self.version,
            "status": self.status,
            "created_by": self.created_by,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }


class ExamQuestion(Base, TimestampMixin):
    __tablename__ = "exam_questions"

    material_id = Column(BigInteger, ForeignKey("training_materials.id"))
    question_type = Column(String(10), nullable=False)   # single / multiple / judge
    content = Column(Text, nullable=False)
    options = Column(JSONB, nullable=False)
    answer = Column(JSONB, nullable=False)
    review_status = Column(String(20), default="pending")  # pending / approved / rejected
    review_reason = Column(String(500))
    reviewed_by = Column(BigInteger)
    reviewed_at = Column(DateTime)
    created_by = Column(BigInteger, ForeignKey("users.id"))

    def to_dict(self, expose_answer: bool = False) -> dict:
        d = {
            "id": self.id,
            "material_id": self.material_id,
            "question_type": self.question_type,
            "content": self.content,
            "options": self.options,
            "review_status": self.review_status,
            "review_reason": self.review_reason,
            "created_by": self.created_by,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }
        if expose_answer:
            d["answer"] = self.answer
        return d


class ExamRecord(Base, TimestampMixin):
    __tablename__ = "exam_records"

    representative_id = Column(BigInteger, ForeignKey("users.id"), nullable=False)
    question_count = Column(Integer, nullable=False)
    correct_count = Column(Integer, nullable=False)
    score = Column(Integer, nullable=False)
    passed = Column(Boolean, nullable=False)
    submitted_at = Column(DateTime, default=datetime.utcnow)

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "representative_id": self.representative_id,
            "question_count": self.question_count,
            "correct_count": self.correct_count,
            "score": self.score,
            "passed": self.passed,
            "submitted_at": self.submitted_at.isoformat() if self.submitted_at else None,
        }
```

> 注意：JSONB 列在 SQLite 测试里能正常建（sqlalchemy 映射为文本 JSON）。若 SQLite 报 JSONB 不支持，测试文件内加 `from sqlalchemy.dialects.postgresql import JSONB` 的 compile 扩展（见 Task 3 测试模板）。

- [ ] **Step 4: 验证模型可建表**

Run: `cd services/auth-service && python -c "import sys,os; sys.path.insert(0, '.'); sys.path.insert(0, os.path.abspath('../../shared/..')); from shared.models.training_exam import TrainingMaterial, ExamQuestion, ExamRecord; print('ok')"`
Expected: `ok`（无导入错误）

- [ ] **Step 5: Commit**

```bash
git add scripts/migrations/013_training_exam.sql scripts/init_db.sql shared/models/training_exam.py
git commit -m "feat(auth): 培训考试三表迁移+模型（training_materials/exam_questions/exam_records）"
```

---

### Task 2: 培训材料管理端点 + 内置材料种子

**Files:**
- Create: `services/auth-service/app/api/training_materials.py`
- Modify: `services/auth-service/app/main.py`
- Create: `scripts/seed_training_materials.py`
- Test: `services/auth-service/tests/test_training_materials.py`

**Interfaces:**
- Consumes: `TrainingMaterial`（Task 1）
- Produces: 路由前缀 `/api/v1/training-materials`；端点 `POST ""`（创建，管理角色）、`GET ""`（分页列表，登录用户可读）、`GET "/{material_id}"`（详情）、`PUT "/{material_id}"`（更新）、`DELETE "/{material_id}"`（软删 status=archived）。`training_materials_router` 导出供 main.py 注册。

- [ ] **Step 1: 写失败测试**

Create `services/auth-service/tests/test_training_materials.py`：

```python
"""培训材料端点测试（Task 2）：创建/列表/详情/更新/软删/权限边界"""
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
from sqlalchemy.ext.compiler import compiles
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from shared.common.auth import create_token
from shared.common.db_session import get_db
from shared.models.base import Base
from shared.models.training_exam import ExamQuestion, ExamRecord, TrainingMaterial
from shared.models.user import User

import app.api.training_materials as tm_api
from app.main import app


@compiles(BigInteger, "sqlite")
def _compile_bigint_for_sqlite(type_, compiler, **kw):
    return "INTEGER"


engine = create_engine(
    "sqlite://",
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)
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
    tables = [User.__table__, TrainingMaterial.__table__]
    Base.metadata.drop_all(engine, tables=tables)
    Base.metadata.create_all(engine, tables=tables)
    db = TestSession()
    db.add_all([
        User(id=1, username="rep01", full_name="张代表", phone="13800000001", role="rep", status="active"),
        User(id=2, username="admin", full_name="管理员", phone="13800000000", role="admin", status="active"),
        User(id=3, username="med", full_name="医学部", phone="13800000003", role="medical", status="active"),
    ])
    db.commit()
    db.close()

    monkeypatch.setitem(app.dependency_overrides, get_db, _override_db)
    audit_mock = AsyncMock(return_value=None)
    monkeypatch.setattr(tm_api, "write_audit_log", audit_mock)
    yield audit_mock


def test_create_requires_admin_role():
    resp = client.post("/api/v1/training-materials", json={
        "title": "办法要点", "material_type": "regulation", "content": "正文",
    }, headers=_token(1, "rep"))
    assert resp.status_code == 403
    assert resp.json()["code"] == 3000


def test_create_material(fresh_state):
    resp = client.post("/api/v1/training-materials", json={
        "title": "医药代表管理办法要点", "material_type": "regulation", "content": "二十二项禁止行为……",
    }, headers=_token(2, "admin"))
    body = resp.json()
    assert body["code"] == 0
    data = body["data"]
    assert data["title"] == "医药代表管理办法要点"
    assert data["status"] == "active"
    assert data["material_type"] == "regulation"
    audit_mock = fresh_state
    audit_mock.assert_awaited_once()


def test_create_validates_required_fields():
    resp = client.post("/api/v1/training-materials", json={"title": ""}, headers=_token(2, "admin"))
    assert resp.status_code == 400
    assert resp.json()["code"] == 1000


def test_list_returns_materials():
    db = TestSession()
    db.add(TrainingMaterial(id=1, title="办法要点", material_type="regulation", content="x", created_by=2))
    db.add(TrainingMaterial(id=2, title="内部政策", material_type="internal", content="y", created_by=2, status="archived"))
    db.commit()
    db.close()

    resp = client.get("/api/v1/training-materials", headers=_token(1, "rep"))
    body = resp.json()
    assert body["code"] == 0
    assert body["data"]["total"] == 1  # archived 不展示
    assert body["data"]["items"][0]["title"] == "办法要点"


def test_get_detail():
    db = TestSession()
    db.add(TrainingMaterial(id=1, title="办法要点", material_type="regulation", content="正文", created_by=2))
    db.commit()
    db.close()

    resp = client.get("/api/v1/training-materials/1", headers=_token(3, "medical"))
    body = resp.json()
    assert body["code"] == 0
    assert body["data"]["content"] == "正文"


def test_update_material(fresh_state):
    db = TestSession()
    db.add(TrainingMaterial(id=1, title="旧标题", material_type="regulation", content="旧", created_by=2))
    db.commit()
    db.close()

    resp = client.put("/api/v1/training-materials/1", json={"title": "新标题", "content": "新"},
                      headers=_token(2, "admin"))
    body = resp.json()
    assert body["code"] == 0
    assert body["data"]["title"] == "新标题"
    audit_mock = fresh_state
    audit_mock.assert_awaited_once()


def test_delete_archives(fresh_state):
    db = TestSession()
    db.add(TrainingMaterial(id=1, title="办法要点", material_type="regulation", content="x", created_by=2))
    db.commit()
    db.close()

    resp = client.delete("/api/v1/training-materials/1", headers=_token(2, "admin"))
    body = resp.json()
    assert body["code"] == 0
    assert body["data"]["status"] == "archived"
    audit_mock = fresh_state
    audit_mock.assert_awaited_once()


def test_missing_row_422():
    resp = client.put("/api/v1/training-materials/999", json={"title": "x"}, headers=_token(2, "admin"))
    assert resp.status_code == 422
    assert resp.json()["code"] == 4001
```

- [ ] **Step 2: 运行测试确认失败**

Run: `cd services/auth-service && python -m pytest tests/test_training_materials.py -x -q`
Expected: 失败（模块 app.api.training_materials 不存在 / 404）

- [ ] **Step 3: 实现端点**

Create `services/auth-service/app/api/training_materials.py`：

```python
"""培训材料管理（需求文档 3.4(1)）：医学部/合规部创建维护，代表端只读"""
import logging
from typing import Optional

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from shared.common.auth import get_current_user, require_roles
from shared.common.context import get_request_id
from shared.common.db_session import get_db
from shared.common.pagination import PaginationParams, paginate
from shared.common.response import BusinessError, ParamError, PermissionError, success
from shared.models.training_exam import TrainingMaterial

from app.services.audit_client import write_audit_log

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/training-materials", tags=["training-materials"])

MATERIAL_ADMIN_ROLES = ("admin", "manager", "compliance", "medical")
VALID_TYPES = ("regulation", "rdpac", "internal")


def _validate_payload(payload: dict) -> dict:
    if not isinstance(payload, dict):
        raise ParamError("请求体必须是 JSON 对象")
    title = (payload.get("title") or "").strip()
    if not title:
        raise ParamError("标题不能为空")
    if len(title) > 200:
        raise ParamError("标题长度不能超过 200 字符")
    content = payload.get("content")
    if not content or not str(content).strip():
        raise ParamError("材料正文不能为空")
    material_type = (payload.get("material_type") or "").strip()
    if material_type not in VALID_TYPES:
        raise ParamError("material_type 必须是 regulation/rdpac/internal 之一")
    return {"title": title, "content": str(content).strip(), "material_type": material_type}


@router.post("")
async def create_material(
    payload: dict,
    current_user: dict = Depends(require_roles(*MATERIAL_ADMIN_ROLES)),
    db: Session = Depends(get_db),
):
    """创建培训材料（医学部/合规部/admin/manager）"""
    data = _validate_payload(payload)
    mat = TrainingMaterial(**data, created_by=current_user["id"], status="active")
    db.add(mat)
    db.commit()
    db.refresh(mat)
    await write_audit_log(
        action="training_material_create",
        user_id=current_user["id"],
        resource_type="training_material",
        resource_id=str(mat.id),
        after_value={"title": mat.title, "material_type": mat.material_type},
        request_id=get_request_id() or None,
    )
    return success(mat.to_dict())


@router.get("")
async def list_materials(
    page: int = 1,
    page_size: int = 20,
    material_type: Optional[str] = None,
    keyword: Optional[str] = None,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """培训材料列表（登录用户可读；archived 不展示）"""
    if material_type and material_type not in VALID_TYPES:
        raise ParamError("material_type 不合法")
    p = PaginationParams(page=page, page_size=page_size)
    query = db.query(TrainingMaterial).filter(TrainingMaterial.status == "active")
    if material_type:
        query = query.filter(TrainingMaterial.material_type == material_type)
    if keyword:
        query = query.filter(TrainingMaterial.title.ilike(f"%{keyword}%"))
    total = query.count()
    rows = query.order_by(TrainingMaterial.id.desc()).offset(p.offset).limit(p.limit).all()
    return success(paginate([m.to_dict() for m in rows], total, p.page, p.page_size))


@router.get("/{material_id}")
async def get_material(
    material_id: int,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    mat = db.query(TrainingMaterial).filter(TrainingMaterial.id == material_id).first()
    if not mat or mat.status != "active":
        raise BusinessError("培训材料不存在", code=4001)
    return success(mat.to_dict())


@router.put("/{material_id}")
async def update_material(
    material_id: int,
    payload: dict,
    current_user: dict = Depends(require_roles(*MATERIAL_ADMIN_ROLES)),
    db: Session = Depends(get_db),
):
    mat = db.query(TrainingMaterial).filter(TrainingMaterial.id == material_id).first()
    if not mat or mat.status != "active":
        raise BusinessError("培训材料不存在", code=4001)
    data = _validate_payload(payload)
    before = {"title": mat.title, "content": mat.content, "material_type": mat.material_type}
    mat.title = data["title"]
    mat.content = data["content"]
    mat.material_type = data["material_type"]
    db.commit()
    db.refresh(mat)
    await write_audit_log(
        action="training_material_update",
        user_id=current_user["id"],
        resource_type="training_material",
        resource_id=str(mat.id),
        before_value=before,
        after_value={"title": mat.title, "material_type": mat.material_type},
        request_id=get_request_id() or None,
    )
    return success(mat.to_dict())


@router.delete("/{material_id}")
async def archive_material(
    material_id: int,
    current_user: dict = Depends(require_roles(*MATERIAL_ADMIN_ROLES)),
    db: Session = Depends(get_db),
):
    mat = db.query(TrainingMaterial).filter(TrainingMaterial.id == material_id).first()
    if not mat or mat.status != "active":
        raise BusinessError("培训材料不存在", code=4001)
    mat.status = "archived"
    db.commit()
    db.refresh(mat)
    await write_audit_log(
        action="training_material_archive",
        user_id=current_user["id"],
        resource_type="training_material",
        resource_id=str(mat.id),
        request_id=get_request_id() or None,
    )
    return success(mat.to_dict())
```

- [ ] **Step 4: 注册 router**

Modify `services/auth-service/app/main.py`：在现有 `app.include_router(...)` 行附近追加：

```python
from app.api.training_materials import router as training_materials_router
app.include_router(training_materials_router)
```

- [ ] **Step 5: 运行测试确认通过**

Run: `cd services/auth-service && python -m pytest tests/test_training_materials.py -q`
Expected: 8 passed

- [ ] **Step 6: 写内置材料种子脚本**

Create `scripts/seed_training_materials.py`（参考 seed_admin.py 的 sys.path/load_dotenv 骨架）：

```python
#!/usr/bin/env python3
"""内置合规培训材料种子：医药代表管理办法要点 + RDPAC 行为准则要点 + 2 条已审核题目

用法：
    python scripts/seed_training_materials.py
幂等：已存在同标题 material 时跳过。
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "services", "auth-service"))

from dotenv import load_dotenv
load_dotenv()

from shared.common.db_session import SessionLocal
from shared.models.training_exam import ExamQuestion, TrainingMaterial

REGULATION_TITLE = "《医药代表管理办法》要点（2026版）"
RDPAC_TITLE = "RDPAC 行业行为准则要点"

REGULATION_CONTENT = """《医药代表管理办法》（2026-08-01 施行）要点：
一、医药代表备案：须在国家医药代表备案平台完成备案，备案信息真实有效；代表证有效期内方可从事学术推广。
二、职责限定：仅从事学术推广（向医务人员介绍药品信息、收集不良反应信息、协助合规推广活动），不得承担销售任务、不得统方（获取处方量/药品用量信息）、不得虚构拜访记录。
三、二十二项禁止行为（要点）：不得提供财物或其他利益（R009）、不得附加销售条件（R008）、不得隐瞒不良反应（R010）、不得误导用药（R011）、不得超适应症推广、不得无授权推广、不得挂靠其他机构等。
四、合规培训：代表须完成年度合规培训并通过考试；签署年度合规承诺书。
五、监督管理：药企对代表行为负主体责任；违规记录纳入信用档案。"""

RDPAC_CONTENT = """RDPAC（中国外商投资企业协会药品研制和开发行业委员会）行业行为准则要点：
一、推广活动须以学术交流为目的，公平竞争，禁止虚假或误导性信息。
二、与医务人员的互动须透明、适度，不得以馈赠影响处方行为。
三、禁止向处方者提供现金、礼品或任何形式的利益输送。
四、推广信息须符合说明书与已获批适应症范围。"""

# 内置 2 条已审核题目，保证考试开箱可用
BUILTIN_QUESTIONS = [
    {
        "question_type": "judge",
        "content": "医药代表可以收集药品不良反应信息。",
        "options": ["正确", "错误"],
        "answer": [0],
    },
    {
        "question_type": "single",
        "content": "医药代表的核心职责是：",
        "options": ["承担药品销售任务", "从事学术推广并收集不良反应信息", "获取处方量信息", "直接向患者推荐处方"],
        "answer": [1],
    },
]


def main() -> None:
    db = SessionLocal()
    try:
        mat_ids = {}
        for title, mtype, content in [
            (REGULATION_TITLE, "regulation", REGULATION_CONTENT),
            (RDPAC_TITLE, "rdpac", RDPAC_CONTENT),
        ]:
            existing = db.query(TrainingMaterial).filter(TrainingMaterial.title == title).first()
            if existing:
                mat_ids[title] = existing.id
                print(f"跳过已存在材料: {title}")
                continue
            mat = TrainingMaterial(title=title, material_type=mtype, content=content, created_by=None, status="active")
            db.add(mat)
            db.flush()
            mat_ids[title] = mat.id
            print(f"已创建材料: {title} (id={mat.id})")

        reg_id = mat_ids.get(REGULATION_TITLE)
        for q in BUILTIN_QUESTIONS:
            existing = db.query(ExamQuestion).filter(ExamQuestion.content == q["content"]).first()
            if existing:
                continue
            db.add(ExamQuestion(
                material_id=reg_id,
                question_type=q["question_type"],
                content=q["content"],
                options=q["options"],
                answer=q["answer"],
                review_status="approved",
            ))
            print(f"已创建题目: {q['content']}")
        db.commit()
        print("培训考试种子完成。")
    finally:
        db.close()


if __name__ == "__main__":
    main()
```

- [ ] **Step 7: Commit**

```bash
git add services/auth-service/app/api/training_materials.py services/auth-service/app/main.py scripts/seed_training_materials.py services/auth-service/tests/test_training_materials.py
git commit -m "feat(auth): 培训材料管理端点 + 内置办法/RDPAC 种子"
```

---

### Task 3: 题库端点（CRUD + 人工审核）

**Files:**
- Create: `services/auth-service/app/api/exams.py`
- Modify: `services/auth-service/app/main.py`
- Test: `services/auth-service/tests/test_exams.py`

**Interfaces:**
- Consumes: `ExamQuestion`（Task 1）
- Produces: 路由前缀 `/api/v1/exams`；`exams_router` 导出。端点：`POST /questions`（创建，管理角色）、`GET /questions`（列表+review_status 筛选）、`PUT /questions/{qid}`、`POST /questions/{qid}/review`、`GET /records/me`（本人考试记录）、`GET /records`（管理端全量）、`POST /start`（抽题）、`POST /submit`（判分）。后续任务复用此文件。

- [ ] **Step 1: 写题库测试**

Append to `services/auth-service/tests/test_exams.py`（新建文件，前部骨架同 Task 2 测试，本任务只测题库部分，考试判分在 Task 5 加）：

```python
"""题库端点测试（Task 3 题库 CRUD + 审核；Task 5 追加考试判分用例）"""
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
from shared.models.training_exam import ExamQuestion, ExamRecord, TrainingMaterial
from shared.models.user import User

import app.api.exams as exams_api
from app.main import app


@compiles(BigInteger, "sqlite")
def _compile_bigint_for_sqlite(type_, compiler, **kw):
    return "INTEGER"


engine = create_engine(
    "sqlite://",
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)
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
    tables = [User.__table__, TrainingMaterial.__table__, ExamQuestion.__table__, ExamRecord.__table__]
    Base.metadata.drop_all(engine, tables=tables)
    Base.metadata.create_all(engine, tables=tables)
    db = TestSession()
    db.add_all([
        User(id=1, username="rep01", full_name="张代表", phone="13800000001", role="rep", status="active"),
        User(id=2, username="admin", full_name="管理员", phone="13800000000", role="admin", status="active"),
        User(id=3, username="med", full_name="医学部", phone="13800000003", role="medical", status="active"),
    ])
    db.commit()
    db.close()

    monkeypatch.setitem(app.dependency_overrides, get_db, _override_db)
    audit_mock = AsyncMock(return_value=None)
    monkeypatch.setattr(exams_api, "write_audit_log", audit_mock)
    yield audit_mock


def _add_q(**kw):
    db = TestSession()
    defaults = dict(
        id=kw.pop("id", 1), material_id=None, question_type="single",
        content="测试题目", options=["A", "B"], answer=[1], review_status="approved",
    )
    defaults.update(kw)
    db.add(ExamQuestion(**defaults))
    db.commit()
    db.close()
    return defaults["id"]


def test_create_question(fresh_state):
    resp = client.post("/api/v1/exams/questions", json={
        "question_type": "single", "content": "医药代表可否承担销售任务？",
        "options": ["可以", "不可以"], "answer": [1], "material_id": None,
    }, headers=_token(2, "admin"))
    body = resp.json()
    assert body["code"] == 0
    assert body["data"]["review_status"] == "pending"
    assert "answer" not in body["data"]  # 默认不暴露答案
    audit_mock = fresh_state
    audit_mock.assert_awaited_once()


def test_create_question_rejects_rep():
    resp = client.post("/api/v1/exams/questions", json={
        "question_type": "single", "content": "x", "options": ["A", "B"], "answer": [1],
    }, headers=_token(1, "rep"))
    assert resp.status_code == 403
    assert resp.json()["code"] == 3000


def test_create_question_validates():
    resp = client.post("/api/v1/exams/questions", json={
        "question_type": "bad", "content": "x", "options": ["A"], "answer": [0],
    }, headers=_token(2, "admin"))
    assert resp.status_code == 400
    assert resp.json()["code"] == 1000


def test_list_questions_filters_status():
    _add_q(id=1, review_status="approved")
    _add_q(id=2, review_status="pending")
    resp = client.get("/api/v1/exams/questions?review_status=pending", headers=_token(3, "medical"))
    body = resp.json()
    assert body["code"] == 0
    assert body["data"]["total"] == 1
    assert body["data"]["items"][0]["id"] == 2
    assert "answer" not in body["data"]["items"][0]


def test_review_approve(fresh_state):
    _add_q(id=1, review_status="pending")
    resp = client.post("/api/v1/exams/questions/1/review", json={"verdict": "approve"},
                       headers=_token(3, "medical"))
    body = resp.json()
    assert body["code"] == 0
    assert body["data"]["review_status"] == "approved"
    assert body["data"]["reviewed_by"] == 3
    audit_mock = fresh_state
    audit_mock.assert_awaited_once()


def test_review_reject_requires_reason():
    _add_q(id=1, review_status="pending")
    resp = client.post("/api/v1/exams/questions/1/review", json={"verdict": "reject"},
                       headers=_token(3, "medical"))
    assert resp.status_code == 400
    assert resp.json()["code"] == 1000


def test_review_reject_saves_reason(fresh_state):
    _add_q(id=1, review_status="pending")
    resp = client.post("/api/v1/exams/questions/1/review",
                       json={"verdict": "reject", "reason": "选项有歧义"},
                       headers=_token(3, "medical"))
    body = resp.json()
    assert body["code"] == 0
    assert body["data"]["review_status"] == "rejected"
    assert body["data"]["review_reason"] == "选项有歧义"


def test_review_not_pending_rejected():
    _add_q(id=1, review_status="approved")
    resp = client.post("/api/v1/exams/questions/1/review", json={"verdict": "approve"},
                       headers=_token(3, "medical"))
    assert resp.status_code == 422
    assert resp.json()["code"] == 4001
```

- [ ] **Step 2: 运行测试确认失败**

Run: `cd services/auth-service && python -m pytest tests/test_exams.py -q`
Expected: 失败（模块 app.api.exams 不存在）

- [ ] **Step 3: 实现题库部分**

Create `services/auth-service/app/api/exams.py`（先实现题库 CRUD + review；考试端点 Task 5 追加）：

```python
"""题库与考试（需求文档 3.4(2)(3)）：医学部/合规部人工审核题目；代表端在线考试"""
import logging
import random
from typing import Optional

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from shared.common.auth import get_current_user, require_roles
from shared.common.context import get_request_id
from shared.common.db_session import get_db
from shared.common.pagination import PaginationParams, paginate
from shared.common.response import BusinessError, ParamError, PermissionError, success
from shared.models.training_exam import ExamQuestion, ExamRecord

from app.services.audit_client import write_audit_log

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/exams", tags=["exams"])

EXAM_ADMIN_ROLES = ("admin", "manager", "compliance", "medical")
VALID_TYPES = ("single", "multiple", "judge")
VALID_REVIEW = ("pending", "approved", "rejected")


def _validate_question(payload: dict) -> dict:
    if not isinstance(payload, dict):
        raise ParamError("请求体必须是 JSON 对象")
    qtype = (payload.get("question_type") or "").strip()
    if qtype not in VALID_TYPES:
        raise ParamError("question_type 必须是 single/multiple/judge 之一")
    content = (payload.get("content") or "").strip()
    if not content:
        raise ParamError("题目内容不能为空")
    options = payload.get("options")
    if not isinstance(options, list) or len(options) < 2:
        raise ParamError("options 必须是至少 2 个选项的数组")
    if not all(isinstance(o, str) and o.strip() for o in options):
        raise ParamError("选项必须是非空字符串")
    answer = payload.get("answer")
    if not isinstance(answer, list) or not answer:
        raise ParamError("answer 必须是正确选项索引数组，如 [0] 或 [1,2]")
    if not all(isinstance(i, int) for i in answer):
        raise ParamError("answer 元素必须是整数索引")
    if any(i < 0 or i >= len(options) for i in answer):
        raise ParamError("answer 索引超出选项范围")
    if qtype in ("single", "judge") and len(answer) != 1:
        raise ParamError("single/judge 题目 answer 必须只有一个选项")
    return {
        "question_type": qtype,
        "content": content,
        "options": [str(o).strip() for o in options],
        "answer": sorted(set(answer)),
    }


# ---------------- 题库管理（管理端） ----------------

@router.post("/questions")
async def create_question(
    payload: dict,
    current_user: dict = Depends(require_roles(*EXAM_ADMIN_ROLES)),
    db: Session = Depends(get_db),
):
    data = _validate_question(payload)
    q = ExamQuestion(
        material_id=payload.get("material_id"),
        question_type=data["question_type"],
        content=data["content"],
        options=data["options"],
        answer=data["answer"],
        review_status="pending",
        created_by=current_user["id"],
    )
    db.add(q)
    db.commit()
    db.refresh(q)
    await write_audit_log(
        action="exam_question_create",
        user_id=current_user["id"],
        resource_type="exam_question",
        resource_id=str(q.id),
        request_id=get_request_id() or None,
    )
    return success(q.to_dict())


@router.get("/questions")
async def list_questions(
    page: int = 1,
    page_size: int = 20,
    review_status: Optional[str] = None,
    material_id: Optional[int] = None,
    keyword: Optional[str] = None,
    current_user: dict = Depends(require_roles(*EXAM_ADMIN_ROLES)),
    db: Session = Depends(get_db),
):
    if review_status and review_status not in VALID_REVIEW:
        raise ParamError("review_status 不合法")
    p = PaginationParams(page=page, page_size=page_size)
    query = db.query(ExamQuestion)
    if review_status:
        query = query.filter(ExamQuestion.review_status == review_status)
    if material_id:
        query = query.filter(ExamQuestion.material_id == material_id)
    if keyword:
        query = query.filter(ExamQuestion.content.ilike(f"%{keyword}%"))
    total = query.count()
    rows = query.order_by(ExamQuestion.id.desc()).offset(p.offset).limit(p.limit).all()
    return success(paginate([q.to_dict() for q in rows], total, p.page, p.page_size))


@router.put("/questions/{question_id}")
async def update_question(
    question_id: int,
    payload: dict,
    current_user: dict = Depends(require_roles(*EXAM_ADMIN_ROLES)),
    db: Session = Depends(get_db),
):
    q = db.query(ExamQuestion).filter(ExamQuestion.id == question_id).first()
    if not q:
        raise BusinessError("题目不存在", code=4001)
    if q.review_status == "approved":
        raise BusinessError("已审核通过的题目不可修改，请先驳回或重建", code=4001)
    data = _validate_question(payload)
    q.question_type = data["question_type"]
    q.content = data["content"]
    q.options = data["options"]
    q.answer = data["answer"]
    if "material_id" in payload:
        q.material_id = payload.get("material_id")
    db.commit()
    db.refresh(q)
    await write_audit_log(
        action="exam_question_update",
        user_id=current_user["id"],
        resource_type="exam_question",
        resource_id=str(q.id),
        request_id=get_request_id() or None,
    )
    return success(q.to_dict())


@router.post("/questions/{question_id}/review")
async def review_question(
    question_id: int,
    payload: dict,
    current_user: dict = Depends(require_roles(*EXAM_ADMIN_ROLES)),
    db: Session = Depends(get_db),
):
    q = db.query(ExamQuestion).filter(ExamQuestion.id == question_id).first()
    if not q:
        raise BusinessError("题目不存在", code=4001)
    if q.review_status != "pending":
        raise BusinessError("当前状态不可审核（仅待审核可审）", code=4001)
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
    q.review_status = "approved" if verdict == "approve" else "rejected"
    q.review_reason = reason if verdict == "reject" else None
    q.reviewed_by = current_user["id"]
    q.reviewed_at = __import__("datetime").datetime.utcnow()
    db.commit()
    db.refresh(q)
    await write_audit_log(
        action="exam_question_review",
        user_id=current_user["id"],
        resource_type="exam_question",
        resource_id=str(q.id),
        after_value={"review_status": q.review_status, "review_reason": q.review_reason},
        request_id=get_request_id() or None,
    )
    return success(q.to_dict())
```

- [ ] **Step 4: 注册 exams router**

Modify `services/auth-service/app/main.py`：追加：

```python
from app.api.exams import router as exams_router
app.include_router(exams_router)
```

- [ ] **Step 5: 运行测试确认通过**

Run: `cd services/auth-service && python -m pytest tests/test_exams.py -q`
Expected: 8 passed

- [ ] **Step 6: Commit**

```bash
git add services/auth-service/app/api/exams.py services/auth-service/app/main.py services/auth-service/tests/test_exams.py
git commit -m "feat(auth): 题库端点（CRUD + 医学部/合规部人工审核）"
```

---

### Task 4: AI 出题草稿端点（qwen 客户端）

**Files:**
- Create: `services/auth-service/app/services/qwen_client.py`
- Modify: `services/auth-service/app/api/exams.py`
- Modify: `services/auth-service/app/config.py`（DASHSCOPE_API_KEY / QWEN_EXAM_MODEL）
- Test: `services/auth-service/tests/test_exams.py`（追加 AI 出题用例）

**Interfaces:**
- Consumes: `_validate_question`（Task 3）、qwen_client
- Produces: `services/auth-service/app/services/qwen_client.py` 的 `QwenExamClient.generate_questions(material_text, count, question_type) -> list[dict]`；端点 `POST /api/v1/exams/questions/ai-generate`，body `{material_id, count?, question_type?}`，返回草稿数组（**不落库**）。

- [ ] **Step 1: 写失败测试**

Append to `services/auth-service/tests/test_exams.py`：

```python
def test_ai_generate_returns_drafts(fresh_state, monkeypatch):
    from app.services import qwen_client as qc

    fake = {
        "questions": [
            {"question_type": "single", "content": "AI 生成的题目？",
             "options": ["A", "B", "C", "D"], "answer": [2]},
        ]
    }
    monkeypatch.setattr(qc.QwenExamClient, "generate_questions", lambda self, *a, **k: fake)

    db = TestSession()
    db.add(TrainingMaterial(id=1, title="办法", material_type="regulation", content="正文", status="active"))
    db.commit()
    db.close()

    resp = client.post("/api/v1/exams/questions/ai-generate",
                       json={"material_id": 1, "count": 1, "question_type": "single"},
                       headers=_token(3, "medical"))
    body = resp.json()
    assert body["code"] == 0
    assert isinstance(body["data"], list)
    assert body["data"][0]["content"] == "AI 生成的题目？"
    assert body["data"][0]["answer"] == [2]


def test_ai_generate_rejects_rep():
    resp = client.post("/api/v1/exams/questions/ai-generate",
                       json={"material_id": 1}, headers=_token(1, "rep"))
    assert resp.status_code == 403
    assert resp.json()["code"] == 3000
```

- [ ] **Step 2: 运行测试确认失败**

Run: `cd services/auth-service && python -m pytest tests/test_exams.py -q`
Expected: 新增 2 用例失败（模块不存在）

- [ ] **Step 3: 实现 qwen 客户端**

Create `services/auth-service/app/services/qwen_client.py`：

```python
"""通义千问客户端（OpenAI 兼容接口，httpx 直调 dashscope，不引 openai SDK）

用于题库 AI 出题草稿（需求 3.4(2)：AI 出题仅作辅助，人工复核后入库）。
"""
import json
import logging
import os
from typing import List, Optional

import httpx

logger = logging.getLogger(__name__)


class QwenExamClient:
    """题库 AI 出题客户端（生成题目草稿，不落库）"""

    def __init__(self, api_key: Optional[str] = None, model: Optional[str] = None):
        self.api_key = api_key or os.getenv("DASHSCOPE_API_KEY", "")
        self.model = model or os.getenv("QWEN_EXAM_MODEL", "qwen-turbo")
        self.base_url = "https://dashscope.aliyuncs.com/compatible-mode/v1"

    def generate_questions(
        self,
        material_text: str,
        count: int = 5,
        question_type: str = "single",
    ) -> dict:
        """根据培训材料生成题目草稿。

        Returns:
            {"questions": [{"question_type", "content", "options", "answer"}, ...]}
        """
        if not self.api_key:
            raise ValueError("未配置 DASHSCOPE_API_KEY")
        ttype = "单选" if question_type == "single" else "判断" if question_type == "judge" else "多选"
        system = (
            "你是医药行业合规培训题库出题助手。只输出 JSON，不要输出任何其他文字。"
            "基于提供的培训材料生成题目，答案必须严格来自材料内容。"
        )
        user = (
            f"请根据以下培训材料生成 {count} 道{ttype}题。\n"
            f"题目类型：{question_type}（single 单选答案只有一个索引；multiple 多选答案多个索引；judge 判断题 options 固定为 [\"正确\",\"错误\"]）。\n"
            "输出格式（严格 JSON）：\n"
            '{"questions": [{"question_type": "single", "content": "题干", '
            '"options": ["选项A", "选项B", "选项C", "选项D"], "answer": [0]}]}\n'
            "answer 是正确选项在 options 中的索引（0 起）数组。判断题 options 用 [\"正确\",\"错误\"]，answer [0] 或 [1]。\n"
            f"培训材料如下：\n<user_content>{material_text[:4000]}</user_content>"
        )
        payload = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            "temperature": 0.3,
        }
        resp = httpx.post(
            f"{self.base_url}/chat/completions",
            headers={"Authorization": f"Bearer {self.api_key}"},
            json=payload,
            timeout=30.0,
        )
        resp.raise_for_status()
        text = resp.json()["choices"][0]["message"]["content"]
        return self._parse_json(text)

    def _parse_json(self, text: str) -> dict:
        """从 LLM 输出里提取 JSON（容忍 ```json 代码块包裹）"""
        cleaned = text.strip()
        if cleaned.startswith("```"):
            cleaned = cleaned.split("\n", 1)[-1]
            if cleaned.endswith("```"):
                cleaned = cleaned[:-3]
        start = cleaned.find("{")
        end = cleaned.rfind("}")
        if start == -1 or end == -1:
            raise ValueError("AI 输出未包含 JSON 对象")
        return json.loads(cleaned[start:end + 1])
```

- [ ] **Step 4: 实现 ai-generate 端点**

Append to `services/auth-service/app/api/exams.py`（在 review_question 之后）：

```python
from app.services.qwen_client import QwenExamClient


@router.post("/questions/ai-generate")
async def ai_generate_questions(
    payload: dict,
    current_user: dict = Depends(require_roles(*EXAM_ADMIN_ROLES)),
    db: Session = Depends(get_db),
):
    """AI 出题草稿（不落库）。管理端预览确认后走正常入库 + 人工审核。"""
    if not isinstance(payload, dict):
        raise ParamError("请求体必须是 JSON 对象")
    material_id = payload.get("material_id")
    mat = db.query(TrainingMaterial).filter(TrainingMaterial.id == material_id).first() if material_id else None
    if not mat or mat.status != "active":
        raise BusinessError("培训材料不存在", code=4001)
    count = payload.get("count") or 5
    if not isinstance(count, int) or not (1 <= count <= 20):
        raise ParamError("count 必须是 1-20 的整数")
    qtype = payload.get("question_type") or "single"
    if qtype not in VALID_TYPES:
        raise ParamError("question_type 不合法")
    try:
        result = await asyncio.to_thread(
            QwenExamClient().generate_questions, mat.content, count, qtype
        )
    except Exception as exc:  # 出题失败不阻塞人工录入
        logger.warning(f"AI 出题失败: {exc}")
        raise BusinessError(f"AI 出题失败：{exc}", code=6001)
    questions = result.get("questions", []) if isinstance(result, dict) else []
    drafts = []
    for raw in questions:
        if not isinstance(raw, dict):
            continue
        try:
            drafts.append(_validate_question(raw))
        except ParamError:
            continue  # 单条草稿不合规跳过，不整体失败
    return success(drafts)
```

> 需要在该文件顶部补 `import asyncio` 和 `from shared.models.training_exam import TrainingMaterial`（若未引入）。

- [ ] **Step 5: 运行测试确认通过**

Run: `cd services/auth-service && python -m pytest tests/test_exams.py -q`
Expected: 10 passed

- [ ] **Step 6: Commit**

```bash
git add services/auth-service/app/services/qwen_client.py services/auth-service/app/api/exams.py services/auth-service/tests/test_exams.py
git commit -m "feat(auth): AI 出题草稿端点（qwen 辅助，人工复核入库）"
```

---

### Task 5: 考试端点（抽题 / 判分 / 记录回写）

**Files:**
- Modify: `services/auth-service/app/api/exams.py`
- Modify: `services/auth-service/app/config.py`（EXAM_PASS_SCORE）
- Modify: `services/auth-service/app/api/qualifications.py`（回写 helper 供本任务复用或本任务直接写）
- Test: `services/auth-service/tests/test_exams.py`（追加考试用例）

**Interfaces:**
- Consumes: `ExamQuestion`、`ExamRecord`、`PaginationParams`
- Produces: `POST /exams/start`（body `{question_count?}` → 抽 approved 题，不含 answer）、`POST /exams/submit`（body `{answers:[{question_id, selected:[...]}]}` → 判分 + 写 exam_records + 回写 representative_qualifications）、`GET /exams/records/me`、`GET /exams/records`。

- [ ] **Step 1: 写失败测试**

Append to `services/auth-service/tests/test_exams.py`：

```python
def _add_qualification(db, representative_id: int):
    from shared.models.qualification import RepresentativeQualification
    db.add(RepresentativeQualification(
        representative_id=representative_id, education_cert="https://oss/edu.pdf",
        audit_status="approved", filing_number="F-1",
    ))
    db.commit()


def test_start_returns_approved_questions_no_answer():
    _add_q(id=1, question_type="single", content="q1", options=["A", "B"], answer=[1], review_status="approved")
    _add_q(id=2, question_type="single", content="q2", options=["A", "B"], answer=[0], review_status="pending")
    resp = client.post("/api/v1/exams/start", json={"question_count": 10}, headers=_token(1, "rep"))
    body = resp.json()
    assert body["code"] == 0
    items = body["data"]["questions"]
    assert len(items) == 1  # 只抽 approved
    assert items[0]["content"] == "q1"
    assert "answer" not in items[0]


def test_start_requires_rep():
    resp = client.post("/api/v1/exams/start", json={}, headers=_token(2, "admin"))
    assert resp.status_code == 403


def test_submit_scores_and_writes_record(fresh_state):
    db = TestSession()
    _add_q_in_db(db, id=1, question_type="single", content="q1", options=["A", "B"], answer=[1], review_status="approved")
    _add_q_in_db(db, id=2, question_type="multiple", content="q2", options=["A", "B", "C"], answer=[0, 2], review_status="approved")
    _add_qualification(db, 1)
    db.close()

    resp = client.post("/api/v1/exams/submit", json={"answers": [
        {"question_id": 1, "selected": [1]},
        {"question_id": 2, "selected": [0, 2]},
    ]}, headers=_token(1, "rep"))
    body = resp.json()
    assert body["code"] == 0
    data = body["data"]
    assert data["question_count"] == 2
    assert data["correct_count"] == 2
    assert data["score"] == 100
    assert data["passed"] is True
    audit_mock = fresh_state
    audit_mock.assert_awaited_once()

    # 回写 representative_qualifications
    from shared.models.qualification import RepresentativeQualification
    db = TestSession()
    qual = db.query(RepresentativeQualification).filter_by(representative_id=1).first()
    assert qual.compliance_exam_score == 100
    assert qual.compliance_training_completed is True
    db.close()


def test_submit_partial_score():
    db = TestSession()
    _add_q_in_db(db, id=1, question_type="single", content="q1", options=["A", "B"], answer=[1], review_status="approved")
    _add_q_in_db(db, id=2, question_type="single", content="q2", options=["A", "B"], answer=[0], review_status="approved")
    _add_qualification(db, 1)
    db.close()

    resp = client.post("/api/v1/exams/submit", json={"answers": [
        {"question_id": 1, "selected": [1]},
        {"question_id": 2, "selected": [1]},  # 错
    ]}, headers=_token(1, "rep"))
    body = resp.json()
    data = body["data"]
    assert data["score"] == 50
    assert data["passed"] is False


def _add_q_in_db(db, **kw):
    defaults = dict(id=1, material_id=None, question_type="single", content="q",
                    options=["A", "B"], answer=[1], review_status="approved")
    defaults.update(kw)
    db.add(ExamQuestion(**defaults))
    db.commit()


def test_submit_unknown_question_rejected():
    resp = client.post("/api/v1/exams/submit", json={"answers": [
        {"question_id": 999, "selected": [0]},
    ]}, headers=_token(1, "rep"))
    assert resp.status_code == 422
    assert resp.json()["code"] == 4001


def test_records_me_and_admin_list():
    db = TestSession()
    db.add(ExamRecord(id=1, representative_id=1, question_count=2, correct_count=2, score=100, passed=True))
    db.add(ExamRecord(id=2, representative_id=1, question_count=2, correct_count=1, score=50, passed=False))
    db.commit()
    db.close()

    me = client.get("/api/v1/exams/records/me", headers=_token(1, "rep"))
    assert me.json()["data"]["total"] == 2
    all_ = client.get("/api/v1/exams/records", headers=_token(2, "admin"))
    assert all_.json()["data"]["total"] == 2
```

> 注意：`_add_q_in_db` 与顶部 `_add_q` 功能重复，二选一即可（测试内自洽）。

- [ ] **Step 2: 运行测试确认失败**

Run: `cd services/auth-service && python -m pytest tests/test_exams.py -q`
Expected: 新增考试用例失败（端点不存在）

- [ ] **Step 3: 实现考试端点**

Append to `services/auth-service/app/api/exams.py`：

```python
import os
import random
from datetime import datetime

from shared.models.qualification import RepresentativeQualification

_PASS_SCORE = int(os.getenv("EXAM_PASS_SCORE", "80"))


def _score_match(selected: list, answer: list) -> bool:
    """判分：按集合相等（排序后比较），多选必须全对。"""
    if not isinstance(selected, list):
        return False
    try:
        return sorted(int(i) for i in selected) == sorted(int(a) for a in answer)
    except (TypeError, ValueError):
        return False


@router.post("/start")
async def start_exam(
    payload: dict,
    current_user: dict = Depends(require_roles("rep")),
    db: Session = Depends(get_db),
):
    """开始考试：从 approved 题目随机抽题（默认 10 道，最多 30），不含答案。"""
    if not isinstance(payload, dict):
        raise ParamError("请求体必须是 JSON 对象")
    question_count = payload.get("question_count") or 10
    if not isinstance(question_count, int) or not (1 <= question_count <= 30):
        raise ParamError("question_count 必须是 1-30 的整数")
    pool = db.query(ExamQuestion).filter(ExamQuestion.review_status == "approved").all()
    if not pool:
        raise BusinessError("暂无可考试的题目，请联系医学部/合规部上架题目", code=4001)
    questions = random.sample(pool, min(question_count, len(pool)))
    return success({"questions": [q.to_dict() for q in questions]})


@router.post("/submit")
async def submit_exam(
    payload: dict,
    current_user: dict = Depends(require_roles("rep")),
    db: Session = Depends(get_db),
):
    """提交考试：判分 + 写 exam_records + 回写 representative_qualifications 三字段。"""
    if not isinstance(payload, dict):
        raise ParamError("请求体必须是 JSON 对象")
    answers = payload.get("answers")
    if not isinstance(answers, list) or not answers:
        raise ParamError("answers 必须是题目作答数组")
    q_ids = [a.get("question_id") for a in answers if isinstance(a, dict)]
    if not q_ids:
        raise ParamError("answers 缺少 question_id")
    rows = db.query(ExamQuestion).filter(ExamQuestion.id.in_(q_ids)).all()
    by_id = {q.id: q for q in rows}
    if len(rows) != len(set(q_ids)):
        raise BusinessError("存在不存在的题目", code=4001)
    if any(q.review_status != "approved" for q in rows):
        raise BusinessError("存在未上架的题目，请重新开始考试", code=4001)

    correct = 0
    for a in answers:
        q = by_id.get(a.get("question_id"))
        if q is None:
            raise BusinessError("存在不存在的题目", code=4001)
        if _score_match(a.get("selected"), q.answer):
            correct += 1
    total = len(answers)
    score = round(correct * 100 / total)
    passed = score >= _PASS_SCORE

    record = ExamRecord(
        representative_id=current_user["id"],
        question_count=total,
        correct_count=correct,
        score=score,
        passed=passed,
    )
    db.add(record)
    # 回写代表资质表
    qual = db.query(RepresentativeQualification).filter(
        RepresentativeQualification.representative_id == current_user["id"]
    ).first()
    if qual:
        if qual.compliance_exam_score is None or score > qual.compliance_exam_score:
            qual.compliance_exam_score = score
        if passed:
            qual.compliance_training_completed = True
    db.commit()
    db.refresh(record)
    await write_audit_log(
        action="exam_submit",
        user_id=current_user["id"],
        resource_type="exam_record",
        resource_id=str(record.id),
        after_value={"score": score, "passed": passed, "question_count": total},
        request_id=get_request_id() or None,
    )
    return success(record.to_dict())


@router.get("/records/me")
async def my_exam_records(
    page: int = 1,
    page_size: int = 20,
    current_user: dict = Depends(require_roles("rep")),
    db: Session = Depends(get_db),
):
    p = PaginationParams(page=page, page_size=page_size)
    query = db.query(ExamRecord).filter(ExamRecord.representative_id == current_user["id"])
    total = query.count()
    rows = query.order_by(ExamRecord.id.desc()).offset(p.offset).limit(p.limit).all()
    return success(paginate([r.to_dict() for r in rows], total, p.page, p.page_size))


@router.get("/records")
async def list_exam_records(
    page: int = 1,
    page_size: int = 20,
    current_user: dict = Depends(require_roles(*EXAM_ADMIN_ROLES)),
    db: Session = Depends(get_db),
):
    p = PaginationParams(page=page, page_size=page_size)
    query = db.query(ExamRecord)
    total = query.count()
    rows = query.order_by(ExamRecord.id.desc()).offset(p.offset).limit(p.limit).all()
    return success(paginate([r.to_dict() for r in rows], total, p.page, p.page_size))
```

> 注意：`require_roles("rep")` 限制仅代表可考试。若需要医生等也可，按需求仅代表有培训考试。其余登录角色考试会 403——符合需求（培训前置针对代表）。

- [ ] **Step 4: 运行测试确认通过**

Run: `cd services/auth-service && python -m pytest tests/test_exams.py -q`
Expected: 全部通过

- [ ] **Step 5: 顺带补 test_training_materials 回归**

Run: `cd services/auth-service && python -m pytest tests/ -q`
Expected: 原 104 基线 + 新增全部通过；若有受 JSONB 影响的旧用例，在相应测试文件加 `@compiles(JSONB, "sqlite")` → `TEXT`。

- [ ] **Step 6: Commit**

```bash
git add services/auth-service/app/api/exams.py services/auth-service/tests/test_exams.py
git commit -m "feat(auth): 考试端点（抽题/判分/记录回写资质三字段）"
```

---

### Task 6: 承诺书签署端点（短信验证码 + 审计）

**Files:**
- Create: `services/auth-service/app/api/commitment.py`
- Modify: `services/auth-service/app/main.py`
- Test: `services/auth-service/tests/test_commitment.py`

**Interfaces:**
- Consumes: `code_store`（`get_code_store`）、`get_sender`、`write_audit_log`、`RepresentativeQualification`
- Produces: `POST /api/v1/qualifications/commitment/send-code`（body `{}` → 向当前 rep 手机发验证码，复用 auth send-code 存储）、`POST /api/v1/qualifications/commitment/sign`（body `{code}` → consume 校验 → commitment_signed=true + 审计）。`commitment_router` 导出。

> 说明：承诺书签名验证码复用 auth 的 code_store（同 Redis 键空间）。发送动作复用 `get_sender`；校验用 `store.consume(phone, code, CODE_MAX_ATTEMPTS)`。

- [ ] **Step 1: 写失败测试**

Create `services/auth-service/tests/test_commitment.py`：

```python
"""承诺书签署端点测试：发送验证码 + 校验签署 + 审计留痕 + 仅 rep"""
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
from sqlalchemy.ext.compiler import compiles
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from shared.common.auth import create_token
from shared.common.db_session import get_db
from shared.models.base import Base
from shared.models.qualification import RepresentativeQualification
from shared.models.user import User

import app.api.commitment as commit_api
from app.main import app


@compiles(BigInteger, "sqlite")
def _compile_bigint_for_sqlite(type_, compiler, **kw):
    return "INTEGER"


engine = create_engine(
    "sqlite://",
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)
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


class _FakeStore:
    """内存版 code store（等价 consume 语义）"""

    def __init__(self):
        self.codes = {}
        self.attempts = {}

    def save(self, phone, code, ttl, cooldown):
        self.codes[phone] = code
        return True

    def in_cooldown(self, phone):
        return 0

    def consume(self, phone, code, max_attempts):
        saved = self.codes.get(phone)
        if saved is None:
            return "notfound"
        if saved == code:
            del self.codes[phone]
            return "matched"
        return "mismatch"

    def drop(self, phone):
        self.codes.pop(phone, None)


class _FakeSender:
    def send_code(self, phone, code):
        return None


@pytest.fixture(autouse=True)
def fresh_state(monkeypatch):
    tables = [User.__table__, RepresentativeQualification.__table__]
    Base.metadata.drop_all(engine, tables=tables)
    Base.metadata.create_all(engine, tables=tables)
    db = TestSession()
    db.add_all([
        User(id=1, username="rep01", full_name="张代表", phone="13800000001", role="rep", status="active"),
        User(id=2, username="admin", full_name="管理员", phone="13800000000", role="admin", status="active"),
    ])
    db.commit()
    db.add(RepresentativeQualification(
        representative_id=1, education_cert="https://oss/edu.pdf",
        audit_status="approved", filing_number="F-1", commitment_signed=False,
    ))
    db.commit()
    db.close()

    monkeypatch.setitem(app.dependency_overrides, get_db, _override_db)
    store = _FakeStore()
    monkeypatch.setattr(commit_api, "get_code_store", lambda: store)
    monkeypatch.setattr(commit_api, "get_sender", lambda: _FakeSender())
    audit_mock = AsyncMock(return_value=None)
    monkeypatch.setattr(commit_api, "write_audit_log", audit_mock)
    yield store, audit_mock


def test_send_code_returns_expire_seconds(fresh_state):
    resp = client.post("/api/v1/qualifications/commitment/send-code", json={},
                       headers=_token(1, "rep"))
    body = resp.json()
    assert body["code"] == 0
    assert body["data"]["expire_seconds"] == 300
    store, _ = fresh_state
    assert "13800000001" in store.codes


def test_sign_success(fresh_state):
    store, audit_mock = fresh_state
    store.save("13800000001", "123456", 300, 60)
    resp = client.post("/api/v1/qualifications/commitment/sign", json={"code": "123456"},
                       headers=_token(1, "rep"))
    body = resp.json()
    assert body["code"] == 0
    assert body["data"]["commitment_signed"] is True
    audit_mock.assert_awaited_once()


def test_sign_wrong_code(fresh_state):
    store, _ = fresh_state
    store.save("13800000001", "123456", 300, 60)
    resp = client.post("/api/v1/qualifications/commitment/sign", json={"code": "000000"},
                       headers=_token(1, "rep"))
    assert resp.status_code == 400
    assert resp.json()["code"] == 1000
    assert "验证码" in resp.json()["message"]


def test_sign_requires_rep():
    resp = client.post("/api/v1/qualifications/commitment/sign", json={"code": "123456"},
                       headers=_token(2, "admin"))
    assert resp.status_code == 403
```

- [ ] **Step 2: 运行测试确认失败**

Run: `cd services/auth-service && python -m pytest tests/test_commitment.py -q`
Expected: 失败（模块不存在）

- [ ] **Step 3: 实现承诺书端点**

Create `services/auth-service/app/api/commitment.py`：

```python
"""年度合规承诺书签署（需求 3.4(4)）：勾选 + 短信验证码 + 审计留痕。
一期为平台内电子确认（不接第三方 CA）；培训前置先上线不强制。"""
import logging
from typing import Optional

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from shared.common.auth import get_current_user, require_roles
from shared.common.context import get_request_id
from shared.common.db_session import get_db
from shared.common.response import ParamError, PermissionError, success
from shared.models.qualification import RepresentativeQualification
from shared.models.user import User

from app.api.auth import get_code_store, get_sender, _client_ip
from app.config import settings
from app.services.audit_client import write_audit_log

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/qualifications/commitment", tags=["commitment"])


@router.post("/send-code")
async def send_commitment_code(
    request: Request,
    current_user: dict = Depends(require_roles("rep")),
    db: Session = Depends(get_db),
    store: CodeStore = Depends(get_code_store),
    sender=Depends(get_sender),
):
    """向当前代表手机发送承诺书签署验证码（复用 auth 验证码存储）"""
    from app.core.code_store import CodeStoreError
    from app.services.sms import SmsSendError
    phone = current_user.get("phone") or ""
    try:
        remaining = store.in_cooldown(phone)
        if remaining > 0:
            raise ParamError(f"请 {remaining} 秒后再试")
        code = __import__("secrets").choice("0123456789")
        code = "".join(__import__("random").choice("0123456789") for _ in range(settings.CODE_LENGTH))
        saved = store.save(phone, code, settings.CODE_TTL_SECONDS, settings.CODE_RESEND_SECONDS)
        if not saved:
            raise ParamError("验证码已发送，请稍后再试")
        await asyncio.to_thread(sender.send_code, phone, code)
    except CodeStoreError as exc:
        logger.error(f"承诺书验证码存储不可用: {exc}")
        from shared.common.response import BusinessError
        raise BusinessError("验证码服务暂时不可用，请稍后重试", code=5004)
    except SmsSendError as exc:
        from shared.common.response import BusinessError
        raise BusinessError(f"短信发送失败: {exc}", code=6001)
    await write_audit_log(
        action="commitment_send_code",
        user_id=current_user["id"],
        resource_type="commitment",
        resource_id=phone,
        client_ip=_client_ip(request),
        request_id=get_request_id() or None,
    )
    return success({"expire_seconds": settings.CODE_TTL_SECONDS})


@router.post("/sign")
async def sign_commitment(
    payload: dict,
    request: Request,
    current_user: dict = Depends(require_roles("rep")),
    db: Session = Depends(get_db),
    store: CodeStore = Depends(get_code_store),
):
    """签署承诺书：校验短信验证码 → commitment_signed=true + 审计"""
    from app.core.code_store import CodeStoreError
    if not isinstance(payload, dict):
        raise ParamError("请求体必须是 JSON 对象")
    code = str(payload.get("code") or "").strip()
    if not code:
        raise ParamError("请输入短信验证码")
    phone = current_user.get("phone") or ""
    try:
        result = store.consume(phone, code, settings.CODE_MAX_ATTEMPTS)
    except CodeStoreError as exc:
        logger.error(f"承诺书验证码校验存储不可用: {exc}")
        from shared.common.response import BusinessError
        raise BusinessError("验证码服务暂时不可用，请稍后重试", code=5004)
    if result != "matched":
        raise ParamError("验证码错误或已过期")

    qual = db.query(RepresentativeQualification).filter(
        RepresentativeQualification.representative_id == current_user["id"]
    ).first()
    if qual:
        qual.commitment_signed = True
    else:
        raise ParamError("请先提交备案与资质材料")
    db.commit()
    db.refresh(qual)

    await write_audit_log(
        action="commitment_signed",
        user_id=current_user["id"],
        resource_type="commitment",
        resource_id=str(qual.id),
        after_value={"commitment_signed": True, "signed_at": datetime.utcnow().isoformat()},
        client_ip=_client_ip(request),
        request_id=get_request_id() or None,
    )
    return success({"commitment_signed": True})
```

> 需要文件顶部补 imports：`import asyncio`、`import secrets`、`import random`、`from datetime import datetime`、`from fastapi import Request`、`from app.core.code_store import CodeStore`。为避免循环导入（commitment 从 auth 导入 get_code_store），确认 `app.api.auth` 不反向导入 commitment——不存在反向引用，安全。

- [ ] **Step 4: 注册 router**

Modify `services/auth-service/app/main.py`：追加：

```python
from app.api.commitment import router as commitment_router
app.include_router(commitment_router)
```

- [ ] **Step 5: 运行测试确认通过**

Run: `cd services/auth-service && python -m pytest tests/test_commitment.py -q`
Expected: 4 passed

- [ ] **Step 6: Commit**

```bash
git add services/auth-service/app/api/commitment.py services/auth-service/app/main.py services/auth-service/tests/test_commitment.py
git commit -m "feat(auth): 年度合规承诺书签署（短信验证码+审计留痕）"
```

---

### Task 7: 网关 ROUTE_MAP 接线

**Files:**
- Modify: `services/gateway/app/main.py`

**Interfaces:**
- Consumes: 无（只加路由）
- Produces: 网关转发 `/api/v1/training-materials`、`/api/v1/exams` → AUTH_SERVICE_URL。

- [ ] **Step 1: 修改 ROUTE_MAP**

Modify `services/gateway/app/main.py` 的 ROUTE_MAP（在 `/api/v1/qualifications` 行附近追加两行）：

```python
    "/api/v1/training-materials": settings.AUTH_SERVICE_URL,  # 培训材料（二期 F）
    "/api/v1/exams": settings.AUTH_SERVICE_URL,  # 题库与考试（二期 F）
```

- [ ] **Step 2: 验证网关测试**

Run: `cd services/gateway && python -m pytest -q`
Expected: 原 74 基线通过（ROUTE_MAP 改动不影响既有断言）

- [ ] **Step 3: Commit**

```bash
git add services/gateway/app/main.py
git commit -m "feat(gateway): 培训材料与考试路由转发（二期 F）"
```

---

### Task 8: web 合规培训页（材料/题库/考试记录）

**Files:**
- Create: `web/src/pages/Training/TrainingList.tsx`
- Create: `web/src/services/training.ts`
- Modify: `web/src/types/index.ts`
- Modify: `web/src/App.tsx`
- Modify: `web/src/constants/menu.tsx`

**Interfaces:**
- Consumes: 后端端点 `/api/v1/training-materials*`、`/api/v1/exams*`
- Produces: 页面 `/training/list`（三 Tab：培训材料 / 题库审核 / 考试记录）

- [ ] **Step 1: 加类型**

Modify `web/src/types/index.ts`（参照现有类型风格追加）：

```ts
export interface TrainingMaterial {
  id: number;
  title: string;
  material_type: 'regulation' | 'rdpac' | 'internal';
  content: string;
  version: string;
  status: string;
  created_at: string | null;
  updated_at: string | null;
}

export interface ExamQuestion {
  id: number;
  material_id: number | null;
  question_type: 'single' | 'multiple' | 'judge';
  content: string;
  options: string[];
  answer?: number[];
  review_status: 'pending' | 'approved' | 'rejected';
  review_reason: string | null;
  created_at: string | null;
}

export interface ExamRecord {
  id: number;
  representative_id: number;
  question_count: number;
  correct_count: number;
  score: number;
  passed: boolean;
  submitted_at: string | null;
}
```

- [ ] **Step 2: 加 service**

Create `web/src/services/training.ts`：

```ts
import client from './client';
import type { ApiResponse, PaginatedResponse, ExamQuestion, ExamRecord, TrainingMaterial } from '../types';

export const trainingAPI = {
  listMaterials: (params?: { page?: number; page_size?: number; material_type?: string; keyword?: string }) =>
    client.get<PaginatedResponse<TrainingMaterial>>('/training-materials', { params }),
  createMaterial: (data: { title: string; material_type: string; content: string }) =>
    client.post<ApiResponse<TrainingMaterial>>('/training-materials', data),
  updateMaterial: (id: number, data: { title: string; material_type: string; content: string }) =>
    client.put<ApiResponse<TrainingMaterial>>(`/training-materials/${id}`, data),
  archiveMaterial: (id: number) => client.delete<ApiResponse<TrainingMaterial>>(`/training-materials/${id}`),

  listQuestions: (params?: { page?: number; page_size?: number; review_status?: string; keyword?: string }) =>
    client.get<PaginatedResponse<ExamQuestion>>('/exams/questions', { params }),
  createQuestion: (data: { question_type: string; content: string; options: string[]; answer: number[]; material_id?: number | null }) =>
    client.post<ApiResponse<ExamQuestion>>('/exams/questions', data),
  reviewQuestion: (id: number, data: { verdict: 'approve' | 'reject'; reason?: string }) =>
    client.post<ApiResponse<ExamQuestion>>(`/exams/questions/${id}/review`, data),
  aiGenerate: (data: { material_id: number; count?: number; question_type?: string }) =>
    client.post<ApiResponse<any[]>>('/exams/questions/ai-generate', data),

  listRecords: (params?: { page?: number; page_size?: number }) =>
    client.get<PaginatedResponse<ExamRecord>>('/exams/records', { params }),
};
```

- [ ] **Step 3: 写页面**

Create `web/src/pages/Training/TrainingList.tsx`（三 Tab，模式参照 FilingList/DoctorCertList）：

```tsx
import { useState } from 'react';
import { App, Button, Form, Input, Modal, Radio, Select, Tabs, Tag } from 'antd';
import { ProTable } from '@ant-design/pro-components';
import type { ProColumns } from '@ant-design/pro-components';
import { trainingAPI } from '../../services/training';
import type { ExamQuestion, ExamRecord, TrainingMaterial } from '../../types';

const MATERIAL_MAP: Record<string, string> = { regulation: '办法', rdpac: 'RDPAC', internal: '内部政策' };
const STATUS_MAP: Record<string, { color: string; text: string }> = {
  pending: { color: 'orange', text: '待审核' },
  approved: { color: 'green', text: '已通过' },
  rejected: { color: 'red', text: '已驳回' },
};
const TYPE_MAP: Record<string, string> = { single: '单选', multiple: '多选', judge: '判断' };

export default function TrainingList() {
  const { message } = App.useApp();
  const [materialModal, setMaterialModal] = useState(false);
  const [questionModal, setQuestionModal] = useState(false);
  const [editing, setEditing] = useState<TrainingMaterial | null>(null);
  const [aiQuestions, setAiQuestions] = useState<any[]>([]);
  const [materialForm] = Form.useForm();
  const [questionForm] = Form.useForm();

  const materialColumns: ProColumns<TrainingMaterial>[] = [
    { title: '标题', dataIndex: 'title', hideInSearch: true },
    { title: '类型', dataIndex: 'material_type', width: 90,
      valueEnum: MATERIAL_MAP,
      render: (_, r) => MATERIAL_MAP[r.material_type] || r.material_type },
    { title: '版本', dataIndex: 'version', width: 80, hideInSearch: true },
    {
      title: '操作', width: 160, hideInSearch: true,
      render: (_, r) => (
        <>
          <a onClick={() => { setEditing(r); materialForm.setFieldsValue(r); setMaterialModal(true); }}>编辑</a>
          <a style={{ marginLeft: 12 }} onClick={async () => {
            await trainingAPI.archiveMaterial(r.id);
            message.success('已归档');
            setTabRefresh(t => t + 1);
          }}>归档</a>
        </>
      ),
    },
  ];

  const questionColumns: ProColumns<ExamQuestion>[] = [
    { title: '题干', dataIndex: 'content', ellipsis: true, hideInSearch: true },
    { title: '类型', dataIndex: 'question_type', width: 80, valueEnum: TYPE_MAP,
      render: (_, r) => TYPE_MAP[r.question_type] || r.question_type },
    { title: '审核状态', dataIndex: 'review_status', width: 100,
      valueEnum: { pending: '待审核', approved: '已通过', rejected: '已驳回' },
      render: (_, r) => { const m = STATUS_MAP[r.review_status] || { color: 'default', text: r.review_status }; return <Tag color={m.color}>{m.text}</Tag>; } },
    { title: '审核', dataIndex: 'review_reason', width: 120, hideInSearch: true },
    {
      title: '操作', width: 160, hideInSearch: true,
      render: (_, r) => r.review_status === 'pending' ? (
        <>
          <a onClick={async () => { await trainingAPI.reviewQuestion(r.id, { verdict: 'approve' }); message.success('已通过'); setTabRefresh(t => t + 1); }}>通过</a>
          <a style={{ marginLeft: 12 }} onClick={() => { Modal.confirm({ title: '驳回', content: <Input.TextArea id="reject-reason" rows={3} placeholder="驳回原因（必填）" />, onOk: async () => { const el = document.getElementById('reject-reason') as HTMLTextAreaElement; await trainingAPI.reviewQuestion(r.id, { verdict: 'reject', reason: el?.value || '' }); message.success('已驳回'); setTabRefresh(t => t + 1); } }); }}>驳回</a>
        </>
      ) : <span style={{ color: '#999' }}>已处理</span>,
    },
  ];

  const recordColumns: ProColumns<ExamRecord>[] = [
    { title: '代表ID', dataIndex: 'representative_id', width: 90 },
    { title: '题数', dataIndex: 'question_count', width: 70 },
    { title: '答对', dataIndex: 'correct_count', width: 70 },
    { title: '分数', dataIndex: 'score', width: 70, render: (_, r) => `${r.score} 分` },
    { title: '通过', dataIndex: 'passed', width: 80, render: (_, r) => r.passed ? <Tag color="green">通过</Tag> : <Tag color="red">未过</Tag> },
    { title: '提交时间', dataIndex: 'submitted_at', hideInSearch: true },
  ];

  const [tabRefresh, setTabRefresh] = useState(0);

  return (
    <Tabs defaultActiveKey="materials" items={[
      {
        key: 'materials', label: '培训材料',
        children: (
          <>
            <ProTable<TrainingMaterial>
              headerTitle="培训材料"
              rowKey="id"
              search={{ labelWidth: 80 }}
              params={{ t: tabRefresh }}
              columns={materialColumns}
              request={async (params) => {
                const res = await trainingAPI.listMaterials({ page: params.current || 1, page_size: params.pageSize || 10, material_type: params.material_type, keyword: params.keyword });
                return { data: res.data.data.items, total: res.data.data.total, success: true };
              }}
              toolBarRender={() => [<Button type="primary" key="new" onClick={() => { setEditing(null); materialForm.resetFields(); setMaterialModal(true); }}>新增材料</Button>]}
            />
            <Modal title={editing ? '编辑材料' : '新增材料'} open={materialModal} onCancel={() => setMaterialModal(false)} onOk={() => materialForm.submit()} destroyOnHidden>
              <Form form={materialForm} layout="vertical" onFinish={async (values) => {
                if (editing) await trainingAPI.updateMaterial(editing.id, values);
                else await trainingAPI.createMaterial(values);
                message.success('已保存');
                setMaterialModal(false);
                setTabRefresh(t => t + 1);
              }}>
                <Form.Item name="title" label="标题" rules={[{ required: true, message: '必填' }]}><Input maxLength={200} /></Form.Item>
                <Form.Item name="material_type" label="类型" rules={[{ required: true, message: '必选' }]}>
                  <Select options={[{ value: 'regulation', label: '办法' }, { value: 'rdpac', label: 'RDPAC' }, { value: 'internal', label: '内部政策' }]} />
                </Form.Item>
                <Form.Item name="content" label="正文" rules={[{ required: true, message: '必填' }]}><Input.TextArea rows={12} /></Form.Item>
              </Form>
            </Modal>
          </>
        ),
      },
      {
        key: 'questions', label: '题库审核',
        children: (
          <>
            <ProTable<ExamQuestion>
              headerTitle="题库"
              rowKey="id"
              search={{ labelWidth: 80 }}
              params={{ t: tabRefresh }}
              columns={questionColumns}
              request={async (params) => {
                const res = await trainingAPI.listQuestions({ page: params.current || 1, page_size: params.pageSize || 10, review_status: params.review_status, keyword: params.keyword });
                return { data: res.data.data.items, total: res.data.data.total, success: true };
              }}
              toolBarRender={() => [<Button type="primary" key="ai" onClick={() => setQuestionModal(true)}>AI 出题</Button>]}
            />
            <Modal title="AI 出题" open={questionModal} onCancel={() => setQuestionModal(false)} footer={null} destroyOnHidden>
              <Form form={questionForm} layout="vertical" onFinish={async (values) => {
                const res = await trainingAPI.aiGenerate(values);
                setAiQuestions(res.data.data);
                message.success(`生成 ${res.data.data.length} 道草稿`);
              }}>
                <Form.Item name="material_id" label="培训材料" rules={[{ required: true, message: '必选' }]}>
                  <Select allowClear placeholder="选择材料" options={[]} />
                </Form.Item>
                <Form.Item name="question_type" label="题型" initialValue="single">
                  <Radio.Group options={[{ value: 'single', label: '单选' }, { value: 'multiple', label: '多选' }, { value: 'judge', label: '判断' }]} />
                </Form.Item>
                <Form.Item name="count" label="数量" initialValue={5}><Input type="number" min={1} max={20} /></Form.Item>
                <Button type="primary" htmlType="submit">生成草稿</Button>
              </Form>
              {aiQuestions.map((q, i) => (
                <div key={i} style={{ marginTop: 8, padding: 8, background: '#fafafa', borderRadius: 4 }}>
                  <div>{q.content}</div>
                  <div style={{ color: '#888', fontSize: 12 }}>选项：{q.options?.join(' / ')}　答案：{q.answer?.join(',')}</div>
                  <Button size="small" onClick={async () => {
                    await trainingAPI.createQuestion({ ...q, material_id: questionForm.getFieldValue('material_id') });
                    message.success('已入库待审核');
                  }}>入库待审核</Button>
                </div>
              ))}
            </Modal>
          </>
        ),
      },
      {
        key: 'records', label: '考试记录',
        children: (
          <ProTable<ExamRecord>
            headerTitle="考试记录"
            rowKey="id"
            search={false}
            columns={recordColumns}
            request={async (params) => {
              const res = await trainingAPI.listRecords({ page: params.current || 1, page_size: params.pageSize || 10 });
              return { data: res.data.data.items, total: res.data.data.total, success: true };
            }}
          />
        ),
      },
    ]} />
  );
}
```

> 注：题库审核 Tab 的 AI 出题 Modal 中材料 Select 未接 listMaterials 数据源——实现时在 useEffect 里拉材料列表填 options（参照 FilingList 既有写法）。若时间紧，AI 出题入口可先隐藏（题库人工录入 + 审核流程完整即可交付）。

- [ ] **Step 4: 注册路由与菜单**

Modify `web/src/App.tsx`：加 lazy import 与路由：

```tsx
const TrainingList = lazy(() => import('./pages/Training/TrainingList'));
// ...
<Route path="training/list" element={<TrainingList />} />
```

Modify `web/src/constants/menu.tsx`：加菜单项（`/training/list`，name '合规培训'，icon 自选如 `ReadOutlined`）：

```tsx
  { path: '/training/list', name: '合规培训', icon: <ReadOutlined /> },
```

- [ ] **Step 5: 验证 build**

Run: `cd web && npm run build`
Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add web/src/pages/Training web/src/services/training.ts web/src/types/index.ts web/src/App.tsx web/src/constants/menu.tsx
git commit -m "feat(web): 合规培训页（材料/题库审核/考试记录）"
```

---

### Task 9: mobile 代表端个人合规中心扩展（材料/考试/承诺书）

**Files:**
- Create: `mobile/src/api/exam.ts`
- Create: `mobile/src/screens/Compliance/TrainingMaterialScreen.tsx`
- Create: `mobile/src/screens/Compliance/ExamScreen.tsx`
- Create: `mobile/src/screens/Compliance/CommitmentScreen.tsx`
- Modify: `mobile/src/screens/Compliance/ComplianceCenterScreen.tsx`
- Modify: `mobile/src/navigation/types.ts`
- Modify: `mobile/src/navigation/AppNavigator.tsx`
- Test: `mobile/src/api/__tests__/exam-contract.test.ts`

**Interfaces:**
- Consumes: 后端 `/api/v1/training-materials*`、`/api/v1/exams*`、`/api/v1/qualifications/commitment*`
- Produces: 契约测试 `exam-contract.test.ts`；个人合规中心新增三个入口（培训学习 / 在线考试 / 承诺书）。

- [ ] **Step 1: 写契约测试**

Create `mobile/src/api/__tests__/exam-contract.test.ts`（参照 qualification-contract 模式）：

```ts
import { examAPI } from '../exam';

const okResponse = (data: any = {}) => ({
  json: async () => ({ code: 0, message: 'success', data }),
});

let fetchMock: jest.Mock;

beforeEach(() => {
  fetchMock = jest.fn().mockResolvedValue(okResponse());
  (global as any).fetch = fetchMock;
});

function lastCall() {
  const [url, init] = fetchMock.mock.calls[fetchMock.mock.calls.length - 1];
  return { url: url as string, init: init as { method: string; headers: Record<string, string>; body?: any } };
}

describe('examAPI', () => {
  it('listMaterials 发 GET /api/v1/training-materials', async () => {
    await examAPI.listMaterials();
    const { url, init } = lastCall();
    expect(url).toContain('/api/v1/training-materials');
    expect(init.method).toBe('GET');
  });

  it('startExam 发 POST /api/v1/exams/start 带 question_count', async () => {
    await examAPI.startExam(5);
    const { url, init } = lastCall();
    expect(url).toContain('/api/v1/exams/start');
    expect(init.method).toBe('POST');
    expect(JSON.parse(init.body)).toEqual({ question_count: 5 });
  });

  it('submitExam 发 POST /api/v1/exams/submit 带 answers', async () => {
    await examAPI.submitExam([{ question_id: 1, selected: [0] }]);
    const { url, init } = lastCall();
    expect(url).toContain('/api/v1/exams/submit');
    expect(JSON.parse(init.body).answers).toEqual([{ question_id: 1, selected: [0] }]);
  });

  it('signCommitment 发 POST /api/v1/qualifications/commitment/sign 带 code', async () => {
    await examAPI.signCommitment('123456');
    const { url, init } = lastCall();
    expect(url).toContain('/api/v1/qualifications/commitment/sign');
    expect(JSON.parse(init.body)).toEqual({ code: '123456' });
  });
});
```

- [ ] **Step 2: 实现 API 层**

Create `mobile/src/api/exam.ts`：

```ts
import { apiClient } from './client';
import type { ExamQuestion, ExamRecord, TrainingMaterial } from '../types';

export interface ExamAnswer { question_id: number; selected: number[]; }

export const examAPI = {
  listMaterials: (params?: { page?: number; page_size?: number }) =>
    apiClient.request<any>('GET', '/api/v1/training-materials', params),

  startExam: (question_count = 10) =>
    apiClient.request<{ questions: ExamQuestion[] }>('POST', '/api/v1/exams/start', { question_count }),

  submitExam: (answers: ExamAnswer[]) =>
    apiClient.request<ExamRecord>('POST', '/api/v1/exams/submit', { answers }),

  myRecords: () =>
    apiClient.request<any>('GET', '/api/v1/exams/records/me'),

  signCommitment: (code: string) =>
    apiClient.request<{ commitment_signed: boolean }>('POST', '/api/v1/qualifications/commitment/sign', { code }),

  sendCommitmentCode: () =>
    apiClient.request<{ expire_seconds: number }>('POST', '/api/v1/qualifications/commitment/send-code', {}),
};
```

> 注意：`apiClient.request` 的第三参数字面量是 query params 还是 body 需按 mobile apiClient 实际签名核对（参照 qualification.ts 的 GET 用法：`GET, url` 无 params；POST 用法参照其他 POST）。实现时以 `mobile/src/api/client.ts` 现有签名对齐。

- [ ] **Step 3: 实现三个屏幕**

Create `mobile/src/screens/Compliance/TrainingMaterialScreen.tsx`（材料列表 + 详情 Modal，模式参照 ComplianceCenterScreen 卡片）：

```tsx
import React, { useEffect, useState } from 'react';
import { Alert, Modal, ScrollView, StyleSheet, Text, TouchableOpacity, View } from 'react-native';
import { useNavigation } from '@react-navigation/native';
import { examAPI } from '../../api/exam';
import Icon from '../../components/Icon';
import { BorderRadius, Colors, FontSize, Shadow, Spacing } from '../../constants/theme';

const TYPE_TEXT: Record<string, string> = { regulation: '办法', rdpac: 'RDPAC', internal: '内部政策' };

export default function TrainingMaterialScreen() {
  const navigation = useNavigation();
  const [items, setItems] = useState<any[]>([]);
  const [detail, setDetail] = useState<any | null>(null);

  const load = async () => {
    try {
      const res = await examAPI.listMaterials({ page: 1, page_size: 50 });
      setItems(res?.data?.items || []);
    } catch { Alert.alert('加载失败', '无法获取培训材料'); }
  };

  useEffect(() => { load(); }, []);

  return (
    <View style={styles.container}>
      <View style={styles.header}>
        <TouchableOpacity onPress={() => navigation.goBack()}><Icon name="chevron-left" size={22} color={Colors.textWhite} /></TouchableOpacity>
        <Text style={styles.headerTitle}>培训材料</Text>
        <View style={{ width: 24 }} />
      </View>
      <ScrollView contentContainerStyle={styles.content}>
        {items.map(item => (
          <TouchableOpacity key={item.id} style={[styles.card, Shadow.card]} onPress={() => setDetail(item)}>
            <Text style={styles.cardTitle}>{item.title}</Text>
            <Text style={styles.desc}>{TYPE_TEXT[item.material_type] || item.material_type} · 版本 {item.version}</Text>
          </TouchableOpacity>
        ))}
        {!items.length && <Text style={styles.empty}>暂无培训材料</Text>}
      </ScrollView>
      <Modal visible={!!detail} transparent animationType="slide" onRequestClose={() => setDetail(null)}>
        <View style={styles.modalWrap}>
          <View style={styles.modalBody}>
            <ScrollView>
              <Text style={styles.modalTitle}>{detail?.title}</Text>
              <Text style={styles.modalContent}>{detail?.content}</Text>
            </ScrollView>
            <TouchableOpacity style={styles.closeBtn} onPress={() => setDetail(null)}><Text style={styles.closeText}>关闭</Text></TouchableOpacity>
          </View>
        </View>
      </Modal>
    </View>
  );
}
// styles 参照 ComplianceCenterScreen（header/container/card 同款，新增 modalWrap/modalBody/modalTitle/modalContent/closeBtn/closeText/empty）
const styles = StyleSheet.create({
  container: { flex: 1, backgroundColor: Colors.background },
  header: { backgroundColor: Colors.primary, paddingTop: 50, paddingBottom: 14, paddingHorizontal: Spacing.lg, flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', ...Shadow.header },
  headerTitle: { color: Colors.textWhite, fontSize: FontSize.lg, fontWeight: '600' },
  content: { padding: Spacing.md },
  card: { backgroundColor: Colors.card, borderRadius: BorderRadius.md, padding: Spacing.lg, marginBottom: Spacing.md },
  cardTitle: { fontSize: FontSize.md, fontWeight: '600', color: Colors.textPrimary },
  desc: { fontSize: FontSize.sm, color: Colors.textSecondary, marginTop: 4 },
  empty: { textAlign: 'center', color: Colors.textHint, marginTop: 40 },
  modalWrap: { flex: 1, justifyContent: 'flex-end', backgroundColor: 'rgba(0,0,0,0.5)' },
  modalBody: { backgroundColor: Colors.card, borderTopLeftRadius: BorderRadius.lg, borderTopRightRadius: BorderRadius.lg, padding: Spacing.lg, maxHeight: '80%' },
  modalTitle: { fontSize: FontSize.lg, fontWeight: '600', marginBottom: Spacing.md },
  modalContent: { fontSize: FontSize.md, color: Colors.textPrimary, lineHeight: 24 },
  closeBtn: { marginTop: Spacing.lg, backgroundColor: Colors.primary, borderRadius: BorderRadius.sm, padding: Spacing.md, alignItems: 'center' },
  closeText: { color: Colors.textWhite, fontSize: FontSize.md, fontWeight: '600' },
});
```

Create `mobile/src/screens/Compliance/ExamScreen.tsx`（答题流程：加载题目 → 逐题选择 → 提交 → 结果）：

```tsx
import React, { useCallback, useEffect, useState } from 'react';
import { Alert, ScrollView, StyleSheet, Text, TouchableOpacity, View } from 'react-native';
import { useNavigation } from '@react-navigation/native';
import { examAPI } from '../../api/exam';
import type { ExamQuestion } from '../../types';
import Icon from '../../components/Icon';
import { BorderRadius, Colors, FontSize, Shadow, Spacing } from '../../constants/theme';

const TYPE_TEXT: Record<string, string> = { single: '单选', multiple: '多选', judge: '判断' };

export default function ExamScreen() {
  const navigation = useNavigation();
  const [questions, setQuestions] = useState<ExamQuestion[]>([]);
  const [answers, setAnswers] = useState<Record<number, number[]>>({});
  const [submitting, setSubmitting] = useState(false);
  const [result, setResult] = useState<any | null>(null);

  const load = async () => {
    try {
      const res = await examAPI.startExam(10);
      setQuestions(res?.data?.questions || []);
      const init: Record<number, number[]> = {};
      (res?.data?.questions || []).forEach((q: ExamQuestion) => { init[q.id] = []; });
      setAnswers(init);
    } catch { Alert.alert('加载失败', '暂无可考试的题目或网络异常'); }
  };

  useEffect(() => { load(); }, []);

  const toggle = (qid: number, idx: number, multi: boolean) => {
    setAnswers(prev => {
      const cur = prev[qid] || [];
      if (multi) {
        const next = cur.includes(idx) ? cur.filter(i => i !== idx) : [...cur, idx];
        return { ...prev, [qid]: next };
      }
      return { ...prev, [qid]: cur.includes(idx) ? [] : [idx] };
    });
  };

  const submit = async () => {
    const payload = Object.entries(answers).map(([qid, selected]) => ({ question_id: Number(qid), selected }));
    if (payload.some(a => !a.selected.length)) { Alert.alert('提示', '请完成所有题目'); return; }
    setSubmitting(true);
    try {
      const res = await examAPI.submitExam(payload);
      setResult(res?.data);
    } catch { Alert.alert('提交失败', '请稍后重试'); }
    finally { setSubmitting(false); }
  };

  if (result) {
    return (
      <View style={styles.container}>
        <View style={styles.header}><TouchableOpacity onPress={() => navigation.goBack()}><Icon name="chevron-left" size={22} color={Colors.textWhite} /></TouchableOpacity><Text style={styles.headerTitle}>考试结果</Text><View style={{ width: 24 }} /></View>
        <View style={[styles.card, Shadow.card]}>
          <Text style={[styles.score, { color: result.passed ? Colors.success : Colors.danger }]}>{result.score} 分</Text>
          <Text style={styles.desc}>{result.passed ? '已通过（≥80 分）' : '未通过，请重新学习后补考'}</Text>
          <Text style={styles.desc}>答对 {result.correct_count} / {result.question_count}</Text>
          <TouchableOpacity style={styles.submitBtn} onPress={() => navigation.goBack()}><Text style={styles.submitText}>返回</Text></TouchableOpacity>
        </View>
      </View>
    );
  }

  return (
    <View style={styles.container}>
      <View style={styles.header}><TouchableOpacity onPress={() => navigation.goBack()}><Icon name="chevron-left" size={22} color={Colors.textWhite} /></TouchableOpacity><Text style={styles.headerTitle}>合规考试</Text><View style={{ width: 24 }} /></View>
      <ScrollView contentContainerStyle={styles.content}>
        {questions.map((q, qi) => (
          <View key={q.id} style={[styles.card, Shadow.card]}>
            <Text style={styles.cardTitle}>{qi + 1}. {q.content} <Text style={styles.typeTag}>[{TYPE_TEXT[q.question_type] || q.question_type}]</Text></Text>
            {q.options.map((opt, oi) => {
              const sel = (answers[q.id] || []).includes(oi);
              return (
                <TouchableOpacity key={oi} style={[styles.option, sel && styles.optionSelected]} onPress={() => toggle(q.id, oi, q.question_type === 'multiple')}>
                  <Icon name={sel ? 'check-circle' : 'circle-outline'} size={18} color={sel ? Colors.primary : Colors.textHint} />
                  <Text style={styles.optionText}>{opt}</Text>
                </TouchableOpacity>
              );
            })}
          </View>
        ))}
        <TouchableOpacity style={[styles.submitBtn, submitting && { opacity: 0.6 }]} disabled={submitting} onPress={submit}>
          <Text style={styles.submitText}>{submitting ? '提交中…' : '提交试卷'}</Text>
        </TouchableOpacity>
      </ScrollView>
    </View>
  );
}
// styles：container/header/headerTitle/content/card/cardTitle 同 ComplianceCenterScreen；
// 新增 typeTag（FontSize.xs, color hint）、option（row, border, radius, padding, marginTop）、
// optionSelected（borderColor primary, bg primary+10%）、optionText、score（FontSize.3xl, bold, center）、
// submitBtn/submitText 同款
const styles = StyleSheet.create({
  container: { flex: 1, backgroundColor: Colors.background },
  header: { backgroundColor: Colors.primary, paddingTop: 50, paddingBottom: 14, paddingHorizontal: Spacing.lg, flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', ...Shadow.header },
  headerTitle: { color: Colors.textWhite, fontSize: FontSize.lg, fontWeight: '600' },
  content: { padding: Spacing.md },
  card: { backgroundColor: Colors.card, borderRadius: BorderRadius.md, padding: Spacing.lg, marginBottom: Spacing.md },
  cardTitle: { fontSize: FontSize.md, fontWeight: '600', color: Colors.textPrimary, marginBottom: Spacing.sm },
  typeTag: { fontSize: FontSize.xs, color: Colors.textHint },
  option: { flexDirection: 'row', alignItems: 'center', gap: 8, borderWidth: 1, borderColor: Colors.border, borderRadius: BorderRadius.sm, padding: Spacing.sm, marginTop: Spacing.sm },
  optionSelected: { borderColor: Colors.primary, backgroundColor: 'rgba(22,119,255,0.08)' },
  optionText: { flex: 1, fontSize: FontSize.sm, color: Colors.textPrimary },
  score: { fontSize: 40, fontWeight: '700', textAlign: 'center', marginBottom: Spacing.sm },
  desc: { fontSize: FontSize.sm, color: Colors.textSecondary, textAlign: 'center', marginTop: 2 },
  submitBtn: { marginTop: Spacing.lg, backgroundColor: Colors.primary, borderRadius: BorderRadius.sm, padding: Spacing.md, alignItems: 'center' },
  submitText: { color: Colors.textWhite, fontSize: FontSize.md, fontWeight: '600' },
});
```

Create `mobile/src/screens/Compliance/CommitmentScreen.tsx`（勾选 + 短信验证码 + 签署）：

```tsx
import React, { useState } from 'react';
import { Alert, ScrollView, StyleSheet, Text, TextInput, TouchableOpacity, View } from 'react-native';
import { useNavigation } from '@react-navigation/native';
import { examAPI } from '../../api/exam';
import Icon from '../../components/Icon';
import { BorderRadius, Colors, FontSize, Shadow, Spacing } from '../../constants/theme';

export default function CommitmentScreen() {
  const navigation = useNavigation();
  const [agreed, setAgreed] = useState(false);
  const [code, setCode] = useState('');
  const [sending, setSending] = useState(false);
  const [signed, setSigned] = useState(false);

  const sendCode = async () => {
    if (!agreed) { Alert.alert('提示', '请先勾选同意承诺书内容'); return; }
    setSending(true);
    try { await examAPI.sendCommitmentCode(); Alert.alert('已发送', '短信验证码已发送至手机号'); }
    catch { Alert.alert('发送失败', '请稍后重试'); }
    finally { setSending(false); }
  };

  const sign = async () => {
    if (!code.trim()) { Alert.alert('提示', '请输入验证码'); return; }
    try {
      await examAPI.signCommitment(code.trim());
      setSigned(true);
      Alert.alert('已签署', '年度合规承诺书签署完成', [{ text: '好', onPress: () => navigation.goBack() }]);
    } catch { Alert.alert('签署失败', '验证码错误或已过期'); }
  };

  return (
    <View style={styles.container}>
      <View style={styles.header}><TouchableOpacity onPress={() => navigation.goBack()}><Icon name="chevron-left" size={22} color={Colors.textWhite} /></TouchableOpacity><Text style={styles.headerTitle}>合规承诺书</Text><View style={{ width: 24 }} /></View>
      <ScrollView contentContainerStyle={styles.content}>
        <View style={[styles.card, Shadow.card]}>
          <Text style={styles.cardTitle}>年度合规承诺书</Text>
          <Text style={styles.body}>
            {"本人承诺：\n\n1. 严格遵守《医药代表管理办法》及相关法律法规；\n2. 仅从事学术推广，不承担销售任务，不进行统方；\n3. 不提供财物或其他利益，不附加销售条件，不隐瞒不良反应，不误导用药；\n4. 配合平台合规管理，按时完成培训与考试。\n\n本承诺书由本人签署，平台留存并接受监管检查。"}
          </Text>
        </View>
        <TouchableOpacity style={styles.agreeRow} onPress={() => setAgreed(!agreed)}>
          <Icon name={agreed ? 'check-circle' : 'circle-outline'} size={20} color={agreed ? Colors.primary : Colors.textHint} />
          <Text style={styles.agreeText}>我已知悉并同意以上内容</Text>
        </TouchableOpacity>
        <TouchableOpacity style={[styles.submitBtn, (!agreed || sending) && { opacity: 0.6 }]} disabled={!agreed || sending} onPress={sendCode}>
          <Text style={styles.submitText}>{sending ? '发送中…' : '发送短信验证码'}</Text>
        </TouchableOpacity>
        <TextInput style={styles.input} value={code} onChangeText={setCode} placeholder="输入验证码" placeholderTextColor={Colors.textHint} maxLength={6} keyboardType="number-pad" />
        <TouchableOpacity style={[styles.submitBtn, !code.trim() && { opacity: 0.6 }]} disabled={!code.trim()} onPress={sign}>
          <Text style={styles.submitText}>签署承诺书</Text>
        </TouchableOpacity>
      </ScrollView>
    </View>
  );
}
// styles 同 ComplianceCenterScreen 基础 + agreeRow/agreeText/body/input
const styles = StyleSheet.create({
  container: { flex: 1, backgroundColor: Colors.background },
  header: { backgroundColor: Colors.primary, paddingTop: 50, paddingBottom: 14, paddingHorizontal: Spacing.lg, flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', ...Shadow.header },
  headerTitle: { color: Colors.textWhite, fontSize: FontSize.lg, fontWeight: '600' },
  content: { padding: Spacing.md },
  card: { backgroundColor: Colors.card, borderRadius: BorderRadius.md, padding: Spacing.lg, marginBottom: Spacing.md },
  cardTitle: { fontSize: FontSize.md, fontWeight: '600', color: Colors.textPrimary, marginBottom: Spacing.sm },
  body: { fontSize: FontSize.sm, color: Colors.textSecondary, lineHeight: 24 },
  agreeRow: { flexDirection: 'row', alignItems: 'center', gap: 8, marginBottom: Spacing.md },
  agreeText: { flex: 1, fontSize: FontSize.md, color: Colors.textPrimary },
  input: { borderWidth: 1, borderColor: Colors.border, borderRadius: BorderRadius.sm, padding: Spacing.sm, color: Colors.textPrimary, fontSize: FontSize.md, marginBottom: Spacing.md },
  submitBtn: { backgroundColor: Colors.primary, borderRadius: BorderRadius.sm, padding: Spacing.md, alignItems: 'center', marginBottom: Spacing.sm },
  submitText: { color: Colors.textWhite, fontSize: FontSize.md, fontWeight: '600' },
});
```

- [ ] **Step 4: 接线导航 + 合规中心入口**

Modify `mobile/src/navigation/types.ts`：RootStackParamList 追加：

```ts
  TrainingMaterial: undefined;
  Exam: undefined;
  Commitment: undefined;
```

Modify `mobile/src/navigation/AppNavigator.tsx`：import 三个 Screen 并注册 `<Stack.Screen>`（参照 ComplianceCenter 那行）。

Modify `mobile/src/screens/Compliance/ComplianceCenterScreen.tsx`：在 ScrollView 内加三个入口卡片（参照备案状态卡模式，渲染时跳转对应 Screen）：

```tsx
        <View style={[styles.card, Shadow.card]}>
          <Text style={styles.cardTitle}>合规培训与承诺</Text>
          <TouchableOpacity style={styles.entryRow} onPress={() => navigation.navigate('TrainingMaterial')}>
            <Icon name="book-open-variant" size={18} color={Colors.primary} />
            <Text style={styles.entryText}>培训材料</Text>
          </TouchableOpacity>
          <TouchableOpacity style={styles.entryRow} onPress={() => navigation.navigate('Exam')}>
            <Icon name="clipboard-text" size={18} color={Colors.primary} />
            <Text style={styles.entryText}>合规考试</Text>
          </TouchableOpacity>
          <TouchableOpacity style={styles.entryRow} onPress={() => navigation.navigate('Commitment')}>
            <Icon name="file-sign" size={18} color={Colors.primary} />
            <Text style={styles.entryText}>签署年度承诺书{qual?.commitment_signed ? '（已签）' : ''}</Text>
          </TouchableOpacity>
        </View>
```

> styles 补 entryRow/entryText（参照 pickBtn 模式）。确认 Icon 组件含 book-open-variant/clipboard-text/file-sign/check-circle/circle-outline 名称，若缺用现有名称（参照 Icon 组件内图标表）。

- [ ] **Step 5: 运行契约测试**

Run: `cd mobile && npx jest src/api/__tests__/exam-contract.test.ts`
Expected: 4 passed

- [ ] **Step 6: TypeScript 校验**

Run: `cd mobile && npx tsc --noEmit`（若项目有 tsconfig 且作为验证门）
Expected: 无新增类型错误（若项目不跑 tsc 全量，跳过此步，以 jest 通过为准）

- [ ] **Step 7: Commit**

```bash
git add mobile/src/api/exam.ts mobile/src/api/__tests__/exam-contract.test.ts mobile/src/screens/Compliance mobile/src/navigation/types.ts mobile/src/navigation/AppNavigator.tsx
git commit -m "feat(mobile): 个人合规中心扩展（培训材料/在线考试/承诺书签署）"
```

---

### Task 10: 全量回归 + CLAUDE.md 同步

**Files:**
- Modify: `CLAUDE.md`
- Modify: `scripts/init_db.sql`（若 Task 1 遗漏再补）

**Interfaces:**
- Consumes: 全部 F 计划产物

- [ ] **Step 1: 后端全量回归**

Run: `cd services/auth-service && python -m pytest -q`（Redis 未起则 7 个 skip，起则全绿；新用例并入基线）
Run: 其余服务 `python -m pytest -q`（specialist/knowledge/compliance/audit/hcp/visit/gateway 各 cd 后跑）
Expected: 全量通过，无回归（auth 基线 + F 新增：test_training_materials 8 + test_exams ~18 + test_commitment 4）

- [ ] **Step 2: 前端验证**

Run: `cd web && npm run build`
Run: `cd mobile && npx jest`
Run: `cd mobile-doctor && npx jest`
Expected: web build PASS、mobile jest 通过（含 exam-contract）、mobile-doctor 通过

- [ ] **Step 3: 同步 CLAUDE.md**

在 CLAUDE.md 的端点/表清单补记 F 计划：
- 新表：training_materials / exam_questions / exam_records（迁移 013）
- 新端点：`/api/v1/training-materials`（CRUD+列表）、`/api/v1/exams/questions`（题库 CRUD+审核）、`/api/v1/exams/questions/ai-generate`（AI 草稿）、`/api/v1/exams/start|submit|records`、`/api/v1/qualifications/commitment/send-code|sign`
- 配置：EXAM_PASS_SCORE（默认 80）、QWEN_EXAM_MODEL（默认 qwen-turbo）、DASHSCOPE_API_KEY
- 基线：auth 服务测试数更新
- Known Gaps 更新：培训前置"先上线不强制"为设计决策；AI 出题草稿不落库；承诺书一期无第三方 CA

- [ ] **Step 4: 本地冒烟（可选，依赖 .env 真实库）**

Run: `cd scripts && python seed_training_materials.py`
Expected: 打印已创建/已跳过；库中有两条材料 + 2 条 approved 题目

- [ ] **Step 5: Commit**

```bash
git add CLAUDE.md
git commit -m "docs: 二期 F 培训考试+承诺书文档同步"
```

---

## Self-Review

**1. Spec 覆盖：**
- 培训材料管理 3.4(1) → Task 2（内置办法/RDPAC + 药企自定义）
- 题库与考试 3.4(2) → Task 3（题库+人工审核）+ Task 4（AI 出题辅助）+ Task 5（考试判分）
- 培训记录存档 3.4(3) → Task 5 回写代表资质三字段 + Task 8/9 records
- 年度承诺书 3.4(4) → Task 6（短信验证码+审计）
- 代表端个人合规中心 4.2(4) → Task 9
- 培训前置先上线不强制 → 全计划（只状态不门禁）
- 附录 A exam_questions/exam_records 表 → Task 1 迁移（对齐需求字段，options/answer JSONB）

**2. 占位符扫描：** Task 8 AI 出题 Modal 材料 Select 数据源标注"实现时补"；Task 9 styles 复用说明明确；无 TBD/TODO 硬占位。

**3. 类型一致性：** `_score_match(selected, answer)` 集合相等；`ExamQuestion.to_dict(expose_answer)` 默认不暴露；`ExamRecord` 字段 question_count/correct_count/score/passed/submitted_at 在测试与 web/mobile 类型一致；`training-materials` 列表 archived 过滤在实现与测试一致。

**已知取舍（写进 CLAUDE.md）：** AI 出题内容仅辅助、人工入库审核；承诺书一期不接第三方 CA；考试题目随机抽 approved；回写只更新更高分（保留历史最好成绩语义）。
