# 医生端 APP + 医师认证 + 医学问答 + 分身订阅（一期 B）实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 落地需求文档（`C:\Users\yuanmenglong\Desktop\AI数字员工架构及功能设计.md` 修订版）一期医生端：新医生端 RN APP（登录/医师资格认证/医学AI问答/分身订阅与知情同意）+ 配套后端（医生角色、认证审核、医学问答、订阅与激活）+ 管理后台认证审核页。**与 C 计划的分界**：B 做链接**接收侧**（share_links 表 + 激活解析 + 订阅 + 知情同意留痕）；C 做链接**生成侧**（创建链接/追踪/夜间简报）。

**Architecture:** 医生账号 = 新角色 `doctor`（复用 auth-service 登录与 RBAC）；`doctor_certifications` / `doctor_twin_subscriptions` / `doctor_consents` / `share_links` 四表走迁移 011；认证端点归 auth-service（复用 A 计划的 OSS+审核模式）；医学问答 = specialist-service 新 `/api/v1/medical/qa`（内部知识检索 → qwen 生成 → 引用/免责声明 → 合规双检 → 审计）；订阅/激活端点归 specialist-service；知识检索经新 internal 端点（网关 INTERNAL_PATHS 双重校验）。医生端为独立 RN 工程 `mobile-doctor/`（RN 0.75，骨架参照 mobile/ 移植，屏幕 UI 参照既有屏范式）。

**Tech Stack:** FastAPI + SQLAlchemy + PostgreSQL（测试 SQLite）/ oss2（auth 已有）；React Native 0.75 + react-navigation 6 + react-native-document-picker（mobile-doctor 新装）；React + AntD（web 认证审核页）。

## Global Constraints

- 提交格式：conventional commits + `Co-Authored-By: Claude <noreply@anthropic.com>`；计划完成后推 origin=Codeup（用户确认）。
- 测试在服务目录下跑；当前基线：auth 96（本机 Redis 起）/ gateway 77 / compliance 104 / specialist 85（本计划增量待测）/ mobile jest 76 / web build。每任务跑全量回归，Task 9 回写基线。
- 响应统一 `{code,message,data}`；权限 `require_roles`（实时查库）；审计 `write_audit_log`（失败不阻断业务）。
- **B/C 边界铁律**：B 只实现链接接收侧。share_links 表在 B 建（迁移 011），**生成链接的端点/管理页/追踪统计全部留 C**——B 的激活测试用 SQL 手工 seed token。
- 知情同意语义（用户已拍板，来自修订版文档 5.3(5)）：首次添加**某位代表**的分身时单独弹窗确认（对话将同步给该代表次日简报 + 平台合规审计）；同代表其他分身不重复弹窗；不同代表各自确认。版本常量 `CONSENT_VERSION = "1.0"`，留痕表 doctor_consents。
- 医生对话"AI 身份明示"：医生端所有对话 UI 必须显示"该分身由 AI 生成"标识（原则四）。
- chat 端点不硬加订阅校验（一期宽松）：订阅表用于前端入口与 C 的简报回传过滤；"未订阅不可 chat"挂账（Known Gaps）。
- 医生端一期用 REST 问答（不做流式）——流式挂账（Known Gaps）。
- 医生端新工程不得引入 mobile/ 之外的新依赖，除：react-native-document-picker（认证上传，装最新不锁版本——audio-record 教训）、复用 mobile 的依赖清单（async-storage/navigation/vector-icons 等）。
- 测试替身惯例同 A/D 计划（SQLite+StaticPool+BigInteger 编译、monkeypatch SessionLocal、fast 文本层断言不烧 LLM）。

## 设计决策（执行前必读）

1. **医生 = 新角色 `doctor`，不复用 medical**：medical 是药企医学部（知识库管理员），语义不可混用。涟漪面已探明：auth users.py `VALID_ROLES`、init_db.sql 注释、web UserList `ROLE_MAP`/valueEnum 两处；`require_roles` 调用方是白名单式不受影响。
2. **医学问答端点任意登录用户可用**（与 specialist /chat 同口径 `get_current_user`），不限定 doctor——产品层医生端入口已限，接口层不重复设限（与既有 /chat 一致）。
3. **内部检索端点**：knowledge/search 是用户端点（get_current_user），服务内调用没有用户 token——新增 `/api/v1/knowledge/search-internal`（`require_internal_key`）+ 网关 INTERNAL_PATHS，复用同款校验与检索逻辑。
4. **医学问答生成**：qwen 直调（specialist 已有 qwen_client），prompt 注入检索片段并要求"只基于片段作答、逐条标注引用标题；片段不足以回答则明说"。引用形状复用 citations 契约 `[{"title","url","doc_id"}]`。免责声明常量随答案返回（前端也强制渲染）。
5. **认证文件存 OSS**（auth-service 已有 oss_client，对象键前缀 `doctor-certs/`）；扩展名 .jpg/.jpeg/.png/.pdf ≤5MB——与 A 计划同口径。
6. **审核端点复用 A 模式**：`audit_status pending/approved/rejected`、驳回必填 reason、仅 pending 可审、审计 action=`doctor_cert_review`。
7. **订阅状态**：`status subscribed/blocked`；block = 暂停推送与对话入口（C 的简报按 status 过滤），可恢复。
8. **深链**：医生端 linking（scheme `medagent-doctor`，path `twin/:token` → 激活页）；C 负责微信侧落地页/下载引导。

## File Structure

**后端/shared**
- Modify: `services/auth-service/app/api/users.py`（VALID_ROLES +doctor）
- Modify: `shared/models/doctor.py`（新建：DoctorCertification / DoctorTwinSubscription / DoctorConsent / ShareLink 四模型）
- Create: `scripts/migrations/011_doctor_platform.sql`；Modify: `scripts/init_db.sql`
- Create: `services/auth-service/app/api/doctors.py`（认证 4 端点）；Modify: auth main.py 注册
- Create: `services/auth-service/tests/test_doctors.py`
- Modify: `services/knowledge-service/app/api/knowledge.py`（search-internal）；Create: `tests/test_search_internal.py`
- Modify: `services/gateway/app/main.py`（ROUTE_MAP + INTERNAL_PATHS）
- Create: `services/specialist-service/app/api/medical.py`（/api/v1/medical/qa）
- Create: `services/specialist-service/app/api/twin_subscriptions.py`（activate/subscriptions/toggle）
- Create: specialist tests `test_medical_qa.py`、`test_twin_subscriptions.py`
- Modify: `services/gateway/tests/test_qualifications_route.py` 同模式 → 新 `tests/test_doctor_routes.py`

**Web**
- Create: `web/src/services/doctorCert.ts`；`web/src/pages/DoctorCert/DoctorCertList.tsx`
- Modify: `web/src/types/index.ts`、`web/src/App.tsx`、`web/src/constants/menu.tsx`

**医生端**
- Create: `mobile-doctor/`（RN 0.75 新工程：package.json/app.json/index.js/android/ios + src/ 骨架）
- 关键屏：`src/screens/Login/LoginScreen.tsx`、`Cert/CertUploadScreen.tsx`、`MedicalQA/MedicalQAScreen.tsx`、`Twin/TwinActivateScreen.tsx`、`Twin/TwinChatScreen.tsx`、`Twin/MyTwinsScreen.tsx`
- `src/api/`（client/auth/doctor/cert/medical/twin）+ `__tests__/doctor-contract.test.ts`
- 深链：AppNavigator linking

**文档**
- Modify: `CLAUDE.md`（Task 9）

---

### Task 1: 医生角色 + 迁移 011（四表）+ init_db.sql 同步

**Files:**
- Modify: `services/auth-service/app/api/users.py`（VALID_ROLES 加 "doctor"）
- Create: `shared/models/doctor.py`
- Create: `scripts/migrations/011_doctor_platform.sql`
- Modify: `scripts/init_db.sql`（users 角色注释 + 四表 DDL）
- Modify: `shared/models/__init__.py`（re-export）
- Test: `services/auth-service/tests/test_doctors.py`（本任务先加角色用例）

**Interfaces:**
- Produces: `DoctorCertification(id, doctor_id FK users.id UNIQUE, cert_type, cert_image_url, cert_status pending/approved/rejected, reject_reason, reviewed_by, reviewed_at, + TimestampMixin)`；`DoctorTwinSubscription(id, doctor_id FK, twin_id FK digital_specialists.id, status subscribed/blocked, consent_version, consent_at, UNIQUE(doctor_id,twin_id), + TimestampMixin)`；`DoctorConsent(id, doctor_id FK, twin_id FK 可空, consent_type='twin', version, agreed_at, + TimestampMixin)`；`ShareLink(id, twin_id FK, url_token String(64) UNIQUE, created_by, expire_at 可空, created_at)`。to_dict 均不含敏感扩展。

- [ ] **Step 1: VALID_ROLES 加 doctor**

`services/auth-service/app/api/users.py:38`：
```python
VALID_ROLES = {"admin", "manager", "rep", "compliance", "medical", "finance", "doctor"}
```
同步 `scripts/init_db.sql` users 表 role 注释行加 `doctor`。

- [ ] **Step 2: 四模型**

创建 `shared/models/doctor.py`（照 TimestampMixin 模式；ShareLink 无 TimestampMixin，显式 id/created_at）：

```python
"""医生端模型（一期 B）：医师认证 / 分身订阅 / 知情同意留痕 / 分享链接"""
from sqlalchemy import BigInteger, Column, DateTime, ForeignKey, String, UniqueConstraint, func
from sqlalchemy.orm import declarative_base

from shared.models.base import Base, TimestampMixin


class DoctorCertification(Base, TimestampMixin):
    __tablename__ = "doctor_certifications"
    doctor_id = Column(BigInteger, ForeignKey("users.id"), unique=True, nullable=False)
    cert_type = Column(String(20), nullable=False)          # physician / practice（资格证/执业证）
    cert_image_url = Column(String(500), nullable=False)    # OSS URL
    cert_status = Column(String(20), default="pending")     # pending/approved/rejected
    reject_reason = Column(String(500))
    reviewed_by = Column(BigInteger)
    reviewed_at = Column(DateTime)

    def to_dict(self) -> dict:
        return {
            "id": self.id, "doctor_id": self.doctor_id, "cert_type": self.cert_type,
            "cert_image_url": self.cert_image_url, "cert_status": self.cert_status,
            "reject_reason": self.reject_reason, "reviewed_by": self.reviewed_by,
            "reviewed_at": self.reviewed_at.isoformat() if self.reviewed_at else None,
        }


class DoctorTwinSubscription(Base, TimestampMixin):
    __tablename__ = "doctor_twin_subscriptions"
    __table_args__ = (UniqueConstraint("doctor_id", "twin_id", name="uq_doctor_twin"),)
    doctor_id = Column(BigInteger, ForeignKey("users.id"), nullable=False)
    twin_id = Column(BigInteger, ForeignKey("digital_specialists.id"), nullable=False)
    status = Column(String(20), default="subscribed")       # subscribed/blocked
    consent_version = Column(String(20), nullable=False)
    consent_at = Column(DateTime, nullable=False)

    def to_dict(self) -> dict:
        return {
            "id": self.id, "doctor_id": self.doctor_id, "twin_id": self.twin_id,
            "status": self.status, "consent_version": self.consent_version,
            "consent_at": self.consent_at.isoformat() if self.consent_at else None,
        }


class DoctorConsent(Base, TimestampMixin):
    __tablename__ = "doctor_consents"
    doctor_id = Column(BigInteger, ForeignKey("users.id"), nullable=False)
    twin_id = Column(BigInteger, ForeignKey("digital_specialists.id"))  # 可空 = 平台级同意
    consent_type = Column(String(20), nullable=False)       # twin / platform
    version = Column(String(20), nullable=False)
    agreed_at = Column(DateTime, nullable=False)

    def to_dict(self) -> dict:
        return {
            "id": self.id, "doctor_id": self.doctor_id, "twin_id": self.twin_id,
            "consent_type": self.consent_type, "version": self.version,
            "agreed_at": self.agreed_at.isoformat() if self.agreed_at else None,
        }


class ShareLink(Base):
    __tablename__ = "share_links"
    id = Column(BigInteger, primary_key=True, autoincrement=True)
    twin_id = Column(BigInteger, ForeignKey("digital_specialists.id"), nullable=False)
    url_token = Column(String(64), unique=True, nullable=False)
    created_by = Column(BigInteger, ForeignKey("users.id"), nullable=False)
    expire_at = Column(DateTime)
    created_at = Column(DateTime, server_default=func.now(), nullable=False)

    def to_dict(self) -> dict:
        return {
            "id": self.id, "twin_id": self.twin_id, "url_token": self.url_token,
            "created_by": self.created_by,
            "expire_at": self.expire_at.isoformat() if self.expire_at else None,
        }
```

`shared/models/__init__.py` 追加四个 import（显式 import，A 计划教训：__all__ 未导出）。

- [ ] **Step 3: 迁移 011**

创建 `scripts/migrations/011_doctor_platform.sql`（\set ON_ERROR_STOP on 头注释风格同 010）：

```sql
-- 011_doctor_platform.sql
-- 一期 B 医生端四表：医师认证 / 分身订阅 / 知情同意留痕 / 分享链接（B 建表，C 做生成侧）
-- 用法：docker exec -i medagent-postgres psql -U medagent medagent < scripts/migrations/011_doctor_platform.sql

\set ON_ERROR_STOP on

CREATE TABLE IF NOT EXISTS doctor_certifications (
    id BIGSERIAL PRIMARY KEY,
    doctor_id BIGINT NOT NULL UNIQUE REFERENCES users(id),
    cert_type VARCHAR(20) NOT NULL,
    cert_image_url VARCHAR(500) NOT NULL,
    cert_status VARCHAR(20) NOT NULL DEFAULT 'pending',
    reject_reason VARCHAR(500),
    reviewed_by BIGINT,
    reviewed_at TIMESTAMP,
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS doctor_twin_subscriptions (
    id BIGSERIAL PRIMARY KEY,
    doctor_id BIGINT NOT NULL REFERENCES users(id),
    twin_id BIGINT NOT NULL REFERENCES digital_specialists(id),
    status VARCHAR(20) NOT NULL DEFAULT 'subscribed',
    consent_version VARCHAR(20) NOT NULL,
    consent_at TIMESTAMP NOT NULL,
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW(),
    CONSTRAINT uq_doctor_twin UNIQUE (doctor_id, twin_id)
);

CREATE TABLE IF NOT EXISTS doctor_consents (
    id BIGSERIAL PRIMARY KEY,
    doctor_id BIGINT NOT NULL REFERENCES users(id),
    twin_id BIGINT REFERENCES digital_specialists(id),
    consent_type VARCHAR(20) NOT NULL,
    version VARCHAR(20) NOT NULL,
    agreed_at TIMESTAMP NOT NULL,
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS share_links (
    id BIGSERIAL PRIMARY KEY,
    twin_id BIGINT NOT NULL REFERENCES digital_specialists(id),
    url_token VARCHAR(64) UNIQUE NOT NULL,
    created_by BIGINT NOT NULL REFERENCES users(id),
    expire_at TIMESTAMP,
    created_at TIMESTAMP DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_dts_doctor ON doctor_twin_subscriptions(doctor_id);
CREATE INDEX IF NOT EXISTS idx_sl_token ON share_links(url_token);
```

- [ ] **Step 4: init_db.sql 同步**

`scripts/init_db.sql`：users 表 role 注释加 doctor；追加与 Step 3 相同的四表 DDL（不带 \set）。

- [ ] **Step 5: 角色用例**

`services/auth-service/tests/test_doctors.py` 先加一条（后续任务追加）：

```python
"""医生端端点测试（角色 / 认证 / 后续任务追加）"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", ".."))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

os.environ.setdefault("JWT_SECRET", "test-secret-not-a-default-value")


def test_valid_roles_includes_doctor():
    from app.api.users import VALID_ROLES
    assert "doctor" in VALID_ROLES
```

- [ ] **Step 6: 回归 + 提交**

Run: `cd services/auth-service && python -m pytest tests/ -q`
Expected: 97 passed（96 + 1）

```bash
git add services/auth-service/app/api/users.py shared/models/doctor.py shared/models/__init__.py scripts/migrations/011_doctor_platform.sql scripts/init_db.sql services/auth-service/tests/test_doctors.py
git commit -m "feat(doctor): doctor 角色 + 一期 B 四表（认证/订阅/同意/分享链接）迁移 011

Co-Authored-By: Claude <noreply@anthropic.com>"
```

---

### Task 2: auth-service 医生认证端点（上传/me/列表/审核）

**Files:**
- Create: `services/auth-service/app/api/doctors.py`
- Modify: `services/auth-service/app/main.py`（注册路由）
- Test: `services/auth-service/tests/test_doctors.py`（追加）

**Interfaces:**
- Consumes: DoctorCertification（Task 1）、auth `_save_upload`（复用 `app/api/qualifications.py::_save_upload`，扩展名白名单改为证书同口径）、`OSSClient`（auth 已有，对象键前缀 `doctor-certs/`）、`_reload_current_user`、`write_audit_log`。
- Produces:
  - `POST /api/v1/doctors/certs`（multipart：cert_image 必传、cert_type Form 必传 ∈ {physician, practice}）——仅 role=doctor；提交重置 cert_status=pending；审计 action=`doctor_cert_submit`。
  - `GET /api/v1/doctors/certs/me` —— 任意登录；无记录 success(None)。
  - `GET /api/v1/doctors/certs?page&page_size&cert_status&keyword` —— require_roles("admin","manager","compliance","medical")；items = to_dict + doctor_name/doctor_phone（join User）。
  - `PUT /api/v1/doctors/certs/{id}/review` —— body `{verdict: approve|reject, reason?}`（reject 必填 reason ≤500，非字符串 → ParamError——A 计划终审修复同款）；仅 pending 可审；BusinessError 4001；审计 action=`doctor_cert_review`。

- [ ] **Step 1: 端点实现**

创建 `services/auth-service/app/api/doctors.py`。关键差异点（相对 qualifications.py 的移植清单）：router prefix `/api/v1/doctors`；角色限制 `current_user["role"] != "doctor"` → PermissionError("仅医生可提交执业资质")；`_save_upload` 从 qualifications import 复用（`from app.api.qualifications import _save_upload`），对象键前缀经 OSSClient 默认（qualifications/）→ **改为在 doctors.py 内包装**：

```python
from app.api.qualifications import _save_upload  # 复用：分块落盘+扩展名/5MB 校验+OSS 上传

async def _save_cert(file: UploadFile) -> str:
    return await _save_upload(file)
```

（OSS 对象键仍为 qualifications/ 前缀——同一 bucket 同前缀可接受，B 计划不新开前缀；如终审要求分离再改。审计写入照 qualifications 模式：before/after 快照含 cert_status。）

其余端点结构逐行参照 `app/api/qualifications.py` 的 me/list/review 三端点（Task 4/5 的 A 计划实现，直接在仓库里读），替换：模型、字段名（filing→cert）、角色集合沿用 `QUAL_ADMIN_ROLES`（从 qualifications import）、审计 action。

- [ ] **Step 2: 注册路由**

`services/auth-service/app/main.py`：`from app.api.doctors import router as doctors_router` + `app.include_router(doctors_router)`。

- [ ] **Step 3: 测试**

`tests/test_doctors.py` 追加（基座照 test_qualifications.py 移植：SQLite 双表 User+DoctorCertification、_FakeOSS、AsyncMock 审计、_token helper、fresh_state autouse fixture 用 monkeypatch.setitem 挂 db 替身）——用例清单（7 条，断言含 HTTP 状态码）：

```python
def test_submit_requires_cert_image_and_type():  # 缺文件/缺 cert_type → 400
def test_submit_creates_pending_row():           # doctor 角色上传 → cert_status=pending, 审计 awaited_once
def test_non_doctor_cannot_submit():             # rep/admin → 403 code 3000
def test_me_returns_row_or_null():               # 有/无记录两分支
def test_list_filters_and_joins():               # admin 列表含 doctor_name；cert_status 过滤；rep → 403
def test_review_approve_and_reject():            # approve 清 reason；reject 存 reason；审计 action
def test_review_reason_non_string_rejected():    # reason=123 → 400（终审修复同款守卫）
```

- [ ] **Step 4: 回归 + 提交**

Run: `cd services/auth-service && python -m pytest tests/ -q`
Expected: 104 passed（97 + 7）

```bash
git add services/auth-service/app/api/doctors.py services/auth-service/app/main.py services/auth-service/tests/test_doctors.py
git commit -m "feat(doctor): 医师认证端点（multipart 上传/me/管理列表/审核）

Co-Authored-By: Claude <noreply@anthropic.com>"
```

---

### Task 3: Web 医生资质审核页

**Files:**
- Create: `web/src/services/doctorCert.ts`、`web/src/pages/DoctorCert/DoctorCertList.tsx`
- Modify: `web/src/types/index.ts`、`web/src/App.tsx`（lazy+路由 `/doctor-cert/list`）、`web/src/constants/menu.tsx`（菜单项「医生认证」，icon 用 `IdcardOutlined`）

**Interfaces:**
- Consumes: Task 2 的列表/review 契约。
- Produces: `doctorCertAPI.list(params)` / `doctorCertAPI.review(id, {verdict, reason})`；`DoctorCert` 类型（字段与 DoctorCertification.to_dict + doctor_name/doctor_phone 对齐）。

- [ ] **Step 1: 页面**

`DoctorCertList.tsx` 结构**逐行参照** `web/src/pages/Filing/FilingList.tsx`（A 计划产物，仓库可读）替换：类型 DoctorCert、列（医生姓名/手机号/证书类型 physician→医师资格证 practice→执业证/审核状态三态 Tag/驳回原因/操作审核）、抽屉（证书图预览用 `<img>` 而非 `<a>` 链接——cert 是图片/PDF，图片直显、PDF 用链接）、审核 Radio+reason+提交（非 pending 禁用）、request 参数（cert_status/keyword）、搜索列 hideInSearch + 仅搜索列 keyword（**A 计划 Task 8 修复的同款写法，照抄该模式**）。

- [ ] **Step 2: 路由/菜单/类型**

同 FilingList 三件套（App.tsx lazy + Route；menu.tsx `IdcardOutlined` import + 菜单项 `/doctor-cert/list`；types/index.ts 加 DoctorCert 接口）。

- [ ] **Step 3: 构建验证 + 提交**

Run: `cd web && npm run build` → exit 0

```bash
git add web/src/services/doctorCert.ts web/src/pages/DoctorCert/DoctorCertList.tsx web/src/types/index.ts web/src/App.tsx web/src/constants/menu.tsx
git commit -m "feat(web): 医生资质审核页（列表 + 审核抽屉）

Co-Authored-By: Claude <noreply@anthropic.com>"
```

---

### Task 4: 知识库 internal 检索端点 + 网关

**Files:**
- Modify: `services/knowledge-service/app/api/knowledge.py`
- Modify: `services/gateway/app/core/auth_middleware.py`（INTERNAL_PATHS 加一行）
- Create: `services/knowledge-service/tests/test_search_internal.py`

**Interfaces:**
- Produces: `POST /api/v1/knowledge/search-internal` —— `Depends(require_internal_key)`（from shared.common.internal_auth），body/校验/返回与 `/search` 完全同款（复用 `validate_search_request` 与 `_manager(db).search`）；网关 INTERNAL_PATHS 加 `"/api/v1/knowledge/search-internal"`（精确/子路径口径）。Task 5 依赖。

- [ ] **Step 1: 端点**

`knowledge.py` 在 `/search` 端点之后追加（内部鉴权换 require_internal_key）：

```python
@router.post("/search-internal")
async def search_knowledge_internal(
    request: dict,
    _key: dict = Depends(require_internal_key),
    db: Session = Depends(get_db),
):
    """服务间检索（specialist medical QA 用）：与 /search 同款校验与检索逻辑，
    鉴权为内部密钥（网关 INTERNAL_PATHS 双重校验）。"""
    data = validate_search_request(request)
    product_id = request.get("product_id")
    if product_id is not None:
        try:
            product_id = int(product_id)
        except (TypeError, ValueError):
            raise ParamError("product_id 必须是整数")
    results, source = await asyncio.to_thread(
        lambda: _manager(db).search(
            query=data["query"], product_id=product_id,
            doc_type=request.get("doc_type"), top_k=data["top_k"],
        )
    )
    return success({"results": results, "source": source,
                    "empty": not results and source != "bailian"})
```

（import 区按 knowledge.py 现状补 `require_internal_key`——先读文件确认 internal_auth 的导入路径与其他服务的用法一致。）

- [ ] **Step 2: 网关 INTERNAL_PATHS**

`services/gateway/app/core/auth_middleware.py` INTERNAL_PATHS 列表加：

```python
    "/api/v1/knowledge/search-internal",
```

- [ ] **Step 3: 测试**

`tests/test_search_internal.py`（照 knowledge-service 既有测试打桩模式，先读 tests/ 下 search 相关测试对齐）：
- 无 X-Internal-Key → 403；有 key → 200 且返回结构含 results/source/empty；
- 校验复用（query 空 → ParamError；top_k 越界 → ParamError）。

- [ ] **Step 4: 回归 + 提交**

Run: `cd services/knowledge-service && python -m pytest tests/ -q`（64 基线 +3 = 67 passed）
Run: `cd services/gateway && python -m pytest tests/ -q`（77 基线；内部路径测试若加用例则 +N，实测为准）

```bash
git add services/knowledge-service/app/api/knowledge.py services/gateway/app/core/auth_middleware.py services/knowledge-service/tests/test_search_internal.py
git commit -m "feat(knowledge): search-internal 服务间检索端点 + 网关内部路径

Co-Authored-By: Claude <noreply@anthropic.com>"
```

---

### Task 5: specialist 医学问答端点 /api/v1/medical/qa

**Files:**
- Create: `services/specialist-service/app/api/medical.py`
- Modify: `services/specialist-service/app/main.py`（注册）
- Modify: `services/gateway/app/main.py`（ROUTE_MAP 加 `"/api/v1/medical": settings.SPECIALIST_SERVICE_URL`）
- Create: `services/specialist-service/tests/test_medical_qa.py`

**Interfaces:**
- Consumes: search-internal（Task 4）、`check_compliance`、`write_audit_log`（specialist 版签名）、`qwen_client`（specialist 已有 app/services/qwen_client.py）。
- Produces: `POST /api/v1/medical/qa` body `{"question": str}`（≤2000 字）→ 任意登录用户；返回 `success({answer, citations:[{title,url,doc_id}], disclaimer, blocked, violations, session_note})`；审计 action=`medical_qa`（ai_involved=True, ai_model="qwen-max"）。

- [ ] **Step 1: 端点**

创建 `services/specialist-service/app/api/medical.py`（核心逻辑完整给出；先读 app/services/qwen_client.py 对齐直调签名，按 end_visit 的 JSON prompt 模式适配为引用型答案）：

```python
"""医生端医学 AI 问答（一期 B）：知识检索 → qwen 生成（仅基于片段）→ 合规双检 → 审计"""
import asyncio
import logging
import os
from typing import Optional

from fastapi import APIRouter, Depends, Request
from sqlalchemy.orm import Session

from shared.common.auth import get_current_user
from shared.common.context import get_request_id
from shared.common.db_session import get_db
from shared.common.response import ParamError, success

from app.services.audit_client import write_audit_log
from app.services.compliance_client import check_compliance

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/medical", tags=["medical"])

MAX_QUESTION_LEN = 2000
DISCLAIMER = "以上内容由 AI 生成，仅供医学专业人士参考，不构成诊疗建议；请以药品说明书与最新指南为准。"
GATEWAY_URL = os.getenv("GATEWAY_URL", "http://localhost:8000")


async def _retrieve(query: str, top_k: int = 5) -> dict:
    """经网关调 search-internal（内部密钥）；失败 fail-open 返回空片段（问答仍可用降级生成）"""
    import httpx
    from shared.common.internal_auth import internal_headers
    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.post(
                f"{GATEWAY_URL}/api/v1/knowledge/search-internal",
                headers=internal_headers(),
                json={"query": query, "top_k": top_k},
            )
            resp.raise_for_status()
            return resp.json().get("data", {})
    except Exception as exc:
        logger.warning("医学问答检索失败（降级为无片段生成）: %s", exc)
        return {"results": [], "source": None, "empty": True}


def _build_prompt(question: str, results: list) -> str:
    """只基于片段作答的 JSON 契约 prompt（引用逐条标注）"""
    snippets = "\n".join(
        f"[{i}] 标题:{r.get('title','')} 内容:{r.get('content','')[:800]}"
        for i, r in enumerate(results or [])
    )
    return (
        "你是医学信息助手。请仅依据以下知识库片段回答问题，"
        "并逐条标注引用编号（如 [0]）。片段不足以回答时明确说明知识库未覆盖，不得编造。\n"
        f"<knowledge_snippets>\n{snippets}\n</knowledge_snippets>\n\n"
        f"<user_content>\n{question}\n</user_content>\n"
        "输出 JSON：{\"answer\": str, \"cited\": [int]}（cited 为引用的片段编号列表）"
    )


@router.post("/qa")
async def medical_qa(
    request: Request,
    payload: dict,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    question = (payload.get("question") or "").strip() if isinstance(payload, dict) else ""
    if not question:
        raise ParamError("question 不能为空")
    if len(question) > MAX_QUESTION_LEN:
        raise ParamError(f"question 长度不能超过 {MAX_QUESTION_LEN} 字符")

    # Step 1 问题合规预检（fast 文本层 + 语义层，命中即拒绝回答）
    pre = await check_compliance(
        question, context={"user_id": current_user["id"], "type": "user_input"},
        service_name="medical",
    )
    if pre.get("blocked"):
        await write_audit_log(
            user_id=current_user["id"], action="medical_qa_blocked",
            resource_type="medical_qa", ai_involved=False,
            compliance_result=pre, request_id=get_request_id() or None,
        )
        return success({
            "answer": "该问题涉及合规限制，无法回答。",
            "citations": [], "disclaimer": DISCLAIMER,
            "blocked": True, "violations": pre.get("violations", []),
        })

    # Step 2 检索 + 生成（qwen 直调丢线程池，不阻塞事件循环）
    retrieved = await _retrieve(question)
    results = retrieved.get("results") or []
    prompt = _build_prompt(question, results)
    from app.services.qwen_client import qwen_chat_json  # 对齐实际导出名（先读该文件确认）
    try:
        generated = await asyncio.to_thread(qwen_chat_json, prompt)
        answer = generated.get("answer", "")
        cited_ids = generated.get("cited", [])
    except Exception as exc:
        logger.error("医学问答生成失败: %s", exc)
        return success({
            "answer": "AI 生成失败，请稍后重试。", "citations": [], "disclaimer": DISCLAIMER,
            "blocked": False, "violations": [],
        })
    citations = []
    for i in cited_ids:
        if isinstance(i, int) and 0 <= i < len(results):
            r = results[i]
            citations.append({
                "title": r.get("title", ""), "url": r.get("url", ""),
                "doc_id": str(r.get("doc_id", "")),
            })

    # Step 3 答案合规审核（fail-closed 由 compliance 服务保证；被拦替换安全话术）
    post = await check_compliance(
        answer, context={"user_id": current_user["id"], "type": "ai_output"},
        service_name="medical",
    )
    if post.get("blocked"):
        answer = "该问题建议直接咨询医学顾问。"
        citations = []

    # Step 4 审计（引用与违规留痕）
    await write_audit_log(
        user_id=current_user["id"], action="medical_qa",
        resource_type="medical_qa", ai_involved=True, ai_model="qwen-max",
        ai_prompt=prompt, ai_response=answer,
        compliance_result=post, request_id=get_request_id() or None,
    )
    return success({
        "answer": answer, "citations": citations, "disclaimer": DISCLAIMER,
        "blocked": bool(post.get("blocked")), "violations": post.get("violations", []),
        "knowledge_empty": bool(retrieved.get("empty")),
    })
```

（`qwen_chat_json` 名称以 qwen_client.py 实际导出为准——计划基于探查的"OpenAI 兼容直调"模式，实现时先读该文件，若无 JSON 契约封装则按 visit-service `_generate_summary_json` 的直调方式在本文件内写一个 `_qwen_json(prompt)`，保持返回 `{"answer","cited"}` 契约。）

- [ ] **Step 2: 网关 ROUTE_MAP**

`services/gateway/app/main.py` ROUTE_MAP 加：`"/api/v1/medical": settings.SPECIALIST_SERVICE_URL,`

- [ ] **Step 3: 测试**

`tests/test_medical_qa.py`（照 test_answer_generator_phases.py 打桩模式：monkeypatch `app.api.medical.check_compliance`/`write_audit_log`/`_retrieve`/qwen 生成函数 + FakeSession/依赖覆盖）——用例（6 条）：

```python
def test_empty_question_param_error()
def test_question_too_long_param_error()
def test_question_blocked_returns_safe_answer_and_audit()   # 预检 blocked → 合规话术 + medical_qa_blocked 审计
def test_qa_cites_only_retrieved_snippets()                 # cited=[0,2] → citations 恰 2 条且标题对应
def test_generation_failure_returns_graceful_message()      # 生成异常 → "AI 生成失败" 不 500
def test_answer_blocked_masked_and_audited()                # 后检 blocked → 掩码话术 + medical_qa 审计
```

- [ ] **Step 4: 回归 + 提交**

Run: `cd services/specialist-service && python -m pytest tests/ -q`（85 基线 +6 = 91 passed）
Run: `cd services/gateway && python -m pytest tests/ -q`（77 基线，若加路由用例则 +N）

```bash
git add services/specialist-service/app/api/medical.py services/specialist-service/app/main.py services/gateway/app/main.py services/specialist-service/tests/test_medical_qa.py
git commit -m "feat(medical): 医生端医学问答端点（检索+生成+引用+合规双检+审计）

Co-Authored-By: Claude <noreply@anthropic.com>"
```

---

### Task 6: 分身订阅 + 激活端点（specialist）

**Files:**
- Create: `services/specialist-service/app/api/twin_subscriptions.py`
- Modify: `services/specialist-service/app/main.py`（注册）
- Modify: `services/gateway/app/main.py`（ROUTE_MAP 加 `"/api/v1/twin-subscriptions"` 与 `"/api/v1/share-links"` → SPECIALIST_SERVICE_URL）
- Create: `services/specialist-service/tests/test_twin_subscriptions.py`
- Create: `services/gateway/tests/test_doctor_routes.py`

**Interfaces:**
- Consumes: DoctorTwinSubscription/DoctorConsent/ShareLink（Task 1）、Specialist 模型。
- Produces:
  - `POST /api/v1/share-links/{token}/activate` —— 任意登录；token 不存在/过期 → BusinessError 4001"链接不存在或已过期"；返回 `{twin: {id,name,status}, subscribed: bool, subscription_status}`（twin 信息不含 bailian_app_id 等内部字段——手写返回 dict）。
  - `POST /api/v1/twin-subscriptions` body `{twin_id: int, consent_agreed: bool, link_token?: str}` —— 任意登录；twin 必须 active（不存在/停用 → BusinessError 4001）；`consent_agreed != True` → ParamError"须先签署知情同意"；已订阅同 twin → 幂等返回现有订阅（不重复写 consent）；新建：写 DoctorConsent（version=CONSENT_VERSION, consent_type='twin'）+ DoctorTwinSubscription（status=subscribed）；审计 action=`twin_subscribe`。
  - `GET /api/v1/twin-subscriptions` —— 本人订阅列表（join Specialist，items = {subscription to_dict, twin_name, twin_status}）。
  - `POST /api/v1/twin-subscriptions/{twin_id}/toggle` body `{status: "subscribed"|"blocked"}` —— 只允许本人已存在的订阅行；审计 action=`twin_subscription_toggle`。
  - 常量：`CONSENT_VERSION = "1.0"`。

- [ ] **Step 1: 端点**

创建 `services/specialist-service/app/api/twin_subscriptions.py`（完整逻辑按上述契约；知情同意语义注释写明"同代表多分身不重复弹窗"由前端按 representative 维度控制，后端只留痕每次 subscribe 的 consent 记录）。激活端点对 ShareLink 的校验：`db.query(ShareLink).filter(ShareLink.url_token == token).first()`；`expire_at and expire_at < datetime.utcnow()` → 4001。

- [ ] **Step 2: 注册 + 网关**

main.py 注册；ROUTE_MAP 加两行（见 Interfaces）。

- [ ] **Step 3: 测试**

`tests/test_twin_subscriptions.py`（FakeSession 或 SQLite 双表模式，照 specialist 既有测试风格）——用例（8 条）：

```python
def test_activate_returns_twin_and_subscribed_flag()
def test_activate_unknown_or_expired_token_4001()
def test_subscribe_requires_consent()                    # consent_agreed 缺失/False → 400
def test_subscribe_creates_subscription_and_consent()    # 订阅行 + consent 行 + 审计
def test_subscribe_idempotent_for_same_twin()            # 重复订阅不建第二行、consent 不重复
def test_subscribe_inactive_twin_4001()
def test_list_returns_own_subscriptions_joined()
def test_toggle_block_and_restore_audited()
```

`tests/test_doctor_routes.py`（gateway，照 test_qualifications_route.py 模式）：`/api/v1/medical/qa` 与 `/api/v1/share-links/abc/activate` 转发到 specialist（+2 用例）。

- [ ] **Step 4: 回归 + 提交**

Run: `cd services/specialist-service && python -m pytest tests/ -q`（91 +8 = 99 passed）
Run: `cd services/gateway && python -m pytest tests/ -q`（77 +2 = 79 passed）

```bash
git add services/specialist-service/app/api/twin_subscriptions.py services/specialist-service/app/main.py services/gateway/app/main.py services/specialist-service/tests/test_twin_subscriptions.py services/gateway/tests/test_doctor_routes.py
git commit -m "feat(twin): 分身订阅与链接激活端点（知情同意留痕）

Co-Authored-By: Claude <noreply@anthropic.com>"
```

---

### Task 7: mobile-doctor 新工程 + 骨架

**Files:**
- Create: `mobile-doctor/`（RN 0.75 工程：package.json、app.json、index.js、babel.config.js、metro.config.js、jest.config.js、jest.setup.js、tsconfig.json、android/、ios/、src/ 骨架）

**Interfaces:**
- Produces: 可构建的医生端工程（`cd mobile-doctor/android && ./gradlew assembleDebug` BUILD SUCCESSFUL）；骨架文件：`src/config.ts`（同 mobile 的 DEV_HOST 模式，scheme 常量）、`src/api/client.ts`（**从 mobile 原样拷贝**，`medagent_token` 存储键一致）、`src/api/auth.ts`（login/sendCode/getProfile，同 mobile）、`src/constants/theme.ts`（从 mobile 拷贝）、`src/components/Icon.tsx`（从 mobile 拷贝）、`src/store/AuthContext.tsx`（从 mobile 拷贝改：refreshProfile 保留）、`src/navigation/AppNavigator.tsx`（Stack：Login + MainTabs[问答/分身/我的] + TwinActivate/TwinChat/CertUpload；linking 配置见 Task 9）、`src/navigation/types.ts`。

- [ ] **Step 1: 生成工程**

Run: `cd d:/gongsi/medical system && npx @react-native-community/cli@latest init MobileDoctor --version 0.75.0 --directory mobile-doctor --skip-git-init --skip-install`
（若 init 网络失败：从 mobile/ 手工复制工程骨架——android/ios/package.json/babel/metro/tsconfig/index.js/app.json，改 app.json name 为 `MedAgentDoctor`、displayName、包名 `com.medagent.doctor`、MainActivity/MainApplication 包路径——报告里说明采用哪条路径。）
Run: `cd mobile-doctor && npm install` + 安装 mobile 同款依赖清单（async-storage/navigation 三件套/safe-area/screens/vector-icons）——版本号抄 mobile/package.json。

- [ ] **Step 2: 骨架移植**

按 Interfaces 清单从 mobile/src 拷贝/改（client.ts 一字不改；theme/Icon 一字不改；AuthContext 改登录后跳转 Tab）。App 显示名「MedAgent·医生端」。

- [ ] **Step 3: 构建验证 + 提交**

Run: `cd mobile-doctor/android && ./gradlew assembleDebug` → BUILD SUCCESSFUL
Run: `cd mobile-doctor && npx tsc --noEmit` → 零错误

```bash
git add mobile-doctor/
git commit -m "feat(mobile-doctor): 医生端 RN 工程骨架（登录/问答/分身/我的 四屏位）

Co-Authored-By: Claude <noreply@anthropic.com>"
```

---

### Task 8: 医生端屏幕 + 契约测试

**Files:**
- Create: `mobile-doctor/src/api/`（doctor.ts: cert 上传+me；medical.ts: qa；twin.ts: activate/subscribe/list/toggle）
- Create: `mobile-doctor/src/api/__tests__/doctor-contract.test.ts`
- Create: `mobile-doctor/src/screens/Login/LoginScreen.tsx`、`Cert/CertUploadScreen.tsx`、`MedicalQA/MedicalQAScreen.tsx`、`Twin/TwinActivateScreen.tsx`、`Twin/TwinChatScreen.tsx`、`Twin/MyTwinsScreen.tsx`
- Modify: `mobile-doctor/src/navigation/`（注册六屏）

**Interfaces:**
- Consumes: Task 2/5/6 端点契约；mobile-doctor 骨架（Task 7）。
- 屏幕 UI 参照表（实现者先读 mobile/ 对应屏，逐屏对齐视觉范式）：Login→mobile/src/screens/Login、CertUpload→mobile/src/screens/Compliance/ComplianceCenterScreen（表单+DocumentPicker 模式）、MedicalQA/TwinChat→mobile/src/screens/Chat/ChatScreen（气泡+引用渲染+加载态）、MyTwins→mobile/src/screens/Specialists（列表卡片）、TwinActivate→登录后落地页（激活+订阅+知情同意弹窗）。

- [ ] **Step 1: API 层 + 契约测试**

`doctor.ts`（multipart 上传走 client.upload——**client.ts 的 upload 方法必须随 Task 7 拷贝保留**，若丢失先补）：

```ts
export const doctorAPI = {
  submitCert: (payload: { cert_type: 'physician' | 'practice'; cert: { uri: string; name: string; type: string } }) => {
    const fd = new FormData();
    fd.append('cert_type', payload.cert_type);
    fd.append('cert_image', payload.cert as any);
    return apiClient.upload<DoctorCert>('/api/v1/doctors/certs', fd);
  },
  getMyCert: () => apiClient.request<DoctorCert | null>('GET', '/api/v1/doctors/certs/me'),
};

export const medicalAPI = {
  qa: (question: string) => apiClient.request<MedicalAnswer>('POST', '/api/v1/medical/qa', { question }),
};

export const twinAPI = {
  activate: (token: string) => apiClient.request<TwinActivateResult>('POST', `/api/v1/share-links/${token}/activate`, {}),
  subscribe: (twinId: number) => apiClient.request<TwinSubscription>('POST', '/api/v1/twin-subscriptions', { twin_id: twinId, consent_agreed: true }),
  list: () => apiClient.request<{ items: TwinSubscriptionItem[] }>('GET', '/api/v1/twin-subscriptions', undefined),
  toggle: (twinId: number, status: 'subscribed' | 'blocked') =>
    apiClient.request<TwinSubscription>('POST', `/api/v1/twin-subscriptions/${twinId}/toggle`, { status }),
};
```

契约测试锁：URL/method/body（含 FormData 字段与 consent_agreed: true）——照 mobile/src/api/__tests__/qualification-contract.test.ts 模式（FDLike 类型技巧同款），6 条用例。

- [ ] **Step 2: 知情同意弹窗（关键逻辑完整给出）**

TwinActivateScreen 核心（Modal + 确认按钮；**按代表维度去重**：后端 subscribe 返回后由"该代表是否已首次确认"判断是否弹窗——一期简化：每次从链接激活都弹，列表内已订阅的直接进对话；文档 5.3(5) 的"同代表不重复"由 activation 结果 subscribed=true 时跳过弹窗实现）：

```tsx
const activate = async (token: string) => {
  const res = await twinAPI.activate(token);          // {twin, subscribed}
  if (res.subscribed) {
    navigation.replace('TwinChat', { twinId: res.twin.id, twinName: res.twin.name });
    return;
  }
  setPendingTwin(res.twin);                            // 弹知情同意 Modal
};

// Modal 文案（逐字）：
// 标题：知情同意
// 正文：您即将添加数字员工「{name}」。与该数字员工的对话内容将同步给
//       该数字员工所属医药代表（用于次日简报）及平台合规审计。
//       该数字员工由 AI 生成，其回答不构成诊疗建议。
// 按钮：同意并添加 / 暂不添加
const agree = async () => {
  await twinAPI.subscribe(pendingTwin.id);             // consent_agreed: true 已含
  navigation.replace('TwinChat', { twinId: pendingTwin.id, twinName: pendingTwin.name });
};
```

- [ ] **Step 3: 其余屏幕**

- MedicalQAScreen：输入框+发送；渲染 `answer` + 引用列表（title 可点/纯展示）+ **强制显示 disclaimer 与"AI 生成"标识**（blocked 态渲染安全话术+违规提示）。MyTwinsScreen：list → 卡片（名称/状态/blocked 置灰）+ 进入对话/屏蔽切换。TwinChatScreen：**顶部常驻"该分身由 AI 生成"标识条**；REST 发 question 走 `POST /api/v1/specialists/{id}/chat`（复用 mobile ChatScreen 的 api 层映射逻辑，twin 对话无流式）。CertUploadScreen：cert_type 选择 + DocumentPicker + 提交 + 审核状态回显（pending/approved/rejected+原因）——照 ComplianceCenterScreen 模式。
- UI 令牌/图标沿用 Task 7 拷贝的 theme/Icon；每屏头部带返回按钮 + paddingTop 50（A 计划 Task 10 终审教训，**不要**再踩）。

- [ ] **Step 4: 验证 + 提交**

Run: `cd mobile-doctor && npx tsc --noEmit`（零错误）→ `cd mobile-doctor && npx jest`（6 契约用例）→ `cd mobile-doctor/android && ./gradlew assembleDebug`（BUILD SUCCESSFUL）

```bash
git add mobile-doctor/src/
git commit -m "feat(mobile-doctor): 登录/认证上传/医学问答/分身激活与对话 + 契约测试

Co-Authored-By: Claude <noreply@anthropic.com>"
```

---

### Task 9: 深链 + 全量回归 + CLAUDE.md + 推送

**Files:**
- Modify: `mobile-doctor/src/navigation/AppNavigator.tsx`（linking）
- Modify: `CLAUDE.md`

- [ ] **Step 1: 深链**

AppNavigator 的 NavigationContainer 加 linking（react-navigation v6）：

```tsx
const linking = {
  prefixes: ['medagent-doctor://'],
  config: {
    screens: {
      TwinActivate: 'twin/:token',
    },
  },
};
// <NavigationContainer linking={linking} ...>
```

Android 侧 scheme 注册：`mobile-doctor/android/app/src/main/AndroidManifest.xml` MainActivity intent-filter 加 `<data android:scheme="medagent-doctor" />`（iOS 待有 Xcode 环境，挂账）。types.ts 的 TwinActivate 参数改 `{ token?: string }`（linking 传入 string 类型，注意 react-navigation 深链参数为 string）。

- [ ] **Step 2: 全量回归**

Run: `cd services/auth-service && python -m pytest tests/ -q`（预期 104）
Run: `cd services/specialist-service && python -m pytest tests/ -q`（预期 99）
Run: `cd services/knowledge-service && python -m pytest tests/ -q`（预期 67）
Run: `cd services/gateway && python -m pytest tests/ -q`（预期 79）
Run: `cd mobile && npx jest`（76 不变——B 未动 mobile/）
Run: `cd mobile-doctor && npx jest`（6）
Run: `cd web && npm run build`（exit 0）
Run: `cd mobile-doctor/android && ./gradlew assembleDebug`（BUILD SUCCESSFUL）
（数字以实测为准，Task 2/5/6 若加了超出计划的用例按实测回写。）

- [ ] **Step 3: CLAUDE.md 同步**

1. 架构段：三端描述补医生端（mobile-doctor/）；网关 ROUTE_MAP 补三行（medical/twin-subscriptions/share-links）+ INTERNAL_PATHS 补 search-internal。
2. 服务端点补记：auth `/api/v1/doctors/certs*` 四端点；specialist `/api/v1/medical/qa`、`/api/v1/twin-subscriptions*`、`/api/v1/share-links/{token}/activate`；knowledge `/search-internal`。
3. 角色表补 doctor；Database 段补 011 四表。
4. 测试基线更新为实测数字；web 模块列表补「医生认证」。
5. Known Gaps 追加：chat 订阅校验未硬限制（一期宽松）、医生端流式对话未做（REST 一期）、iOS 深链/构建未验证、doctor_cert 文件与 A 计划共 OSS 前缀（若终审要求分离）、C 计划待做（链接生成/追踪/夜间简报）。
6. 计划文档归档：`docs/superpowers/plans/2026-08-17-doctor-app.md` 一并提交。

- [ ] **Step 4: 提交 + 推送（用户确认）**

```bash
git add mobile-doctor/src/navigation/AppNavigator.tsx mobile-doctor/android/app/src/main/AndroidManifest.xml CLAUDE.md docs/superpowers/plans/2026-08-17-doctor-app.md
git commit -m "docs: 医生端深链 + CLAUDE.md 同步（一期 B）+ 计划归档

Co-Authored-By: Claude <noreply@anthropic.com>"
git push origin master   # origin = Codeup（用户确认后）
```

---

## 附录：验收对照（需求文档 → 本计划任务）

| 需求条目 | 落点 |
|---|---|
| 5.1(1) 医生手机号注册登录 | Task 1（doctor 角色）+ Task 7/8（登录屏，复用 auth 链路） |
| 5.1(2) 医师资格认证（人工审核） | Task 2（端点）+ Task 3（审核页）+ Task 8（上传屏） |
| 5.1(3) 知情同意（隐私政策含数据同步范围） | Task 8（登录流程展示）+ Task 6（consent 留痕） |
| 5.2 医学AI问答（引用/免责声明/收藏历史——收藏挂账） | Task 5（后端）+ Task 4（内部检索）+ Task 8（问答屏） |
| 5.3 分身订阅与交互（含 5.3(5) 知情同意弹窗） | Task 6（订阅/激活）+ Task 8（激活屏/弹窗/对话屏）+ Task 9（深链） |
| 3.9(1) 医生执业资质审核（管理后台） | Task 3 |
| 一期互通「分身链接跨端打开」（接收侧） | Task 6（activate）+ Task 9（深链）；生成侧 = C 计划 |
| 原则四 AI 身份明示 | Task 8（对话屏常驻标识 + 知情同意文案） |
| 5.2(4) 收藏与历史 | 挂账（复用 specialist 收藏端点，二期接线） |
| 5.6/5.7（广场/隐私中心） | 二期/三期，不在本计划 |
