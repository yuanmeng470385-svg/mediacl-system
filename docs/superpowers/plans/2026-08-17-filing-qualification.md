# 备案与资质子系统（一期 A）实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 落地需求文档（`C:\Users\yuanmenglong\Desktop\AI数字员工架构及功能设计.md` 修订版）3.3/4.2 条：医药代表备案号录入、资质材料上传、管理后台人工审核、备案到期自动冻结、90 天到期提醒，全链路带审计留痕。

**Architecture:** 数据落在 auth-service（账号生命周期归它管）：新表 `representative_qualifications`（迁移 009），新路由 `/api/v1/qualifications`（multipart 提交 / me 查询 / 管理端列表+审核），证书文件存 OSS（复用 knowledge-service 的 OSSClient 模式，前缀 `qualifications/`），lifespan 每日扫描到期备案自动冻结 rep 账号。网关加路由映射。Web 新增「备案管理」页，mobile 新增「个人合规中心」屏。

**Tech Stack:** FastAPI + SQLAlchemy 2 + PostgreSQL 15（测试用 SQLite）/ oss2 / python-multipart；React + AntD 5 + ProTable；React Native 0.75 + react-native-document-picker。

## Global Constraints

- 提交格式：conventional commits，末尾 `Co-Authored-By: Claude <noreply@anthropic.com>`；每个 Task 末尾 commit，计划完成后统一推 origin=Codeup（用户确认）。
- 测试必须在服务目录下跑（sys.path 依赖 cwd）：`cd services/auth-service && python -m pytest tests/ -v`、`cd services/gateway && python -m pytest tests/ -v`、`cd mobile && npx jest`；web 无测试设施，验证门 = `cd web && npm run build`。
- 当前基线：auth 70 / gateway 74 / mobile jest 73 / web build PASS。本计划每加一个测试文件都要在 Task 11 回写新基线。
- 响应统一 `{code, message, data}`；错误码：1000 参数 / 2000 认证 / 3000 权限 / 4000+ 业务。权限用 `require_roles`（实时查库），角色 `admin/manager/rep/compliance/medical/finance`。
- 所有提交/审核动作必须写审计（`write_audit_log`，auth-service 已有 `app/services/audit_client.py`，失败不阻断业务）。
- 备案状态 `filing_status` 是**派生值**（不落库）：`not_filed`（无备案号）/ `expired`（到期日 < 今天）/ `valid`，在模型 `to_dict()` 计算——避免状态列与日期双写不一致。
- 冻结范围仅 `role='rep'` 且 `status='active'` 的用户（管理员/合规/医学不冻结）。
- 上传限制：`.jpg/.jpeg/.png/.pdf`，单文件 ≤ 5MB，分块落盘。
- 新依赖原则：mobile 新增 `react-native-document-picker`（原生模块需重新 build）；auth-service 新增 `oss2`、`python-multipart`。安装命令不写死版本号（历史教训：`react-native-audio-record@^0.6.2` 不存在，装最新即可）。
- **测试替身惯例**（沿用 test_auth.py）：SQLite + StaticPool + BigInteger→INTEGER 编译、显式给 id、`app.dependency_overrides[get_db]`、JWT_SECRET 环境变量在 import app.main 前设置。

## 设计决策与范围边界（执行前必读）

1. **存量代表宽限**：现有 13+ 代表均无备案记录，立即强制"未备案不可使用"会全员锁死。本计划只实现**到期冻结**（确定性事实）；"未备案/未过审的全量使用门禁"挂账，待老板拍板存量处理方案后另开任务（写入 CLAUDE.md Known Gaps）。
2. **医生资质审核（需求 3.9(1)）不在本计划**：医生账号在 Plan B（医生端）才出现，审核端点/页面复用本计划的 review 模式，届时接入。本计划只做代表侧。
3. **备案平台公开查询接口是调研项**：一期按"录入 + 凭证上传 + 人工审核"落地（需求文档 3.3(1) 同口径），不依赖外部 API。
4. **证书文件隐私**：证书是个人信息，MVP 复用现有 OSS bucket 存 URL；bucket ACL 收紧为私有 + 预览改签名 URL 挂账（写入 Known Gaps）。
5. **提交允许过去日期**：审核人核对凭证时以实际有效期为准；若提交/审核出过期日期，下一轮每日扫描会冻结账号（管理员可在用户管理解冻）——这是"备案过期自动冻结"语义的正确体现，不做提交期日期拦截。
6. **90 天提醒**：`days_until_expiry` 由 `to_dict()` 计算，web/mobile 端渲染（≤90 天标红），不建推送任务。
7. **培训考试字段**（compliance_training_completed/exam_score/commitment_signed）：表结构按需求附录 A 建列，本计划不接线 UI/接口（二期）。

## File Structure

**后端**
- Create: `shared/models/qualification.py` — RepresentativeQualification 模型 + to_dict（派生 filing_status/days_until_expiry）
- Modify: `shared/models/__init__.py` — re-export 新模型
- Create: `scripts/migrations/009_representative_qualifications.sql`
- Modify: `scripts/init_db.sql` — 并入新表 DDL
- Modify: `services/auth-service/app/config.py` — OSS_* 四项 + QUALIFICATION_CHECK_INTERVAL_HOURS
- Create: `services/auth-service/app/services/oss_client.py` — OSS 上传（对象键前缀 qualifications/）
- Modify: `services/auth-service/requirements.txt` — +oss2、python-multipart
- Create: `services/auth-service/app/api/qualifications.py` — 提交/me/列表/审核 4 端点
- Create: `services/auth-service/app/core/filing_expiry.py` — 到期扫描冻结
- Modify: `services/auth-service/app/main.py` — 注册路由 + lifespan 每日扫描
- Create: `services/auth-service/tests/test_qualification_model.py`、`test_qualifications.py`、`test_filing_expiry.py`
- Modify: `services/gateway/app/main.py` — ROUTE_MAP 加 `/api/v1/qualifications`
- Create: `services/gateway/tests/test_qualifications_route.py`

**Web**
- Create: `web/src/services/filing.ts`
- Modify: `web/src/types/index.ts` — Qualification 类型
- Create: `web/src/pages/Filing/FilingList.tsx`
- Modify: `web/src/App.tsx`（lazy + 路由）、`web/src/constants/menu.tsx`（菜单项）

**Mobile**
- Modify: `mobile/src/api/client.ts` — 新增 upload()（multipart 通道）
- Create: `mobile/src/api/qualification.ts`
- Modify: `mobile/src/types/index.ts` — Qualification 类型
- Modify: `mobile/jest.setup.js` — FormData polyfill（守卫式）
- Create: `mobile/src/api/__tests__/qualification-contract.test.ts`
- Create: `mobile/src/screens/Compliance/ComplianceCenterScreen.tsx`
- Modify: `mobile/src/navigation/types.ts`、`mobile/src/navigation/AppNavigator.tsx`、`mobile/src/screens/Settings/SettingsScreen.tsx`
- Modify: `mobile/package.json`（npm install react-native-document-picker）

**文档**
- Modify: `CLAUDE.md`（端点、基线、模块、Known Gaps 挂账项）

---

### Task 1: 模型 + 迁移 009 + init_db.sql

**Files:**
- Create: `shared/models/qualification.py`
- Modify: `shared/models/__init__.py`
- Create: `scripts/migrations/009_representative_qualifications.sql`
- Modify: `scripts/init_db.sql`
- Test: `services/auth-service/tests/test_qualification_model.py`

**Interfaces:**
- Produces: `RepresentativeQualification`（表名 `representative_qualifications`）；`to_dict()` 返回键：`id, representative_id, education_cert, training_cert, audit_status, filing_number, filing_status, filing_expire_date, days_until_expiry, reject_reason, reviewed_by, reviewed_at, compliance_training_completed, compliance_exam_score, commitment_signed`。后续 Task 3/4/5/6/8/9/10 全部依赖此形状。

- [ ] **Step 1: 写模型（含派生状态）**

创建 `shared/models/qualification.py`：

```python
"""代表备案与资质模型（需求文档 3.3/4.2/附录A representative_qualifications）"""
from datetime import date

from sqlalchemy import BigInteger, Boolean, Column, Date, DateTime, ForeignKey, Integer, String

from shared.models.base import Base, TimestampMixin


class RepresentativeQualification(Base, TimestampMixin):
    __tablename__ = "representative_qualifications"

    representative_id = Column(BigInteger, ForeignKey("users.id"), unique=True, nullable=False)
    education_cert = Column(String(500), nullable=False)   # OSS URL（学历证明）
    training_cert = Column(String(500))                    # OSS URL（培训合格证明，可空）
    audit_status = Column(String(20), default="pending")   # pending/approved/rejected
    filing_number = Column(String(50))                     # 国家备案平台备案号
    filing_expire_date = Column(Date)                      # 备案有效期（审核人核对凭证确认）
    reject_reason = Column(String(500))
    reviewed_by = Column(BigInteger)
    reviewed_at = Column(DateTime)
    # 二期培训考试字段（本计划只建列，不接线 UI/接口）
    compliance_training_completed = Column(Boolean, default=False)
    compliance_exam_score = Column(Integer)
    commitment_signed = Column(Boolean, default=False)

    def _filing_status(self) -> str:
        """派生状态：未备案 > 已过期 > 有效。不落库，避免与日期列双写不一致。"""
        if not (self.filing_number or "").strip():
            return "not_filed"
        if self.filing_expire_date and self.filing_expire_date < date.today():
            return "expired"
        return "valid"

    def to_dict(self) -> dict:
        expire = self.filing_expire_date
        return {
            "id": self.id,
            "representative_id": self.representative_id,
            "education_cert": self.education_cert,
            "training_cert": self.training_cert,
            "audit_status": self.audit_status,
            "filing_number": self.filing_number,
            "filing_status": self._filing_status(),
            "filing_expire_date": expire.isoformat() if expire else None,
            "days_until_expiry": (expire - date.today()).days if expire else None,
            "reject_reason": self.reject_reason,
            "reviewed_by": self.reviewed_by,
            "reviewed_at": self.reviewed_at.isoformat() if self.reviewed_at else None,
            "compliance_training_completed": self.compliance_training_completed,
            "compliance_exam_score": self.compliance_exam_score,
            "commitment_signed": self.commitment_signed,
        }
```

- [ ] **Step 2: re-export**

修改 `shared/models/__init__.py`，按文件内既有 import 风格追加一行：

```python
from shared.models.qualification import RepresentativeQualification
```

- [ ] **Step 3: 迁移 009**

创建 `scripts/migrations/009_representative_qualifications.sql`（沿用 008 的 `\set ON_ERROR_STOP on` 头与用法注释风格）：

```sql
-- 009_representative_qualifications.sql
-- 代表备案与资质表（需求文档 3.3/4.2/附录A，一期 A 计划）
--   - 备案状态 filing_status 是派生值不落库（not_filed/valid/expired 由
--     filing_number + filing_expire_date 计算，见 shared/models/qualification.py）
--   - compliance_training_completed / compliance_exam_score / commitment_signed
--     为二期培训考试预留列，本计划不接线
-- 用法：
--   docker exec -i medagent-postgres psql -U medagent medagent \
--     < scripts/migrations/009_representative_qualifications.sql

\set ON_ERROR_STOP on

CREATE TABLE IF NOT EXISTS representative_qualifications (
    id BIGSERIAL PRIMARY KEY,
    representative_id BIGINT NOT NULL UNIQUE REFERENCES users(id),
    education_cert VARCHAR(500) NOT NULL,
    training_cert VARCHAR(500),
    audit_status VARCHAR(20) NOT NULL DEFAULT 'pending',
    filing_number VARCHAR(50),
    filing_expire_date DATE,
    reject_reason VARCHAR(500),
    reviewed_by BIGINT,
    reviewed_at TIMESTAMP,
    compliance_training_completed BOOLEAN NOT NULL DEFAULT FALSE,
    compliance_exam_score INTEGER,
    commitment_signed BOOLEAN NOT NULL DEFAULT FALSE,
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_qual_audit_status ON representative_qualifications(audit_status);
CREATE INDEX IF NOT EXISTS idx_qual_expire ON representative_qualifications(filing_expire_date);
```

- [ ] **Step 4: init_db.sql 同步**

修改 `scripts/init_db.sql`，在 users 相关建表之后追加与 Step 3 相同的 `CREATE TABLE` / `CREATE INDEX` 语句（不带 `\set` 行，保持文件现有风格）。

- [ ] **Step 5: 写模型测试**

创建 `services/auth-service/tests/test_qualification_model.py`（纯内存测试，不需要 DB——to_dict 是纯计算）：

```python
"""备案资质模型派生字段测试（filing_status / days_until_expiry 计算口径）"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", ".."))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

os.environ.setdefault("JWT_SECRET", "test-secret-not-a-default-value")

from datetime import date, timedelta

from shared.models.qualification import RepresentativeQualification


def _mk_qual(**kw):
    defaults = dict(
        id=1, representative_id=1, education_cert="https://oss/edu.pdf",
        audit_status="pending",
    )
    defaults.update(kw)
    return RepresentativeQualification(**defaults)


def test_status_not_filed_without_number():
    q = _mk_qual(filing_number=None)
    assert q.to_dict()["filing_status"] == "not_filed"


def test_status_expired_when_date_passed():
    q = _mk_qual(filing_number="F123", filing_expire_date=date.today() - timedelta(days=1))
    assert q.to_dict()["filing_status"] == "expired"


def test_status_valid_future_date_and_days_count():
    q = _mk_qual(filing_number="F123", filing_expire_date=date.today() + timedelta(days=30))
    assert q.to_dict()["filing_status"] == "valid"
    assert q.to_dict()["days_until_expiry"] == 30


def test_status_valid_when_number_without_date():
    q = _mk_qual(filing_number="F123", filing_expire_date=None)
    assert q.to_dict()["filing_status"] == "valid"
    assert q.to_dict()["days_until_expiry"] is None


def test_empty_number_string_counts_as_not_filed():
    q = _mk_qual(filing_number="  ")
    assert q.to_dict()["filing_status"] == "not_filed"
```

- [ ] **Step 6: 运行测试验证通过**

Run: `cd services/auth-service && python -m pytest tests/test_qualification_model.py -v`
Expected: 5 passed

- [ ] **Step 7: 提交**

```bash
git add shared/models/qualification.py shared/models/__init__.py scripts/migrations/009_representative_qualifications.sql scripts/init_db.sql services/auth-service/tests/test_qualification_model.py
git commit -m "feat(qualification): 代表备案资质模型 + 迁移 009 + init_db 同步

Co-Authored-By: Claude <noreply@anthropic.com>"
```

---

### Task 2: auth-service OSS 客户端 + 配置 + 依赖

**Files:**
- Create: `services/auth-service/app/services/oss_client.py`
- Modify: `services/auth-service/app/config.py`
- Modify: `services/auth-service/requirements.txt`
- Test: `services/auth-service/tests/test_oss_client.py`

**Interfaces:**
- Produces: `app.services.oss_client.OSSClient` —— `upload_local_file(local_path: str, object_key: Optional[str] = None) -> str`（返回 URL；默认对象键 `qualifications/{YYYYMMDD}/{uuid4.hex}{suffix}`）。Task 3 上传依赖。
- Produces: `app.config.settings.OSS_ACCESS_KEY_ID / OSS_ACCESS_KEY_SECRET / OSS_ENDPOINT / OSS_BUCKET`（与 knowledge-service 同款 .env 键名）、`QUALIFICATION_CHECK_INTERVAL_HOURS`（默认 24）。

- [ ] **Step 1: OSS 客户端**

创建 `services/auth-service/app/services/oss_client.py`（从 knowledge-service 同文件移植，改前缀与注释）：

```python
"""阿里云 OSS 客户端（备案资质证书文件，前缀 qualifications/）"""
import os
import uuid
from datetime import datetime
from typing import Optional

import oss2

from app.config import settings


class OSSClient:
    def __init__(self):
        auth = oss2.Auth(settings.OSS_ACCESS_KEY_ID, settings.OSS_ACCESS_KEY_SECRET)
        self.bucket = oss2.Bucket(auth, settings.OSS_ENDPOINT, settings.OSS_BUCKET)
        self.bucket_name = settings.OSS_BUCKET
        self.endpoint = settings.OSS_ENDPOINT

    def upload_local_file(self, local_path: str, object_key: Optional[str] = None) -> str:
        if not object_key:
            suffix = os.path.splitext(local_path)[1]
            object_key = f"qualifications/{datetime.now():%Y%m%d}/{uuid.uuid4().hex}{suffix}"
        self.bucket.put_object_from_file(object_key, local_path)
        return f"https://{self.bucket_name}.{self.endpoint}/{object_key}"
```

- [ ] **Step 2: config.py 追加配置**

修改 `services/auth-service/app/config.py`，在 `LOG_LEVEL` 之前追加：

```python
    # --- OSS（资质证书文件；与 knowledge-service 共用 .env 键名）---
    OSS_ACCESS_KEY_ID = os.getenv("OSS_ACCESS_KEY_ID", "")
    OSS_ACCESS_KEY_SECRET = os.getenv("OSS_ACCESS_KEY_SECRET", "")
    OSS_ENDPOINT = os.getenv("OSS_ENDPOINT", "")
    OSS_BUCKET = os.getenv("OSS_BUCKET", "")

    # --- 备案到期扫描 ---
    QUALIFICATION_CHECK_INTERVAL_HOURS = int(os.getenv("QUALIFICATION_CHECK_INTERVAL_HOURS", "24"))
```

- [ ] **Step 3: requirements.txt 追加依赖**

修改 `services/auth-service/requirements.txt`，末尾追加两行：

```txt
oss2>=2.18.0
python-multipart>=0.0.9
```

（版本号与 knowledge-service 的 oss2 一致；python-multipart 是 FastAPI multipart 解析的必需依赖。）

- [ ] **Step 4: 写 OSS 客户端测试**

创建 `services/auth-service/tests/test_oss_client.py`：

```python
"""OSS 客户端测试：对象键前缀与 URL 格式（不真连 OSS，stub oss2.Bucket）"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", ".."))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

os.environ.setdefault("JWT_SECRET", "test-secret-not-a-default-value")
os.environ["OSS_ACCESS_KEY_ID"] = "test-ak"
os.environ["OSS_ACCESS_KEY_SECRET"] = "test-sk"
os.environ["OSS_ENDPOINT"] = "oss-cn-hangzhou.aliyuncs.com"
os.environ["OSS_BUCKET"] = "test-bucket"


class _FakeBucket:
    def __init__(self):
        self.puts = []

    def put_object_from_file(self, object_key, local_path):
        self.puts.append((object_key, local_path))


def test_upload_uses_qualifications_prefix_and_returns_url(monkeypatch):
    import oss2 as real_oss2
    from app.services.oss_client import OSSClient

    fake_bucket = _FakeBucket()
    monkeypatch.setattr(real_oss2, "Bucket", lambda *a, **k: fake_bucket)
    client = OSSClient()
    url = client.upload_local_file("C:/tmp/cert.pdf")

    assert fake_bucket.puts
    object_key = fake_bucket.puts[0][0]
    assert object_key.startswith("qualifications/")
    assert object_key.endswith(".pdf")
    assert url == f"https://test-bucket.oss-cn-hangzhou.aliyuncs.com/{object_key}"
```

- [ ] **Step 5: 运行测试验证通过**

Run: `cd services/auth-service && python -m pytest tests/test_oss_client.py -v`
Expected: 1 passed

- [ ] **Step 6: 提交**

```bash
git add services/auth-service/app/services/oss_client.py services/auth-service/app/config.py services/auth-service/requirements.txt services/auth-service/tests/test_oss_client.py
git commit -m "feat(auth): OSS 客户端（qualifications 前缀）+ 配置 + 依赖

Co-Authored-By: Claude <noreply@anthropic.com>"
```

---

### Task 3: 代表提交端点 POST /api/v1/qualifications（multipart）

**Files:**
- Create: `services/auth-service/app/api/qualifications.py`（本 Task 只实现提交端点与模块骨架；GET /me、列表、审核在 Task 4/5 追加）
- Modify: `services/auth-service/app/main.py`（注册路由）
- Test: `services/auth-service/tests/test_qualifications.py`（本 Task 建测试基座 + 提交用例）

**Interfaces:**
- Consumes: `RepresentativeQualification`（Task 1）、`OSSClient`（Task 2）、`write_audit_log`（已有 `app.services.audit_client`）、`get_current_user`（shared，返回 `{"id","username","role"}`，实时查库）。
- Produces: `POST /api/v1/qualifications`（multipart）——文件字段 `education_cert`（可选 UploadFile）、`training_cert`（可选）；表单字段 `filing_number`（可选 str ≤50）、`filing_expire_date`（可选 "YYYY-MM-DD"）。仅 role=rep 可提交；首次提交（无记录或 education_cert 为空）必须带学历证明文件。返回 `success(qual.to_dict())`。审计 action=`qualification_submit`。

- [ ] **Step 1: 写端点**

创建 `services/auth-service/app/api/qualifications.py`：

```python
"""备案与资质（需求文档 3.3/4.2）：代表提交（multipart）→ 管理端审核 → 到期冻结"""
import asyncio
import logging
import os
import tempfile
from datetime import date, datetime
from typing import Optional

from fastapi import APIRouter, Depends, File, Form, Request, UploadFile
from sqlalchemy import case, func, or_
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from shared.common.auth import get_current_user, require_roles
from shared.common.context import get_request_id
from shared.common.db_session import get_db
from shared.common.pagination import PaginationParams, paginate
from shared.common.response import BusinessError, ParamError, PermissionError, success
from shared.models.qualification import RepresentativeQualification
from shared.models.user import User

from app.api.users import _reload_current_user
from app.services.audit_client import write_audit_log
from app.services.oss_client import OSSClient

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/qualifications", tags=["qualifications"])

QUAL_ADMIN_ROLES = ("admin", "manager", "compliance", "medical")
ALLOWED_CERT_EXTENSIONS = {".jpg", ".jpeg", ".png", ".pdf"}
MAX_CERT_SIZE = 5 * 1024 * 1024      # 单文件 5MB
_CERT_READ_CHUNK = 1024 * 1024       # 1MB 分块落盘，避免全量读内存
VALID_AUDIT_STATUSES = ("pending", "approved", "rejected")

# 管理端列表按派生 filing_status 过滤用的 SQL 表达式（与模型 to_dict 计算口径一致）
_filing_status_expr = case(
    (
        or_(
            RepresentativeQualification.filing_number.is_(None),
            RepresentativeQualification.filing_number == "",
        ),
        "not_filed",
    ),
    (RepresentativeQualification.filing_expire_date < func.current_date(), "expired"),
    else_="valid",
)


def _client_ip(request: Request) -> str:
    return request.client.host if request.client else ""


async def _save_upload(file: UploadFile) -> str:
    """分块落盘 + 扩展名/大小校验 → OSS 上传（线程池）→ 返回 URL"""
    suffix = (os.path.splitext(file.filename or "")[1] or "").lower()
    if suffix not in ALLOWED_CERT_EXTENSIONS:
        raise ParamError(f"不支持的文件类型 {suffix or '(无扩展名)'}，仅支持 jpg/jpeg/png/pdf")
    total = 0
    with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
        tmp_path = tmp.name
        while True:
            chunk = file.file.read(_CERT_READ_CHUNK)
            if not chunk:
                break
            total += len(chunk)
            if total > MAX_CERT_SIZE:
                break
            tmp.write(chunk)
    if total > MAX_CERT_SIZE:
        try:
            os.unlink(tmp_path)
        except OSError:
            pass
        raise ParamError(f"文件大小超过上限 {MAX_CERT_SIZE // (1024 * 1024)}MB")
    try:
        return await asyncio.to_thread(OSSClient().upload_local_file, tmp_path)
    finally:
        try:
            os.unlink(tmp_path)
        except OSError:
            pass


@router.post("")
async def submit_qualification(
    request: Request,
    education_cert: Optional[UploadFile] = File(None),
    training_cert: Optional[UploadFile] = File(None),
    filing_number: Optional[str] = Form(None),
    filing_expire_date: Optional[str] = Form(None),
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """代表提交/更新本人备案与资质（提交后进入待审核，重新提交重置审核态）"""
    if current_user["role"] != "rep":
        raise PermissionError("仅医药代表可提交备案与资质材料")

    number = (filing_number or "").strip()
    if len(number) > 50:
        raise ParamError("备案号长度不能超过 50 字符")
    parsed_date = None
    if filing_expire_date:
        try:
            parsed_date = date.fromisoformat(filing_expire_date)
        except ValueError as exc:
            raise ParamError("filing_expire_date 格式应为 YYYY-MM-DD") from exc

    qual = db.query(RepresentativeQualification).filter(
        RepresentativeQualification.representative_id == current_user["id"]
    ).first()
    if (not qual or not qual.education_cert) and not education_cert:
        raise ParamError("首次提交必须上传学历证明")

    before = {
        "filing_number": qual.filing_number if qual else None,
        "audit_status": qual.audit_status if qual else None,
    }
    if not qual:
        qual = RepresentativeQualification(
            representative_id=current_user["id"],
            education_cert="",  # 上传成功后覆盖
        )
        db.add(qual)

    if education_cert:
        qual.education_cert = await _save_upload(education_cert)
    if training_cert:
        qual.training_cert = await _save_upload(training_cert)
    if number:
        qual.filing_number = number
    if parsed_date:
        qual.filing_expire_date = parsed_date
    # 重新提交回到待审核；上一轮审核信息清空
    qual.audit_status = "pending"
    qual.reject_reason = None
    qual.reviewed_by = None
    qual.reviewed_at = None
    try:
        db.commit()
    except IntegrityError:
        # TOCTOU 兜底：并发双提交撞 representative_id 唯一索引 → 可读业务错误而非 500
        db.rollback()
        raise BusinessError("提交冲突，请重试", code=4001)
    db.refresh(qual)

    await write_audit_log(
        action="qualification_submit",
        user_id=current_user["id"],
        resource_type="qualification",
        resource_id=str(qual.id),
        before_value=before,
        after_value={
            "filing_number": qual.filing_number,
            "audit_status": qual.audit_status,
            "filing_expire_date": qual.filing_expire_date.isoformat() if qual.filing_expire_date else None,
        },
        client_ip=_client_ip(request),
        user_agent=request.headers.get("user-agent"),
        request_id=get_request_id() or None,
    )
    return success(qual.to_dict())
```

- [ ] **Step 2: main.py 注册路由**

修改 `services/auth-service/app/main.py`，在 users_router 注册之后追加：

```python
from app.api.qualifications import router as qualifications_router
app.include_router(qualifications_router)
```

- [ ] **Step 3: 写测试基座 + 提交用例**

创建 `services/auth-service/tests/test_qualifications.py`（本 Task 的测试基座 Task 4/5 继续沿用）：

```python
"""
备案资质端点测试

覆盖：首次提交必须带学历证明、非 rep 禁止提交、扩展名/大小/日期校验、
提交重置审核态、审计留痕、me/列表/审核的权限边界（Task 4/5 补齐）。

不依赖真实 Redis/PostgreSQL/OSS：DB 用 SQLite，OSS 用桩。
"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", ".."))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

os.environ.setdefault("JWT_SECRET", "test-secret-not-a-default-value")
os.environ["AUTH_DEV_MODE"] = "true"

from datetime import date, timedelta
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

import app.api.qualifications as qual_api
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


app.dependency_overrides[get_db] = _override_db
client = TestClient(app)


def _token(user_id: int, role: str) -> dict:
    token = create_token(user_id=user_id, username=f"u{user_id}", role=role)
    return {"Authorization": f"Bearer {token}"}


class _FakeOSS:
    def upload_local_file(self, local_path, object_key=None):
        return f"https://fake-oss/{os.path.basename(local_path)}"


@pytest.fixture(autouse=True)
def fresh_state(monkeypatch):
    """每用例重建 users + representative_qualifications 表，OSS 与审计打桩"""
    tables = [User.__table__, RepresentativeQualification.__table__]
    Base.metadata.drop_all(engine, tables=tables)
    Base.metadata.create_all(engine, tables=tables)
    db = TestSession()
    db.add_all([
        User(id=1, username="rep01", full_name="张代表", phone="13800000001", role="rep",
             status="active"),
        User(id=2, username="admin", full_name="管理员", phone="13800000000", role="admin",
             status="active"),
        User(id=3, username="rep02", full_name="李代表", phone="13800000002", role="rep",
             status="active"),
    ])
    db.commit()
    db.close()

    monkeypatch.setattr(qual_api, "OSSClient", lambda: _FakeOSS())
    audit_mock = AsyncMock(return_value=None)
    monkeypatch.setattr(qual_api, "write_audit_log", audit_mock)
    yield audit_mock


def test_submit_requires_education_cert_on_first_time():
    resp = client.post(
        "/api/v1/qualifications",
        data={"filing_number": "F-2026-001"},
        headers=_token(1, "rep"),
    )
    assert resp.status_code == 400
    body = resp.json()
    assert body["code"] == 1000
    assert "学历证明" in body["message"]


def test_submit_creates_row_and_sets_pending():
    resp = client.post(
        "/api/v1/qualifications",
        data={"filing_number": "F-2026-001", "filing_expire_date": "2028-06-30"},
        files={"education_cert": ("edu.pdf", b"%PDF-1.4 fake", "application/pdf")},
        headers=_token(1, "rep"),
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["code"] == 0
    data = body["data"]
    assert data["filing_number"] == "F-2026-001"
    assert data["filing_status"] == "valid"
    assert data["audit_status"] == "pending"
    assert data["education_cert"].startswith("https://fake-oss/")
    assert data["filing_expire_date"] == "2028-06-30"


def test_resubmit_resets_review_state(fresh_state):
    db = TestSession()
    db.add(RepresentativeQualification(
        id=1, representative_id=1, education_cert="https://oss/edu.pdf",
        filing_number="F-OLD", audit_status="rejected", reject_reason="材料不清晰",
        reviewed_by=2, reviewed_at=None,
    ))
    db.commit()
    db.close()

    resp = client.post(
        "/api/v1/qualifications",
        data={"filing_number": "F-NEW"},
        headers=_token(1, "rep"),
    )
    body = resp.json()
    assert body["code"] == 0
    assert body["data"]["audit_status"] == "pending"
    assert body["data"]["filing_number"] == "F-NEW"
    assert body["data"]["reject_reason"] is None
    assert body["data"]["reviewed_by"] is None
    audit_mock = fresh_state
    audit_mock.assert_awaited_once()


def test_non_rep_cannot_submit():
    resp = client.post(
        "/api/v1/qualifications",
        data={},
        files={"education_cert": ("edu.pdf", b"%PDF-1.4 fake", "application/pdf")},
        headers=_token(2, "admin"),
    )
    assert resp.status_code == 403
    body = resp.json()
    assert body["code"] == 3000
    assert "仅医药代表" in body["message"]


def test_bad_extension_rejected():
    resp = client.post(
        "/api/v1/qualifications",
        data={},
        files={"education_cert": ("evil.exe", b"MZ fake", "application/octet-stream")},
        headers=_token(1, "rep"),
    )
    assert resp.status_code == 400
    body = resp.json()
    assert body["code"] == 1000
    assert "文件类型" in body["message"]


def test_bad_date_format_rejected():
    resp = client.post(
        "/api/v1/qualifications",
        data={"filing_expire_date": "2028/06/30"},
        files={"education_cert": ("edu.pdf", b"%PDF-1.4 fake", "application/pdf")},
        headers=_token(1, "rep"),
    )
    assert resp.status_code == 400
    body = resp.json()
    assert body["code"] == 1000
    assert "YYYY-MM-DD" in body["message"]
```

- [ ] **Step 4: 运行测试验证通过**

Run: `cd services/auth-service && python -m pytest tests/test_qualifications.py -v`
Expected: 6 passed
（若 `test_resubmit_resets_review_state` 里 audit_mock 断言与 fixture 用法冲突，把审计断言改为检查 `qual_api.write_audit_log` 的调用记录对象，保证语义不变。）

- [ ] **Step 5: 全量回归**

Run: `cd services/auth-service && python -m pytest tests/ -q`
Expected: 70 + 5 + 1 + 6 = 82 passed

- [ ] **Step 6: 提交**

```bash
git add services/auth-service/app/api/qualifications.py services/auth-service/app/main.py services/auth-service/tests/test_qualifications.py
git commit -m "feat(qualification): 代表提交端点（multipart 上传 + 校验 + 审计）

Co-Authored-By: Claude <noreply@anthropic.com>"
```

---

### Task 4: GET /api/v1/qualifications/me

**Files:**
- Modify: `services/auth-service/app/api/qualifications.py`
- Test: `services/auth-service/tests/test_qualifications.py`（追加用例）

**Interfaces:**
- Produces: `GET /api/v1/qualifications/me` —— 任意已登录用户；无记录返回 `success(None)`（移动端据此渲染"未备案"空态）。Task 9/10 依赖。

- [ ] **Step 1: 写端点**

在 `qualifications.py` 的 submit 端点之后追加：

```python
@router.get("/me")
async def get_my_qualification(
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """本人备案与资质（无记录返回 null，移动端渲染"未备案"空态）"""
    qual = db.query(RepresentativeQualification).filter(
        RepresentativeQualification.representative_id == current_user["id"]
    ).first()
    return success(qual.to_dict() if qual else None)
```

- [ ] **Step 2: 追加测试**

在 `test_qualifications.py` 末尾追加：

```python
def test_me_returns_row_when_exists(fresh_state):
    db = TestSession()
    db.add(RepresentativeQualification(
        id=1, representative_id=1, education_cert="https://oss/edu.pdf",
        filing_number="F-1", audit_status="approved",
        filing_expire_date=date.today() + timedelta(days=100),
    ))
    db.commit()
    db.close()

    resp = client.get("/api/v1/qualifications/me", headers=_token(1, "rep"))
    body = resp.json()
    assert body["code"] == 0
    assert body["data"]["filing_number"] == "F-1"
    assert body["data"]["days_until_expiry"] == 100


def test_me_returns_null_without_row():
    resp = client.get("/api/v1/qualifications/me", headers=_token(3, "rep"))
    body = resp.json()
    assert body["code"] == 0
    assert body["data"] is None


def test_me_requires_auth():
    resp = client.get("/api/v1/qualifications/me")
    assert resp.status_code == 401
```

- [ ] **Step 3: 运行测试验证通过**

Run: `cd services/auth-service && python -m pytest tests/test_qualifications.py -v`
Expected: 9 passed

- [ ] **Step 4: 提交**

```bash
git add services/auth-service/app/api/qualifications.py services/auth-service/tests/test_qualifications.py
git commit -m "feat(qualification): GET /me 本人备案资质查询

Co-Authored-By: Claude <noreply@anthropic.com>"
```

---

### Task 5: 管理端列表 + 审核端点

**Files:**
- Modify: `services/auth-service/app/api/qualifications.py`
- Test: `services/auth-service/tests/test_qualifications.py`（追加用例）

**Interfaces:**
- Produces: `GET /api/v1/qualifications?page&page_size&audit_status&filing_status&keyword` —— `require_roles(*QUAL_ADMIN_ROLES)`；items 每项 = `{**q.to_dict(), "rep_name": u.full_name, "rep_phone": u.phone}`；返回 `success(paginate(items, total, p.page, p.page_size))`。Task 8 依赖。
- Produces: `PUT /api/v1/qualifications/{qualification_id}/review`，body `{"verdict": "approve"|"reject", "reason": str, "filing_expire_date": "YYYY-MM-DD"}` —— reject 必须带 reason；仅 pending 可审；审核人可确认/修正备案有效期；审计 action=`qualification_review`。Task 8 依赖。

- [ ] **Step 1: 写两个端点**

在 `qualifications.py` 的 me 端点之后追加：

```python
@router.get("")
async def list_qualifications(
    page: int = 1,
    page_size: int = 20,
    audit_status: Optional[str] = None,
    filing_status: Optional[str] = None,
    keyword: Optional[str] = None,
    current_user: dict = Depends(require_roles(*QUAL_ADMIN_ROLES)),
    db: Session = Depends(get_db),
):
    """备案与资质列表（管理端：admin/manager/compliance/medical）"""
    _reload_current_user(db, current_user)
    if audit_status and audit_status not in VALID_AUDIT_STATUSES:
        raise ParamError("audit_status 不合法")
    if filing_status and filing_status not in ("valid", "expired", "not_filed"):
        raise ParamError("filing_status 不合法")
    p = PaginationParams(page=page, page_size=page_size)
    query = db.query(RepresentativeQualification, User).join(
        User, User.id == RepresentativeQualification.representative_id
    )
    if audit_status:
        query = query.filter(RepresentativeQualification.audit_status == audit_status)
    if filing_status:
        query = query.filter(_filing_status_expr == filing_status)
    if keyword:
        like = f"%{keyword}%"
        query = query.filter(or_(
            User.full_name.ilike(like),
            User.phone.ilike(like),
            User.username.ilike(like),
            RepresentativeQualification.filing_number.ilike(like),
        ))
    total = query.count()
    rows = query.order_by(RepresentativeQualification.id.desc()).offset(p.offset).limit(p.limit).all()
    items = [{**q.to_dict(), "rep_name": u.full_name, "rep_phone": u.phone} for q, u in rows]
    return success(paginate(items, total, p.page, p.page_size))


@router.put("/{qualification_id}/review")
async def review_qualification(
    qualification_id: int,
    request: dict,
    current_user: dict = Depends(require_roles(*QUAL_ADMIN_ROLES)),
    db: Session = Depends(get_db),
):
    """资质审核（通过/驳回）。驳回必须附原因；可同时确认/修正备案有效期。"""
    actor = _reload_current_user(db, current_user)
    if not isinstance(request, dict):
        raise ParamError("请求体必须是 JSON 对象")
    verdict = request.get("verdict")
    if verdict not in ("approve", "reject"):
        raise ParamError("verdict 必须是 approve 或 reject")
    reason = (request.get("reason") or "").strip()
    if verdict == "reject" and not reason:
        raise ParamError("驳回必须填写原因")
    if len(reason) > 500:
        raise ParamError("原因长度不能超过 500 字符")
    parsed_date = None
    raw_date = request.get("filing_expire_date")
    if raw_date:
        try:
            parsed_date = date.fromisoformat(str(raw_date))
        except ValueError as exc:
            raise ParamError("filing_expire_date 格式应为 YYYY-MM-DD") from exc

    qual = db.query(RepresentativeQualification).filter(
        RepresentativeQualification.id == qualification_id
    ).first()
    if not qual:
        raise BusinessError("备案记录不存在", code=4001)
    if qual.audit_status != "pending":
        raise BusinessError("当前状态不可审核（仅待审核可审）", code=4001)

    before = {
        "audit_status": qual.audit_status,
        "filing_expire_date": qual.filing_expire_date.isoformat() if qual.filing_expire_date else None,
    }
    qual.audit_status = "approved" if verdict == "approve" else "rejected"
    qual.reject_reason = reason if verdict == "reject" else None
    qual.reviewed_by = actor.id
    qual.reviewed_at = datetime.utcnow()
    if parsed_date:
        qual.filing_expire_date = parsed_date
    db.commit()
    db.refresh(qual)

    await write_audit_log(
        action="qualification_review",
        user_id=actor.id,
        resource_type="qualification",
        resource_id=str(qual.id),
        before_value=before,
        after_value={
            "audit_status": qual.audit_status,
            "reject_reason": qual.reject_reason,
            "filing_expire_date": qual.filing_expire_date.isoformat() if qual.filing_expire_date else None,
        },
    )
    return success(qual.to_dict())
```

- [ ] **Step 2: 追加测试**

在 `test_qualifications.py` 末尾追加：

```python
def _add_qual(**kw):
    db = TestSession()
    defaults = dict(
        id=kw.pop("id", 1), representative_id=kw.pop("representative_id", 1),
        education_cert="https://oss/edu.pdf",
        filing_number="F-1", audit_status="pending",
        filing_expire_date=date.today() + timedelta(days=100),
    )
    defaults.update(kw)
    db.add(RepresentativeQualification(**defaults))
    db.commit()
    db.close()
    return defaults["id"]


def test_list_returns_joined_items(fresh_state):
    _add_qual()
    resp = client.get("/api/v1/qualifications", headers=_token(2, "admin"))
    body = resp.json()
    assert body["code"] == 0
    data = body["data"]
    assert data["total"] == 1
    assert data["items"][0]["rep_name"] == "张代表"
    assert data["items"][0]["rep_phone"] == "13800000001"
    assert data["items"][0]["filing_status"] == "valid"


def test_list_filter_by_expired_status(fresh_state):
    _add_qual(id=1, filing_expire_date=date.today() - timedelta(days=1))
    _add_qual(id=2, representative_id=3, filing_number="F-2",
              filing_expire_date=date.today() + timedelta(days=10))
    resp = client.get("/api/v1/qualifications?filing_status=expired", headers=_token(2, "admin"))
    data = resp.json()["data"]
    assert data["total"] == 1
    assert data["items"][0]["representative_id"] == 1


def test_list_rejects_rep(fresh_state):
    resp = client.get("/api/v1/qualifications", headers=_token(1, "rep"))
    assert resp.status_code == 403
    body = resp.json()
    assert body["code"] == 3000


def test_review_approve_sets_fields(fresh_state):
    _add_qual()
    resp = client.put(
        "/api/v1/qualifications/1/review",
        json={"verdict": "approve", "filing_expire_date": "2029-01-01"},
        headers=_token(2, "admin"),
    )
    body = resp.json()
    assert body["code"] == 0
    assert body["data"]["audit_status"] == "approved"
    assert body["data"]["filing_expire_date"] == "2029-01-01"
    assert body["data"]["reviewed_by"] == 2
    audit_mock = fresh_state
    audit_mock.assert_awaited_once()


def test_review_reject_requires_reason(fresh_state):
    _add_qual()
    resp = client.put(
        "/api/v1/qualifications/1/review",
        json={"verdict": "reject"},
        headers=_token(2, "admin"),
    )
    assert resp.status_code == 400
    body = resp.json()
    assert body["code"] == 1000
    assert "原因" in body["message"]


def test_review_reject_saves_reason(fresh_state):
    _add_qual()
    resp = client.put(
        "/api/v1/qualifications/1/review",
        json={"verdict": "reject", "reason": "材料不清晰"},
        headers=_token(2, "admin"),
    )
    body = resp.json()
    assert body["code"] == 0
    assert body["data"]["audit_status"] == "rejected"
    assert body["data"]["reject_reason"] == "材料不清晰"


def test_review_not_pending_rejected(fresh_state):
    _add_qual(audit_status="approved")
    resp = client.put(
        "/api/v1/qualifications/1/review",
        json={"verdict": "approve"},
        headers=_token(2, "admin"),
    )
    body = resp.json()
    assert resp.status_code == 422
    assert body["code"] == 4001


def test_review_missing_row(fresh_state):
    resp = client.put(
        "/api/v1/qualifications/999/review",
        json={"verdict": "approve"},
        headers=_token(2, "admin"),
    )
    assert resp.status_code == 422
    assert resp.json()["code"] == 4001
```

- [ ] **Step 3: 运行测试验证通过**

Run: `cd services/auth-service && python -m pytest tests/test_qualifications.py -v`
Expected: 17 passed

- [ ] **Step 4: 全量回归**

Run: `cd services/auth-service && python -m pytest tests/ -q`
Expected: 93 passed

- [ ] **Step 5: 提交**

```bash
git add services/auth-service/app/api/qualifications.py services/auth-service/tests/test_qualifications.py
git commit -m "feat(qualification): 管理端列表（状态过滤/关键词）+ 审核端点（通过/驳回）

Co-Authored-By: Claude <noreply@anthropic.com>"
```

---

### Task 6: 备案到期自动冻结（lifespan 每日扫描）

**Files:**
- Create: `services/auth-service/app/core/filing_expiry.py`
- Modify: `services/auth-service/app/main.py`（lifespan）
- Test: `services/auth-service/tests/test_filing_expiry.py`

**Interfaces:**
- Consumes: `RepresentativeQualification`（Task 1）、`write_audit_log`、`SessionLocal`（shared.common.db_session）。
- Produces: `app.core.filing_expiry.freeze_expired_qualifications(db: Session) -> List[User]`（同步，测试直接调用；冻结 `role='rep'` 且 `status='active'` 且 `filing_expire_date < 今天` 的用户，返回被冻结用户列表）；`run_filing_expiry_scan()`（lifespan 每日调用：开新会话 → to_thread 扫描 → 逐用户写审计 action=`qualification_expired_freeze`）。

- [ ] **Step 1: 写扫描冻结模块**

创建 `services/auth-service/app/core/filing_expiry.py`：

```python
"""备案到期自动冻结（需求文档 3.3(2)）：每日扫描 filing_expire_date < 今天的代表，
将账号置为 disabled（冻结）。备案状态是确定性事实，无需人工确认。

冻结范围仅 role='rep' 且 status='active'（管理员/合规/医学不冻结）。
多 worker 部署各进程各跑一份——UPDATE 幂等（status 过滤），可接受。
"""
import asyncio
import logging
from datetime import date
from typing import List

from sqlalchemy.orm import Session

from shared.common.db_session import SessionLocal
from shared.models.qualification import RepresentativeQualification
from shared.models.user import User

from app.services.audit_client import write_audit_log

logger = logging.getLogger(__name__)


def freeze_expired_qualifications(db: Session) -> List[User]:
    """同步扫描并冻结到期代表（测试直接调用本函数，不碰 httpx/审计）。"""
    today = date.today()
    rows = (
        db.query(RepresentativeQualification, User)
        .join(User, User.id == RepresentativeQualification.representative_id)
        .filter(
            User.role == "rep",
            User.status == "active",
            RepresentativeQualification.filing_expire_date.isnot(None),
            RepresentativeQualification.filing_expire_date < today,
        )
        .all()
    )
    frozen: List[User] = []
    for _qual, user in rows:
        user.status = "disabled"
        frozen.append(user)
    if frozen:
        db.commit()
    return frozen


async def run_filing_expiry_scan() -> dict:
    """开新会话扫描冻结 + 逐用户写审计（审计失败不阻断冻结结果）。"""
    db = SessionLocal()
    try:
        frozen = await asyncio.to_thread(freeze_expired_qualifications, db)
        for user in frozen:
            await write_audit_log(
                action="qualification_expired_freeze",
                user_id=user.id,
                resource_type="user",
                resource_id=str(user.id),
                after_value={"reason": "备案到期自动冻结", "freeze_date": date.today().isoformat()},
            )
        if frozen:
            logger.info("备案到期扫描：冻结 %s 个代表账号", len(frozen))
        return {"frozen": len(frozen), "scanned_at": date.today().isoformat()}
    finally:
        db.close()
```

- [ ] **Step 2: main.py 加 lifespan**

修改 `services/auth-service/app/main.py`：
- 顶部 import 区追加 `import asyncio` 与 `from contextlib import asynccontextmanager`；
- 在 `app = FastAPI(...)` 之前追加循环函数与 lifespan，并把 lifespan 挂到 FastAPI：

```python
async def _filing_expiry_loop() -> None:
    """备案到期扫描：启动即跑一次，此后每 QUALIFICATION_CHECK_INTERVAL_HOURS 小时执行（参照 audit-service 清理任务模式）"""
    from app.core.filing_expiry import run_filing_expiry_scan

    while True:
        try:
            await run_filing_expiry_scan()
        except Exception as exc:
            logger.error("备案到期扫描失败: %s", exc)
        await asyncio.sleep(settings.QUALIFICATION_CHECK_INTERVAL_HOURS * 3600)


@asynccontextmanager
async def lifespan(app: FastAPI):
    task = asyncio.create_task(_filing_expiry_loop())
    try:
        yield
    finally:
        task.cancel()


app = FastAPI(
    title="MedAgent - 认证服务",
    description="手机号验证码登录 / 用户名密码登录 / 当前用户信息",
    version="1.0.0",
    lifespan=lifespan,
)
```

- [ ] **Step 3: 写测试**

创建 `services/auth-service/tests/test_filing_expiry.py`：

```python
"""备案到期冻结测试（直接测同步扫描函数，不启动 lifespan 循环）"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", ".."))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

os.environ.setdefault("JWT_SECRET", "test-secret-not-a-default-value")

from datetime import date, timedelta

from sqlalchemy import BigInteger, create_engine
from sqlalchemy.ext.compiler import compiles
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from shared.models.base import Base
from shared.models.qualification import RepresentativeQualification
from shared.models.user import User

from app.core.filing_expiry import freeze_expired_qualifications


@compiles(BigInteger, "sqlite")
def _compile_bigint_for_sqlite(type_, compiler, **kw):
    return "INTEGER"


engine = create_engine(
    "sqlite://",
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)
TestSession = sessionmaker(bind=engine, autocommit=False, autoflush=False)


def _seed():
    db = TestSession()
    Base.metadata.drop_all(engine, tables=[User.__table__, RepresentativeQualification.__table__])
    Base.metadata.create_all(engine, tables=[User.__table__, RepresentativeQualification.__table__])
    db.add_all([
        User(id=1, username="rep01", full_name="张代表", phone="13800000001", role="rep",
             status="active"),
        User(id=2, username="admin", full_name="管理员", phone="13800000000", role="admin",
             status="active"),
        User(id=3, username="rep02", full_name="李代表", phone="13800000002", role="rep",
             status="active"),
        User(id=4, username="rep03", full_name="王代表", phone="13800000003", role="rep",
             status="active"),
    ])
    db.add_all([
        RepresentativeQualification(id=1, representative_id=1, education_cert="https://oss/e.pdf",
                                    filing_number="F-1", filing_expire_date=date.today() - timedelta(days=1)),
        RepresentativeQualification(id=2, representative_id=3, education_cert="https://oss/e.pdf",
                                    filing_number="F-2", filing_expire_date=date.today() + timedelta(days=30)),
        RepresentativeQualification(id=3, representative_id=4, education_cert="https://oss/e.pdf",
                                    filing_number="F-3", filing_expire_date=None),
    ])
    db.commit()
    db.close()


def test_freezes_only_expired_rep():
    _seed()
    db = TestSession()
    frozen = freeze_expired_qualifications(db)
    db.close()

    assert [u.id for u in frozen] == [1]

    db = TestSession()
    users = {u.id: u for u in db.query(User).all()}
    db.close()
    assert users[1].status == "disabled"
    assert users[2].status == "active"   # admin 不冻结
    assert users[3].status == "active"   # 未到期不冻结
    assert users[4].status == "active"   # 无到期日（有备案号无日期）不冻结


def test_second_run_is_idempotent():
    _seed()
    db = TestSession()
    freeze_expired_qualifications(db)
    frozen_again = freeze_expired_qualifications(db)
    db.close()
    assert frozen_again == []
```

- [ ] **Step 4: 运行测试验证通过**

Run: `cd services/auth-service && python -m pytest tests/test_filing_expiry.py -v`
Expected: 2 passed

- [ ] **Step 5: 全量回归**

Run: `cd services/auth-service && python -m pytest tests/ -q`
Expected: 95 passed

- [ ] **Step 6: 提交**

```bash
git add services/auth-service/app/core/filing_expiry.py services/auth-service/app/main.py services/auth-service/tests/test_filing_expiry.py
git commit -m "feat(qualification): 备案到期每日扫描自动冻结代表账号

Co-Authored-By: Claude <noreply@anthropic.com>"
```

---

### Task 7: 网关路由 /api/v1/qualifications

**Files:**
- Modify: `services/gateway/app/main.py`（ROUTE_MAP，行 134-157 区域）
- Create: `services/gateway/tests/test_qualifications_route.py`

**Interfaces:**
- Produces: 网关把 `/api/v1/qualifications*` 转发到 `settings.AUTH_SERVICE_URL`；路径不在 PUBLIC_PATHS，需要 Bearer JWT（网关统一鉴权，无需额外配置）。

- [ ] **Step 1: ROUTE_MAP 加映射**

修改 `services/gateway/app/main.py`，在 `"/api/v1/users"` 行之后追加：

```python
    "/api/v1/qualifications": settings.AUTH_SERVICE_URL,  # 备案与资质（Web 后台 + 移动端）
```

- [ ] **Step 2: 写路由测试（异步模式与 test_path_traversal.py 一致：`asyncio.run` + `httpx.ASGITransport`，测试函数本身是同步的）**

创建 `services/gateway/tests/test_qualifications_route.py`（桩模式沿用 test_path_traversal.py 的 `_RecordingClient` + `_auth_headers()`）：

```python
"""qualifications 路由：网关转发到 auth-service，且必须带 JWT"""
import asyncio
import time
import types

import httpx
import jwt as pyjwt
import pytest

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
    payload = {"sub": "1", "username": "u", "role": "rep", "iat": now, "exp": now + 3600}
    token = pyjwt.encode(payload, middleware_settings.JWT_SECRET, algorithm="HS256")
    return {"Authorization": f"Bearer {token}"}


def test_me_routes_to_auth_service(monkeypatch):
    log = _record_forwarding(monkeypatch)

    async def _run():
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as c:
            return await c.get("/api/v1/qualifications/me", headers=_auth_headers())

    resp = asyncio.run(_run())
    assert resp.status_code == 200
    assert len(log) == 1
    method, url = log[0]
    assert method == "GET"
    assert url == f"{main.settings.AUTH_SERVICE_URL}/api/v1/qualifications/me"


def test_requires_bearer_token(monkeypatch):
    log = _record_forwarding(monkeypatch)

    async def _run():
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as c:
            return await c.get("/api/v1/qualifications/me")

    resp = asyncio.run(_run())
    assert resp.status_code == 401
    assert log == []

- [ ] **Step 4: 运行测试验证通过**

Run: `cd services/gateway && python -m pytest tests/test_qualifications_route.py -v`
Expected: 2 passed

- [ ] **Step 5: 全量回归**

Run: `cd services/gateway && python -m pytest tests/ -q`
Expected: 76 passed

- [ ] **Step 6: 提交**

```bash
git add services/gateway/app/main.py services/gateway/tests/test_qualifications_route.py
git commit -m "feat(gateway): /api/v1/qualifications 路由到 auth-service

Co-Authored-By: Claude <noreply@anthropic.com>"
```

---

### Task 8: Web 备案管理页

**Files:**
- Create: `web/src/services/filing.ts`
- Modify: `web/src/types/index.ts`
- Create: `web/src/pages/Filing/FilingList.tsx`
- Modify: `web/src/App.tsx`
- Modify: `web/src/constants/menu.tsx`

**Interfaces:**
- Consumes: `GET /api/v1/qualifications`（Task 5 列表形状，items 含 rep_name/rep_phone）、`PUT /api/v1/qualifications/{id}/review`（Task 5）。
- Produces: `web/src/services/filing.ts` 导出 `filingAPI.list(params)` 与 `filingAPI.review(id, data)`；`web/src/types/index.ts` 新增 `Qualification` 接口（Task 8 全量定义，mobile Task 9 用同形状另定义）。

- [ ] **Step 1: 类型定义**

修改 `web/src/types/index.ts`，在用户类型之后追加：

```ts
// ========== 备案与资质 ==========
// 字段与 auth-service RepresentativeQualification.to_dict 对齐（列表项另含 rep_name/rep_phone）
export interface Qualification {
  id: string;
  representative_id: string;
  education_cert: string;
  training_cert?: string;
  audit_status: 'pending' | 'approved' | 'rejected';
  filing_number?: string;
  filing_status: 'not_filed' | 'valid' | 'expired';
  filing_expire_date?: string;
  days_until_expiry?: number | null;
  reject_reason?: string;
  reviewed_by?: number;
  reviewed_at?: string;
  rep_name?: string;
  rep_phone?: string;
  compliance_training_completed: boolean;
  commitment_signed: boolean;
}
```

- [ ] **Step 2: API 层**

创建 `web/src/services/filing.ts`：

```ts
import client from './client';
import type { ApiResponse, PaginatedResponse, Qualification } from '../types';

export interface QualificationReviewPayload {
  verdict: 'approve' | 'reject';
  reason?: string;
  filing_expire_date?: string;
}

export const filingAPI = {
  list: (params?: {
    page?: number;
    page_size?: number;
    audit_status?: string;
    filing_status?: string;
    keyword?: string;
  }) => client.get<PaginatedResponse<Qualification>>('/qualifications', { params }),

  review: (id: string, data: QualificationReviewPayload) =>
    client.put<ApiResponse<Qualification>>(`/qualifications/${id}/review`, data),
};
```

- [ ] **Step 3: 页面**

创建 `web/src/pages/Filing/FilingList.tsx`（ProTable 列表 + 审核抽屉，抽屉参照 SpecialistList「数据」抽屉写法）：

```tsx
import { useRef, useState } from 'react';
import { ProTable } from '@ant-design/pro-components';
import type { ProColumns, ActionType } from '@ant-design/pro-components';
import { App, Button, DatePicker, Descriptions, Drawer, Input, Radio, Space, Tag } from 'antd';
import dayjs, { Dayjs } from 'dayjs';
import { filingAPI } from '../../services/filing';
import type { Qualification } from '../../types';

const AUDIT_MAP: Record<string, { color: string; text: string }> = {
  pending: { color: 'orange', text: '待审核' },
  approved: { color: 'green', text: '已通过' },
  rejected: { color: 'red', text: '已驳回' },
};
const FILING_MAP: Record<string, { color: string; text: string }> = {
  valid: { color: 'green', text: '有效' },
  expired: { color: 'red', text: '已过期' },
  not_filed: { color: 'default', text: '未备案' },
};

export default function FilingList() {
  const actionRef = useRef<ActionType>();
  const [current, setCurrent] = useState<Qualification | null>(null);
  const [verdict, setVerdict] = useState<'approve' | 'reject'>('approve');
  const [reason, setReason] = useState('');
  const [expireDate, setExpireDate] = useState<Dayjs | null>(null);
  const [submitting, setSubmitting] = useState(false);
  const { message } = App.useApp();

  const openDrawer = (row: Qualification) => {
    setCurrent(row);
    setVerdict('approve');
    setReason('');
    setExpireDate(row.filing_expire_date ? dayjs(row.filing_expire_date) : null);
  };

  const submitReview = async () => {
    if (!current) return;
    if (verdict === 'reject' && !reason.trim()) {
      message.warning('驳回必须填写原因');
      return;
    }
    setSubmitting(true);
    try {
      await filingAPI.review(current.id, {
        verdict,
        reason: verdict === 'reject' ? reason.trim() : undefined,
        filing_expire_date: expireDate ? expireDate.format('YYYY-MM-DD') : undefined,
      });
      message.success('审核完成');
      setCurrent(null);
      actionRef.current?.reload();
    } catch {
      /* client.ts 拦截器已弹错误 */
    } finally {
      setSubmitting(false);
    }
  };

  const columns: ProColumns<Qualification>[] = [
    { title: '代表', dataIndex: 'rep_name', width: 120 },
    { title: '手机号', dataIndex: 'rep_phone', width: 130 },
    { title: '备案号', dataIndex: 'filing_number', width: 160 },
    {
      title: '备案状态', dataIndex: 'filing_status', width: 90,
      valueEnum: { valid: '有效', expired: '已过期', not_filed: '未备案' },
      render: (_, r) => {
        const m = FILING_MAP[r.filing_status] || { color: 'default', text: r.filing_status };
        return <Tag color={m.color}>{m.text}</Tag>;
      },
    },
    {
      title: '备案有效期', dataIndex: 'filing_expire_date', width: 160,
      render: (_, r) => {
        if (!r.filing_expire_date) return '—';
        const d = r.days_until_expiry;
        const expiring = d !== null && d !== undefined && d <= 90 && d > 0;
        return (
          <span>
            {r.filing_expire_date}
            {expiring && <Tag color="red" style={{ marginLeft: 8 }}>{d} 天后到期</Tag>}
          </span>
        );
      },
    },
    {
      title: '资质审核', dataIndex: 'audit_status', width: 100,
      valueEnum: { pending: '待审核', approved: '已通过', rejected: '已驳回' },
      render: (_, r) => {
        const m = AUDIT_MAP[r.audit_status] || { color: 'default', text: r.audit_status };
        return <Tag color={m.color}>{m.text}</Tag>;
      },
    },
    {
      title: '操作', width: 80,
      render: (_, r) => <a onClick={() => openDrawer(r)}>审核</a>,
    },
  ];

  return (
    <>
      <ProTable<Qualification>
        headerTitle="备案管理"
        actionRef={actionRef}
        columns={columns}
        rowKey="id"
        search={{ labelWidth: 90 }}
        request={async (params) => {
          const res = await filingAPI.list({
            page: params.current || 1,
            page_size: params.pageSize || 10,
            audit_status: params.audit_status,
            filing_status: params.filing_status,
            keyword: params.keyword,
          });
          return { data: res.data.data.items, total: res.data.data.total, success: true };
        }}
      />
      <Drawer
        title="备案与资质审核"
        width={480}
        open={!!current}
        onClose={() => setCurrent(null)}
        destroyOnHidden
      >
        {current && (
          <Space direction="vertical" size="middle" style={{ width: '100%' }}>
            <Descriptions column={1} size="small">
              <Descriptions.Item label="代表">{current.rep_name}（{current.rep_phone}）</Descriptions.Item>
              <Descriptions.Item label="备案号">{current.filing_number || '—'}</Descriptions.Item>
              <Descriptions.Item label="备案有效期">{current.filing_expire_date || '—'}</Descriptions.Item>
              <Descriptions.Item label="学历证明">
                <a href={current.education_cert} target="_blank" rel="noreferrer">查看</a>
              </Descriptions.Item>
              {current.training_cert && (
                <Descriptions.Item label="培训证明">
                  <a href={current.training_cert} target="_blank" rel="noreferrer">查看</a>
                </Descriptions.Item>
              )}
              {current.reject_reason && (
                <Descriptions.Item label="驳回原因">{current.reject_reason}</Descriptions.Item>
              )}
            </Descriptions>
            <Radio.Group value={verdict} onChange={(e) => setVerdict(e.target.value)}>
              <Radio.Button value="approve">通过</Radio.Button>
              <Radio.Button value="reject">驳回</Radio.Button>
            </Radio.Group>
            {verdict === 'reject' && (
              <Input.TextArea
                rows={3}
                placeholder="驳回原因（必填）"
                value={reason}
                onChange={(e) => setReason(e.target.value)}
                maxLength={500}
              />
            )}
            <DatePicker
              placeholder="确认备案有效期（按凭证核对）"
              value={expireDate}
              onChange={setExpireDate}
              style={{ width: '100%' }}
            />
            <Button
              type="primary"
              block
              loading={submitting}
              onClick={submitReview}
              disabled={current.audit_status !== 'pending'}
            >
              {current.audit_status !== 'pending' ? '当前状态不可审核' : '提交审核'}
            </Button>
          </Space>
        )}
      </Drawer>
    </>
  );
}
```

- [ ] **Step 4: 路由 + 菜单**

修改 `web/src/App.tsx`：
- lazy 区追加：`const FilingList = lazy(() => import('./pages/Filing/FilingList'));`
- Routes 区 `user/list` 行之后追加：`<Route path="filing/list" element={<FilingList />} />`

修改 `web/src/constants/menu.tsx`：
- import 区加 `FileProtectOutlined`（追加到 `@ant-design/icons` 的导入列表）；
- menuConfig 数组在 `/user/list` 之后追加：

```tsx
{ path: '/filing/list', name: '备案管理', icon: <FileProtectOutlined /> },
```

- [ ] **Step 5: 构建验证**

Run: `cd web && npm run build`
Expected: exit 0（`✓ built in ...`，允许 chunk size 警告）

- [ ] **Step 6: 提交**

```bash
git add web/src/services/filing.ts web/src/types/index.ts web/src/pages/Filing/FilingList.tsx web/src/App.tsx web/src/constants/menu.tsx
git commit -m "feat(web): 备案管理页（列表 + 90 天到期提醒 + 审核抽屉）

Co-Authored-By: Claude <noreply@anthropic.com>"
```

---

### Task 9: Mobile API 层（multipart 通道 + 契约测试）

**Files:**
- Modify: `mobile/src/api/client.ts`（新增 upload 方法）
- Create: `mobile/src/api/qualification.ts`
- Modify: `mobile/src/types/index.ts`
- Modify: `mobile/jest.setup.js`（FormData polyfill 守卫）
- Test: `mobile/src/api/__tests__/qualification-contract.test.ts`

**Interfaces:**
- Produces: `apiClient.upload<T>(path, formData: FormData) -> Promise<T>`（60s 超时、token 注入、不设 Content-Type 让 fetch 生成 multipart boundary、错误/401 语义与 request 一致）；`qualificationAPI.getMy()`、`qualificationAPI.submit(payload: QualificationSubmitPayload)`。Task 10 依赖。
- `QualificationSubmitPayload = { filing_number?: string; filing_expire_date?: string; educationCert?: { uri: string; name: string; type: string }; trainingCert?: { uri: string; name: string; type: string } }`

- [ ] **Step 1: client.ts 加 upload 方法**

修改 `mobile/src/api/client.ts`，在 `request<T>` 方法之后、`generateUUID` 之前追加：

```ts
  /**
   * multipart 上传通道（资质证书文件）：request 是 JSON 专用，上传走这里。
   * 不设 Content-Type —— fetch 自动生成 multipart boundary；超时放宽到 60s。
   */
  async upload<T>(path: string, formData: FormData): Promise<T> {
    const token = await this.getToken();
    const headers: Record<string, string> = {
      'X-Request-ID': this.generateUUID(),
    };
    if (token) {
      headers['Authorization'] = `Bearer ${token}`;
    }

    const controller = new AbortController();
    const timeoutId = setTimeout(() => controller.abort(), 60000);

    try {
      const response = await fetch(`${this.baseURL}${path}`, {
        method: 'POST',
        headers,
        body: formData,
        signal: controller.signal,
      });

      clearTimeout(timeoutId);

      const result = await response.json();

      if (result.code !== 0) {
        throw new APIError(
          result.message || '请求失败',
          result.code || -1,
          response.status
        );
      }

      return result.data as T;
    } catch (error: any) {
      clearTimeout(timeoutId);
      if (error instanceof APIError) {
        const tokenInvalid =
          error.status === 401 || [2000, 2001, 2002, 2003].includes(error.code);
        if (tokenInvalid) {
          await this.clearToken();
          this.onUnauthorized?.();
        }
        throw error;
      }
      if (error.name === 'AbortError') {
        throw new APIError('上传超时，请检查网络连接', -1);
      }
      throw new APIError(error.message || '网络异常，请检查网络连接', -1);
    }
  }
```

- [ ] **Step 2: qualification.ts**

创建 `mobile/src/api/qualification.ts`：

```ts
/**
 * 备案与资质 API（需求文档 4.2）：
 *   - getMy: 本人备案资质状态（无记录返回 null → 屏幕渲染"未备案"空态）
 *   - submit: multipart 提交（react-native-document-picker 输出的文件对象
 *     {uri,name,type} 原样 append；RN 运行时提供 FormData，若 tsc 报未定义
 *     改用 (globalThis as any).FormData）
 */
import { apiClient } from './client';
import type { Qualification } from '../types';

export interface QualificationSubmitPayload {
  filing_number?: string;
  /** YYYY-MM-DD */
  filing_expire_date?: string;
  educationCert?: { uri: string; name: string; type: string };
  trainingCert?: { uri: string; name: string; type: string };
}

export const qualificationAPI = {
  getMy: () => apiClient.request<Qualification | null>('GET', '/api/v1/qualifications/me'),

  submit: (payload: QualificationSubmitPayload) => {
    const fd = new FormData();
    if (payload.filing_number) {
      fd.append('filing_number', payload.filing_number);
    }
    if (payload.filing_expire_date) {
      fd.append('filing_expire_date', payload.filing_expire_date);
    }
    if (payload.educationCert) {
      fd.append('education_cert', payload.educationCert as any);
    }
    if (payload.trainingCert) {
      fd.append('training_cert', payload.trainingCert as any);
    }
    return apiClient.upload<Qualification>('/api/v1/qualifications', fd);
  },
};
```

- [ ] **Step 3: 类型定义**

修改 `mobile/src/types/index.ts`，User 类型之后追加：

```ts
// ========== 备案与资质（后端 to_dict 同形状，见 web/src/types Qualification） ==========
export interface Qualification {
  id: number;
  representative_id: number;
  education_cert: string;
  training_cert?: string;
  audit_status: 'pending' | 'approved' | 'rejected';
  filing_number?: string;
  filing_status: 'not_filed' | 'valid' | 'expired';
  filing_expire_date?: string;
  days_until_expiry?: number | null;
  reject_reason?: string;
  reviewed_by?: number;
  reviewed_at?: string;
  compliance_training_completed: boolean;
  commitment_signed: boolean;
}
```

- [ ] **Step 4: jest.setup.js 追加 FormData polyfill（守卫式）**

修改 `mobile/jest.setup.js`，文件末尾追加：

```js
// multipart 契约测试需要 FormData；RN jest 环境不保证提供，缺失时给最小实现
if (typeof global.FormData === 'undefined') {
  class FormDataPolyfill {
    constructor() {
      this.parts = [];
    }
    append(key, value) {
      this.parts.push({ key, value });
    }
    get(key) {
      const found = this.parts.find((p) => p.key === key);
      return found ? found.value : null;
    }
    getAll(key) {
      return this.parts.filter((p) => p.key === key).map((p) => p.value);
    }
  }
  global.FormData = FormDataPolyfill;
}
```

- [ ] **Step 5: 契约测试**

创建 `mobile/src/api/__tests__/qualification-contract.test.ts`（沿用 api-contract.test.ts 的 fetch mock 模式）：

```ts
/**
 * 备案资质 API 契约测试：锁定 URL/method/multipart 字段。
 * multipart 走 client.upload（fetch body 为 FormData），与 JSON request 是两条通道。
 */
import { qualificationAPI } from '../qualification';

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

describe('qualificationAPI', () => {
  it('getMy 发 GET /api/v1/qualifications/me', async () => {
    await qualificationAPI.getMy();
    const { url, init } = lastCall();
    expect(url).toContain('/api/v1/qualifications/me');
    expect(init.method).toBe('GET');
  });

  it('submit 用 FormData 携带备案字段与文件，不设 Content-Type', async () => {
    await qualificationAPI.submit({
      filing_number: 'F-2026-001',
      filing_expire_date: '2028-06-30',
      educationCert: { uri: 'file:///edu.pdf', name: 'edu.pdf', type: 'application/pdf' },
    });
    const { url, init } = lastCall();
    expect(url).toContain('/api/v1/qualifications');
    expect(init.method).toBe('POST');
    expect(init.headers).not.toHaveProperty('Content-Type');
    const fd = init.body as FormData;
    expect(fd.get('filing_number')).toBe('F-2026-001');
    expect(fd.get('filing_expire_date')).toBe('2028-06-30');
    expect(fd.get('education_cert')).toEqual({
      uri: 'file:///edu.pdf',
      name: 'edu.pdf',
      type: 'application/pdf',
    });
  });

  it('submit 可选项不传时不 append（后端首次提交校验靠 education_cert 缺失拒绝）', async () => {
    await qualificationAPI.submit({
      educationCert: { uri: 'file:///edu.pdf', name: 'edu.pdf', type: 'application/pdf' },
    });
    const { init } = lastCall();
    const fd = init.body as FormData;
    expect(fd.get('filing_number')).toBeNull();
    expect(fd.get('filing_expire_date')).toBeNull();
    expect(fd.get('training_cert')).toBeNull();
    expect(fd.get('education_cert')).not.toBeNull();
  });
});
```

- [ ] **Step 6: 运行测试验证通过**

Run: `cd mobile && npx jest src/api/__tests__/qualification-contract.test.ts`
Expected: 3 passed
若报 `FormData is not defined`：确认 Step 4 的 polyfill 已写入且 jest.config.js 的 setupFiles 包含 jest.setup.js（现有 73 用例已依赖它，通常已配置）。

- [ ] **Step 7: 全量回归**

Run: `cd mobile && npx jest`
Expected: 76 passed（73 + 3）

- [ ] **Step 8: 提交**

```bash
git add mobile/src/api/client.ts mobile/src/api/qualification.ts mobile/src/types/index.ts mobile/jest.setup.js mobile/src/api/__tests__/qualification-contract.test.ts
git commit -m "feat(mobile): 备案资质 API 层（multipart 通道 + 契约测试）

Co-Authored-By: Claude <noreply@anthropic.com>"
```

---

### Task 10: Mobile 个人合规中心屏 + 导航 + Settings 入口

**Files:**
- Create: `mobile/src/screens/Compliance/ComplianceCenterScreen.tsx`
- Modify: `mobile/src/navigation/types.ts`
- Modify: `mobile/src/navigation/AppNavigator.tsx`
- Modify: `mobile/src/screens/Settings/SettingsScreen.tsx`
- Modify: `mobile/package.json`（安装 react-native-document-picker，不写死版本）

**Interfaces:**
- Consumes: `qualificationAPI.getMy()/submit()`（Task 9）、`RootStackParamList` 新增 `ComplianceCenter: undefined`。

- [ ] **Step 1: 安装依赖**

Run: `cd mobile && npm install react-native-document-picker`
（历史教训：别写死 `@^x.y.z` 版本号——audio-record@^0.6.2 曾不存在；装最新即可。原生模块 autolink，需重新 build：`cd mobile/android && ./gradlew assembleDebug`。iOS 无 Xcode 环境不验证，不影响本计划验收。）

- [ ] **Step 2: 导航类型**

修改 `mobile/src/navigation/types.ts`，`// 设置` 分组追加：

```ts
  ComplianceCenter: undefined;
```

- [ ] **Step 3: 注册路由**

修改 `mobile/src/navigation/AppNavigator.tsx`：
- import 区追加 `import ComplianceCenterScreen from '../screens/Compliance/ComplianceCenterScreen';`
- Stack.Screen 列表（Settings 行之后）追加：

```tsx
<Stack.Screen name="ComplianceCenter" component={ComplianceCenterScreen} options={{ animation: 'slide_from_right' }} />
```

- [ ] **Step 4: Settings 入口**

修改 `mobile/src/screens/Settings/SettingsScreen.tsx`：
- `RowAction` 联合类型追加 `'compliance'`：

```ts
type RowAction = 'profile' | 'notifications' | 'compliance' | 'coming' | 'about';
```

- sections 的「工作」分组 items 在「我的团队」之后追加一行（复用既有 `shield-account` 图标，不引入新图标名）：

```ts
{ icon: 'shield-account', label: '备案与资质', desc: '备案状态、资质审核', action: 'compliance' },
```

- `handleRowPress` 的 switch 追加分支：

```ts
case 'compliance':
  navigation.navigate('ComplianceCenter');
  break;
```

- [ ] **Step 5: 屏幕实现**

创建 `mobile/src/screens/Compliance/ComplianceCenterScreen.tsx`：

```tsx
/**
 * 个人合规中心（需求文档 4.2(4)）：
 *   备案状态 / 90 天到期提醒 / 资质审核状态 / 备案号+有效期录入 / 证书上传提交
 */
import React, { useCallback, useEffect, useState } from 'react';
import {
  Alert, ScrollView, StyleSheet, Text, TextInput, TouchableOpacity, View,
} from 'react-native';
import DocumentPicker from 'react-native-document-picker';
import Icon from '../../components/Icon';
import { qualificationAPI } from '../../api/qualification';
import type { Qualification } from '../../types';
import { BorderRadius, Colors, FontSize, Shadow, Spacing } from '../../constants/theme';

type PickedFile = { uri: string; name: string; type: string };

const AUDIT_TEXT: Record<string, string> = {
  pending: '待审核', approved: '已通过', rejected: '已驳回',
};
const FILING_TEXT: Record<string, string> = {
  valid: '有效', expired: '已过期', not_filed: '未备案',
};
const AUDIT_COLOR: Record<string, string> = {
  pending: Colors.warning, approved: Colors.success, rejected: Colors.danger,
};

export default function ComplianceCenterScreen() {
  const [qual, setQual] = useState<Qualification | null>(null);
  const [loaded, setLoaded] = useState(false);
  const [filingNumber, setFilingNumber] = useState('');
  const [expireDate, setExpireDate] = useState('');
  const [education, setEducation] = useState<PickedFile | null>(null);
  const [training, setTraining] = useState<PickedFile | null>(null);
  const [submitting, setSubmitting] = useState(false);

  const load = useCallback(async () => {
    setLoaded(false);
    try {
      const q = await qualificationAPI.getMy();
      setQual(q);
      if (q?.filing_number) setFilingNumber(q.filing_number);
      if (q?.filing_expire_date) setExpireDate(q.filing_expire_date);
    } catch {
      Alert.alert('加载失败', '无法获取备案信息，请检查网络后重试');
    } finally {
      setLoaded(true);
    }
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  const pickFile = async (target: 'education' | 'training') => {
    try {
      const res = await DocumentPicker.pick({
        type: [DocumentPicker.types.pdf, DocumentPicker.types.images],
      });
      const picked = Array.isArray(res) ? res[0] : res;
      const file: PickedFile = {
        uri: picked.uri,
        name: picked.name || 'cert',
        type: picked.type || 'application/pdf',
      };
      if (target === 'education') setEducation(file);
      else setTraining(file);
    } catch (err: any) {
      if (DocumentPicker.isCancel(err)) return; // 用户取消不弹错
      Alert.alert('选择失败', err?.message || '无法打开文件选择器');
    }
  };

  const submit = async () => {
    if (!education && !qual?.education_cert) {
      Alert.alert('提示', '请先选择学历证明文件');
      return;
    }
    if (expireDate.trim() && !/^\d{4}-\d{2}-\d{2}$/.test(expireDate.trim())) {
      Alert.alert('提示', '有效期格式应为 YYYY-MM-DD，如 2028-06-30');
      return;
    }
    setSubmitting(true);
    try {
      await qualificationAPI.submit({
        filing_number: filingNumber.trim() || undefined,
        filing_expire_date: expireDate.trim() || undefined,
        educationCert: education || undefined,
        trainingCert: training || undefined,
      });
      Alert.alert('已提交', '资质与备案材料已提交，等待医学部/合规部审核');
      setEducation(null);
      setTraining(null);
      await load();
    } catch (err: any) {
      Alert.alert('提交失败', err?.message || '请稍后重试');
    } finally {
      setSubmitting(false);
    }
  };

  const filingStatus = qual?.filing_status || 'not_filed';
  const days = qual?.days_until_expiry;
  const expiringSoon = days !== null && days !== undefined && days <= 90 && days > 0;
  const expired = filingStatus === 'expired';

  return (
    <View style={styles.container}>
      <View style={styles.header}>
        <Text style={styles.headerTitle}>备案与资质</Text>
      </View>
      <ScrollView contentContainerStyle={styles.content}>
        {/* 备案状态卡 */}
        <View style={[styles.card, Shadow.card]}>
          <Text style={styles.cardTitle}>备案状态</Text>
          <View style={styles.statusRow}>
            <Text style={styles.statusValue}>
              {FILING_TEXT[filingStatus] || filingStatus}
            </Text>
            {qual?.filing_number ? (
              <Text style={styles.desc}>备案号：{qual.filing_number}</Text>
            ) : (
              <Text style={styles.desc}>尚未录入备案号</Text>
            )}
            {qual?.filing_expire_date ? (
              <Text style={styles.desc}>有效期至：{qual.filing_expire_date}</Text>
            ) : null}
          </View>
          {expiringSoon && (
            <View style={styles.warnBox}>
              <Icon name="alert-circle" size={16} color={Colors.danger} />
              <Text style={styles.warnText}>备案将在 {days} 天后到期，请及时办理续期</Text>
            </View>
          )}
          {expired && (
            <View style={styles.warnBox}>
              <Icon name="alert-circle" size={16} color={Colors.danger} />
              <Text style={styles.warnText}>备案已过期，账号将被冻结，请尽快续期并重新提交</Text>
            </View>
          )}
        </View>

        {/* 资质审核状态卡 */}
        <View style={[styles.card, Shadow.card]}>
          <Text style={styles.cardTitle}>资质审核</Text>
          <View style={styles.statusRow}>
            <Text style={[styles.statusValue, { color: AUDIT_COLOR[qual?.audit_status || 'pending'] }]}>
              {AUDIT_TEXT[qual?.audit_status || 'pending']}
            </Text>
            {qual?.reject_reason ? (
              <Text style={styles.desc}>驳回原因：{qual.reject_reason}</Text>
            ) : null}
            {!qual && <Text style={styles.desc}>尚未提交资质材料</Text>}
          </View>
        </View>

        {/* 提交表单卡 */}
        <View style={[styles.card, Shadow.card]}>
          <Text style={styles.cardTitle}>提交 / 更新材料</Text>
          <Text style={styles.label}>备案号</Text>
          <TextInput
            style={styles.input}
            value={filingNumber}
            onChangeText={setFilingNumber}
            placeholder="国家备案平台备案号"
            placeholderTextColor={Colors.textHint}
          />
          <Text style={styles.label}>备案有效期（YYYY-MM-DD）</Text>
          <TextInput
            style={styles.input}
            value={expireDate}
            onChangeText={setExpireDate}
            placeholder="如 2028-06-30"
            placeholderTextColor={Colors.textHint}
          />
          <TouchableOpacity style={styles.pickBtn} onPress={() => pickFile('education')} activeOpacity={0.7}>
            <Icon name="file-pdf-box" size={20} color={Colors.primary} />
            <Text style={styles.pickText} numberOfLines={1}>
              {education ? education.name : qual?.education_cert ? '学历证明（已上传，可重新选择）' : '选择学历证明（必传）'}
            </Text>
          </TouchableOpacity>
          <TouchableOpacity style={styles.pickBtn} onPress={() => pickFile('training')} activeOpacity={0.7}>
            <Icon name="file-pdf-box" size={20} color={Colors.primary} />
            <Text style={styles.pickText} numberOfLines={1}>
              {training ? training.name : '选择培训考核合格证明（可选）'}
            </Text>
          </TouchableOpacity>
          <TouchableOpacity
            style={[styles.submitBtn, submitting && { opacity: 0.6 }]}
            disabled={submitting || !loaded}
            onPress={submit}
            activeOpacity={0.7}
          >
            <Text style={styles.submitText}>{submitting ? '提交中…' : '提交审核'}</Text>
          </TouchableOpacity>
          <Text style={styles.footnote}>提交后由医学部/合规部人工审核；重新提交将回到待审核状态</Text>
        </View>
      </ScrollView>
    </View>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1, backgroundColor: Colors.background },
  header: { paddingTop: Spacing.xl, paddingBottom: Spacing.md, alignItems: 'center' },
  headerTitle: { fontSize: FontSize.lg, fontWeight: '600', color: Colors.textPrimary },
  content: { padding: Spacing.md },
  card: { backgroundColor: Colors.card, borderRadius: BorderRadius.md, padding: Spacing.lg, marginBottom: Spacing.md },
  cardTitle: { fontSize: FontSize.md, fontWeight: '600', color: Colors.textPrimary, marginBottom: Spacing.sm },
  statusRow: { marginBottom: Spacing.xs },
  statusValue: { fontSize: FontSize.lg, fontWeight: '600', color: Colors.textPrimary, marginBottom: Spacing.xs },
  desc: { fontSize: FontSize.sm, color: Colors.textSecondary, marginTop: 2 },
  warnBox: { flexDirection: 'row', alignItems: 'center', marginTop: Spacing.sm, gap: 6 },
  warnText: { flex: 1, fontSize: FontSize.sm, color: Colors.danger },
  label: { fontSize: FontSize.sm, color: Colors.textSecondary, marginTop: Spacing.sm },
  input: {
    borderWidth: 1, borderColor: Colors.border, borderRadius: BorderRadius.sm,
    padding: Spacing.sm, marginTop: Spacing.xs, color: Colors.textPrimary, fontSize: FontSize.md,
  },
  pickBtn: {
    flexDirection: 'row', alignItems: 'center', gap: 8, marginTop: Spacing.md,
    borderWidth: 1, borderColor: Colors.border, borderRadius: BorderRadius.sm, padding: Spacing.sm,
  },
  pickText: { flex: 1, fontSize: FontSize.sm, color: Colors.textPrimary },
  submitBtn: {
    marginTop: Spacing.lg, backgroundColor: Colors.primary, borderRadius: BorderRadius.sm,
    padding: Spacing.md, alignItems: 'center',
  },
  submitText: { color: Colors.textWhite, fontSize: FontSize.md, fontWeight: '600' },
  footnote: { marginTop: Spacing.sm, fontSize: FontSize.xs, color: Colors.textHint, textAlign: 'center' },
});
```

> 注：主题令牌与图标名已核对——theme.ts 全量提供 `Colors.primary/textPrimary/textSecondary/textHint/textWhite/background/card/border/success/warning/danger`、`FontSize.xs/sm/md/lg`、`Spacing`、`BorderRadius.sm/md`、`Shadow.card`；Icon 组件透传 MaterialCommunityIcons，`alert-circle` / `file-pdf-box` 均为有效图标名。

- [ ] **Step 6: 编译与测试验证**

Run: `cd mobile && npx tsc --noEmit`
Expected: 无类型错误

Run: `cd mobile && npx jest`
Expected: 76 passed（屏幕文件不参与 jest，仅回归确认无破坏）

Run: `cd mobile/android && ./gradlew assembleDebug`
Expected: BUILD SUCCESSFUL（新原生依赖编译通过；模拟器装包见 CLAUDE.md mobile 节）

- [ ] **Step 7: 提交**

```bash
git add mobile/src/screens/Compliance/ComplianceCenterScreen.tsx mobile/src/navigation/types.ts mobile/src/navigation/AppNavigator.tsx mobile/src/screens/Settings/SettingsScreen.tsx mobile/package.json mobile/package-lock.json
git commit -m "feat(mobile): 个人合规中心（备案状态/到期提醒/资质上传提交）

Co-Authored-By: Claude <noreply@anthropic.com>"
```

---

### Task 11: 全量回归 + 迁移实跑 + 文档同步

**Files:**
- Modify: `CLAUDE.md`
- （如缺）Modify: `.env.example`（OSS_* 四项，knowledge-service 同款键名；QUALIFICATION_CHECK_INTERVAL_HOURS 注明默认 24 可省略）

**Interfaces:**
- 无新接口。收尾：跑全部门禁、实跑迁移 009、更新文档基线。

- [ ] **Step 1: 后端全量回归**

Run: `cd services/auth-service && python -m pytest tests/ -q`
Run: `cd services/gateway && python -m pytest tests/ -q`
Expected: auth 95 / gateway 76，全绿

- [ ] **Step 2: 前端全量回归**

Run: `cd mobile && npx jest`
Run: `cd web && npm run build`
Expected: mobile 76 / web build exit 0

- [ ] **Step 3: 迁移 009 实跑（本地 Docker 库）**

先确认 Docker Desktop 已起（WSL 引擎），然后：

```bash
docker exec -i medagent-postgres psql -U medagent medagent \
  < scripts/migrations/009_representative_qualifications.sql
docker exec medagent-postgres psql -U medagent medagent \
  -c "\d representative_qualifications"
```

Expected: 表结构含全部 16 列 + 两个索引。

- [ ] **Step 4: 实机冒烟（可选但建议，服务直跑）**

```bash
# 起 postgres/redis 后重启 auth + gateway（taskkill PID 后直跑，见 CLAUDE.md）
# 1. rep 登录拿 token → POST /api/v1/qualifications（curl 上传小 pdf）→ 200
# 2. GET /api/v1/qualifications/me → 备案状态 not_filed/valid 正确
# 3. admin 登录 → GET /api/v1/qualifications → 列表含 rep_name
# 4. PUT /{id}/review approve → audit_status=approved
# 5. 审计页能查到 qualification_submit / qualification_review 两条记录
```

- [ ] **Step 5: CLAUDE.md 同步**

修改 `CLAUDE.md`：
1. Architecture 服务端点补记段追加：auth `POST /api/v1/qualifications`（代表提交，multipart）、`GET /api/v1/qualifications/me`、`GET /api/v1/qualifications` + `PUT /{id}/review`（admin/manager/compliance/medical）。
2. Commands 测试基线行更新为本次回归实际数字（当前记录值：auth 70 / gateway 74 / mobile 73）。
3. Frontend web 模块列表补「备案管理 `/filing/list`」；mobile 屏幕列表补 `ComplianceCenterScreen`。
4. Gotchas 或 Database 段补：`representative_qualifications` 表（迁移 009，filing_status 为派生值）；`QUALIFICATION_CHECK_INTERVAL_HOURS`。
5. Known Gaps 追加挂账项：未备案/未过审全量使用门禁（待老板拍板存量方案）；医生资质审核（Plan B 复用 review 模式）；备案证书 OSS bucket ACL 私有化 + 签名 URL 预览；国家备案平台公开查询接口调研；培训考试字段二期接线。
6. `.env.example` 若缺 OSS_ACCESS_KEY_ID / OSS_ACCESS_KEY_SECRET / OSS_ENDPOINT / OSS_BUCKET 则补齐（与 knowledge-service 共用）。

- [ ] **Step 6: 提交**

```bash
git add CLAUDE.md .env.example
git commit -m "docs: 备案资质子系统（一期 A）文档同步 + 测试基线更新

Co-Authored-By: Claude <noreply@anthropic.com>"
```

- [ ] **Step 7: 推送（用户确认后）**

```bash
git push origin master   # origin = Codeup
```

---

## 附录：验收对照（需求文档 → 本计划任务）

| 需求条目 | 落点 |
|---|---|
| 3.3(1) 备案号录入与校验（人工审核兜底） | Task 3（录入+凭证上传）、Task 5（人工审核） |
| 3.3(2) 备案状态监控 / 90 天提醒 / 过期冻结 | Task 1（派生状态）、Task 6（冻结）、Task 8/10（提醒渲染） |
| 3.3(3) 备案变更记录 | Task 3/5 审计留痕（qualification_submit/review） |
| 3.3(4) 资质材料审核 | Task 5 |
| 4.2(1)(2)(3)(4) 代表端上传/校验/提醒/合规中心 | Task 9（API）、Task 10（屏幕） |
| 七 备案前置 | Task 6 到期冻结；未备案门禁挂账（设计决策 1） |
| 附录A representative_qualifications 表 | Task 1（含二期预留列） |
| 3.9(1) 医生资质审核 | 挂账至 Plan B（设计决策 2） |
| 一期管理后台「备案管理」 | Task 8 |
