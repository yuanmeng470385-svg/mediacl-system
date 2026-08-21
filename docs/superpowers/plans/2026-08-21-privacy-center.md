# 隐私中心（三期 L）Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 医生端隐私中心（隐私政策/个人信息查看/更正·导出·删除·注销申请）+ 管理后台隐私请求处理（30 日 SLA）+ 注销去标识化执行。

**Architecture:** privacy_requests 子系统在 **auth-service**——correct/delete/account_delete 都直接改 users（auth 域），登录与 token 状态拦截（`UserRepo.is_active` / `get_current_user` 的 `status != "active"` → 401）就在 auth；personal-data 同库直读 doctor_profile（`shared/models/doctor_profile.py` 直接 import，与三期 K mah_overview 同库直读先例一致）。conversation 模型是 specialist-service 本地模型，auth **不跨服务 import**，个人数据包用 `db.execute(text(...))` 显式列只读查询。网关 ROUTE_MAP 加一行 `/api/v1/privacy-requests` → auth；`/api/v1/doctors/personal-data`、`/api/v1/doctors/privacy-policy` 复用既有 `/api/v1/doctors` 前缀（不改网关）。web 隐私请求处理页 `/privacy/requests`；mobile-doctor 隐私中心两屏。

**Tech Stack:** FastAPI + SQLAlchemy（auth:8000）+ React web（Ant Design Pro Components）+ React Native 医生端 + SQLite 单测（StaticPool + BigInteger/JSONB 编译垫片）。

## Global Constraints

- **不做物理删除**（法务已拍板）：delete/account_delete 一律去标识化——full_name→`"已注销医生"`、phone→`f"DELETED-{user.id}"`（嵌 id 防脱敏串互撞；users.phone 无唯一约束）、status→`"deleted"`、deleted_at=now；**仅目标 doctor，不触碰代表/管理员**；历史业务数据一律留存。
- token 失效靠实时查库天然拦截：`shared/common/auth.py:103` `user.status != "active"` → 401；登录走 `UserRepo.is_active` 拒绝——**不做 token 黑名单**。
- SLA = 创建时间 + 30 自然日（`sla_deadline` 落库）；超时仅管理端列表高亮（`sla_overdue=true`），**不自动执行**（对齐导出审批"超时不放行"原则）。
- 权限：提交/me 仅 `role=doctor`；管理端列表/handle 为 admin/manager/compliance（`PRIVACY_ADMIN_ROLES`）；写审计 action=`privacy_request_create` / `privacy_request_handle`。
- request_type ∈ `view/correct/delete/export/account_delete`；status ∈ `pending/processing/done/rejected`（done/rejected 终态不可再 handle）；handle 的 action ∈ `processing/done/rejected`，done/rejected 时 `response` 必填（≤500 字）。
- correct 的 fields（full_name/phone）至少一项；phone 格式 `^1\d{10}$`、full_name ≤100 字；account_delete 必须带 `confirm: true`（前端二次确认 + 后端校验双保险）。
- 个人数据包（export 的 done 处理产物）：JSON 落 `logs/exports/privacy_<request_id>.json`（logs/ 已 gitignore），内容 = 用户安全字段 + 偏好画像 + 医师认证记录 + 对话历史（text() 只读，上限 5000 行，**绝不含患者诊断信息**）+ 隐私请求历史；`file_url` 留痕，**不做在线下载端点**（管理端线下交付）。
- 历史对话查看不自建端点：mobile 复用既有「收藏历史」入口（需求原文即"复用 favorites/conversations 历史"）。
- 测试约定：SQLite + StaticPool；`monkeypatch.setitem(app.dependency_overrides, get_db, _override_db)`；`write_audit_log` 用 `monkeypatch.setattr` 打 AsyncMock；JSONB/BigInteger 编译垫片照 `test_exams.py`/`test_doctors.py`；`create_token(user_id=…, username=…, role=…)`。
- 验证门：`cd services/auth-service && python -m pytest tests/ -q`（基线 135 passed，2026-08-19）+ `cd services/gateway && python -m pytest tests/ -q`（基线 82 passed）+ `cd mobile-doctor && npx jest`（基线 18 passed）+ `cd web && npm run build`（PASS）。
- **禁止子代理 push 任何远程**——推 Codeup 由主会话在用户确认后执行。

---

### Task 1: 迁移 023 + PrivacyRequest 模型 + users.deleted_at

**Files:**
- Create: `scripts/migrations/023_privacy_center.sql`
- Create: `shared/models/privacy.py`
- Modify: `shared/models/user.py`（status 列后加 deleted_at）
- Modify: `scripts/init_db.sql`（users 表定义加 deleted_at + 追加 privacy_requests 建表块）
- Test: `services/auth-service/tests/test_privacy.py`（新建，含 fixture）

**Interfaces:**
- Produces: `PrivacyRequest(id, doctor_id, request_type, status, content, sla_deadline, handled_by, handled_at, file_url)` + `to_dict()`；常量 `PRIVACY_REQUEST_TYPES` / `PRIVACY_REQUEST_STATUSES`（Task 3/4 依赖）。`User.deleted_at` 列（Task 4 去标识化依赖）。

- [ ] **Step 1: 写迁移 SQL**

Create `scripts/migrations/023_privacy_center.sql`:

```sql
-- 023_privacy_center.sql
-- 三期 L：隐私中心（需求 5.7/3.8(4)(5)）
-- 用法：docker exec -i medagent-postgres psql -U medagent medagent < scripts/migrations/023_privacy_center.sql

\set ON_ERROR_STOP on

CREATE TABLE IF NOT EXISTS privacy_requests (
    id BIGSERIAL PRIMARY KEY,
    doctor_id BIGINT NOT NULL REFERENCES users(id),
    request_type VARCHAR(20) NOT NULL,               -- view/correct/delete/export/account_delete
    status VARCHAR(20) NOT NULL DEFAULT 'pending',   -- pending/processing/done/rejected
    content JSONB,                                   -- {detail, fields:{full_name,phone}, confirm, response}
    sla_deadline TIMESTAMP NOT NULL,                 -- created_at + 30 自然日（API 层写入）
    handled_by BIGINT REFERENCES users(id),
    handled_at TIMESTAMP,
    file_url VARCHAR(500),
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_pr_doctor ON privacy_requests(doctor_id);
CREATE INDEX IF NOT EXISTS idx_pr_status ON privacy_requests(status);

-- 注销标记列（status 值域扩 'deleted'；物理删除不做，法务拍板）
ALTER TABLE users ADD COLUMN IF NOT EXISTS deleted_at TIMESTAMP;
```

- [ ] **Step 2: 写模型 shared/models/privacy.py**

```python
"""隐私请求（三期 L，需求 3.8(4)(5)/5.7）

医生侧行使查阅/更正/删除/导出/注销权利的请求工单：
  - request_type ∈ view/correct/delete/export/account_delete；
  - status ∈ pending/processing/done/rejected（done/rejected 为终态，不可再处理）；
  - sla_deadline = 创建时间 + 30 自然日（API 层写入；超时仅管理端高亮，不自动执行）；
  - content JSONB：{detail: 申请说明, fields: {full_name, phone}（correct 用）,
    confirm: bool（account_delete 用）, response: 处理回复（handle 写入）}；
  - delete/account_delete 的 done 处理 = users 去标识化（status→deleted + deleted_at），
    物理删除不做（法务拍板）。
"""
from sqlalchemy import BigInteger, Column, DateTime, ForeignKey, String
from sqlalchemy.dialects.postgresql import JSONB

from shared.models.base import Base, TimestampMixin

PRIVACY_REQUEST_TYPES = ("view", "correct", "delete", "export", "account_delete")
PRIVACY_REQUEST_STATUSES = ("pending", "processing", "done", "rejected")


class PrivacyRequest(Base, TimestampMixin):
    __tablename__ = "privacy_requests"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    doctor_id = Column(BigInteger, ForeignKey("users.id"), nullable=False, index=True)
    request_type = Column(String(20), nullable=False)
    status = Column(String(20), nullable=False, default="pending")
    content = Column(JSONB)
    sla_deadline = Column(DateTime, nullable=False)
    handled_by = Column(BigInteger, ForeignKey("users.id"))
    handled_at = Column(DateTime)
    file_url = Column(String(500))

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "doctor_id": self.doctor_id,
            "request_type": self.request_type,
            "status": self.status,
            "content": self.content or {},
            "sla_deadline": self.sla_deadline.isoformat() if self.sla_deadline else None,
            "handled_by": self.handled_by,
            "handled_at": self.handled_at.isoformat() if self.handled_at else None,
            "file_url": self.file_url,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }
```

- [ ] **Step 3: user.py 加 deleted_at 列**

`shared/models/user.py` 的 `status = Column(String(20), default="active")` 行后加：

```python
    status = Column(String(20), default="active")
    # 注销标记（三期 L）：status='deleted' 时写入；物理删除不做，去标识化+留存
    deleted_at = Column(DateTime)
```

并在文件头 import 行补 `DateTime`：`from sqlalchemy import Column, DateTime, String, BigInteger, ForeignKey`。

- [ ] **Step 4: 同步 init_db.sql**

两处：① users 建表块的 `status` 列后加 `deleted_at TIMESTAMP,`（带同款注释）；② 文件末尾（022 块之后）追加 privacy_requests 建表块——照 Step 1 的 SQL 原样（init_db 用 `CREATE TABLE IF NOT EXISTS` 风格，与 022 一致），并加一行注释 `-- 三期 L：隐私中心（迁移 023，2026-08-21 起已并入 init_db.sql；旧库须执行 023）`。

- [ ] **Step 5: 写失败测试（fixture + 模型级）**

Create `services/auth-service/tests/test_privacy.py`（fixture 照 `test_doctors.py` 模式 + JSONB 垫片照 `test_exams.py`）：

```python
"""隐私中心测试（三期 L）

覆盖：模型往返（content JSONB / sla_deadline）、隐私政策公开读、个人信息查看
（doctor-only）、请求提交校验（类型/字段/确认）、本人查询隔离与分页、管理端
列表（JOIN 医生名 / SLA 高亮 / 过滤）、handle 执行语义（更正/数据包/去标识化/
终态拦截）、审计留痕。

不依赖真实 Redis/PostgreSQL/OSS：DB 用 SQLite（BigInteger/JSONB 编译垫片）。
"""
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
from sqlalchemy import BigInteger, create_engine, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.ext.compiler import compiles
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from shared.common.auth import create_token
from shared.common.db_session import get_db
from shared.models.base import Base
from shared.models.privacy import PrivacyRequest
from shared.models.user import User

import app.api.privacy as privacy_api
from app.main import app


@compiles(BigInteger, "sqlite")
def _compile_bigint_for_sqlite(type_, compiler, **kw):
    return "INTEGER"


@compiles(JSONB, "sqlite")
def _compile_jsonb_for_sqlite(type_, compiler, **kw):
    return "JSON"


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
    """每用例重建 users + privacy_requests 表；审计打桩。

    doctor_profiles/doctor_certifications/conversations 按需在用例内建表
    （Task 2/4 引入后再放进 tables 列表或用 DDL 建）。
    """
    tables = [User.__table__, PrivacyRequest.__table__]
    Base.metadata.drop_all(engine, tables=tables)
    Base.metadata.create_all(engine, tables=tables)
    db = TestSession()
    db.add_all([
        User(id=1, username="doc01", full_name="张医生", phone="13800000001",
             role="doctor", status="active"),
        User(id=2, username="admin", full_name="管理员", phone="13800000000",
             role="admin", status="active"),
        User(id=3, username="rep01", full_name="李代表", phone="13800000002",
             role="rep", status="active"),
    ])
    db.commit()
    db.close()

    monkeypatch.setitem(app.dependency_overrides, get_db, _override_db)
    audit_mock = AsyncMock(return_value=None)
    monkeypatch.setattr(privacy_api, "write_audit_log", audit_mock)
    yield audit_mock


# ---------- Task 1：模型往返 ----------

def test_privacy_request_model_roundtrip():
    db = TestSession()
    req = PrivacyRequest(
        doctor_id=1,
        request_type="correct",
        status="pending",
        content={"detail": "改名", "fields": {"full_name": "张三丰"}},
        sla_deadline=datetime.utcnow() + timedelta(days=30),
    )
    db.add(req)
    db.commit()
    db.refresh(req)

    loaded = db.query(PrivacyRequest).filter(PrivacyRequest.id == req.id).first()
    assert loaded.content["fields"]["full_name"] == "张三丰"
    d = loaded.to_dict()
    assert d["request_type"] == "correct"
    assert d["status"] == "pending"
    assert d["doctor_id"] == 1
    assert d["content"]["detail"] == "改名"
    assert d["sla_deadline"] is not None
    assert d["handled_by"] is None and d["handled_at"] is None


def test_user_model_has_deleted_at():
    db = TestSession()
    u = db.query(User).filter(User.id == 1).first()
    u.status = "deleted"
    u.deleted_at = datetime.utcnow()
    db.commit()
    loaded = db.query(User).filter(User.id == 1).first()
    assert loaded.status == "deleted"
    assert loaded.deleted_at is not None
```

注意：`import app.api.privacy as privacy_api` 与 `write_audit_log` 打桩在本 Task 会 ImportError（模块还不存在）——**这正是失败点**，先确认失败，Task 3 实现后通过。

- [ ] **Step 6: 运行确认失败**

Run: `cd services/auth-service && python -m pytest tests/test_privacy.py -v`
Expected: FAIL / collection error —— `ModuleNotFoundError: No module named 'app.api.privacy'`

- [ ] **Step 7: 实现并确认通过**

本 Task 模型已就位，但测试文件 import 了 Task 3 才创建的 `app.api.privacy`。为让本 Task 独立可交付，先创建**最小路由骨架** `services/auth-service/app/api/privacy.py`（Task 3 再填端点）：

```python
"""隐私请求（三期 L，需求 3.8(4)(5)/5.7）：提交/本人查询/管理端处理

Task 1 仅建骨架挂路由；端点在 Task 3/4 实现。
write_audit_log 先占位 import——测试 fixture 对它做 monkeypatch.setattr，
属性必须存在（Task 3 替换全文后真正使用）。
"""
import logging

from fastapi import APIRouter

from app.services.audit_client import write_audit_log  # noqa: F401（fixture 打桩锚点）

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/privacy-requests", tags=["privacy-requests"])
```

并在 `services/auth-service/app/main.py` 照既有 include 模式追加：

```python
from app.api.privacy import router as privacy_router
# ...
app.include_router(privacy_router)
```

Run: `cd services/auth-service && python -m pytest tests/test_privacy.py -v`
Expected: 2 passed

- [ ] **Step 8: 全量确认**

Run: `cd services/auth-service && python -m pytest tests/ -q`
Expected: 137 passed（基线 135 + 新增 2）

- [ ] **Step 9: Commit**

```bash
git add scripts/migrations/023_privacy_center.sql scripts/init_db.sql shared/models/privacy.py shared/models/user.py services/auth-service/app/api/privacy.py services/auth-service/app/main.py services/auth-service/tests/test_privacy.py
git commit -m "feat(privacy): 迁移 023 + PrivacyRequest 模型 + users.deleted_at（三期 L）"
```

---

### Task 2: 隐私政策 + 个人信息查看端点（doctors.py）

**Files:**
- Modify: `services/auth-service/app/api/doctors.py`（文件末尾追加两端点 + 顶部补 DoctorProfile import）
- Test: `services/auth-service/tests/test_privacy.py`（追加）

**Interfaces:**
- Consumes: `User.to_dict()`、`DoctorProfile.to_dict()`（shared 模型，均已有）。
- Produces: `GET /api/v1/doctors/privacy-policy`（公开）→ `success({title, version, updated_at, content})`；`GET /api/v1/doctors/personal-data`（require_roles("doctor")）→ `success({user: <to_dict>, doctor_profile: <to_dict|null>})`。mobile-doctor Task 7 依赖此形状。

- [ ] **Step 1: 写失败测试**

追加到 `test_privacy.py`：

```python
# ---------- Task 2：隐私政策 + 个人信息 ----------

def test_privacy_policy_public_no_auth_required():
    r = client.get("/api/v1/doctors/privacy-policy")
    assert r.status_code == 200
    body = r.json()
    assert body["code"] == 0
    data = body["data"]
    assert data["version"] == "1.0"
    assert "注销" in data["content"]
    assert "30" in data["content"]


def test_personal_data_returns_user_and_profile():
    from shared.models.doctor_profile import DoctorProfile
    Base.metadata.create_all(engine, tables=[DoctorProfile.__table__])
    db = TestSession()
    db.add(DoctorProfile(doctor_id=1, interest_areas=["心血管"],
                         preferred_doc_type="rct", preferred_style="标准", closed=False))
    db.commit()
    db.close()

    r = client.get("/api/v1/doctors/personal-data", headers=_token(1, "doctor"))
    assert r.status_code == 200
    data = r.json()["data"]
    assert data["user"]["id"] == 1
    assert data["user"]["full_name"] == "张医生"
    assert "password_hash" not in data["user"]
    assert data["doctor_profile"]["interest_areas"] == ["心血管"]


def test_personal_data_without_profile_returns_null():
    r = client.get("/api/v1/doctors/personal-data", headers=_token(1, "doctor"))
    assert r.status_code == 200
    assert r.json()["data"]["doctor_profile"] is None


def test_personal_data_doctor_only_rep_403():
    r = client.get("/api/v1/doctors/personal-data", headers=_token(3, "rep"))
    assert r.status_code == 403
```

- [ ] **Step 2: 运行确认失败**

Run: `cd services/auth-service && python -m pytest tests/test_privacy.py -v -k "policy or personal_data"`
Expected: FAIL（404 Not Found，端点不存在）

- [ ] **Step 3: 实现两端点**

`doctors.py` 顶部 import 区补：

```python
from shared.models.doctor_profile import DoctorProfile
```

文件末尾追加：

```python
# ---------- 隐私中心（三期 L，需求 5.7） ----------

PRIVACY_POLICY = {
    "title": "MedAgent 医生端隐私政策",
    "version": "1.0",
    "updated_at": "2026-08-21",
    "content": (
        "1. 我们收集的信息：账号信息（姓名/手机号/科室/地区）、医师资质文件、"
        "您与数字分身的对话记录、学术偏好设置。\n"
        "2. 使用目的：提供医学问答、分身订阅、学术触达与患教服务；未经同意不会"
        "将您的个人信息用于其他目的。\n"
        "3. 存储与保护：数据加密存储于境内服务器，访问全程留痕审计。\n"
        "4. 对话合规：所有对话经合规系统实时检查，违规内容将被拦截。\n"
        "5. 您的权利：您可在隐私中心查看个人信息、申请更正、申请导出数据包、"
        "申请删除数据或注销账号。\n"
        "6. 删除与注销：注销采用去标识化处理（姓名置为『已注销医生』、手机号脱敏），"
        "依法留存的合规记录不做物理删除。\n"
        "7. 响应时限：您的请求将在 30 日内处理并反馈结果。\n"
        "8. 联系我们：可通过隐私请求提交说明，或联系平台管理员。"
    ),
}


@router.get("/privacy-policy")
def get_privacy_policy():
    """隐私政策全文（静态文案，公开可读——登录前亦可展示）"""
    return success(PRIVACY_POLICY)


@router.get("/personal-data")
def get_personal_data(
    current_user: dict = Depends(require_roles("doctor")),
    db: Session = Depends(get_db),
):
    """个人信息查看（需求 5.7(2)）：user 安全字段 + 偏好画像（无画像为 null）

    历史对话查看不自建端点——mobile 复用既有收藏历史（需求原文即"复用"）。
    """
    user = db.query(User).filter(User.id == current_user["id"]).first()
    if not user:
        raise BusinessError("用户不存在")
    profile = (
        db.query(DoctorProfile).filter(DoctorProfile.doctor_id == user.id).first()
    )
    return success({
        "user": user.to_dict(),
        "doctor_profile": profile.to_dict() if profile else None,
    })
```

注意：doctors.py 已 import `success`/`BusinessError`（qualifications 同款）；若 `require_roles`/`Depends`/`get_db` 未在 import 区则照文件既有用法补齐。

- [ ] **Step 4: 运行确认通过**

Run: `cd services/auth-service && python -m pytest tests/test_privacy.py -v`
Expected: 6 passed

- [ ] **Step 5: Commit**

```bash
git add services/auth-service/app/api/doctors.py services/auth-service/tests/test_privacy.py
git commit -m "feat(privacy): 隐私政策公开端点 + 医生个人信息查看（三期 L）"
```

---

### Task 3: 隐私请求提交 + 本人查询

**Files:**
- Modify: `services/auth-service/app/api/privacy.py`（骨架填入创建/me 端点）
- Test: `services/auth-service/tests/test_privacy.py`（追加）

**Interfaces:**
- Consumes: Task 1 的 `PrivacyRequest`/常量；`PaginationParams, paginate`；`get_request_id()`。
- Produces: `POST /api/v1/privacy-requests`（doctor；body `{request_type, detail?, fields?, confirm?}`）→ `success(PrivacyRequest.to_dict())`；`GET /api/v1/privacy-requests/me?status=&page=&page_size=`（doctor）→ `success(paginate(...))`。Task 4/6/7 依赖此形状。

- [ ] **Step 1: 写失败测试**

追加到 `test_privacy.py`：

```python
# ---------- Task 3：提交 + 本人查询 ----------

def test_create_privacy_request_success_with_30d_sla(audit_mock):
    r = client.post("/api/v1/privacy-requests", headers=_token(1, "doctor"),
                    json={"request_type": "export", "detail": "申请导出本人数据"})
    assert r.status_code == 200
    data = r.json()["data"]
    assert data["status"] == "pending"
    assert data["request_type"] == "export"
    deadline = datetime.fromisoformat(data["sla_deadline"])
    assert timedelta(days=29) < (deadline - datetime.utcnow()) <= timedelta(days=31)
    audit_mock.assert_awaited_once()
    assert audit_mock.await_args.kwargs["action"] == "privacy_request_create"


def test_create_invalid_type_400():
    r = client.post("/api/v1/privacy-requests", headers=_token(1, "doctor"),
                    json={"request_type": "destroy"})
    assert r.status_code == 400


def test_create_correct_requires_at_least_one_field():
    r = client.post("/api/v1/privacy-requests", headers=_token(1, "doctor"),
                    json={"request_type": "correct", "fields": {}})
    assert r.status_code == 400


def test_create_correct_phone_format_validated():
    r = client.post("/api/v1/privacy-requests", headers=_token(1, "doctor"),
                    json={"request_type": "correct", "fields": {"phone": "123"}})
    assert r.status_code == 400


def test_create_account_delete_requires_confirm():
    r = client.post("/api/v1/privacy-requests", headers=_token(1, "doctor"),
                    json={"request_type": "account_delete"})
    assert r.status_code == 400
    r2 = client.post("/api/v1/privacy-requests", headers=_token(1, "doctor"),
                     json={"request_type": "account_delete", "confirm": True})
    assert r2.status_code == 200


def test_create_doctor_only_rep_403():
    r = client.post("/api/v1/privacy-requests", headers=_token(3, "rep"),
                    json={"request_type": "view"})
    assert r.status_code == 403


def test_me_lists_only_own_requests_with_pagination():
    db = TestSession()
    for i in range(3):
        db.add(PrivacyRequest(
            doctor_id=1, request_type="view", status="done",
            content={}, sla_deadline=datetime.utcnow() + timedelta(days=30),
        ))
    db.add(PrivacyRequest(
        doctor_id=4, request_type="view", status="pending",
        content={}, sla_deadline=datetime.utcnow() + timedelta(days=30),
    ))
    db.commit()
    db.close()

    r = client.get("/api/v1/privacy-requests/me", headers=_token(1, "doctor"))
    assert r.status_code == 200
    data = r.json()["data"]
    assert data["total"] == 3
    assert all(item["doctor_id"] == 1 for item in data["items"])

    r2 = client.get("/api/v1/privacy-requests/me?status=done", headers=_token(1, "doctor"))
    assert r2.json()["data"]["total"] == 3
    r3 = client.get("/api/v1/privacy-requests/me?status=pending", headers=_token(1, "doctor"))
    assert r3.json()["data"]["total"] == 0
```

注意：doctor_id=4 的请求行——fresh_state 只造了 id 1/2/3 三个用户，FK 在 SQLite 默认不强制（无 PRAGMA foreign_keys），可直接插入；若你选择打开外键，请先补 `User(id=4, ...)`。

- [ ] **Step 2: 运行确认失败**

Run: `cd services/auth-service && python -m pytest tests/test_privacy.py -v -k "create or me_lists"`
Expected: FAIL（404，路由未实现）

- [ ] **Step 3: 实现 privacy.py 提交 + me**

替换 `privacy.py` 全文为：

```python
"""隐私请求（三期 L，需求 3.8(4)(5)/5.7）：提交/本人查询/管理端处理

医生侧行使隐私权利（查阅/更正/删除/导出/注销）走请求工单：
  - 提交/me：仅 role=doctor；
  - 列表/handle：admin/manager/compliance（PRIVACY_ADMIN_ROLES，Task 4）；
  - SLA = 创建时间 + 30 自然日（sla_deadline 落库；超时仅管理端高亮不自动执行）；
  - 审计 action=privacy_request_create / privacy_request_handle。

角色与审计模式移植自 qualifications/doctors；分页复用 PaginationParams。
"""
import logging
import re
from datetime import datetime, timedelta
from typing import Optional

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.orm import Session

from shared.common.auth import require_roles
from shared.common.context import get_request_id
from shared.common.db_session import get_db
from shared.common.pagination import PaginationParams, paginate
from shared.common.response import ParamError, success
from shared.models.privacy import (
    PRIVACY_REQUEST_STATUSES,
    PRIVACY_REQUEST_TYPES,
    PrivacyRequest,
)

from app.services.audit_client import write_audit_log

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/privacy-requests", tags=["privacy-requests"])

PRIVACY_ADMIN_ROLES = ("admin", "manager", "compliance")
SLA_DAYS = 30
PHONE_RE = re.compile(r"^1\d{10}$")


class PrivacyRequestCreate(BaseModel):
    request_type: str
    detail: str = ""
    fields: Optional[dict] = None   # correct 用：{full_name?, phone?} 至少一项
    confirm: bool = False           # account_delete 必须 True


@router.post("")
async def create_privacy_request(
    payload: PrivacyRequestCreate,
    current_user: dict = Depends(require_roles("doctor")),
    db: Session = Depends(get_db),
):
    if payload.request_type not in PRIVACY_REQUEST_TYPES:
        raise ParamError(f"request_type 必须是 {'/'.join(PRIVACY_REQUEST_TYPES)} 之一")
    if len(payload.detail) > 500:
        raise ParamError("detail 最长 500 字")
    fields = payload.fields or {}
    if payload.request_type == "correct":
        if not fields.get("full_name") and not fields.get("phone"):
            raise ParamError("更正申请必须至少提供 full_name/phone 之一")
        if fields.get("phone") and not PHONE_RE.match(str(fields["phone"])):
            raise ParamError("phone 格式不正确（11 位手机号）")
        if fields.get("full_name") and len(str(fields["full_name"])) > 100:
            raise ParamError("full_name 最长 100 字")
    if payload.request_type == "account_delete" and not payload.confirm:
        raise ParamError("注销申请必须先确认（confirm=true）")

    req = PrivacyRequest(
        doctor_id=current_user["id"],
        request_type=payload.request_type,
        status="pending",
        content={"detail": payload.detail, "fields": fields, "confirm": payload.confirm},
        sla_deadline=datetime.utcnow() + timedelta(days=SLA_DAYS),
    )
    db.add(req)
    db.commit()
    db.refresh(req)

    await write_audit_log(
        action="privacy_request_create",
        user_id=current_user["id"],
        resource_type="privacy_request",
        resource_id=str(req.id),
        after_value={"request_type": req.request_type},
        request_id=get_request_id(),
    )
    return success(req.to_dict())


@router.get("/me")
def list_my_privacy_requests(
    status: Optional[str] = None,
    paging: PaginationParams = Depends(),
    current_user: dict = Depends(require_roles("doctor")),
    db: Session = Depends(get_db),
):
    """本人请求分页 + 状态过滤（只能看到自己的）"""
    if status and status not in PRIVACY_REQUEST_STATUSES:
        raise ParamError("status 取值不合法")
    q = db.query(PrivacyRequest).filter(PrivacyRequest.doctor_id == current_user["id"])
    if status:
        q = q.filter(PrivacyRequest.status == status)
    total = q.count()
    items = (
        q.order_by(PrivacyRequest.created_at.desc())
        .offset((paging.page - 1) * paging.page_size)
        .limit(paging.page_size)
        .all()
    )
    return success(paginate([r.to_dict() for r in items], total, paging.page, paging.page_size))
```

- [ ] **Step 4: 运行确认通过**

Run: `cd services/auth-service && python -m pytest tests/test_privacy.py -v`
Expected: 14 passed

- [ ] **Step 5: Commit**

```bash
git add services/auth-service/app/api/privacy.py services/auth-service/tests/test_privacy.py
git commit -m "feat(privacy): 医生隐私请求提交 + 本人查询（30 日 SLA 落库，三期 L）"
```

---

### Task 4: 管理端列表 + handle + 去标识化 + 个人数据包

**Files:**
- Modify: `services/auth-service/app/api/privacy.py`（追加管理端两端点 + 两个内部函数）
- Test: `services/auth-service/tests/test_privacy.py`（追加）

**Interfaces:**
- Consumes: Task 3 的路由/常量；`User`/`DoctorProfile`/`DoctorCertification`（shared 模型）；conversations 表（text() 只读）。
- Produces: `GET /api/v1/privacy-requests?status=&request_type=&page=&page_size=`（PRIVACY_ADMIN_ROLES；每条含 `doctor_name` + `sla_overdue`）→ `success(paginate(...))`；`POST /api/v1/privacy-requests/{id}/handle`（body `{action: processing|done|rejected, response}`）→ `success(请求 to_dict + doctor_name + sla_overdue)`。web Task 6 依赖此形状。

- [ ] **Step 1: 写失败测试**

追加到 `test_privacy.py`：

```python
# ---------- Task 4：管理端列表 + handle ----------

def _add_request(**kw):
    db = TestSession()
    defaults = dict(
        doctor_id=1, request_type="view", status="pending", content={},
        sla_deadline=datetime.utcnow() + timedelta(days=30),
    )
    defaults.update(kw)
    req = PrivacyRequest(**defaults)
    db.add(req)
    db.commit()
    db.close()
    return req


def test_admin_list_requires_admin_roles():
    r = client.get("/api/v1/privacy-requests", headers=_token(3, "rep"))
    assert r.status_code == 403


def test_admin_list_joins_doctor_name_and_flags_sla_overdue():
    _add_request()  # 未超时
    _add_request(status="pending",
                 sla_deadline=datetime.utcnow() - timedelta(days=1))  # 已超时
    _add_request(status="done",
                 sla_deadline=datetime.utcnow() - timedelta(days=1))  # 终态不算超时

    r = client.get("/api/v1/privacy-requests", headers=_token(2, "admin"))
    assert r.status_code == 200
    data = r.json()["data"]
    assert data["total"] == 3
    overdue = [i for i in data["items"] if i["sla_overdue"]]
    assert len(overdue) == 1
    assert data["items"][0]["doctor_name"] == "张医生"


def test_admin_list_filters_by_status_and_type():
    _add_request(request_type="correct")
    _add_request(request_type="export")
    r = client.get("/api/v1/privacy-requests?request_type=export",
                   headers=_token(2, "admin"))
    assert r.json()["data"]["total"] == 1
    r2 = client.get("/api/v1/privacy-requests?status=pending",
                    headers=_token(2, "admin"))
    assert r2.json()["data"]["total"] == 2


def test_handle_requires_response_for_done_and_rejected():
    _add_request()
    r = client.post("/api/v1/privacy-requests/1/handle", headers=_token(2, "admin"),
                    json={"action": "done"})
    assert r.status_code == 400
    r2 = client.post("/api/v1/privacy-requests/1/handle", headers=_token(2, "admin"),
                     json={"action": "bad"})
    assert r2.status_code == 400


def test_handle_nonexistent_request_fails():
    r = client.post("/api/v1/privacy-requests/999/handle", headers=_token(2, "admin"),
                    json={"action": "rejected", "response": "查无此人"})
    assert r.status_code == 400


def test_handle_rejected_keeps_user_untouched(audit_mock):
    _add_request(request_type="delete")
    r = client.post("/api/v1/privacy-requests/1/handle", headers=_token(2, "admin"),
                    json={"action": "rejected", "response": "依法须留存"})
    assert r.status_code == 200
    assert r.json()["data"]["status"] == "rejected"
    db = TestSession()
    u = db.query(User).filter(User.id == 1).first()
    db.close()
    assert u.status == "active" and u.full_name == "张医生"
    audit_mock.assert_awaited_once()


def test_handle_processing_marks_without_response():
    _add_request()
    r = client.post("/api/v1/privacy-requests/1/handle", headers=_token(2, "admin"),
                    json={"action": "processing"})
    assert r.status_code == 200
    assert r.json()["data"]["status"] == "processing"


def test_handle_done_correct_updates_user_fields():
    _add_request(request_type="correct",
                 content={"fields": {"full_name": "张三丰", "phone": "13900000001"}})
    r = client.post("/api/v1/privacy-requests/1/handle", headers=_token(2, "admin"),
                    json={"action": "done", "response": "已更正"})
    assert r.status_code == 200
    db = TestSession()
    u = db.query(User).filter(User.id == 1).first()
    db.close()
    assert u.full_name == "张三丰"
    assert u.phone == "13900000001"


def test_handle_done_account_delete_deidentifies_and_kills_token():
    _add_request(request_type="account_delete")
    r = client.post("/api/v1/privacy-requests/1/handle", headers=_token(2, "admin"),
                    json={"action": "done", "response": "已注销"})
    assert r.status_code == 200

    db = TestSession()
    u = db.query(User).filter(User.id == 1).first()
    db.close()
    assert u.full_name == "已注销医生"
    assert u.phone == "DELETED-1"
    assert u.status == "deleted"
    assert u.deleted_at is not None

    # 旧 token 实时查库被拦（get_current_user status != active → 401）
    r2 = client.get("/api/v1/privacy-requests/me", headers=_token(1, "doctor"))
    assert r2.status_code == 401


def test_handle_done_export_writes_package_json(tmp_path, monkeypatch):
    from shared.models.doctor_profile import DoctorProfile
    Base.metadata.create_all(engine, tables=[DoctorProfile.__table__])
    monkeypatch.setattr(privacy_api, "EXPORT_DIR", str(tmp_path))
    # conversations 表用 DDL 建（模型在 specialist 本地，auth 不 import——这正是
    # 数据包走 text() 只读的原因）
    with engine.begin() as conn:
        conn.execute(text(
            "CREATE TABLE IF NOT EXISTS conversations ("
            "id INTEGER PRIMARY KEY, user_id INTEGER, specialist_id INTEGER, "
            "session_id VARCHAR(100), role VARCHAR(20), content TEXT, "
            "compliance_result JSON, created_at TIMESTAMP)"
        ))
        conn.execute(text(
            "INSERT INTO conversations (user_id, specialist_id, session_id, role, content) "
            "VALUES (1, 9, 's1', 'user', '最近有什么新指南？')"
        ))

    _add_request(request_type="export")
    r = client.post("/api/v1/privacy-requests/1/handle", headers=_token(2, "admin"),
                    json={"action": "done", "response": "数据包已生成，线下交付"})
    assert r.status_code == 200
    file_url = r.json()["data"]["file_url"]
    assert file_url and file_url.endswith("privacy_1.json")

    import json as _json
    with open(file_url, encoding="utf-8") as f:
        pkg = _json.load(f)
    assert pkg["user"]["id"] == 1
    assert pkg["doctor_profile"]["interest_areas"] == ["心血管"]
    assert pkg["conversations"][0]["content"] == "最近有什么新指南？"
    assert pkg["privacy_requests"][0]["id"] == 1


def test_handle_terminal_state_cannot_be_handled_again():
    _add_request(status="done")
    r = client.post("/api/v1/privacy-requests/1/handle", headers=_token(2, "admin"),
                    json={"action": "rejected", "response": "再来一次"})
    assert r.status_code == 400
```

注意：`test_handle_done_export_writes_package_json` 依赖 DoctorProfile 表已建并有一行——把 Task 2 的 `test_personal_data_returns_user_and_profile` 里建画像的 4 行抽成 `_make_profile()` helper 复用（该用例和本用例开头各调一次）。

- [ ] **Step 2: 运行确认失败**

Run: `cd services/auth-service && python -m pytest tests/test_privacy.py -v -k "admin_list or handle"`
Expected: FAIL（404，管理端路由未实现）

- [ ] **Step 3: 实现管理端列表 + handle + 数据包 + 去标识化**

`privacy.py` 追加（import 区补 `json, os`、`from sqlalchemy import text`、`BusinessError`、`User/DoctorProfile/DoctorCertification`）：

```python
EXPORT_DIR = os.path.join("logs", "exports")
CONVERSATION_EXPORT_LIMIT = 5000
HANDLE_ACTIONS = ("processing", "done", "rejected")


class PrivacyRequestHandle(BaseModel):
    action: str          # processing / done / rejected
    response: str = ""   # done/rejected 必填（≤500 字）


def _serialize_admin(req: PrivacyRequest, doctor_name: Optional[str]) -> dict:
    data = req.to_dict()
    data["doctor_name"] = doctor_name
    data["sla_overdue"] = bool(
        req.status in ("pending", "processing")
        and req.sla_deadline
        and req.sla_deadline < datetime.utcnow()
    )
    return data


def _deidentify_user(db: Session, doctor: User) -> None:
    """注销/删除去标识化（需求 3.8(5)，法务拍板不做物理删除）：
    full_name→"已注销医生"、phone→"DELETED-{id}"（嵌 id 防脱敏串互撞）、
    status→"deleted"、deleted_at=now；历史业务数据一律留存不动。
    token 失效由 get_current_user 实时查库（status != active → 401）天然拦截。
    """
    doctor.full_name = "已注销医生"
    doctor.phone = f"DELETED-{doctor.id}"
    doctor.status = "deleted"
    doctor.deleted_at = datetime.utcnow()
    db.commit()


def _build_privacy_package(db: Session, doctor: User, request_id: int) -> str:
    """生成医生个人数据包（export 请求 done 处理的产物）。

    JSON 落 EXPORT_DIR/privacy_<request_id>.json（logs/ 已 gitignore）：
    用户安全字段 + 偏好画像 + 医师认证 + 对话历史 + 隐私请求历史。
    conversation 模型在 specialist-service 本地，auth 不跨服务 import——对话用
    text() 显式列只读查询（同库直读；上限 5000 行；绝不含患者诊断信息）。
    """
    profile = db.query(DoctorProfile).filter(DoctorProfile.doctor_id == doctor.id).first()
    certs = (
        db.query(DoctorCertification)
        .filter(DoctorCertification.doctor_id == doctor.id)
        .order_by(DoctorCertification.id)
        .all()
    )
    conv_rows = db.execute(
        text(
            "SELECT id, specialist_id, session_id, role, content, compliance_result, created_at "
            "FROM conversations WHERE user_id = :uid ORDER BY created_at LIMIT :lim"
        ),
        {"uid": doctor.id, "lim": CONVERSATION_EXPORT_LIMIT},
    ).fetchall()
    history = (
        db.query(PrivacyRequest)
        .filter(PrivacyRequest.doctor_id == doctor.id)
        .order_by(PrivacyRequest.id)
        .all()
    )

    package = {
        "generated_at": datetime.utcnow().isoformat(),
        "request_id": request_id,
        "user": doctor.to_dict(),
        "doctor_profile": profile.to_dict() if profile else None,
        "doctor_certifications": [
            {
                "id": c.id,
                "cert_type": c.cert_type,
                "cert_status": c.cert_status,
                "cert_image_url": c.cert_image_url,
                "created_at": c.created_at.isoformat() if c.created_at else None,
            }
            for c in certs
        ],
        "conversations": [
            {
                "id": r.id,
                "specialist_id": r.specialist_id,
                "session_id": r.session_id,
                "role": r.role,
                "content": r.content,
                "compliance_result": r.compliance_result,
                "created_at": r.created_at.isoformat() if r.created_at else None,
            }
            for r in conv_rows
        ],
        "privacy_requests": [h.to_dict() for h in history],
    }

    os.makedirs(EXPORT_DIR, exist_ok=True)
    path = os.path.join(EXPORT_DIR, f"privacy_{request_id}.json")
    with open(path, "w", encoding="utf-8") as f:
        json.dump(package, f, ensure_ascii=False, indent=2, default=str)
    return path


@router.get("")
def list_privacy_requests(
    status: Optional[str] = None,
    request_type: Optional[str] = None,
    paging: PaginationParams = Depends(),
    current_user: dict = Depends(require_roles(*PRIVACY_ADMIN_ROLES)),
    db: Session = Depends(get_db),
):
    """管理端全量分页（admin/manager/compliance）+ 状态/类型过滤 + 30 日 SLA 超时高亮"""
    if status and status not in PRIVACY_REQUEST_STATUSES:
        raise ParamError("status 取值不合法")
    if request_type and request_type not in PRIVACY_REQUEST_TYPES:
        raise ParamError("request_type 取值不合法")
    q = db.query(PrivacyRequest, User.full_name).join(
        User, PrivacyRequest.doctor_id == User.id
    )
    if status:
        q = q.filter(PrivacyRequest.status == status)
    if request_type:
        q = q.filter(PrivacyRequest.request_type == request_type)
    total = q.count()
    rows = (
        q.order_by(PrivacyRequest.created_at.desc())
        .offset((paging.page - 1) * paging.page_size)
        .limit(paging.page_size)
        .all()
    )
    items = [_serialize_admin(r, name) for r, name in rows]
    return success(paginate(items, total, paging.page, paging.page_size))


@router.post("/{request_id}/handle")
async def handle_privacy_request(
    request_id: int,
    payload: PrivacyRequestHandle,
    current_user: dict = Depends(require_roles(*PRIVACY_ADMIN_ROLES)),
    db: Session = Depends(get_db),
):
    """处理留痕（需求 3.8(4)）：done 落地动作、rejected/processing 只改状态。

    执行语义（仅 done）：correct→更新 user 字段；export→生成数据包 JSON；
    delete/account_delete→去标识化（不做物理删除）。handled_by/handled_at/
    response 必填留痕；审计 action=privacy_request_handle。
    """
    if payload.action not in HANDLE_ACTIONS:
        raise ParamError("action 必须是 processing/done/rejected 之一")
    if payload.action in ("done", "rejected") and not payload.response.strip():
        raise ParamError("处理必须填写回复（response）")
    if len(payload.response) > 500:
        raise ParamError("response 最长 500 字")

    req = db.query(PrivacyRequest).filter(PrivacyRequest.id == request_id).first()
    if not req:
        raise BusinessError("请求不存在")
    if req.status in ("done", "rejected"):
        raise BusinessError("该请求已处理完毕，不能重复处理")

    doctor = db.query(User).filter(
        User.id == req.doctor_id, User.role == "doctor"
    ).first()

    file_url = None
    if payload.action == "done" and doctor:
        if req.request_type == "correct":
            fields = (req.content or {}).get("fields") or {}
            if not fields.get("full_name") and not fields.get("phone"):
                raise BusinessError("更正请求缺少待更正字段，请驳回并让医生重新提交")
            if fields.get("full_name"):
                doctor.full_name = str(fields["full_name"])[:100]
            if fields.get("phone"):
                doctor.phone = str(fields["phone"])
            db.commit()
        elif req.request_type == "export":
            file_url = _build_privacy_package(db, doctor, req.id)
        elif req.request_type in ("delete", "account_delete"):
            _deidentify_user(db, doctor)

    content = dict(req.content or {})
    content["response"] = payload.response
    req.content = content
    req.status = payload.action
    req.handled_by = current_user["id"]
    req.handled_at = datetime.utcnow()
    if file_url:
        req.file_url = file_url
    db.commit()
    db.refresh(req)

    await write_audit_log(
        action="privacy_request_handle",
        user_id=current_user["id"],
        resource_type="privacy_request",
        resource_id=str(req.id),
        after_value={"action": payload.action, "request_type": req.request_type},
        request_id=get_request_id(),
    )
    return success(_serialize_admin(req, doctor.full_name if doctor else None))
```

- [ ] **Step 4: 运行确认通过**

Run: `cd services/auth-service && python -m pytest tests/test_privacy.py -v`
Expected: 25 passed

- [ ] **Step 5: 全量确认**

Run: `cd services/auth-service && python -m pytest tests/ -q`
Expected: 160 passed（基线 135 + 本计划新增 25）

- [ ] **Step 6: Commit**

```bash
git add services/auth-service/app/api/privacy.py services/auth-service/tests/test_privacy.py
git commit -m "feat(privacy): 管理端处理流——更正/数据包/去标识化 + SLA 高亮（三期 L）"
```

---

### Task 5: 网关路由 privacy-requests → auth

**Files:**
- Modify: `services/gateway/app/main.py`（ROUTE_MAP 加一行）
- Test: `services/gateway/tests/test_privacy_routes.py`（新建，照 test_doctor_routes.py 模式）

**Interfaces:**
- Consumes: 既有 ROUTE_MAP / `settings.AUTH_SERVICE_URL`。
- Produces: `/api/v1/privacy-requests/*` 经网关转发 auth-service（JWT 必带）。前端（web/mobile-doctor）依赖。

- [ ] **Step 1: 写失败测试**

Create `services/gateway/tests/test_privacy_routes.py`:

```python
"""privacy-requests 路由（三期 L）：转发到 auth-service，且必须带 JWT

照 test_doctor_routes.py 模式：打桩 httpx，断言转发目标 URL + 方法。
"""
import asyncio
import time
import types

import httpx
import jwt as pyjwt

import app.main as main
from app.main import app
from app.core.auth_middleware import settings as middleware_settings


class _StubResponse:
    status_code = 200
    headers = {"content-type": "application/json"}
    content = b'{"code":0,"message":"success","data":null}'

    def json(self):
        return {"code": 0, "message": "success", "data": None}


class _RecordingClient:
    def __init__(self, log: list):
        self._log = log

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        pass

    async def request(self, method, url, **kwargs):
        self._log.append((method, str(url)))
        return _StubResponse()


def _record_forwarding(monkeypatch) -> list:
    log: list = []
    fake_httpx = types.SimpleNamespace(
        AsyncClient=lambda *a, **k: _RecordingClient(log),
        ConnectError=httpx.ConnectError,
        TimeoutException=httpx.TimeoutException,
        HTTPError=httpx.HTTPError,
    )
    monkeypatch.setattr(main, "httpx", fake_httpx)
    return log


def _auth_headers() -> dict:
    now = int(time.time())
    payload = {"sub": "1", "username": "u", "role": "doctor", "iat": now, "exp": now + 3600}
    token = pyjwt.encode(payload, middleware_settings.JWT_SECRET, algorithm="HS256")
    return {"Authorization": f"Bearer {token}"}


def test_privacy_requests_routes_to_auth_service(monkeypatch):
    log = _record_forwarding(monkeypatch)

    async def _run():
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as c:
            return await c.post(
                "/api/v1/privacy-requests",
                json={"request_type": "export", "detail": "导出"},
                headers=_auth_headers(),
            )

    resp = asyncio.run(_run())
    assert resp.status_code == 200
    assert len(log) == 1
    method, url = log[0]
    assert method == "POST"
    assert url == f"{main.settings.AUTH_SERVICE_URL}/api/v1/privacy-requests"


def test_privacy_requests_requires_jwt():
    async def _run():
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as c:
            return await c.get("/api/v1/privacy-requests/me")

    resp = asyncio.run(_run())
    assert resp.status_code == 401
```

- [ ] **Step 2: 运行确认失败**

Run: `cd services/gateway && python -m pytest tests/test_privacy_routes.py -v`
Expected: FAIL——转发测试 404（ROUTE_MAP 无此前缀；`test_privacy_requests_requires_jwt` 可能因网关先拦 401 而通过，以前者为准）

- [ ] **Step 3: ROUTE_MAP 加一行**

`services/gateway/app/main.py` 的 ROUTE_MAP 中 `"/api/v1/data-exports"` 行后加：

```python
    "/api/v1/privacy-requests": settings.AUTH_SERVICE_URL,  # 隐私请求（三期 L）
```

（`/api/v1/doctors/personal-data`、`/api/v1/doctors/privacy-policy` 复用既有 `"/api/v1/doctors"` 前缀，不需要动。）

- [ ] **Step 4: 运行确认通过 + 全量**

Run: `cd services/gateway && python -m pytest tests/ -q`
Expected: 84 passed（基线 82 + 新增 2）

- [ ] **Step 5: Commit**

```bash
git add services/gateway/app/main.py services/gateway/tests/test_privacy_routes.py
git commit -m "feat(gateway): privacy-requests 前缀转发 auth-service（三期 L）"
```

---

### Task 6: web 隐私请求处理页

**Files:**
- Modify: `web/src/types/index.ts`（加 PrivacyRequest 类型）
- Create: `web/src/services/privacy.ts`
- Create: `web/src/pages/Privacy/PrivacyRequests.tsx`
- Modify: `web/src/App.tsx`（lazy import + Route）
- Modify: `web/src/constants/menu.tsx`（菜单项）

**Interfaces:**
- Consumes: Task 4 的两个端点（`GET /privacy-requests`、`POST /privacy-requests/{id}/handle`）；`client`（web/src/services/client.ts）。
- Produces: `privacyAPI.list(params)` / `privacyAPI.handle(id, data)`；页面路由 `/privacy/requests`。

- [ ] **Step 1: 类型 + API 封装**

`web/src/types/index.ts` 加（照 ExportRequest 先例放一起）：

```ts
export interface PrivacyRequest {
  id: number;
  doctor_id: number;
  doctor_name?: string;
  request_type: 'view' | 'correct' | 'delete' | 'export' | 'account_delete';
  status: 'pending' | 'processing' | 'done' | 'rejected';
  content: {
    detail?: string;
    fields?: { full_name?: string; phone?: string };
    confirm?: boolean;
    response?: string;
  };
  sla_deadline: string | null;
  sla_overdue?: boolean;
  handled_by: number | null;
  handled_at: string | null;
  file_url: string | null;
  created_at: string | null;
}
```

Create `web/src/services/privacy.ts`（导入行照 `dataExports.ts` 头部原样——client 默认导出、类型来自 `../types`）：

```ts
/** 隐私请求处理（三期 L）：管理端列表 + 处理留痕 */
import client from './client';
import type { ApiResponse, PaginatedResponse, PrivacyRequest } from '../types';

export interface PrivacyRequestQuery {
  page?: number;
  page_size?: number;
  status?: string;
  request_type?: string;
}

export interface HandlePayload {
  action: 'processing' | 'done' | 'rejected';
  response?: string;
}

export const privacyAPI = {
  list: (params: PrivacyRequestQuery) =>
    client.get<PaginatedResponse<PrivacyRequest>>('/privacy-requests', { params }),
  handle: (id: number, data: HandlePayload) =>
    client.post<ApiResponse<PrivacyRequest>>(`/privacy-requests/${id}/handle`, data),
};
```

（若 `ApiResponse`/`PaginatedResponse` 的实际导出名与 dataExports.ts 用法有出入，以 dataExports.ts 为准对齐——契约不变。）

- [ ] **Step 2: 页面 PrivacyRequests.tsx**

Create `web/src/pages/Privacy/PrivacyRequests.tsx`（照 DataExports.tsx 的 ProTable + ModalForm 模式）：

```tsx
import { useRef, useState } from 'react';
import { ProTable, ModalForm, ProFormText } from '@ant-design/pro-components';
import type { ProColumns, ActionType } from '@ant-design/pro-components';
import { App, Button, Descriptions, Drawer, Input, Radio, Space, Tag } from 'antd';
import { privacyAPI } from '../../services/privacy';
import type { PrivacyRequest } from '../../types';

const TYPE_MAP: Record<string, { color: string; text: string }> = {
  view: { color: 'default', text: '查阅' },
  correct: { color: 'blue', text: '更正' },
  delete: { color: 'orange', text: '删除' },
  export: { color: 'purple', text: '导出' },
  account_delete: { color: 'red', text: '注销' },
};

const STATUS_MAP: Record<string, { color: string; text: string }> = {
  pending: { color: 'orange', text: '待处理' },
  processing: { color: 'blue', text: '处理中' },
  done: { color: 'green', text: '已完成' },
  rejected: { color: 'red', text: '已驳回' },
};

export default function PrivacyRequests() {
  const actionRef = useRef<ActionType>();
  const { message } = App.useApp();
  const [current, setCurrent] = useState<PrivacyRequest | null>(null);
  const [detail, setDetail] = useState<PrivacyRequest | null>(null);
  const [action, setAction] = useState<'processing' | 'done' | 'rejected'>('done');
  const [response, setResponse] = useState('');
  const [submitting, setSubmitting] = useState(false);

  const openHandle = (row: PrivacyRequest) => {
    setCurrent(row);
    setAction('done');
    setResponse('');
  };

  const submitHandle = async () => {
    if (!current) return;
    if (action !== 'processing' && !response.trim()) {
      message.warning('完成/驳回必须填写回复');
      return;
    }
    setSubmitting(true);
    try {
      await privacyAPI.handle(current.id, { action, response });
      message.success('处理成功');
      setCurrent(null);
      actionRef.current?.reload();
    } catch {
      /* HTTP 错误已由全局拦截器统一弹 toast，此处不重复弹 */
    } finally {
      setSubmitting(false);
    }
  };

  const columns: ProColumns<PrivacyRequest>[] = [
    { title: 'ID', dataIndex: 'id', width: 60, search: false },
    { title: '医生', dataIndex: 'doctor_name', search: false },
    {
      title: '类型',
      dataIndex: 'request_type',
      valueType: 'select',
      valueEnum: Object.fromEntries(
        Object.entries(TYPE_MAP).map(([k, v]) => [k, { text: v.text }]),
      ),
      render: (_, row) => <Tag color={TYPE_MAP[row.request_type]?.color}>{TYPE_MAP[row.request_type]?.text ?? row.request_type}</Tag>,
    },
    {
      title: '状态',
      dataIndex: 'status',
      valueType: 'select',
      valueEnum: Object.fromEntries(
        Object.entries(STATUS_MAP).map(([k, v]) => [k, { text: v.text }]),
      ),
      render: (_, row) => (
        <Space size={4}>
          <Tag color={STATUS_MAP[row.status]?.color}>{STATUS_MAP[row.status]?.text ?? row.status}</Tag>
          {row.sla_overdue && <Tag color="red">SLA 超时</Tag>}
        </Space>
      ),
    },
    {
      title: '申请说明',
      dataIndex: ['content', 'detail'],
      ellipsis: true,
      search: false,
    },
    { title: '申请时间', dataIndex: 'created_at', search: false, width: 170 },
    { title: 'SLA 截止', dataIndex: 'sla_deadline', search: false, width: 170 },
    {
      title: '操作',
      valueType: 'option',
      render: (_, row) => [
        <a key="detail" onClick={() => setDetail(row)}>详情</a>,
        ...(row.status === 'pending' || row.status === 'processing'
          ? [<a key="handle" onClick={() => openHandle(row)}>处理</a>]
          : []),
      ],
    },
  ];

  return (
    <>
      <ProTable<PrivacyRequest>
        headerTitle="隐私请求处理"
        rowKey="id"
        actionRef={actionRef}
        columns={columns}
        search={{ labelWidth: 'auto' }}
        request={async (params) => {
          const res = await privacyAPI.list({
            page: params.current,
            page_size: params.pageSize,
            status: params.status,
            request_type: params.request_type,
          });
          return { data: res.data.data.items, total: res.data.data.total, success: true };
        }}
        rowClassName={(row) => (row.sla_overdue ? 'sla-overdue-row' : ''))}
      />
      <Drawer
        open={!!detail}
        title={`请求 #${detail?.id ?? ''}`}
        width={480}
        onClose={() => setDetail(null)}
      >
        {detail && (
          <Descriptions column={1} size="small" bordered>
            <Descriptions.Item label="医生">{detail.doctor_name ?? detail.doctor_id}</Descriptions.Item>
            <Descriptions.Item label="类型">{TYPE_MAP[detail.request_type]?.text}</Descriptions.Item>
            <Descriptions.Item label="状态">{STATUS_MAP[detail.status]?.text}</Descriptions.Item>
            <Descriptions.Item label="申请说明">{detail.content?.detail || '—'}</Descriptions.Item>
            {detail.content?.fields && (detail.content.fields.full_name || detail.content.fields.phone) && (
              <Descriptions.Item label="待更正字段">
                {detail.content.fields.full_name && <>姓名 → {detail.content.fields.full_name}<br /></>}
                {detail.content.fields.phone && <>手机号 → {detail.content.fields.phone}</>}
              </Descriptions.Item>
            )}
            <Descriptions.Item label="SLA 截止">{detail.sla_deadline ?? '—'}</Descriptions.Item>
            <Descriptions.Item label="处理回复">{detail.content?.response || '—'}</Descriptions.Item>
            <Descriptions.Item label="数据包">{detail.file_url || '—'}</Descriptions.Item>
          </Descriptions>
        )}
      </Drawer>
      <ModalForm
        title={`处理请求 #${current?.id ?? ''}（${current ? TYPE_MAP[current.request_type]?.text : ''}）`}
        open={!!current}
        onFinish={async () => {
          await submitHandle();
          return false; /* 成功时由 submitHandle 关闭，返回 false 阻止自动关 */
        }}
        modalProps={{ onCancel: () => setCurrent(null), confirmLoading: submitting }}
      >
        <Radio.Group
          value={action}
          onChange={(e) => setAction(e.target.value)}
          options={[
            { value: 'done', label: '完成（落地执行）' },
            { value: 'rejected', label: '驳回' },
            { value: 'processing', label: '标记处理中' },
          ]}
        />
        <Input.TextArea
          rows={3}
          maxLength={500}
          value={response}
          onChange={(e) => setResponse(e.target.value)}
          placeholder={
            action === 'done'
              ? '处理回复（必填）：更正已生效 / 数据包已生成，线下交付 / 已注销去标识化…'
              : action === 'rejected'
                ? '驳回原因（必填）：依法须留存 / 信息不符…'
                : '备注（可选）：已联系医生核实中…'
          }
          style={{ marginTop: 12 }}
        />
      </ModalForm>
    </>
  );
}
```

（`sla-overdue-row` 行高亮需最小 CSS——若项目无全局样式文件挂载点，退化为仅 `SLA 超时` 红 Tag，不引新样式文件；以 Tag 为准即可，rowClassName 可删。）

- [ ] **Step 3: 路由 + 菜单**

`web/src/App.tsx`：import 区照 DataExports 样式加 `const PrivacyRequests = lazy(() => import('./pages/Privacy/PrivacyRequests'));`，路由区 `data/exports` 行后加：

```tsx
<Route path="privacy/requests" element={<PrivacyRequests />} />
```

`web/src/constants/menu.tsx`：`{ path: '/data/exports', ... }` 行后加：

```tsx
  { path: '/privacy/requests', name: '隐私请求', icon: <SafetyOutlined /> },
```

（`SafetyOutlined` 已在该文件使用，无需新 import。）

- [ ] **Step 4: 构建验证**

Run: `cd web && npm run build`
Expected: PASS（无 TS 错误）

- [ ] **Step 5: Commit**

```bash
git add web/src/types/index.ts web/src/services/privacy.ts web/src/pages/Privacy/PrivacyRequests.tsx web/src/App.tsx web/src/constants/menu.tsx
git commit -m "feat(web): 隐私请求处理页（SLA 高亮 + 处理留痕，三期 L）"
```

---

### Task 7: mobile-doctor 隐私中心两屏 + 契约测试

**Files:**
- Create: `mobile-doctor/src/api/privacy.ts`
- Create: `mobile-doctor/src/screens/Privacy/PrivacyCenterScreen.tsx`
- Create: `mobile-doctor/src/screens/Privacy/PrivacyRequestsScreen.tsx`
- Modify: `mobile-doctor/src/navigation/types.ts`（RootStackParamList 加两屏）
- Modify: `mobile-doctor/src/navigation/AppNavigator.tsx`（import + Stack.Screen × 2）
- Modify: `mobile-doctor/src/screens/Profile/ProfileScreen.tsx`（「隐私中心」入口）
- Test: `mobile-doctor/src/api/__tests__/privacy-contract.test.ts`（新建）

**Interfaces:**
- Consumes: Task 2 的 policy/personal-data 端点形状；Task 3 的创建/me 端点形状；`apiClient.request`（mobile-doctor/src/api/client.ts）。
- Produces: `privacyAPI.getPrivacyPolicy()/getPersonalData()/createPrivacyRequest(payload)/getMyPrivacyRequests(status?)`。

- [ ] **Step 1: 写失败契约测试**

Create `mobile-doctor/src/api/__tests__/privacy-contract.test.ts`（照 doctor-exp-contract.test.ts 模式）：

```ts
/**
 * 医生端隐私中心 API 契约测试：锁定 URL/method/body。
 *   - getPrivacyPolicy: GET /api/v1/doctors/privacy-policy
 *   - getPersonalData: GET /api/v1/doctors/personal-data
 *   - createPrivacyRequest: POST /api/v1/privacy-requests {request_type, detail, fields, confirm}
 *   - getMyPrivacyRequests: GET /api/v1/privacy-requests/me[?status=]
 */
import { privacyAPI } from '../privacy';

const okResponse = (data: any = {}) => ({ json: async () => ({ code: 0, message: 'success', data }) });
let fetchMock: jest.Mock;
beforeEach(() => { fetchMock = jest.fn().mockResolvedValue(okResponse()); (global as any).fetch = fetchMock; });
function lastCall() { const [url, init] = fetchMock.mock.calls[fetchMock.mock.calls.length - 1]; return { url, init }; }

describe('privacy API', () => {
  it('getPrivacyPolicy 发 GET /api/v1/doctors/privacy-policy', async () => {
    await privacyAPI.getPrivacyPolicy();
    const { url, init } = lastCall();
    expect(url).toContain('/api/v1/doctors/privacy-policy');
    expect(init.method).toBe('GET');
  });

  it('getPersonalData 发 GET /api/v1/doctors/personal-data', async () => {
    await privacyAPI.getPersonalData();
    const { url, init } = lastCall();
    expect(url).toContain('/api/v1/doctors/personal-data');
    expect(init.method).toBe('GET');
  });

  it('createPrivacyRequest 发 POST /api/v1/privacy-requests 带 body', async () => {
    await privacyAPI.createPrivacyRequest({
      request_type: 'correct',
      detail: '手机号换新',
      fields: { phone: '13900000001' },
    });
    const { url, init } = lastCall();
    expect(url).toContain('/api/v1/privacy-requests');
    expect(init.method).toBe('POST');
    expect(JSON.parse(init.body)).toEqual({
      request_type: 'correct',
      detail: '手机号换新',
      fields: { phone: '13900000001' },
    });
  });

  it('createPrivacyRequest 注销带 confirm=true', async () => {
    await privacyAPI.createPrivacyRequest({ request_type: 'account_delete', confirm: true });
    const { init } = lastCall();
    expect(JSON.parse(init.body).confirm).toBe(true);
  });

  it('getMyPrivacyRequests 发 GET /me，可带 status 过滤', async () => {
    await privacyAPI.getMyPrivacyRequests();
    let { url, init } = lastCall();
    expect(url).toContain('/api/v1/privacy-requests/me');
    expect(url).not.toContain('status=');
    expect(init.method).toBe('GET');

    await privacyAPI.getMyPrivacyRequests('done');
    ({ url } = lastCall());
    expect(url).toContain('/api/v1/privacy-requests/me?status=done');
  });
});
```

Run: `cd mobile-doctor && npx jest src/api/__tests__/privacy-contract.test.ts`
Expected: FAIL（Cannot find module '../privacy'）

- [ ] **Step 2: API 封装（实现使 Step 1 的契约测试通过）**

Create `mobile-doctor/src/api/privacy.ts`：

```ts
/**
 * 医生端隐私中心 API（三期 L 端点契约）：
 *   - getPrivacyPolicy: 隐私政策全文（静态文案，公开）
 *   - getPersonalData: 个人信息查看（user + doctor_profile）
 *   - createPrivacyRequest: 发起 更正/导出/删除/注销 申请
 *   - getMyPrivacyRequests: 本人请求分页 + 状态过滤
 *
 * 契约铁律：请求体/响应形状以本文件为唯一映射点（snake_case、分页解包在此做）。
 */
import { apiClient } from './client';
import type { PaginatedResponse } from '../types';

export interface PrivacyPolicy {
  title: string;
  version: string;
  updated_at: string;
  content: string;
}

export interface PersonalData {
  user: {
    id: number;
    username: string;
    full_name: string;
    name: string;
    phone: string | null;
    email: string | null;
    role: string;
    region: string | null;
    status: string;
  };
  doctor_profile: {
    interest_areas: string[] | null;
    preferred_doc_type: string | null;
    preferred_style: string | null;
    closed: boolean;
  } | null;
}

export type PrivacyRequestType = 'view' | 'correct' | 'delete' | 'export' | 'account_delete';
export type PrivacyRequestStatus = 'pending' | 'processing' | 'done' | 'rejected';

export interface PrivacyRequestItem {
  id: number;
  request_type: PrivacyRequestType;
  status: PrivacyRequestStatus;
  content: {
    detail?: string;
    fields?: { full_name?: string; phone?: string };
    response?: string;
  };
  sla_deadline: string | null;
  file_url: string | null;
  created_at: string | null;
}

export interface CreatePrivacyRequestPayload {
  request_type: Exclude<PrivacyRequestType, 'view'>;
  detail?: string;
  fields?: { full_name?: string; phone?: string };
  confirm?: boolean;
}

export const privacyAPI = {
  getPrivacyPolicy: () =>
    apiClient.request<PrivacyPolicy>('GET', '/api/v1/doctors/privacy-policy'),

  getPersonalData: () =>
    apiClient.request<PersonalData>('GET', '/api/v1/doctors/personal-data'),

  createPrivacyRequest: (payload: CreatePrivacyRequestPayload) =>
    apiClient.request<PrivacyRequestItem>('POST', '/api/v1/privacy-requests', payload),

  getMyPrivacyRequests: (status?: PrivacyRequestStatus) =>
    apiClient.request<PaginatedResponse<PrivacyRequestItem>>(
      'GET',
      `/api/v1/privacy-requests/me${status ? `?status=${status}` : ''}`,
    ),
};
```

Run: `cd mobile-doctor && npx jest src/api/__tests__/privacy-contract.test.ts`
Expected: PASS（5 passed）

- [ ] **Step 3: PrivacyCenterScreen**

Create `mobile-doctor/src/screens/Privacy/PrivacyCenterScreen.tsx`（结构照 Preferences/Profile 屏风格：ScrollView + 卡片分节；样式令牌用既有 `Colors/FontSize`）：

```tsx
/**
 * 隐私中心（三期 L，需求 5.7）：隐私政策全文 + 个人信息 + 四类申请入口。
 * 注销需二次确认（Alert.alert 确认后才提交 confirm=true，后端再校验一次）。
 */
import React, { useCallback, useEffect, useState } from 'react';
import {
  ActivityIndicator, Alert, Modal, Pressable, ScrollView, Text, TextInput, View,
} from 'react-native';
import type { NativeStackScreenProps } from '@react-navigation/native-stack';
import { privacyAPI } from '../../api/privacy';
import type { CreatePrivacyRequestPayload, PersonalData, PrivacyPolicy } from '../../api/privacy';
import type { RootStackParamList } from '../../navigation/types';
import { Colors, FontSize } from '../../constants/theme';

type Props = NativeStackScreenProps<RootStackParamList, 'PrivacyCenter'>;

type FormKind = Extract<CreatePrivacyRequestPayload['request_type'], 'correct' | 'export' | 'delete' | 'account_delete'>;

const FORM_META: Record<FormKind, { title: string; hint: string; confirmText?: string }> = {
  correct: { title: '申请更正', hint: '填写要更正为的姓名/手机号（至少一项）' },
  export: { title: '申请导出', hint: '申请导出本人全部数据包，管理端 30 日内处理' },
  delete: { title: '申请删除', hint: '删除采用去标识化处理，依法留存的合规记录不物理删除' },
  account_delete: {
    title: '申请注销',
    hint: '注销后账号不可恢复，个人信息将去标识化',
    confirmText: '注销后账号将无法登录且不可恢复，确认申请注销？',
  },
};

export default function PrivacyCenterScreen({ navigation }: Props) {
  const [policy, setPolicy] = useState<PrivacyPolicy | null>(null);
  const [personal, setPersonal] = useState<PersonalData | null>(null);
  const [loading, setLoading] = useState(true);
  const [formKind, setFormKind] = useState<FormKind | null>(null);
  const [detail, setDetail] = useState('');
  const [fullName, setFullName] = useState('');
  const [phone, setPhone] = useState('');
  const [submitting, setSubmitting] = useState(false);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const [p, d] = await Promise.all([privacyAPI.getPrivacyPolicy(), privacyAPI.getPersonalData()]);
      setPolicy(p);
      setPersonal(d);
    } catch {
      /* 错误已由 client 统一 toast */
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { load(); }, [load]);

  const submit = (kind: FormKind) => {
    const meta = FORM_META[kind];
    const doSubmit = async () => {
      setSubmitting(true);
      try {
        const payload: CreatePrivacyRequestPayload = { request_type: kind, detail };
        if (kind === 'correct' && (fullName || phone)) payload.fields = {};
        if (fullName) payload.fields!.full_name = fullName;
        if (phone) payload.fields!.phone = phone;
        if (kind === 'account_delete') payload.confirm = true;
        await privacyAPI.createPrivacyRequest(payload);
        setFormKind(null);
        setDetail(''); setFullName(''); setPhone('');
        Alert.alert('已提交', '请求已受理，将在 30 日内处理，可在「我的隐私请求」查看进度');
      } catch {
        /* 校验错误由 client 统一 toast */
      } finally {
        setSubmitting(false);
      }
    };

    if (meta.confirmText) {
      Alert.alert('二次确认', meta.confirmText, [
        { text: '取消', style: 'cancel' },
        { text: '确认', style: 'destructive', onPress: () => doSubmit() },
      ]);
      return;
    }
    doSubmit();
  };

  if (loading) {
    return <View style={{ flex: 1, justifyContent: 'center' }}><ActivityIndicator /></View>;
  }

  return (
    <ScrollView style={{ flex: 1, backgroundColor: Colors.background }} contentContainerStyle={{ padding: 16, gap: 16 }}>
      <View style={{ backgroundColor: Colors.card, borderRadius: 12, padding: 16, gap: 8 }}>
        <Text style={{ fontSize: FontSize.lg, fontWeight: '600', color: Colors.textPrimary }}>
          {policy?.title ?? '隐私政策'}（v{policy?.version ?? '—'}）
        </Text>
        <Text style={{ color: Colors.textSecondary, lineHeight: 20 }}>{policy?.content ?? ''}</Text>
      </View>

      <View style={{ backgroundColor: Colors.card, borderRadius: 12, padding: 16, gap: 8 }}>
        <Text style={{ fontSize: FontSize.md, fontWeight: '600', color: Colors.textPrimary }}>个人信息</Text>
        <Text style={{ color: Colors.textSecondary }}>姓名：{personal?.user.full_name ?? '—'}</Text>
        <Text style={{ color: Colors.textSecondary }}>手机号：{personal?.user.phone ?? '—'}</Text>
        <Text style={{ color: Colors.textSecondary }}>地区：{personal?.user.region ?? '—'}</Text>
        <Text style={{ color: Colors.textSecondary }}>
          历史对话：请前往「我的-收藏历史」查看本人问答记录
        </Text>
      </View>

      <View style={{ backgroundColor: Colors.card, borderRadius: 12, padding: 16, gap: 12 }}>
        <Text style={{ fontSize: FontSize.md, fontWeight: '600', color: Colors.textPrimary }}>数据权利申请</Text>
        {(Object.keys(FORM_META) as FormKind[]).map((kind) => (
          <Pressable
            key={kind}
            onPress={() => setFormKind(kind)}
            style={{ padding: 12, borderRadius: 8, backgroundColor: Colors.background }}
          >
            <Text style={{ color: Colors.textPrimary, fontWeight: '500' }}>{FORM_META[kind].title}</Text>
            <Text style={{ color: Colors.textSecondary, fontSize: FontSize.sm, marginTop: 2 }}>
              {FORM_META[kind].hint}
            </Text>
          </Pressable>
        ))}
        <Pressable
          onPress={() => navigation.navigate('PrivacyRequests')}
          style={{ padding: 12, borderRadius: 8, backgroundColor: Colors.background }}
        >
          <Text style={{ color: Colors.primary, fontWeight: '500' }}>我的隐私请求（进度查询）</Text>
        </Pressable>
      </View>

      <Modal visible={!!formKind} transparent animationType="fade" onRequestClose={() => setFormKind(null)}>
        <View style={{ flex: 1, justifyContent: 'center', padding: 24, backgroundColor: 'rgba(0,0,0,0.4)' }}>
          <View style={{ backgroundColor: Colors.card, borderRadius: 12, padding: 16, gap: 10 }}>
            <Text style={{ fontSize: FontSize.md, fontWeight: '600', color: Colors.textPrimary }}>
              {formKind ? FORM_META[formKind].title : ''}
            </Text>
            <TextInput
              value={detail}
              onChangeText={setDetail}
              placeholder="申请说明（可选，500 字内）"
              multiline
              style={{ borderWidth: 1, borderColor: Colors.border, borderRadius: 8, padding: 8, color: Colors.textPrimary }}
            />
            {formKind === 'correct' && (
              <>
                <TextInput
                  value={fullName}
                  onChangeText={setFullName}
                  placeholder="更正为的姓名（与手机号至少填一项）"
                  style={{ borderWidth: 1, borderColor: Colors.border, borderRadius: 8, padding: 8, color: Colors.textPrimary }}
                />
                <TextInput
                  value={phone}
                  onChangeText={setPhone}
                  placeholder="更正为的手机号（11 位）"
                  keyboardType="phone-pad"
                  style={{ borderWidth: 1, borderColor: Colors.border, borderRadius: 8, padding: 8, color: Colors.textPrimary }}
                />
              </>
            )}
            <View style={{ flexDirection: 'row', gap: 12, justifyContent: 'flex-end' }}>
              <Pressable onPress={() => setFormKind(null)} style={{ padding: 8 }}>
                <Text style={{ color: Colors.textSecondary }}>取消</Text>
              </Pressable>
              <Pressable
                onPress={() => formKind && submit(formKind)}
                disabled={submitting}
                style={{ padding: 8 }}
              >
                <Text style={{ color: Colors.primary, fontWeight: '600' }}>{submitting ? '提交中…' : '提交'}</Text>
              </Pressable>
            </View>
          </View>
        </View>
      </Modal>
    </ScrollView>
  );
}
```

（主题令牌名以 `mobile-doctor/src/constants/theme.ts` 实际导出为准——若 `Colors.card/border/primary/background` 命名不同，按该文件对齐；结构不变。）

- [ ] **Step 4: PrivacyRequestsScreen**

Create `mobile-doctor/src/screens/Privacy/PrivacyRequestsScreen.tsx`：

```tsx
/**
 * 我的隐私请求（三期 L）：本人请求列表 + 状态/SLA 展示 + 处理回复。
 */
import React, { useCallback, useEffect, useState } from 'react';
import { ActivityIndicator, FlatList, RefreshControl, Text, View } from 'react-native';
import { privacyAPI } from '../../api/privacy';
import type { PrivacyRequestItem } from '../../api/privacy';
import { Colors, FontSize } from '../../constants/theme';

const STATUS_TEXT: Record<string, { label: string; color: string }> = {
  pending: { label: '待处理', color: '#fa8c16' },
  processing: { label: '处理中', color: '#1677ff' },
  done: { label: '已完成', color: '#52c41a' },
  rejected: { label: '已驳回', color: '#ff4d4f' },
};

const TYPE_TEXT: Record<string, string> = {
  view: '查阅', correct: '更正', delete: '删除', export: '导出', account_delete: '注销',
};

export default function PrivacyRequestsScreen() {
  const [items, setItems] = useState<PrivacyRequestItem[]>([]);
  const [loading, setLoading] = useState(true);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const data = await privacyAPI.getMyPrivacyRequests();
      setItems(data.items ?? []);
    } catch {
      /* 错误已由 client 统一 toast */
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { load(); }, [load]);

  if (loading && items.length === 0) {
    return <View style={{ flex: 1, justifyContent: 'center' }}><ActivityIndicator /></View>;
  }

  return (
    <FlatList
      style={{ flex: 1, backgroundColor: Colors.background }}
      contentContainerStyle={{ padding: 16, gap: 12 }}
      data={items}
      keyExtractor={(item) => String(item.id)}
      refreshControl={<RefreshControl refreshing={loading} onRefresh={load} />}
      ListEmptyComponent={
        <Text style={{ color: Colors.textSecondary, textAlign: 'center', marginTop: 32 }}>
          暂无隐私请求
        </Text>
      }
      renderItem={({ item }) => (
        <View style={{ backgroundColor: Colors.card, borderRadius: 12, padding: 16, gap: 6 }}>
          <View style={{ flexDirection: 'row', justifyContent: 'space-between' }}>
            <Text style={{ fontWeight: '600', color: Colors.textPrimary }}>
              #{item.id} {TYPE_TEXT[item.request_type] ?? item.request_type}
            </Text>
            <Text style={{ color: STATUS_TEXT[item.status]?.color ?? Colors.textSecondary }}>
              {STATUS_TEXT[item.status]?.label ?? item.status}
            </Text>
          </View>
          {item.content?.detail ? (
            <Text style={{ color: Colors.textSecondary }}>{item.content.detail}</Text>
          ) : null}
          {item.content?.fields?.full_name || item.content?.fields?.phone ? (
            <Text style={{ color: Colors.textSecondary }}>
              待更正：{item.content.fields.full_name ?? ''} {item.content.fields.phone ?? ''}
            </Text>
          ) : null}
          {item.content?.response ? (
            <Text style={{ color: Colors.primary }}>回复：{item.content.response}</Text>
          ) : null}
          <Text style={{ color: Colors.textSecondary, fontSize: FontSize.sm }}>
            SLA 截止：{item.sla_deadline ?? '—'}
          </Text>
        </View>
      )}
    />
  );
}
```

- [ ] **Step 5: 导航注册 + Profile 入口**

`mobile-doctor/src/navigation/types.ts` 的 `RootStackParamList` 加：

```ts
  PrivacyCenter: undefined;
  PrivacyRequests: undefined;
```

`mobile-doctor/src/navigation/AppNavigator.tsx`：import 区加

```ts
import PrivacyCenterScreen from '../screens/Privacy/PrivacyCenterScreen';
import PrivacyRequestsScreen from '../screens/Privacy/PrivacyRequestsScreen';
```

`Favorites` 的 `<Stack.Screen>` 后照样式加：

```tsx
            <Stack.Screen
              name="PrivacyCenter"
              component={PrivacyCenterScreen}
              options={{ title: '隐私中心' }}
            />
            <Stack.Screen
              name="PrivacyRequests"
              component={PrivacyRequestsScreen}
              options={{ title: '我的隐私请求' }}
            />
```

`mobile-doctor/src/screens/Profile/ProfileScreen.tsx`：「收藏历史」入口块后照同款样式加一个入口块（label「隐私中心」desc「隐私政策 · 个人信息 · 数据权利申请」），onPress `navigation.navigate('PrivacyCenter')`。

- [ ] **Step 6: 运行确认通过**

Run: `cd mobile-doctor && npx jest`
Expected: 23 passed（基线 18 + 契约新增 5）

- [ ] **Step 7: Commit**

```bash
git add mobile-doctor/src/api/privacy.ts mobile-doctor/src/api/__tests__/privacy-contract.test.ts mobile-doctor/src/screens/Privacy/ mobile-doctor/src/navigation/types.ts mobile-doctor/src/navigation/AppNavigator.tsx mobile-doctor/src/screens/Profile/ProfileScreen.tsx
git commit -m "feat(mobile-doctor): 隐私中心两屏——政策/个人信息/四类申请 + 进度查询（三期 L）"
```

---

### Task 8: 全量回归 + 文档同步

**Files:**
- Modify: `CLAUDE.md`（端点/表/基线/挂账）
- Modify: `README.md`（功能矩阵）

**Interfaces:**
- Consumes: 前 7 个 Task 的全部交付物。
- Produces: 基线更新 + 文档记录（后续任何工作的依据）。

- [ ] **Step 1: 全量后端回归**

```bash
cd services/auth-service && python -m pytest tests/ -q      # 期望 160 passed
cd services/gateway && python -m pytest tests/ -q           # 期望 84 passed
cd services/specialist-service && python -m pytest tests/ -q # 期望 267 passed（不改，抽查无回归）
cd services/compliance-service && python -m pytest tests/ -q # 期望 109 passed（同上）
```

- [ ] **Step 2: 前端验证**

```bash
cd mobile-doctor && npx jest   # 期望 23 passed
cd mobile && npx jest          # 期望 96 passed（不改，抽查无回归）
cd web && npm run build        # 期望 PASS
```

- [ ] **Step 3: 同步 CLAUDE.md + README**

CLAUDE.md：
1. 网关 ROUTE_MAP 段追加：**2026-08-21 隐私中心（三期 L）追加**：`/api/v1/privacy-requests`（→auth，提交/me/管理列表/handle）；`/api/v1/doctors/personal-data|privacy-policy` 复用既有 doctors 前缀。
2. 数据库段追加迁移 023 块（照 022 的行文样式）：`privacy_requests`（doctor_id/request_type view|correct|delete|export|account_delete/status pending|processing|done|rejected/content JSONB/sla_deadline 30 日/handled_by/handled_at/file_url；索引 idx_pr_doctor/idx_pr_status）+ `users.deleted_at`；旧库须执行 023。
3. auth-service 端点清单追加：`GET /api/v1/doctors/privacy-policy`（公开静态文案）、`GET /api/v1/doctors/personal-data`（doctor；user+doctor_profile）、`POST /api/v1/privacy-requests`（doctor；correct 至少一字段+手机号格式、account_delete 须 confirm=true）、`GET /api/v1/privacy-requests/me`、`GET /api/v1/privacy-requests`（admin/manager/compliance；JOIN doctor_name+sla_overdue）、`POST /{id}/handle`（processing/done/rejected；done 落地：correct→改 user、export→logs/exports/privacy_<id>.json 数据包（conversations 走 text() 只读 5000 行上限，**不做在线下载端点，线下交付**）、delete/account_delete→去标识化 full_name="已注销医生"/phone="DELETED-{id}"/status=deleted/deleted_at）。
4. 测试基线更新：auth 160 / gateway 84 / mobile-doctor 23 / web build PASS（其余不变），照既有行文记日期 2026-08-21。
5. 挂账段补一条：隐私请求数据包为服务器本地文件线下交付（未做在线下载端点；如需对称 K 的 blob 直下可后续补）。

README.md：功能矩阵照既有样式补一行隐私中心（医生端隐私政策/个人信息/四类申请 + 管理端 30 日 SLA 处理）。

- [ ] **Step 4: Commit + 推送（主会话执行，先征求用户确认）**

```bash
git add CLAUDE.md README.md
git commit -m "docs: 三期 L 隐私中心文档同步（端点/迁移 023/基线/挂账）"
git log --oneline -8   # 核对本批次提交
```

推送由主会话在用户确认后执行 `git push origin master`（子代理禁止 push）。
