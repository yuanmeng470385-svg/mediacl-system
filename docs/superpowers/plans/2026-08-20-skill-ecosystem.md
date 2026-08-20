# Skill 生态闭环（三期 J）Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 代表把个人 Skill 发布到公共空间，经管理后台审核后上代表侧广场；支持合规/作者双类下架并同步禁用已加载陪练场。

**Architecture:** 在二期 H 已有的 `skill_packages`/`skill_audits` 底座上扩展（加 description/content 内容字段 + 下架字段 + `skill_off_shelves` 下架记录表）。代表通过 `POST /skill-packages/release` 发布（pending，is_public=True），管理端在资产列表审核/下架，代表侧广场与陪练加载均校验 `off_shelf_status`。Skill 内容与权重任何 API 不返回（隐私铁律），仅审核 `detail` 受控查看并写访问审计。

**Tech Stack:** FastAPI + SQLAlchemy（specialist-service:8001）+ React web + React Native mobile + SQLite 单测（StaticPool + JSONB compile shim）。

## Global Constraints

- Skill 内容（`content`）与权重（`skill_weights`）任何 API 不返回；`to_dict()` 默认不暴露，仅 `expose_weights=True`（审核 detail）暴露。
- 公共列表/资产列表仅元数据（名称/创建者/治疗领域 description/风格标签/热度/好评率/下架状态）。
- 权限：`require_roles` 实时查库；管理端 `SKILL_ADMIN_ROLES = ("admin","manager","compliance","medical")`；代表端 `"rep"`。
- 静态路由（`/release`/`/mine`/`/asset-list`）必须声明在既有 `/{skill_id}` 动态路由之前，否则被 `/{id}` 先匹配报 422。
- 审计失败不影响业务（`write_audit_log` fail-silent）。
- 测试约定：SQLite + StaticPool；`BigInteger`/`JSONB` compile shim；`monkeypatch.setitem(app.dependency_overrides, get_db, _override_db)`；`write_audit_log` 用 AsyncMock。
- 错误码：ParamError→HTTP 400 code 1000；BusinessError(code=4001)→HTTP 422 code 4001。
- 验证门：`cd services/specialist-service && python -m pytest tests/ -v` 全量通过；`cd web && npm run build`；`cd mobile && npx jest`。

---

### Task 1: 迁移 019 + 模型扩展（skill_packages 新列 + skill_off_shelves + to_dict）

**Files:**
- Create: `scripts/migrations/019_skill_ecosystem.sql`
- Modify: `shared/models/skill.py`
- Modify: `scripts/init_db.sql`（skill_packages 建表块 + 追加 skill_off_shelves）

**Interfaces:**
- Produces: `SkillPackage` 新增列 `description: str|None`、`content: str|None`、`off_shelf_status: str`（默认 "active"）、`off_shelf_reason: str|None`、`off_shelf_type: str|None`、`off_shelf_by: int|None`、`off_shelf_at: datetime|None`；`SkillPackage.to_dict(expose_weights=False)`；新模型 `SkillOffShelf(skill_id, operator_id, off_shelf_type, reason)`。后续 Task 2-4 依赖这些字段名。

- [ ] **Step 1: 写迁移 SQL**

Create `scripts/migrations/019_skill_ecosystem.sql`:

```sql
-- 019_skill_ecosystem.sql
-- 三期 J：Skill 生态闭环（代表发布内容字段 / 下架字段 / 下架记录）
-- 用法：docker exec -i medagent-postgres psql -U medagent medagent < scripts/migrations/019_skill_ecosystem.sql

\set ON_ERROR_STOP on

ALTER TABLE skill_packages ADD COLUMN IF NOT EXISTS description VARCHAR(200);
ALTER TABLE skill_packages ADD COLUMN IF NOT EXISTS content TEXT;
ALTER TABLE skill_packages ADD COLUMN IF NOT EXISTS off_shelf_status VARCHAR(20) NOT NULL DEFAULT 'active';
ALTER TABLE skill_packages ADD COLUMN IF NOT EXISTS off_shelf_reason VARCHAR(500);
ALTER TABLE skill_packages ADD COLUMN IF NOT EXISTS off_shelf_type VARCHAR(20);
ALTER TABLE skill_packages ADD COLUMN IF NOT EXISTS off_shelf_by BIGINT REFERENCES users(id);
ALTER TABLE skill_packages ADD COLUMN IF NOT EXISTS off_shelf_at TIMESTAMP;
CREATE INDEX IF NOT EXISTS idx_sp_off ON skill_packages(off_shelf_status);

CREATE TABLE IF NOT EXISTS skill_off_shelves (
    id BIGSERIAL PRIMARY KEY,
    skill_id BIGINT NOT NULL REFERENCES skill_packages(id),
    operator_id BIGINT NOT NULL REFERENCES users(id),
    off_shelf_type VARCHAR(20) NOT NULL,   -- compliance/author
    reason VARCHAR(500),
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_sos_skill ON skill_off_shelves(skill_id);
```

- [ ] **Step 2: 扩展模型**

Modify `shared/models/skill.py`：
- 顶部 import 增加 `Text`（当前为 `from sqlalchemy import BigInteger, Boolean, Column, DateTime, ForeignKey, Numeric, String`）。
- `SkillPackage` 类在 `skill_weights` 之后加列；`to_dict` 加元数据/下架字段、`expose_weights=True` 时暴露 content。
- 追加 `SkillOffShelf` 类。

```python
"""Skill 模版与审核模型（需求 3.6/附录A skill_packages/skill_audits；三期 J 下架）"""
from sqlalchemy import BigInteger, Boolean, Column, DateTime, ForeignKey, Numeric, String, Text
from sqlalchemy.dialects.postgresql import JSONB

from shared.models.base import Base, TimestampMixin


class SkillPackage(Base, TimestampMixin):
    __tablename__ = "skill_packages"

    name = Column(String(100), nullable=False)
    creator_id = Column(BigInteger, ForeignKey("users.id"))
    is_public = Column(Boolean, nullable=False, default=False)
    is_anonymous = Column(Boolean, nullable=False, default=False)
    audit_status = Column(String(20), default="pending")
    audit_reason = Column(String(500))
    style_tags = Column(JSONB)
    heat = Column(BigInteger, default=0)
    approval_rate = Column(Numeric(5, 4))
    skill_weights = Column(JSONB)          # 任何 API 不返回
    # 三期 J：代表发布内容字段
    description = Column(String(200))      # 治疗领域/一句话说明（元数据，公共列表展示）
    content = Column(Text)                 # 话术素材（内容，仅审核人受控查看）
    # 三期 J：下架（3.6(3)）
    off_shelf_status = Column(String(20), nullable=False, default="active")  # active/off_shelved
    off_shelf_reason = Column(String(500))
    off_shelf_type = Column(String(20))    # compliance/author
    off_shelf_by = Column(BigInteger, ForeignKey("users.id"))
    off_shelf_at = Column(DateTime)

    def to_dict(self, expose_weights: bool = False) -> dict:
        d = {
            "id": self.id,
            "name": self.name,
            "creator_id": self.creator_id,
            "is_public": self.is_public,
            "is_anonymous": self.is_anonymous,
            "audit_status": self.audit_status,
            "audit_reason": self.audit_reason,
            "style_tags": self.style_tags,
            "heat": self.heat,
            "approval_rate": float(self.approval_rate) if self.approval_rate is not None else None,
            "description": self.description,
            "off_shelf_status": self.off_shelf_status,
            "off_shelf_reason": self.off_shelf_reason,
            "off_shelf_type": self.off_shelf_type,
            "off_shelf_by": self.off_shelf_by,
            "off_shelf_at": self.off_shelf_at.isoformat() if self.off_shelf_at else None,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }
        if expose_weights:
            d["skill_weights"] = self.skill_weights
            d["content"] = self.content
        return d


class SkillAudit(Base, TimestampMixin):
    __tablename__ = "skill_audits"

    skill_id = Column(BigInteger, ForeignKey("skill_packages.id"), nullable=False)
    auditor_id = Column(BigInteger, ForeignKey("users.id"), nullable=False)
    audit_result = Column(String(20), nullable=False)
    reason = Column(String(500))

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "skill_id": self.skill_id,
            "auditor_id": self.auditor_id,
            "audit_result": self.audit_result,
            "reason": self.reason,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }


class SkillOffShelf(Base, TimestampMixin):
    """下架记录存档（3.6(3) 下架操作记录存档）"""
    __tablename__ = "skill_off_shelves"

    skill_id = Column(BigInteger, ForeignKey("skill_packages.id"), nullable=False)
    operator_id = Column(BigInteger, ForeignKey("users.id"), nullable=False)
    off_shelf_type = Column(String(20), nullable=False)
    reason = Column(String(500))

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "skill_id": self.skill_id,
            "operator_id": self.operator_id,
            "off_shelf_type": self.off_shelf_type,
            "reason": self.reason,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }
```

- [ ] **Step 3: 同步 init_db.sql**

在 `scripts/init_db.sql` 的 `skill_packages` CREATE TABLE 块（~531-546 行）内 `skill_weights` 列后补 6 列，并在 `skill_audits` 建表后追加 `skill_off_shelves` 建表与索引。新库建表列与迁移 019 一致。

- [ ] **Step 4: 写失败测试（模型级）**

追加到 `services/specialist-service/tests/test_skill_packages.py`（import 加 `from shared.models.skill import SkillAudit, SkillPackage, SkillOffShelf`；`fresh_state` 的 `tables` 数组加 `SkillOffShelf.__table__`）：

```python
def test_to_dict_hides_content_weights_by_default():
    db = TestSession()
    sk = SkillPackage(
        id=99, name="测试", creator_id=1, description="心内科", content="话术素材",
        is_public=True, is_anonymous=False, audit_status="pending",
        style_tags=["严谨"], heat=0, skill_weights={"formal_level": "标准学术"},
        off_shelf_status="active",
    )
    db.add(sk)
    db.commit()
    d = sk.to_dict()
    assert d["description"] == "心内科"
    assert d["off_shelf_status"] == "active"
    assert "content" not in d
    assert "skill_weights" not in d
    d2 = sk.to_dict(expose_weights=True)
    assert d2["content"] == "话术素材"
    assert d2["skill_weights"] == {"formal_level": "标准学术"}
    db.close()
```

- [ ] **Step 5: 运行测试确认失败**

Run: `cd services/specialist-service && python -m pytest tests/test_skill_packages.py::test_to_dict_hides_content_weights_by_default -v`
Expected: FAIL（`'description'` 属性不存在 —— 模型未加列）。

- [ ] **Step 6: 实现并确认通过**

应用 Step 2 模型改动。重跑 Step 5 命令。
Expected: PASS。

- [ ] **Step 7: 全量单测确认无回归**

Run: `cd services/specialist-service && python -m pytest tests/ -q`
Expected: 既有 219 passed 不降。

- [ ] **Step 8: Commit**

```bash
git add scripts/migrations/019_skill_ecosystem.sql shared/models/skill.py scripts/init_db.sql services/specialist-service/tests/test_skill_packages.py
git commit -m "feat(skill): 迁移 019 + 模型扩展（Skill 内容字段/下架字段/下架记录）"
```

---

### Task 2: 后端 — 代表发布 release + 我的 Skill mine

**Files:**
- Modify: `services/specialist-service/app/api/skill_packages.py`（在 `/public` 端点后、`GET /{skill_id}/detail` 前插入 `POST /release` 与 `GET /mine`）
- Test: `services/specialist-service/tests/test_skill_packages.py`

**Interfaces:**
- Consumes: Task 1 的 `SkillPackage` 新列（description/content/is_public/is_anonymous）。
- Produces: `POST /api/v1/skill-packages/release`（rep）与 `GET /api/v1/skill-packages/mine`（rep）。Task 6 mobile 依赖。

- [ ] **Step 1: 写失败测试**

追加到 `test_skill_packages.py`：

```python
def test_release_requires_rep():
    resp = client.post("/api/v1/skill-packages/release", json={
        "name": "亲和力型", "description": "心内科", "content": "话术素材",
        "skill_weights": {"formal_level": "标准学术"},
    }, headers=_token(2, "admin"))
    assert resp.status_code == 403
    assert resp.json()["code"] == 3000


def test_release_creates_pending_public(fresh_state):
    resp = client.post("/api/v1/skill-packages/release", json={
        "name": "亲和力型", "description": "心内科", "content": "话术素材",
        "style_tags": ["亲和力"], "skill_weights": {"formal_level": "标准学术"}, "is_anonymous": True,
    }, headers=_token(1, "rep"))
    body = resp.json()
    assert body["code"] == 0
    data = body["data"]
    assert data["audit_status"] == "pending"
    assert data["is_public"] is True
    assert data["is_anonymous"] is True
    assert data["description"] == "心内科"
    assert "content" not in data
    assert "skill_weights" not in data
    fresh_state.assert_awaited_once()


def test_release_requires_description_content_weights():
    resp = client.post("/api/v1/skill-packages/release", json={"name": "缺内容"},
                       headers=_token(1, "rep"))
    assert resp.status_code == 400
    assert resp.json()["code"] == 1000


def test_mine_returns_own_skills(fresh_state):
    db = TestSession()
    db.add(SkillPackage(id=1, name="医学部建的", creator_id=3, is_public=True, is_anonymous=False,
                        audit_status="approved", style_tags=[], heat=0, skill_weights={}))
    db.add(SkillPackage(id=2, name="我的", creator_id=1, is_public=True, is_anonymous=False,
                        audit_status="approved", style_tags=["严谨"], heat=5, skill_weights={}))
    db.commit()
    db.close()
    resp = client.get("/api/v1/skill-packages/mine", headers=_token(1, "rep"))
    body = resp.json()
    assert body["code"] == 0
    assert body["data"]["total"] == 1
    item = body["data"]["items"][0]
    assert item["id"] == 2
    assert item["heat"] == 5
    assert "skill_weights" not in item


def test_mine_requires_rep():
    resp = client.get("/api/v1/skill-packages/mine", headers=_token(2, "admin"))
    assert resp.status_code == 403
```

- [ ] **Step 2: 运行测试确认失败**

Run: `cd services/specialist-service && python -m pytest tests/test_skill_packages.py -k "release or mine" -v`
Expected: FAIL（404/405 —— 路由不存在）。

- [ ] **Step 3: 实现**

在 `skill_packages.py` 中 `_validate_payload` 之后新增 `_validate_release_payload`；在 `GET /public` 端点函数结束后、`@router.get("/{skill_id}/detail")` 装饰器之前插入两个端点（**必须位于 `/{skill_id}` 动态路由之前**）：

```python
def _validate_release_payload(payload: dict) -> dict:
    if not isinstance(payload, dict):
        raise ParamError("请求体必须是 JSON 对象")
    name = (payload.get("name") or "").strip()
    if not name or len(name) > 100:
        raise ParamError("名称必填且不超过 100 字符")
    description = (payload.get("description") or "").strip()
    if not description or len(description) > 200:
        raise ParamError("治疗领域/说明必填且不超过 200 字符")
    content = (payload.get("content") or "").strip()
    if not content:
        raise ParamError("Skill 内容（话术素材）不能为空")
    weights = payload.get("skill_weights")
    if not isinstance(weights, dict) or not weights:
        raise ParamError("skill_weights 必须是非空对象（沟通风格参数）")
    style_tags = payload.get("style_tags")
    if style_tags is not None and not isinstance(style_tags, list):
        raise ParamError("style_tags 必须是数组")
    return {
        "name": name, "description": description, "content": content,
        "skill_weights": weights, "style_tags": style_tags,
        "is_anonymous": bool(payload.get("is_anonymous", False)),
    }


@router.post("/release")
async def release_skill(
    payload: dict,
    current_user: dict = Depends(require_roles("rep")),
    db: Session = Depends(get_db),
):
    """三期 J：代表发布 Skill 到公共空间 → pending，审核通过后上代表侧广场。
    is_public=True（发布意图）；/public 广场按 audit_status=approved 过滤，pending 不可见。"""
    data = _validate_release_payload(payload)
    sk = SkillPackage(
        name=data["name"], creator_id=current_user["id"],
        description=data["description"], content=data["content"],
        is_public=True, is_anonymous=data["is_anonymous"],
        audit_status="pending", style_tags=data["style_tags"], heat=0,
        skill_weights=data["skill_weights"],
    )
    db.add(sk)
    db.commit()
    db.refresh(sk)
    await write_audit_log(
        action="skill_release", user_id=current_user["id"],
        resource_type="skill_package", resource_id=str(sk.id),
        after_value={"name": sk.name, "description": sk.description},
        request_id=get_request_id() or None,
    )
    return success(sk.to_dict())


@router.get("/mine")
async def my_skills(
    page: int = 1,
    page_size: int = 20,
    current_user: dict = Depends(require_roles("rep")),
    db: Session = Depends(get_db),
):
    """三期 J：代表查看本人发布 Skill（审核状态 + 热度数据 heat/approval_rate）。"""
    p = PaginationParams(page=page, page_size=page_size)
    q = db.query(SkillPackage).filter(SkillPackage.creator_id == current_user["id"])
    total = q.count()
    rows = q.order_by(SkillPackage.id.desc()).offset(p.offset).limit(p.limit).all()
    return success(paginate([s.to_dict() for s in rows], total, p.page, p.page_size))
```

- [ ] **Step 4: 运行测试确认通过**

Run: `cd services/specialist-service && python -m pytest tests/test_skill_packages.py -k "release or mine" -v`
Expected: 4 PASS（含路由顺序：`/mine` 未被 `/{id}` 吞成 422）。

- [ ] **Step 5: Commit**

```bash
git add services/specialist-service/app/api/skill_packages.py services/specialist-service/tests/test_skill_packages.py
git commit -m "feat(skill): 代表发布 Skill 到公共空间 + 我的 Skill 列表"
```

---

### Task 3: 后端 — 资产列表 asset-list + detail 内容/访问审计 + public/load 下架过滤

**Files:**
- Modify: `services/specialist-service/app/api/skill_packages.py`
- Test: `services/specialist-service/tests/test_skill_packages.py`

**Interfaces:**
- Consumes: Task 1 的 `off_shelf_status`、`expose_weights`（含 content）、`SkillOffShelf`。
- Produces: `GET /api/v1/skill-packages/asset-list`（管理四角色，返回 `creator_name`/`creator_role`/`off_shelf_*` 元数据，绝不含 content/weights）；detail 每次查看写 `action="skill_detail_view"` 审计。Task 5 web 依赖。

- [ ] **Step 1: 写失败测试**

追加到 `test_skill_packages.py`（`from shared.models.user import User` 已存在）：

```python
def test_asset_list_includes_rep_skill_with_creator(fresh_state):
    db = TestSession()
    db.add(SkillPackage(id=1, name="代表风格", creator_id=1, is_public=True, is_anonymous=False,
                        audit_status="pending", description="心内科", content="素材",
                        style_tags=["严谨"], heat=0, skill_weights={}))
    db.commit()
    db.close()
    resp = client.get("/api/v1/skill-packages/asset-list", headers=_token(2, "admin"))
    body = resp.json()
    assert body["code"] == 0
    assert body["data"]["total"] == 1
    item = body["data"]["items"][0]
    assert item["name"] == "代表风格"
    assert item["creator_name"] == "张代表"
    assert item["creator_role"] == "rep"
    assert "content" not in item
    assert "skill_weights" not in item


def test_asset_list_filters_off_shelf(fresh_state):
    db = TestSession()
    db.add_all([
        SkillPackage(id=1, name="正常", creator_id=3, is_public=True, is_anonymous=False,
                     audit_status="approved", style_tags=[], heat=0, skill_weights={}),
        SkillPackage(id=2, name="已下架", creator_id=3, is_public=True, is_anonymous=False,
                     audit_status="approved", style_tags=[], heat=0, skill_weights={},
                     off_shelf_status="off_shelved", off_shelf_reason="违规", off_shelf_type="compliance"),
    ])
    db.commit()
    db.close()
    resp = client.get("/api/v1/skill-packages/asset-list", params={"off_shelf_status": "off_shelved"},
                      headers=_token(2, "admin"))
    body = resp.json()
    assert body["data"]["total"] == 1
    assert body["data"]["items"][0]["id"] == 2


def test_detail_exposes_content_and_writes_view_audit(fresh_state):
    _add_skill(id=1, audit_status="approved", content="话术素材")
    resp = client.get("/api/v1/skill-packages/1/detail", headers=_token(2, "admin"))
    body = resp.json()
    assert body["code"] == 0
    assert body["data"]["content"] == "话术素材"
    assert body["data"]["skill_weights"] == {"formal_level": "标准学术"}
    audit_mock = fresh_state
    audit_mock.assert_awaited()
    args, kwargs = audit_mock.call_args
    assert kwargs.get("action") == "skill_detail_view"


def test_public_excludes_off_shelved(fresh_state):
    db = TestSession()
    db.add_all([
        SkillPackage(id=1, name="正常", creator_id=1, is_public=True, is_anonymous=False,
                     audit_status="approved", style_tags=[], heat=0, skill_weights={}),
        SkillPackage(id=2, name="下架", creator_id=1, is_public=True, is_anonymous=False,
                     audit_status="approved", style_tags=[], heat=0, skill_weights={},
                     off_shelf_status="off_shelved", off_shelf_type="author", off_shelf_reason="作者申请"),
    ])
    db.commit()
    db.close()
    resp = client.get("/api/v1/skill-packages/public", headers=_token(1, "rep"))
    assert resp.json()["data"]["total"] == 1
    assert resp.json()["data"]["items"][0]["id"] == 1


def test_load_excludes_off_shelved(fresh_state):
    _add_skill(id=1, is_public=True, audit_status="approved",
               off_shelf_status="off_shelved", off_shelf_type="author", off_shelf_reason="作者申请")
    resp = client.post("/api/v1/skill-packages/1/load", json={}, headers=_token(1, "rep"))
    assert resp.status_code == 422
    assert resp.json()["code"] == 4001
```

- [ ] **Step 2: 运行测试确认失败**

Run: `cd services/specialist-service && python -m pytest tests/test_skill_packages.py -k "asset_list or detail_exposes or public_excludes or load_excludes" -v`
Expected: FAIL。

- [ ] **Step 3: 实现**

在 `skill_packages.py` 中：
- `from shared.models.user import User` 加入口 import。
- 新增 `GET /asset-list` 端点（放在 `/mine` 之后、`/{skill_id}/detail` 之前）。
- `GET /public` 查询加 `SkillPackage.off_shelf_status == "active"` 过滤。
- `GET /{skill_id}/detail` 写访问审计（action=`skill_detail_view`）。
- `POST /{skill_id}/load` 查询加 `SkillPackage.off_shelf_status == "active"`，错误文案改为「该 Skill 不可加载（已下架或未通过审核）」。

```python
@router.get("/asset-list")
async def asset_list(
    page: int = 1,
    page_size: int = 20,
    audit_status: Optional[str] = None,
    off_shelf_status: Optional[str] = None,
    keyword: Optional[str] = None,
    current_user: dict = Depends(require_roles(*SKILL_ADMIN_ROLES)),
    db: Session = Depends(get_db),
):
    """三期 J：Skill 资产公共列表（含代表发布，元数据 + 创建者姓名/角色）。
    绝不含 content/skill_weights（隐私边界附录B-1）。"""
    if audit_status and audit_status not in VALID_AUDIT:
        raise ParamError("audit_status 不合法")
    if off_shelf_status and off_shelf_status not in ("active", "off_shelved"):
        raise ParamError("off_shelf_status 不合法")
    p = PaginationParams(page=page, page_size=page_size)
    q = db.query(SkillPackage).outerjoin(User, SkillPackage.creator_id == User.id)
    if audit_status:
        q = q.filter(SkillPackage.audit_status == audit_status)
    if off_shelf_status:
        q = q.filter(SkillPackage.off_shelf_status == off_shelf_status)
    if keyword:
        q = q.filter(SkillPackage.name.ilike(f"%{keyword}%"))
    total = q.count()
    rows = (
        q.order_by(SkillPackage.id.desc())
        .offset(p.offset).limit(p.limit)
        .with_entities(SkillPackage, User.full_name, User.role)
        .all()
    )
    items = []
    for sk, creator_name, creator_role in rows:
        d = sk.to_dict()
        d["creator_name"] = creator_name
        d["creator_role"] = creator_role
        items.append(d)
    return success(paginate(items, total, p.page, p.page_size))
```

detail 端点改动（保留既有 `to_dict(expose_weights=True)`，增加审计）：

```python
    await write_audit_log(
        action="skill_detail_view", user_id=current_user["id"],
        resource_type="skill_package", resource_id=str(sk.id),
        after_value={"name": sk.name},
        request_id=get_request_id() or None,
    )
    return success(sk.to_dict(expose_weights=True))
```

- [ ] **Step 4: 运行测试确认通过**

Run: `cd services/specialist-service && python -m pytest tests/test_skill_packages.py -k "asset_list or detail_exposes or public_excludes or load_excludes" -v`
Expected: 5 PASS。再跑全量：`python -m pytest tests/ -q`，既有用例不降（`test_detail_exposes_weights_to_admin` 仍过——detail 现在多写一次审计，mock 不计数断言兼容；`test_public_plaza_only_approved`、`test_load_increments_heat` 仍过——新增行默认 active）。

- [ ] **Step 5: Commit**

```bash
git add services/specialist-service/app/api/skill_packages.py services/specialist-service/tests/test_skill_packages.py
git commit -m "feat(skill): 资产列表+审核访问审计+广场/加载下架过滤"
```

---

### Task 4: 后端 — 下架 off-shelf + 陪练场同步禁用

**Files:**
- Modify: `services/specialist-service/app/api/skill_packages.py`
- Modify: `services/specialist-service/app/api/practices.py`（create_session / practice_turn）
- Test: `services/specialist-service/tests/test_skill_packages.py`、`services/specialist-service/tests/test_practices.py`

**Interfaces:**
- Consumes: Task 1 的 `SkillOffShelf` + `off_shelf_*` 列；Task 3 的过滤。
- Produces: `POST /api/v1/skill-packages/{id}/off-shelf`；practice_turn 对 compliance 下架的 Skill 拒绝并提示原因；create_session 拒绝 off_shelved Skill。Task 5 web 依赖。

- [ ] **Step 1: 写失败测试**

追加到 `test_skill_packages.py`：

```python
def test_off_shelf_compliance_fields_and_record(fresh_state):
    _add_skill(id=1)
    resp = client.post("/api/v1/skill-packages/1/off-shelf", json={"type": "compliance", "reason": "含敏感信息"},
                       headers=_token(2, "admin"))
    body = resp.json()
    assert body["code"] == 0
    data = body["data"]
    assert data["off_shelf_status"] == "off_shelved"
    assert data["off_shelf_type"] == "compliance"
    assert data["off_shelf_reason"] == "含敏感信息"
    assert data["off_shelf_by"] == 2
    assert data["off_shelf_at"] is not None
    fresh_state.assert_awaited_once()
    db = TestSession()
    rec = db.query(SkillOffShelf).filter(SkillOffShelf.skill_id == 1).first()
    assert rec is not None and rec.off_shelf_type == "compliance"
    assert rec.operator_id == 2
    db.close()


def test_off_shelf_requires_reason(fresh_state):
    _add_skill(id=1)
    resp = client.post("/api/v1/skill-packages/1/off-shelf", json={"type": "compliance"},
                       headers=_token(2, "admin"))
    assert resp.status_code == 400
    assert resp.json()["code"] == 1000


def test_off_shelf_requires_type(fresh_state):
    _add_skill(id=1)
    resp = client.post("/api/v1/skill-packages/1/off-shelf", json={"reason": "下架"},
                       headers=_token(2, "admin"))
    assert resp.status_code == 400


def test_off_shelf_twice_4001(fresh_state):
    _add_skill(id=1, off_shelf_status="off_shelved", off_shelf_type="author", off_shelf_reason="作者申请")
    resp = client.post("/api/v1/skill-packages/1/off-shelf", json={"type": "compliance", "reason": "再下架"},
                       headers=_token(2, "admin"))
    assert resp.status_code == 422
    assert resp.json()["code"] == 4001
```

追加到 `test_practices.py`：

```python
def test_create_session_rejects_off_shelved(fresh_state):
    db = TestSession()
    db.add(SkillPackage(id=1, name="已下架", creator_id=3, is_public=True,
                        audit_status="approved", skill_weights={},
                        off_shelf_status="off_shelved", off_shelf_type="author", off_shelf_reason="作者申请"))
    db.commit()
    db.close()
    resp = client.post("/api/v1/practices", json={"skill_id": 1, "scenario": "心内科推广"},
                       headers=_token(1, "rep"))
    assert resp.status_code == 422
    assert resp.json()["code"] == 4001


def test_practice_turn_disabled_for_compliance_off_shelved(fresh_state, monkeypatch):
    db = TestSession()
    db.add(SkillPackage(id=1, name="违规下架", creator_id=3, is_public=True,
                        audit_status="approved", skill_weights={},
                        off_shelf_status="off_shelved", off_shelf_type="compliance", off_shelf_reason="含敏感信息"))
    db.add(PracticeSession(id=1, representative_id=1, skill_id=1, scenario="x",
                           status="in_progress", turn_count=1))
    db.commit()
    db.close()
    resp = client.post("/api/v1/practices/1/turn", json={"message": "您好"},
                       headers=_token(1, "rep"))
    assert resp.status_code == 422
    assert resp.json()["code"] == 4001
    assert "含敏感信息" in resp.json()["message"]


def test_practice_turn_allowed_for_author_off_shelved(fresh_state, monkeypatch):
    # 作者申请下架：已加载用户不受影响（3.6(3)）
    db = TestSession()
    db.add(SkillPackage(id=1, name="作者下架", creator_id=1, is_public=True,
                        audit_status="approved", skill_weights={},
                        off_shelf_status="off_shelved", off_shelf_type="author", off_shelf_reason="不想发了"))
    db.add(PracticeSession(id=1, representative_id=1, skill_id=1, scenario="x",
                           status="in_progress", turn_count=1))
    db.commit()
    db.close()
    from app.services import qwen_client as qc
    monkeypatch.setattr(qc.QwenClient, "chat", lambda self, *a, **k: {"content": "医生：请介绍下。", "usage": {}})
    monkeypatch.setattr(practices_api, "check_compliance", AsyncMock(return_value={"blocked": False}))
    resp = client.post("/api/v1/practices/1/turn", json={"message": "您好"},
                       headers=_token(1, "rep"))
    assert resp.json()["code"] == 0
```

- [ ] **Step 2: 运行测试确认失败**

Run: `cd services/specialist-service && python -m pytest tests/test_skill_packages.py -k off_shelf tests/test_practices.py -k "off_shelved" -v`
Expected: FAIL（404 —— off-shelf 路由不存在；practice 未校验）。

- [ ] **Step 3: 实现**

`skill_packages.py` 顶部加 `from datetime import datetime`，`from shared.models.skill import SkillAudit, SkillOffShelf, SkillPackage`。新增端点（放在 `POST /{skill_id}/review` 之后）：

```python
VALID_OFF_SHELF_TYPE = ("compliance", "author")


@router.post("/{skill_id}/off-shelf")
async def off_shelf_skill(
    skill_id: int,
    payload: dict,
    current_user: dict = Depends(require_roles(*SKILL_ADMIN_ROLES)),
    db: Session = Depends(get_db),
):
    """三期 J：Skill 下架（3.6(3)）。
    compliance=合规下架（已加载陪练禁用）；author=作者申请（已加载不受影响、新用户不可加载）。
    下架记录存档 skill_off_shelves + 审计。"""
    sk = db.query(SkillPackage).filter(SkillPackage.id == skill_id).first()
    if not sk:
        raise BusinessError("Skill 不存在", code=4001)
    if sk.off_shelf_status != "active":
        raise BusinessError("该 Skill 已下架", code=4001)
    if not isinstance(payload, dict):
        raise ParamError("请求体必须是 JSON 对象")
    off_type = payload.get("type")
    if off_type not in VALID_OFF_SHELF_TYPE:
        raise ParamError("type 必须是 compliance 或 author")
    reason = (payload.get("reason") or "").strip() if isinstance(payload.get("reason"), str) else ""
    if not reason:
        raise ParamError("下架原因必填")
    if len(reason) > 500:
        raise ParamError("原因长度不能超过 500 字符")
    sk.off_shelf_status = "off_shelved"
    sk.off_shelf_reason = reason
    sk.off_shelf_type = off_type
    sk.off_shelf_by = current_user["id"]
    sk.off_shelf_at = datetime.utcnow()
    db.add(SkillOffShelf(
        skill_id=sk.id, operator_id=current_user["id"],
        off_shelf_type=off_type, reason=reason,
    ))
    db.commit()
    db.refresh(sk)
    await write_audit_log(
        action="skill_off_shelf", user_id=current_user["id"],
        resource_type="skill_package", resource_id=str(sk.id),
        after_value={"off_shelf_status": sk.off_shelf_status, "off_shelf_type": off_type, "reason": reason},
        request_id=get_request_id() or None,
    )
    return success(sk.to_dict())
```

`practices.py` 两处改动：

`create_session` 的 skill 校验改为：

```python
    skill = None
    if skill_id:
        skill = db.query(SkillPackage).filter(SkillPackage.id == skill_id).first()
        if not skill or skill.audit_status != "approved" or not skill.is_public or skill.off_shelf_status != "active":
            raise BusinessError("Skill 不可用（未上架、未通过审核或已下架）", code=4001)
```

`practice_turn` 在 `skill = db.query(...)` 之后加：

```python
    if skill and skill.off_shelf_status == "off_shelved" and skill.off_shelf_type == "compliance":
        # 3.6(3) 合规下架：已加载该 Skill 的陪练场同步禁用并提示原因
        raise BusinessError(f"该 Skill 因合规原因已下架：{skill.off_shelf_reason or '违规内容'}，陪练已停用", code=4001)
```

- [ ] **Step 4: 运行测试确认通过**

Run: `cd services/specialist-service && python -m pytest tests/test_skill_packages.py tests/test_practices.py -q`
Expected: 全过（skill 原有 9 + 新增 4；practice 原有 9 + 新增 3）。

- [ ] **Step 5: Commit**

```bash
git add services/specialist-service/app/api/skill_packages.py services/specialist-service/app/api/practices.py services/specialist-service/tests/test_skill_packages.py services/specialist-service/tests/test_practices.py
git commit -m "feat(skill): Skill 下架（合规/作者双类）+ 陪练场同步禁用"
```

---

### Task 5: web — Skill 管理页升级（资产列表 + 下架抽屉）

**Files:**
- Modify: `web/src/services/skill.ts`
- Modify: `web/src/pages/Skill/SkillList.tsx`
- Test: 无 jest；验证门 = `cd web && npm run build`

**Interfaces:**
- Consumes: `GET /api/v1/skill-packages/asset-list`、`POST /api/v1/skill-packages/{id}/off-shelf`（Task 3/4）。

- [ ] **Step 1: 写失败测试（类型层：web 类型扩展）**

`web/src/types/index.ts` 的 `SkillPackage` 接口加字段（与后端 to_dict 对齐）：

```ts
  description: string | null;
  off_shelf_status: 'active' | 'off_shelved';
  off_shelf_reason: string | null;
  off_shelf_type: 'compliance' | 'author' | null;
  off_shelf_at: string | null;
  creator_name?: string | null;
  creator_role?: string | null;
  /** 话术内容：仅审核 detail 接口受控返回（隐私边界），列表/资产接口不返回 */
  content?: string;
```

- [ ] **Step 2: 扩展 skill.ts**

`web/src/services/skill.ts` 增加：

```ts
  assetList: (params?: { page?: number; page_size?: number; audit_status?: string; off_shelf_status?: string; keyword?: string }) =>
    client.get<PaginatedResponse<SkillPackage>>('/skill-packages/asset-list', { params }),
  offShelf: (id: number, data: { type: 'compliance' | 'author'; reason: string }) =>
    client.post<ApiResponse<SkillPackage>>(`/skill-packages/${id}/off-shelf`, data),
```

- [ ] **Step 3: 升级 SkillList.tsx**

改动要点（保持现有 ProTable + 审核抽屉 + 官方模版创建 ModalForm 结构）：
- `skillAPI.list` 换为 `skillAPI.assetList`（资产列表，含代表 Skill）；`params` 传 `{ page, page_size, audit_status, off_shelf_status }`。
- columns 增加：创建者（`creator_name` + `creator_role` Tag，rep 标注「代表发布」）、下架状态（`off_shelf_status` Tag：active 绿「已上架」/ off_shelved 红「已下架」+ `off_shelf_reason` tooltip）。
- 行操作新增「下架」按钮（`off_shelf_status === 'active'` 时显示）→ 新 `Drawer`：Radio 选 `type`（compliance「合规下架」/ author「作者申请下架」）+ `reason` TextArea（必填）→ `skillAPI.offShelf(id, { type, reason })` → 成功后 reload + message。
- 表格 `request` 参数已有 `off_shelf_status` 搜索列（选择 active/off_shelved）。

- [ ] **Step 4: 构建验证**

Run: `cd web && npm run build`
Expected: 构建成功（tsc -b && vite build 零错误）。

- [ ] **Step 5: Commit**

```bash
git add web/src/types/index.ts web/src/services/skill.ts web/src/pages/Skill/SkillList.tsx
git commit -m "feat(web): Skill 资产列表（含代表发布）+ 下架抽屉"
```

---

### Task 6: mobile — 发布 Skill + 我的 Skill 两屏 + 契约测试

**Files:**
- Modify: `mobile/src/api/practice.ts`
- Create: `mobile/src/screens/Skill/SkillReleaseScreen.tsx`
- Create: `mobile/src/screens/Skill/MySkillListScreen.tsx`
- Modify: `mobile/src/navigation/types.ts`
- Modify: `mobile/src/navigation/AppNavigator.tsx`
- Modify: `mobile/src/screens/Profile/ProfileScreen.tsx`
- Test: `mobile/src/api/__tests__/practice-contract.test.ts`

**Interfaces:**
- Consumes: `POST /api/v1/skill-packages/release`、`GET /api/v1/skill-packages/mine`（Task 2）。

- [ ] **Step 1: 写失败契约测试**

追加到 `mobile/src/api/__tests__/practice-contract.test.ts`：

```ts
  it('releaseSkill 发 POST /api/v1/skill-packages/release', async () => {
    await plazaAPI.releaseSkill({
      name: '亲和力型', description: '心内科', content: '话术素材',
      style_tags: ['亲和力'], skill_weights: { formal_level: '标准学术' }, is_anonymous: true,
    });
    const { url, init } = lastCall();
    expect(url).toContain('/api/v1/skill-packages/release');
    expect(JSON.parse(init.body)).toEqual({
      name: '亲和力型', description: '心内科', content: '话术素材',
      style_tags: ['亲和力'], skill_weights: { formal_level: '标准学术' }, is_anonymous: true,
    });
  });

  it('mySkills 发 GET /api/v1/skill-packages/mine', async () => {
    await plazaAPI.mySkills();
    const { url, init } = lastCall();
    expect(url).toContain('/api/v1/skill-packages/mine');
    expect(init.method).toBe('GET');
  });
```

- [ ] **Step 2: 运行契约测试确认失败**

Run: `cd mobile && npx jest practice-contract`
Expected: FAIL（releaseSkill/mySkills 不存在）。

- [ ] **Step 3: 实现 api 层**

`mobile/src/api/practice.ts` 的 `plazaAPI` 增加：

```ts
  releaseSkill: (payload: {
    name: string; description: string; content: string;
    style_tags?: string[]; skill_weights: Record<string, string>; is_anonymous?: boolean;
  }) => apiClient.request<any>('POST', '/api/v1/skill-packages/release', payload),
  mySkills: (params?: { page?: number; page_size?: number }) =>
    apiClient.request<any>('GET', '/api/v1/skill-packages/mine', params),
```

- [ ] **Step 4: 运行契约测试确认通过**

Run: `cd mobile && npx jest practice-contract`
Expected: PASS（新增 2 用例，原有全过）。

- [ ] **Step 5: 导航类型 + 注册**

`mobile/src/navigation/types.ts` 的 `RootStackParamList` 增加：

```ts
  SkillRelease: undefined;
  MySkillList: undefined;
```

`mobile/src/navigation/AppNavigator.tsx` 注册两个 Screen（参照 `Plaza`/`TwinManage` 的 lazy import 模式）：`SkillRelease` → `SkillReleaseScreen`、`MySkillList` → `MySkillListScreen`。

- [ ] **Step 6: 实现 SkillReleaseScreen**

Create `mobile/src/screens/Skill/SkillReleaseScreen.tsx`。表单（ScrollView + 受控 state）：名称 `name`、治疗领域/说明 `description`、话术内容 `content`（TextInput multiline）、风格标签 `style_tags`（多选 chips：严谨学术/亲和力/幽默/专业）、沟通风格权重三选 `skill_weights = { formal_level: '非常严谨'|'标准学术'|'略带亲和力', reply_length: '简洁'|'标准'|'详尽', opening_mode: '直切主题'|'先寒暄' }`、匿名 `is_anonymous`（Switch）。提交调 `plazaAPI.releaseSkill(...)` → `Alert.alert('已提交', 'Skill 已进入审核，审核通过后上架广场')` → `navigation.goBack()`。字段缺失时 Alert 提示，不发请求。顶部标题「发布 Skill」。视觉令牌用 `constants/theme.ts`（参照 PlazaScreen 的 StyleSheet 风格）。

- [ ] **Step 7: 实现 MySkillListScreen**

Create `mobile/src/screens/Skill/MySkillListScreen.tsx`。进入时 `plazaAPI.mySkills()` 拉列表；每条展示：名称 + `audit_status` 徽标（pending 橙「审核中」/approved 绿「已通过」/rejected 红「已驳回」）+ `heat` 加载数 + `approval_rate` 好评率（百分比）+ `off_shelf_status === 'off_shelved'` 时红字提示下架原因。空态用 `components/EmptyState`（参照 PracticeListScreen）。刷新按钮。

- [ ] **Step 8: Profile 入口**

`mobile/src/screens/Profile/ProfileScreen.tsx` 的入口数组（~27-32 行）追加两项（icon 用既有 MaterialCommunityIcons 名）：

```tsx
  { icon: 'creation-outline', label: 'Skill 发布', route: 'SkillRelease' as const },
  { icon: 'clipboard-list-outline', label: '我的 Skill', route: 'MySkillList' as const },
```

- [ ] **Step 9: 全量 jest + 类型检查**

Run: `cd mobile && npx jest && npx tsc --noEmit`
Expected: jest 全过（94 + 2 新契约用例）；tsc 零错误。

- [ ] **Step 10: Commit**

```bash
git add mobile/src/api/practice.ts mobile/src/api/__tests__/practice-contract.test.ts mobile/src/navigation/types.ts mobile/src/navigation/AppNavigator.tsx mobile/src/screens/Skill mobile/src/screens/Profile/ProfileScreen.tsx
git commit -m "feat(mobile): Skill 发布 + 我的 Skill 两屏（三期 J）"
```

---

### Task 7: 全量回归 + 文档同步

**Files:**
- Modify: `CLAUDE.md`（端点/表/基线/挂账）
- Modify: `README.md`（三期功能矩阵）
- Test: 全量回归

- [ ] **Step 1: 全量后端回归**

Run: `cd services/specialist-service && python -m pytest tests/ -q && cd ../../services/auth-service && python -m pytest tests/ -q`
Expected: specialist 219+新增全过；auth 不降。

- [ ] **Step 2: 前端验证**

Run: `cd web && npm run build` 与 `cd mobile && npx jest`
Expected: 全绿。

- [ ] **Step 3: 同步 CLAUDE.md**

在 Skill 模版段落后补三期 J 端点（`/skill-packages/release`、`/mine`、`/asset-list`、`/{id}/off-shelf`、detail 访问审计）与表（skill_packages 新列 + `skill_off_shelves`，迁移 019）；测试基线按实测更新（specialist ~219+新）；Known Gaps 划掉「Skill 上架仅官方模版」、补下架语义（compliance 禁用陪练/author 新用户不可加载）。

- [ ] **Step 4: 同步 README**

功能矩阵加三期 J 行（管理后台 Skill 资产审核/下架、代表端 Skill 发布）。

- [ ] **Step 5: Commit**

```bash
git add CLAUDE.md README.md
git commit -m "docs: 三期 J Skill 生态闭环文档同步"
```
