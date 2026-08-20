# 患教专区审核流（三期 M）Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 医生把患教内容分享到平台患教专区，经管理后台审核后专区可见；本人使用与站外转发不经过平台审核流。

**Architecture:** 在二期 I 的 `edu_content_records` 上加 `audit_status`（NULL=未分享/pending/approved/rejected），分享即 `visibility=shared + audit_status=pending`，管理端在 `review-queue` 审核，`zone` 过滤 `shared+approved` 供医生浏览。端点全部在 specialist-service 既有 `patient_edu.py`（网关前缀已存在）。

**Tech Stack:** FastAPI + SQLAlchemy（specialist-service:8001）+ React web + React Native mobile-doctor + SQLite 单测（StaticPool + JSONB compile shim）。

## Global Constraints

- 患教内容**不采集患者诊断/用药**（既有铁律）；专区内容仍标注"AI 生成"（`is_ai_generated`）。
- `audit_status` 值域：`NULL`=未分享 / `pending`=分享待审 / `approved` / `rejected`（对齐需求附录 A 三值 + NULL 表达未分享，见 spec §4 已修正）。
- 权限：`require_roles` 实时查库；管理端 `EDU_ADMIN_ROLES = ("admin","manager","compliance","medical")`；医生端 `"doctor"`。
- 本人使用与站外转发不经过平台审核流（publish 只影响平台专区可见性）。
- 路由顺序：静态路由（`/review-queue`、`/zone`）声明在动态 `/{record_id}/...` 之前；`POST /{record_id}/review` 声明在 `POST /templates/{template_id}/review` 之后（避免 int 转换歧义——FastAPI 会跳过 int 解析失败，但保持清晰）。
- 错误码：ParamError→400 code 1000；BusinessError(4001)→422 code 4001。
- 测试约定：SQLite + StaticPool；`monkeypatch.setitem(app.dependency_overrides, get_db, _override_db)`；`write_audit_log` AsyncMock。
- 验证门：`cd services/specialist-service && python -m pytest tests/ -q`；`cd web && npm run build`；`cd mobile-doctor && npx jest` + `npx tsc --noEmit`。
- **禁止子代理 push 到任何远程**——推 Codeup 由主会话在用户确认后统一执行。

---

### Task 1: 迁移 020 + 模型扩展（EduContentRecord.audit_status + to_dict + init_db 同步）

**Files:**
- Create: `scripts/migrations/020_patient_edu_review.sql`
- Modify: `shared/models/patient_edu.py`
- Modify: `scripts/init_db.sql`
- Test: `services/specialist-service/tests/test_patient_edu.py`

**Interfaces:**
- Produces: `EduContentRecord` 新增列 `audit_status: str|None`（默认 NULL）；`to_dict()` 含 `audit_status`。Task 2-4 依赖。

- [ ] **Step 1: 写迁移 SQL**

Create `scripts/migrations/020_patient_edu_review.sql`:

```sql
-- 020_patient_edu_review.sql
-- 三期 M：患教内容审核流（分享到专区审核，需求 5.5(3)/附录A）
-- NULL=未分享；分享→pending；审核→approved/rejected
-- 用法：docker exec -i medagent-postgres psql -U medagent medagent < scripts/migrations/020_patient_edu_review.sql

\set ON_ERROR_STOP on

ALTER TABLE edu_content_records ADD COLUMN IF NOT EXISTS audit_status VARCHAR(20);
CREATE INDEX IF NOT EXISTS idx_ecr_audit ON edu_content_records(audit_status);
```

- [ ] **Step 2: 扩展模型**

Modify `shared/models/patient_edu.py` 的 `EduContentRecord`：加列 + to_dict 补字段。

```python
    is_ai_generated = Column(Boolean, nullable=False, default=True)
    visibility = Column(String(20), default="private")
    audit_status = Column(String(20))   # 三期 M：NULL=未分享；pending/approved/rejected

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "doctor_id": self.doctor_id,
            "template_id": self.template_id,
            "content": self.content,
            "is_ai_generated": self.is_ai_generated,
            "visibility": self.visibility,
            "audit_status": self.audit_status,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }
```

- [ ] **Step 3: 同步 init_db.sql**

`edu_content_records` CREATE TABLE 块（~616 行）`visibility` 列后补 `audit_status VARCHAR(20)` + `idx_ecr_audit` 索引（与迁移 020 一致）。

- [ ] **Step 4: 写失败测试**

追加到 `test_patient_edu.py`：

```python
def test_to_dict_includes_audit_status():
    db = TestSession()
    rec = EduContentRecord(
        id=1, doctor_id=2, template_id=1,
        content={"title": "高血压患教", "body": "低盐饮食", "notes": "监测血压", "seek_care": "头晕就医"},
        is_ai_generated=True, visibility="shared", audit_status="pending",
    )
    db.add(rec)
    db.commit()
    d = rec.to_dict()
    assert d["audit_status"] == "pending"
    assert d["visibility"] == "shared"
    db.close()
```

- [ ] **Step 5: 运行确认失败**

Run: `cd services/specialist-service && python -m pytest tests/test_patient_edu.py::test_to_dict_includes_audit_status -v`
Expected: FAIL（`'audit_status'` 属性不存在）。

- [ ] **Step 6: 实现并确认通过**

应用 Step 2 模型改动。重跑 Step 5。Expected: PASS。

- [ ] **Step 7: 全量确认**

Run: `cd services/specialist-service && python -m pytest tests/ -q`
Expected: 既有 239 不降。

- [ ] **Step 8: Commit**

```bash
git add scripts/migrations/020_patient_edu_review.sql shared/models/patient_edu.py scripts/init_db.sql services/specialist-service/tests/test_patient_edu.py
git commit -m "feat(edu): 迁移 020 + 模型扩展（患教内容 audit_status）"
```

---

### Task 2: 后端 — 分享到专区 publish + 撤回 unpublish

**Files:**
- Modify: `services/specialist-service/app/api/patient_edu.py`
- Test: `services/specialist-service/tests/test_patient_edu.py`

**Interfaces:**
- Consumes: Task 1 的 `audit_status`。
- Produces: `POST /api/v1/patient-edu/{id}/publish`、`POST /api/v1/patient-edu/{id}/unpublish`（doctor，仅本人）。Task 6 mobile-doctor 依赖。

- [ ] **Step 1: 写失败测试**

追加到 `test_patient_edu.py`（先加 helper `_add_record`）：

```python
def _add_record(**kw):
    db = TestSession()
    defaults = dict(id=kw.pop("id", 1), doctor_id=2, template_id=1,
                    content={"title": "高血压患教", "body": "低盐饮食", "notes": "监测血压", "seek_care": "头晕就医"},
                    is_ai_generated=True, visibility="private", audit_status=None)
    defaults.update(kw)
    db.add(EduContentRecord(**defaults))
    db.commit()
    db.close()
    return defaults["id"]


def test_publish_sets_shared_pending(fresh_state):
    _add_record(id=1)
    resp = client.post("/api/v1/patient-edu/1/publish", json={}, headers=_token(2, "doctor"))
    body = resp.json()
    assert body["code"] == 0
    assert body["data"]["visibility"] == "shared"
    assert body["data"]["audit_status"] == "pending"
    fresh_state.assert_awaited_once()


def test_publish_requires_own_record(fresh_state):
    # 另一名医生（id=4）非本人 → 4001；rep 会先被 require_roles("doctor") 拦成 403
    _add_record(id=1)  # doctor_id=2
    db = TestSession()
    db.add(User(id=4, username="doctor2", full_name="李医生", phone="13800000004", role="doctor", status="active"))
    db.commit()
    db.close()
    resp = client.post("/api/v1/patient-edu/1/publish", json={}, headers=_token(4, "doctor"))
    assert resp.status_code == 422
    assert resp.json()["code"] == 4001


def test_publish_already_shared_4001(fresh_state):
    _add_record(id=1, visibility="shared", audit_status="pending")
    resp = client.post("/api/v1/patient-edu/1/publish", json={}, headers=_token(2, "doctor"))
    assert resp.status_code == 422
    assert resp.json()["code"] == 4001


def test_unpublish_resets_private(fresh_state):
    _add_record(id=1, visibility="shared", audit_status="approved")
    resp = client.post("/api/v1/patient-edu/1/unpublish", json={}, headers=_token(2, "doctor"))
    body = resp.json()
    assert body["code"] == 0
    assert body["data"]["visibility"] == "private"
    assert body["data"]["audit_status"] is None
    fresh_state.assert_awaited_once()


def test_unpublish_requires_shared(fresh_state):
    _add_record(id=1)
    resp = client.post("/api/v1/patient-edu/1/unpublish", json={}, headers=_token(2, "doctor"))
    assert resp.status_code == 422
    assert resp.json()["code"] == 4001
```

- [ ] **Step 2: 运行确认失败**

Run: `cd services/specialist-service && python -m pytest tests/test_patient_edu.py -k "publish or unpublish" -v`
Expected: FAIL（404）。

- [ ] **Step 3: 实现**

在 `patient_edu.py` 的 `mine` 端点之后追加（`/{record_id}/publish` 等动态路由放静态 `/templates`、`/generate`、`/mine` 之后）：

```python
def _get_own_record(db: Session, record_id: int, doctor_id: int) -> EduContentRecord:
    rec = db.query(EduContentRecord).filter(EduContentRecord.id == record_id).first()
    if not rec or rec.doctor_id != doctor_id:
        raise BusinessError("患教记录不存在", code=4001)
    return rec


@router.post("/{record_id}/publish")
async def publish_edu(
    record_id: int,
    current_user: dict = Depends(require_roles("doctor")),
    db: Session = Depends(get_db),
):
    """三期 M：分享到平台患教专区 → visibility=shared + audit_status=pending，进入审核流。
    本人使用与站外转发不经此（5.5(3)）。"""
    rec = _get_own_record(db, record_id, current_user["id"])
    if rec.audit_status is not None:
        raise BusinessError("该内容已在专区审核流中", code=4001)
    rec.visibility = "shared"
    rec.audit_status = "pending"
    db.commit()
    db.refresh(rec)
    await write_audit_log(
        action="edu_publish", user_id=current_user["id"],
        resource_type="edu_content_record", resource_id=str(rec.id),
        after_value={"audit_status": rec.audit_status},
        request_id=get_request_id() or None,
    )
    return success(rec.to_dict())


@router.post("/{record_id}/unpublish")
async def unpublish_edu(
    record_id: int,
    current_user: dict = Depends(require_roles("doctor")),
    db: Session = Depends(get_db),
):
    """三期 M：撤回分享（含已审核通过的内容——撤回后专区不可见）。"""
    rec = _get_own_record(db, record_id, current_user["id"])
    if rec.audit_status is None:
        raise BusinessError("该内容未分享", code=4001)
    rec.visibility = "private"
    rec.audit_status = None
    db.commit()
    db.refresh(rec)
    await write_audit_log(
        action="edu_unpublish", user_id=current_user["id"],
        resource_type="edu_content_record", resource_id=str(rec.id),
        after_value={"audit_status": rec.audit_status},
        request_id=get_request_id() or None,
    )
    return success(rec.to_dict())
```

需在 `patient_edu.py` 顶部 import 加 `from shared.common.context import get_request_id`（如已存在则跳过）。

- [ ] **Step 4: 运行确认通过**

Run: `cd services/specialist-service && python -m pytest tests/test_patient_edu.py -k "publish or unpublish" -v`
Expected: 5 PASS。全量 `python -m pytest tests/ -q` 不降。

- [ ] **Step 5: Commit**

```bash
git add services/specialist-service/app/api/patient_edu.py services/specialist-service/tests/test_patient_edu.py
git commit -m "feat(edu): 患教内容分享到专区 + 撤回（审核流入口）"
```

---

### Task 3: 后端 — 审核队列 review-queue + 审核 review

**Files:**
- Modify: `services/specialist-service/app/api/patient_edu.py`
- Test: `services/specialist-service/tests/test_patient_edu.py`

**Interfaces:**
- Consumes: Task 1/2 的 `audit_status` 状态机。
- Produces: `GET /api/v1/patient-edu/review-queue`（管理四角色，含 `doctor_name`）、`POST /api/v1/patient-edu/{record_id}/review`。Task 5 web 依赖。

- [ ] **Step 1: 写失败测试**

追加到 `test_patient_edu.py`：

```python
def test_review_queue_requires_admin():
    _add_record(id=1, visibility="shared", audit_status="pending")
    resp = client.get("/api/v1/patient-edu/review-queue", headers=_token(2, "doctor"))
    assert resp.status_code == 403
    assert resp.json()["code"] == 3000


def test_review_queue_lists_pending_with_doctor_name(fresh_state):
    _add_record(id=1, visibility="shared", audit_status="pending")
    resp = client.get("/api/v1/patient-edu/review-queue", headers=_token(3, "medical"))
    body = resp.json()
    assert body["code"] == 0
    assert body["data"]["total"] == 1
    item = body["data"]["items"][0]
    assert item["doctor_name"] == "王医生"
    assert item["audit_status"] == "pending"
    assert item["content"]["title"] == "高血压患教"


def test_review_approve(fresh_state):
    _add_record(id=1, visibility="shared", audit_status="pending")
    resp = client.post("/api/v1/patient-edu/1/review", json={"verdict": "approve"},
                       headers=_token(3, "medical"))
    body = resp.json()
    assert body["code"] == 0
    assert body["data"]["audit_status"] == "approved"
    fresh_state.assert_awaited_once()


def test_review_reject_requires_reason(fresh_state):
    _add_record(id=1, visibility="shared", audit_status="pending")
    resp = client.post("/api/v1/patient-edu/1/review", json={"verdict": "reject"},
                       headers=_token(3, "medical"))
    assert resp.status_code == 400
    assert resp.json()["code"] == 1000


def test_review_not_pending_4001(fresh_state):
    _add_record(id=1, visibility="shared", audit_status="approved")
    resp = client.post("/api/v1/patient-edu/1/review", json={"verdict": "reject", "reason": "不合规"},
                       headers=_token(3, "medical"))
    assert resp.status_code == 422
    assert resp.json()["code"] == 4001
```

- [ ] **Step 2: 运行确认失败**

Run: `cd services/specialist-service && python -m pytest tests/test_patient_edu.py -k "review_queue or review" -v`
Expected: FAIL（404）。

- [ ] **Step 3: 实现**

在 `patient_edu.py` 追加（`/review-queue` 静态路由放 `/{record_id}/publish` 之前；`/{record_id}/review` 放 `POST /templates/{template_id}/review` 之后）。需要 `from shared.models.user import User` import：

```python
@router.get("/review-queue")
async def edu_review_queue(
    page: int = 1,
    page_size: int = 20,
    current_user: dict = Depends(require_roles(*EDU_ADMIN_ROLES)),
    db: Session = Depends(get_db),
):
    """三期 M：管理端患教内容审核队列（audit_status=pending，含医生姓名）。"""
    p = PaginationParams(page=page, page_size=page_size)
    q = (
        db.query(EduContentRecord, User.full_name)
        .outerjoin(User, EduContentRecord.doctor_id == User.id)
        .filter(EduContentRecord.audit_status == "pending")
    )
    total = q.count()
    rows = (
        q.order_by(EduContentRecord.id.desc())
        .offset(p.offset).limit(p.limit)
        .all()
    )
    items = []
    for rec, doctor_name in rows:
        d = rec.to_dict()
        d["doctor_name"] = doctor_name
        items.append(d)
    return success(paginate(items, total, p.page, p.page_size))


@router.post("/{record_id}/review")
async def review_edu(
    record_id: int,
    payload: dict,
    current_user: dict = Depends(require_roles(*EDU_ADMIN_ROLES)),
    db: Session = Depends(get_db),
):
    """三期 M：审核患教内容 approve/reject；reject 必填 reason；仅 pending 可审。"""
    rec = db.query(EduContentRecord).filter(EduContentRecord.id == record_id).first()
    if not rec:
        raise BusinessError("患教记录不存在", code=4001)
    if rec.audit_status != "pending":
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
    rec.audit_status = "approved" if verdict == "approve" else "rejected"
    db.commit()
    db.refresh(rec)
    await write_audit_log(
        action="edu_review", user_id=current_user["id"],
        resource_type="edu_content_record", resource_id=str(rec.id),
        after_value={"audit_status": rec.audit_status, "reason": reason or None},
        request_id=get_request_id() or None,
    )
    return success(rec.to_dict())
```

- [ ] **Step 4: 运行确认通过**

Run: `cd services/specialist-service && python -m pytest tests/test_patient_edu.py -k "review_queue or review" -v`
Expected: 5 PASS。全量不降。

- [ ] **Step 5: Commit**

```bash
git add services/specialist-service/app/api/patient_edu.py services/specialist-service/tests/test_patient_edu.py
git commit -m "feat(edu): 患教内容审核队列 + 审核端点"
```

---

### Task 4: 后端 — 患教专区 zone

**Files:**
- Modify: `services/specialist-service/app/api/patient_edu.py`
- Test: `services/specialist-service/tests/test_patient_edu.py`

**Interfaces:**
- Consumes: Task 1 的 `audit_status`。
- Produces: `GET /api/v1/patient-edu/zone`（doctor；shared+approved 分页）。Task 7 mobile-doctor 依赖。

- [ ] **Step 1: 写失败测试**

追加到 `test_patient_edu.py`：

```python
def test_zone_lists_approved_shared(fresh_state):
    _add_record(id=1, visibility="shared", audit_status="approved")
    _add_record(id=2, visibility="shared", audit_status="pending")
    _add_record(id=3, visibility="private", audit_status=None)
    resp = client.get("/api/v1/patient-edu/zone", headers=_token(2, "doctor"))
    body = resp.json()
    assert body["code"] == 0
    assert body["data"]["total"] == 1
    assert body["data"]["items"][0]["id"] == 1
    assert body["data"]["items"][0]["content"]["title"] == "高血压患教"


def test_zone_requires_doctor(fresh_state):
    resp = client.get("/api/v1/patient-edu/zone", headers=_token(1, "rep"))
    assert resp.status_code == 403
    assert resp.json()["code"] == 3000
```

- [ ] **Step 2: 运行确认失败**

Run: `cd services/specialist-service && python -m pytest tests/test_patient_edu.py -k "zone" -v`
Expected: FAIL（404）。

- [ ] **Step 3: 实现**

在 `patient_edu.py` 追加（放在 `/{record_id}/review` 之后）：

```python
@router.get("/zone")
async def edu_zone(
    page: int = 1,
    page_size: int = 20,
    current_user: dict = Depends(require_roles("doctor")),
    db: Session = Depends(get_db),
):
    """三期 M：患教专区——仅 shared + approved 内容可见（审核通过后专区可见）。"""
    p = PaginationParams(page=page, page_size=page_size)
    q = (
        db.query(EduContentRecord)
        .filter(
            EduContentRecord.visibility == "shared",
            EduContentRecord.audit_status == "approved",
        )
    )
    total = q.count()
    rows = q.order_by(EduContentRecord.id.desc()).offset(p.offset).limit(p.limit).all()
    return success(paginate([r.to_dict() for r in rows], total, p.page, p.page_size))
```

- [ ] **Step 4: 运行确认通过**

Run: `cd services/specialist-service && python -m pytest tests/test_patient_edu.py -k "zone" -v`
Expected: 2 PASS。全量不降。

- [ ] **Step 5: Commit**

```bash
git add services/specialist-service/app/api/patient_edu.py services/specialist-service/tests/test_patient_edu.py
git commit -m "feat(edu): 患教专区浏览（approved+shared）"
```

---

### Task 5: web — 患教内容审核页

**Files:**
- Modify: `web/src/services/patientEdu.ts`
- Modify: `web/src/types/index.ts`
- Create: `web/src/pages/PatientEdu/PatientEduReview.tsx`
- Modify: `web/src/App.tsx`、`web/src/constants/menu.tsx`
- Test: 无 jest；验证门 = `cd web && npm run build`

**Interfaces:**
- Consumes: `GET /api/v1/patient-edu/review-queue`、`POST /api/v1/patient-edu/{id}/review`（Task 3）。

- [ ] **Step 1: 类型 + API 扩展**

`web/src/types/index.ts` 加（放在 PatientEduTemplate 接口后）：

```ts
// ========== 患教内容记录（三期 M，GET /patient-edu/zone|review-queue）==========
export interface EduContentRecord {
  id: number;
  doctor_id: number;
  template_id: number | null;
  content: { title: string; body: string; notes: string; seek_care: string };
  is_ai_generated: boolean;
  visibility: 'private' | 'shared';
  audit_status: 'pending' | 'approved' | 'rejected' | null;
  doctor_name?: string | null;
  created_at: string | null;
}
```

`web/src/services/patientEdu.ts` 加：

```ts
  reviewQueue: (params?: { page?: number; page_size?: number }) =>
    client.get<PaginatedResponse<EduContentRecord>>('/patient-edu/review-queue', { params }),
  reviewRecord: (id: number, data: { verdict: 'approve' | 'reject'; reason?: string }) =>
    client.post<ApiResponse<EduContentRecord>>(`/patient-edu/${id}/review`, data),
```

`web/src/types/index.ts` 的 patientEdu.ts import 需补 `EduContentRecord` 类型（按文件顶部 import 模式）。

- [ ] **Step 2: 新页面 PatientEduReview.tsx**

Create `web/src/pages/PatientEdu/PatientEduReview.tsx`：ProTable 数据源 `patientEduAPI.reviewQueue`；columns：标题（`content.title`）/发布医生（`doctor_name`）/AI 生成（Tag）/疾病领域不展示/提交时间/操作（`audit_status==='pending'` 显示「审核」→ Drawer 展示完整 content 卡片 + verdict Radio + reason TextArea → `reviewRecord` → reload）。参照 `PatientEduList.tsx` 与 `SkillList.tsx` 的 Drawer 审核范式（`App.useApp()` message、`actionRef.current?.reload()`）。

- [ ] **Step 3: 路由 + 菜单**

`web/src/App.tsx` 加懒加载路由 `'/patient-edu/review'` → `PatientEduReview`（参照既有 `'/patient-edu/list'` 注册）。`web/src/constants/menu.tsx` 在 `{ path: '/patient-edu/list', name: '患教模板' }` 后加 `{ path: '/patient-edu/review', name: '患教内容', icon: <ReadOutlined /> }`。

- [ ] **Step 4: 构建验证**

Run: `cd web && npm run build`
Expected: 构建成功零错误。

- [ ] **Step 5: Commit**

```bash
git add web/src/types/index.ts web/src/services/patientEdu.ts web/src/pages/PatientEdu/PatientEduReview.tsx web/src/App.tsx web/src/constants/menu.tsx
git commit -m "feat(web): 患教内容审核页（审核队列）"
```

---

### Task 6: mobile-doctor — 分享到专区 + 撤回

**Files:**
- Modify: `mobile-doctor/src/api/doctorExp.ts`
- Modify: `mobile-doctor/src/types/index.ts`
- Modify: `mobile-doctor/src/screens/PatientEdu/PatientEduScreen.tsx`
- Test: `mobile-doctor/src/api/__tests__/doctor-exp-contract.test.ts`

**Interfaces:**
- Consumes: `POST /api/v1/patient-edu/{id}/publish`、`POST /api/v1/patient-edu/{id}/unpublish`（Task 2）。

- [ ] **Step 1: 写失败契约测试**

追加到 `mobile-doctor/src/api/__tests__/doctor-exp-contract.test.ts`（参照该文件既有用例的 `lastCall()` 模式）：

```ts
  it('publishEdu 发 POST /api/v1/patient-edu/1/publish', async () => {
    await doctorExpAPI.publishEdu(1);
    const { url, init } = lastCall();
    expect(url).toContain('/api/v1/patient-edu/1/publish');
    expect(init.method).toBe('POST');
  });

  it('unpublishEdu 发 POST /api/v1/patient-edu/1/unpublish', async () => {
    await doctorExpAPI.unpublishEdu(1);
    const { url, init } = lastCall();
    expect(url).toContain('/api/v1/patient-edu/1/unpublish');
    expect(init.method).toBe('POST');
  });
```

- [ ] **Step 2: 运行确认失败**

Run: `cd mobile-doctor && npx jest doctor-exp-contract`
Expected: FAIL（publishEdu/unpublishEdu 不存在）。

- [ ] **Step 3: api + 类型**

`mobile-doctor/src/api/doctorExp.ts` 的 `doctorExpAPI` 加：

```ts
  publishEdu: (recordId: number) =>
    apiClient.request<EduCard>('POST', `/api/v1/patient-edu/${recordId}/publish`, {}),
  unpublishEdu: (recordId: number) =>
    apiClient.request<EduCard>('POST', `/api/v1/patient-edu/${recordId}/unpublish`, {}),
```

`mobile-doctor/src/types/index.ts` 的 `EduCard` 接口加 `audit_status?: string | null;`。

- [ ] **Step 4: 运行契约测试确认通过**

Run: `cd mobile-doctor && npx jest doctor-exp-contract`
Expected: PASS（+2 用例）。

- [ ] **Step 5: PatientEduScreen 分享/撤回按钮**

`PatientEduScreen.tsx`：`handleGenerate` 成功后 card 即记录对象（`EduCard` 含 audit_status）。在卡片元数据行（AI 生成 badge 旁）按 `card.audit_status` 分支渲染：
- `null`：蓝色按钮「分享到患教专区」→ `handlePublish`（`publishEdu(card.id)` → `setCard(updated)` → Alert 成功 + 提示"已提交审核，通过后专区可见"）
- `'pending'`：橙色 Tag「审核中」+ 按钮「撤回分享」→ `handleUnpublish`（`unpublishEdu(card.id)` → `setCard(updated)`）
- `'approved'`：绿色 Tag「已上架专区」
- `'rejected'`：红色 Tag「未通过审核」+ 按钮「撤回」（unpublish 后重新编辑分享）

加 `publishing` state 防重入。参照 `handleGenerate` 的 `generatingId` 模式。

- [ ] **Step 6: 全量 jest + tsc**

Run: `cd mobile-doctor && npx jest && npx tsc --noEmit`
Expected: 全过（15+2=17）+ 零错误。

- [ ] **Step 7: Commit**

```bash
git add mobile-doctor/src/api/doctorExp.ts mobile-doctor/src/types/index.ts mobile-doctor/src/screens/PatientEdu/PatientEduScreen.tsx mobile-doctor/src/api/__tests__/doctor-exp-contract.test.ts
git commit -m "feat(mobile-doctor): 患教内容分享到专区 + 撤回"
```

---

### Task 7: mobile-doctor — 患教专区浏览屏

**Files:**
- Modify: `mobile-doctor/src/api/doctorExp.ts`
- Create: `mobile-doctor/src/screens/PatientEdu/PatientEduZoneScreen.tsx`
- Modify: `mobile-doctor/src/screens/PatientEdu/PatientEduScreen.tsx`（header 加「患教专区」入口）
- Modify: `mobile-doctor/src/navigation/types.ts`、`mobile-doctor/src/navigation/AppNavigator.tsx`
- Test: `mobile-doctor/src/api/__tests__/doctor-exp-contract.test.ts`

**Interfaces:**
- Consumes: `GET /api/v1/patient-edu/zone`（Task 4）。

- [ ] **Step 1: 写失败契约测试**

追加到 `doctor-exp-contract.test.ts`：

```ts
  it('zoneList 发 GET /api/v1/patient-edu/zone', async () => {
    await doctorExpAPI.zoneList();
    const { url, init } = lastCall();
    expect(url).toContain('/api/v1/patient-edu/zone');
    expect(init.method).toBe('GET');
  });
```

- [ ] **Step 2: 运行确认失败**

Run: `cd mobile-doctor && npx jest doctor-exp-contract`
Expected: FAIL。

- [ ] **Step 3: api**

`doctorExp.ts` 加：

```ts
  zoneList: () =>
    apiClient.request<PaginatedResponse<EduCard>>('GET', '/api/v1/patient-edu/zone'),
```

- [ ] **Step 4: 契约测试确认通过**

Run: `cd mobile-doctor && npx jest doctor-exp-contract`
Expected: PASS。

- [ ] **Step 5: PatientEduZoneScreen**

Create `mobile-doctor/src/screens/PatientEdu/PatientEduZoneScreen.tsx`：进入 `doctorExpAPI.zoneList()` 拉专区卡片；列表渲染每张卡片（标题/AI 生成 badge/正文/注意事项/就医指征——复用 PatientEduScreen 的卡片渲染结构，可用内联组件 `EduCardView`）；空态 + 重试。视觉令牌 `constants/theme.ts`。

- [ ] **Step 6: 导航 + 入口**

`mobile-doctor/src/navigation/types.ts` 加 `PatientEduZone: undefined;`；`AppNavigator.tsx` 注册 `PatientEduZone` → `PatientEduZoneScreen`；`PatientEduScreen.tsx` header（「患教工具」标题旁）加可点「患教专区」→ `navigation.navigate('PatientEduZone')`。

- [ ] **Step 7: 全量 jest + tsc**

Run: `cd mobile-doctor && npx jest && npx tsc --noEmit`
Expected: 全过 + 零错误。

- [ ] **Step 8: Commit**

```bash
git add mobile-doctor/src/api/doctorExp.ts mobile-doctor/src/api/__tests__/doctor-exp-contract.test.ts mobile-doctor/src/screens/PatientEdu/PatientEduZoneScreen.tsx mobile-doctor/src/screens/PatientEdu/PatientEduScreen.tsx mobile-doctor/src/navigation/types.ts mobile-doctor/src/navigation/AppNavigator.tsx
git commit -m "feat(mobile-doctor): 患教专区浏览屏"
```

---

### Task 8: 全量回归 + 文档同步

**Files:**
- Modify: `CLAUDE.md`、`README.md`
- Test: 全量回归

- [ ] **Step 1: 全量后端回归**

Run: `cd services/specialist-service && python -m pytest tests/ -q`
Expected: 239 + 新增（Task 1 +1 / Task 2 +5 / Task 3 +5 / Task 4 +2 = 预计 ~252）。

- [ ] **Step 2: 前端验证**

Run: `cd web && npm run build`；`cd mobile-doctor && npx jest`。
Expected: 全绿。

- [ ] **Step 3: 同步 CLAUDE.md**

三期 M 补记段（`/patient-edu/{id}/publish`、`/unpublish`、`/review-queue`、`/{id}/review`、`/zone`）；Database 段迁移 020（edu_content_records.audit_status + idx_ecr_audit，已并入 init_db.sql，旧库须执行 020）；specialist 基线改实测；mobile-doctor jest 基线改实测；Known Gaps 划掉「患教专区内容审核流（edu_content_records.audit_status 三期启用）→ 三期 M 已交付」类表述、补分享语义（本人使用与站外转发不经审核流）。

- [ ] **Step 4: 同步 README**

功能矩阵加三期 M 行（管理后台患教内容审核；医生端分享到专区 + 专区浏览）。

- [ ] **Step 5: Commit**

```bash
git add CLAUDE.md README.md
git commit -m "docs: 三期 M 患教专区审核流文档同步"
```
