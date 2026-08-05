# MedAgent 缺口补齐 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 按设计文档实现 MedAgent 14 项缺口（规则热更新、监管报告导出、引用溯源、反馈/收藏、专员 CRUD、任务创建、画像更新、实时转写 fail-closed、DashVector/检索测试/版本管理/反馈落库/种子脚本、CI/CD、ARMS）。

**Architecture:** 全部为现有微服务内的增量改造。新表走一次迁移（003）+ init_db.sql 同步；第三方能力（DashVector/ES/ARMS/NLS）写真实客户端、未配置自动降级到现有链路并明确告警；跨服务调用走网关 internal 路由（X-Internal-Key）。

**Tech Stack:** FastAPI + SQLAlchemy + PostgreSQL（同库）、openpyxl（导出）、dashvector SDK + dashscope（向量）、prometheus-client（指标）、GitHub Actions（CI/CD）。

## Global Constraints

- 统一响应 `{code, message, data}`，用 `shared/common/response.py` 的 `success()` / `ParamError` / `BusinessError`
- 权限：业务接口 `Depends(get_current_user)` + 归属校验（本人或 admin）；管理接口 `require_roles(...)`；内部接口 `require_internal_key` + 网关 `INTERNAL_PATHS`
- 写操作一律 `write_audit_log(...)`（失败不阻塞业务）
- 新表必须同时出现在 `scripts/migrations/003_gap_closure.sql` 与 `scripts/init_db.sql`
- 所有第三方调用降级路径必须 `logger.warning/error` 明确告警，绝不静默假数据
- 测试命令：`cd services/<svc> && python -m pytest tests/ -v`（PYTHONPATH 指到仓库根，shared 可导入）
- 每个任务结束提交一次 git（仓库已在 master 分支，本地提交即可，不 push）

---

## Task 0: 迁移 003 + init_db.sql 同步

**Files:**
- Create: `scripts/migrations/003_gap_closure.sql`
- Modify: `scripts/init_db.sql`（文件末尾追加同款建表语句）

**Interfaces:**
- Produces: 新表 `conversation_feedback`、`conversation_favorites`、`tasks`、`knowledge_feedback`；`knowledge_documents` 加列 `revision INT`、`parent_doc_id BIGINT`

- [ ] **Step 1: 写迁移脚本** `scripts/migrations/003_gap_closure.sql`：

```sql
-- ============================================
-- 003 — 缺口补齐：反馈/收藏/任务/知识反馈表 + 版本链列
-- 执行：docker exec -i medagent-postgres psql -U medagent medagent \
--          < scripts/migrations/003_gap_closure.sql
-- 全新环境：init_db.sql 已同步包含以下定义，无需执行本脚本。
-- ============================================

BEGIN;

CREATE TABLE IF NOT EXISTS conversation_feedback (
    id BIGSERIAL PRIMARY KEY,
    conversation_id BIGINT REFERENCES conversations(id),
    user_id BIGINT REFERENCES users(id),
    specialist_id BIGINT REFERENCES digital_specialists(id),
    rating SMALLINT NOT NULL CHECK (rating IN (-1, 1)),
    comment TEXT,
    created_at TIMESTAMP DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_feedback_conversation ON conversation_feedback(conversation_id);
CREATE INDEX IF NOT EXISTS idx_feedback_user ON conversation_feedback(user_id);

CREATE TABLE IF NOT EXISTS conversation_favorites (
    id BIGSERIAL PRIMARY KEY,
    conversation_id BIGINT REFERENCES conversations(id),
    user_id BIGINT REFERENCES users(id),
    specialist_id BIGINT REFERENCES digital_specialists(id),
    question TEXT,
    answer TEXT,
    citations JSONB,
    created_at TIMESTAMP DEFAULT NOW(),
    UNIQUE (user_id, conversation_id)
);
CREATE INDEX IF NOT EXISTS idx_favorites_user ON conversation_favorites(user_id);

CREATE TABLE IF NOT EXISTS tasks (
    id BIGSERIAL PRIMARY KEY,
    visit_id BIGINT REFERENCES visit_records(id),
    user_id BIGINT REFERENCES users(id),
    title VARCHAR(500) NOT NULL,
    description TEXT,
    task_type VARCHAR(50) DEFAULT 'follow_up',
    due_date DATE,
    channel VARCHAR(50),
    status VARCHAR(20) DEFAULT 'open',
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_tasks_user_status ON tasks(user_id, status);
CREATE INDEX IF NOT EXISTS idx_tasks_visit ON tasks(visit_id);

CREATE TABLE IF NOT EXISTS knowledge_feedback (
    id BIGSERIAL PRIMARY KEY,
    user_id BIGINT REFERENCES users(id),
    query TEXT,
    doc_id VARCHAR(100),
    rating SMALLINT NOT NULL CHECK (rating IN (-1, 1)),
    comment TEXT,
    created_at TIMESTAMP DEFAULT NOW()
);

ALTER TABLE knowledge_documents ADD COLUMN IF NOT EXISTS revision INT DEFAULT 1;
ALTER TABLE knowledge_documents ADD COLUMN IF NOT EXISTS parent_doc_id BIGINT REFERENCES knowledge_documents(id);

COMMIT;
```

- [ ] **Step 2: 同步 init_db.sql** — 在文件末尾追加与 Step 1 完全相同的表/列定义（含索引），去掉 `IF NOT EXISTS` 也不影响新库（直接用同一份 SQL 即可，保持一致）。
- [ ] **Step 3: 验证语法**

Run: `docker exec -i medagent-postgres psql -U medagent medagent -v ON_ERROR_STOP=1 < scripts/migrations/003_gap_closure.sql`
Expected: 无报错；`\d tasks` 能看到新表。

- [ ] **Step 4: Commit**

```bash
git add scripts/migrations/003_gap_closure.sql scripts/init_db.sql
git commit -m "feat(db): migration 003 - feedback/favorites/tasks/knowledge_feedback tables + doc revision chain"
```

---

## 批次 A：合规闭环

### Task A1: 合规规则引擎 DB 加载 + 正则隔离

**Files:**
- Modify: `services/compliance-service/app/core/checker.py`（规则加载/编译/热更新）
- Modify: `services/compliance-service/app/config.py`（加 RULES_RELOAD_TTL）
- Modify: `services/compliance-service/app/api/rules.py`（create_rule 缺字段防护、CRUD 后触发 reload）
- Test: `services/compliance-service/tests/test_db_rules.py`

**Interfaces:**
- Consumes: `shared/models/compliance.ComplianceRule`（字段 rule_code/rule_name/rule_type/content(JSONB)/severity/action/enabled）、`shared/common/db_session.SessionLocal`、`checker.get_checker()` 单例
- Produces: `ComplianceChecker._load_db_rules() -> List[dict]`（引擎格式：id/name/type/patterns/severity/action/description/enabled）、`ComplianceChecker._merge_rules(yaml_rules, db_rules) -> List[dict]`（DB 覆盖 YAML，同 id 以 DB 为准）、`checker.reload()` 语义变为"清 TTL 立即重载"；`checker.rules` 在 TTL 内自动重载

- [ ] **Step 1: 写失败测试** `services/compliance-service/tests/test_db_rules.py`：

```python
"""合规规则 DB 加载单测（monkeypatch SessionLocal，不连真库）"""
import time
from app.core.checker import ComplianceChecker


class _FakeRow:
    def __init__(self, code, name, rtype, content, severity="high", action="reject", enabled=True):
        self.rule_code = code
        self.rule_name = name
        self.rule_type = rtype
        self.content = content
        self.severity = severity
        self.action = action
        self.enabled = enabled


class _FakeDb:
    def __init__(self, rows):
        self._rows = rows

    def query(self, *a, **kw):
        return self

    def filter(self, *a, **kw):
        return self

    def all(self):
        return [r for r in self._rows if r.enabled]

    def close(self):
        pass


def test_db_rules_override_yaml(monkeypatch):
    # DB 提供 R001（关键词，DB 版 patterns 覆盖 YAML）
    rows = [_FakeRow("R001", "禁止承诺疗效(DB版)", "keyword", {"patterns": ["包治百病"]})]
    monkeypatch.setattr(
        "shared.common.db_session.SessionLocal",
        lambda: _FakeDb(rows),
    )
    checker = ComplianceChecker()
    r001 = next(r for r in checker.rules if r["id"] == "R001")
    assert r001["patterns"] == ["包治百病"]  # DB 覆盖 YAML
    assert any(r["id"] == "R005" for r in checker.rules)  # YAML 补位仍在


def test_db_unavailable_falls_back_to_yaml(monkeypatch):
    def boom():
        raise RuntimeError("db down")
    monkeypatch.setattr("shared.common.db_session.SessionLocal", boom)
    checker = ComplianceChecker()
    assert len(checker.rules) >= 4  # YAML 兜底仍加载


def test_bad_regex_rule_isolated(monkeypatch):
    # 一条坏正则不拖垮整个引擎
    rows = [_FakeRow("R999", "坏正则", "regex", {"patterns": ["([unclosed"]})]
    monkeypatch.setattr("shared.common.db_session.SessionLocal", lambda: _FakeDb(rows))
    checker = ComplianceChecker()
    bad = [r for r in checker.rules if r["id"] == "R999"]
    assert bad == []  # 坏正则规则被剔除
    assert any(r["id"] == "R001" for r in checker.rules)  # 其余规则正常


def test_ttl_auto_reload(monkeypatch):
    rows = [_FakeRow("R001", "旧", "keyword", {"patterns": ["旧词"]})]
    monkeypatch.setattr("shared.common.db_session.SessionLocal", lambda: _FakeDb(rows))
    checker = ComplianceChecker()
    # 新规则出现 + 手动拨快 TTL
    rows2 = [_FakeRow("R001", "旧", "keyword", {"patterns": ["旧词"]}),
             _FakeRow("R010", "新规则", "keyword", {"patterns": ["新词"]})]
    monkeypatch.setattr("shared.common.db_session.SessionLocal", lambda: _FakeDb(rows2))
    checker.rules_ttl = 0.01
    time.sleep(0.02)
    result = checker.check("这里有新词", {})
    assert any(v["rule_code"] == "R010" for v in result["violations"])
```

- [ ] **Step 2: 运行确认失败**

Run: `cd services/compliance-service && python -m pytest tests/test_db_rules.py -v`
Expected: FAIL（DB 加载未实现，R001 patterns 仍是 YAML 的）

- [ ] **Step 3: 实现 DB 加载** `checker.py` 修改：

```python
import time  # 文件头部已有 import json/logging，补 time

class ComplianceChecker:
    def __init__(self):
        self.qwen_client = None
        self.rules: List[Dict] = []
        self.rules_ttl = settings.RULES_RELOAD_TTL
        self._rules_loaded_at = 0.0
        self._reload_rules()
```

`_reload_rules()` 中 TODO 位置（:53-55）替换为：

```python
        # 2. 从数据库加载规则（优先级高于 YAML，可覆盖）
        try:
            db_rules = self._load_db_rules()
            rules = self._merge_rules(rules, db_rules)
            logger.info("数据库规则加载完成，共 %d 条（含 YAML %d 条）", len(db_rules), len(rules))
        except Exception as exc:
            logger.error("数据库规则加载失败，仅用 YAML（危险：DB 规则不生效）: %s", exc)
```

方法末尾（`_compile_rules()` 之前）加：

```python
    def _load_db_rules(self) -> List[Dict]:
        """从 compliance_rules 表加载启用的规则（引擎格式）"""
        from shared.common.db_session import SessionLocal
        from shared.models.compliance import ComplianceRule
        db = SessionLocal()
        try:
            rows = db.query(ComplianceRule).filter(ComplianceRule.enabled == True).all()  # noqa: E712
            out = []
            for r in rows:
                content = r.content or {}
                out.append({
                    "id": r.rule_code,
                    "name": r.rule_name,
                    "type": r.rule_type,
                    "patterns": content.get("patterns", []),
                    "severity": r.severity,
                    "action": r.action,
                    "description": r.description or "",
                    "enabled": r.enabled,
                })
            return out
        finally:
            db.close()

    @staticmethod
    def _merge_rules(yaml_rules: List[Dict], db_rules: List[Dict]) -> List[Dict]:
        """DB 覆盖 YAML：同 id 以 DB 为准，YAML 独有的保留"""
        by_id = {r["id"]: r for r in db_rules}
        for r in yaml_rules:
            by_id.setdefault(r["id"], r)
        return list(by_id.values())
```

- [ ] **Step 4: 正则隔离 + TTL** `_compile_rules()` 替换为：

```python
    def _compile_rules(self):
        """预编译关键词和正则（单条失败只剔除该条，不拖垮引擎）"""
        valid = []
        for rule in self.rules:
            if rule["type"] == "keyword":
                rule["_patterns"] = [p for p in rule.get("patterns", [])]
                valid.append(rule)
            elif rule["type"] == "regex":
                compiled = []
                ok = True
                for p in rule.get("patterns", []):
                    try:
                        compiled.append(re.compile(p))
                    except re.error as exc:
                        logger.error("规则 %s 的正则 %r 编译失败，整条规则剔除: %s", rule["id"], p, exc)
                        ok = False
                        break
                if ok:
                    rule["_compiled"] = compiled
                    valid.append(rule)
            else:  # semantic
                valid.append(rule)
        self.rules = valid
```

`check()` 开头（:97 `if not content...` 之前）加 TTL 检查：

```python
        # 规则热更新：超过 TTL 自动重载（双 worker 各自最多延迟 rules_ttl 秒生效）
        if time.time() - self._rules_loaded_at > self.rules_ttl:
            try:
                self._reload_rules()
            except Exception as exc:
                logger.error("TTL 自动重载规则失败: %s", exc)
```

`_reload_rules()` 末尾（`logger.info(f"合规规则加载完成...")` 之后）加：

```python
        self._rules_loaded_at = time.time()
```

- [ ] **Step 5: 配置 TTL** `config.py` Settings 加：

```python
    RULES_RELOAD_TTL = float(os.getenv("RULES_RELOAD_TTL", "60"))
```

- [ ] **Step 6: rules.py CRUD 触发 reload + 缺字段防护**

- `create_rule`：`rule_code=request["rule_code"]` 改为：

```python
    rule_code = (request.get("rule_code") or "").strip()
    rule_name = (request.get("rule_name") or "").strip()
    if not rule_code or not rule_name:
        raise ParamError("rule_code 和 rule_name 不能为空")
    rule = ComplianceRule(
        rule_code=rule_code,
        rule_name=rule_name,
        rule_type=request.get("rule_type") or "keyword",
        ...
```

- `create_rule` commit 后、`update_rule` commit 后、`delete_rule` commit 后各加一行 `checker.reload()`（让本 worker 立即生效；其他 worker 靠 TTL）。
- `reload_rules` 端点（:201-212）保持不变（它调 checker.reload()）。

- [ ] **Step 7: 运行测试**

Run: `cd services/compliance-service && python -m pytest tests/ -v`
Expected: 新旧全部 PASS（原 test_checker.py 不受影响，因为启动时 DB 可连时 DB 行格式与 YAML 等价或覆盖后仍命中）

- [ ] **Step 8: Commit**

```bash
git add services/compliance-service/app/core/checker.py services/compliance-service/app/config.py services/compliance-service/app/api/rules.py services/compliance-service/tests/test_db_rules.py
git commit -m "feat(compliance): load rules from DB with YAML fallback, TTL auto-reload, isolate bad regex"
```

### Task A2: 合规监管自查报告导出

**Files:**
- Create: `services/compliance-service/app/api/report.py`
- Modify: `services/compliance-service/app/main.py`（include router）
- Modify: `services/compliance-service/requirements.txt`（加 openpyxl）
- Test: `services/compliance-service/tests/test_report_export.py`

**Interfaces:**
- Produces: `POST /api/v1/compliance/report/export`，body `{start_time?, end_time?}`（ISO 格式），返回 xlsx StreamingResponse；Sheet 名固定 `规则快照`/`拦截明细`/`汇总`

- [ ] **Step 1: 加依赖** `requirements.txt` 末尾加 `openpyxl>=3.1.0`。安装：`cd services/compliance-service && pip install openpyxl`（宿主 venv 已装则跳过）。
- [ ] **Step 2: 写失败测试** `tests/test_report_export.py`：

```python
"""监管自查报告导出单测（真实 openpyxl 写文件，读回断言）"""
import io
from datetime import datetime

import pytest
from openpyxl import load_workbook
from fastapi import Depends

from shared.common.response import success


def _build_rows():
    """构造与报告生成同构的数据（绕过 DB，直接测 Excel 组装函数）"""
    from app.api.report import build_report_workbook
    rules = [
        {"rule_code": "R001", "rule_name": "禁止承诺疗效", "rule_type": "keyword",
         "severity": "high", "action": "reject", "enabled": True, "version": 1, "hit_count": 3},
    ]
    blocks = [
        {"id": 1, "user_id": 1, "service_name": "specialist", "content": "保证治好",
         "rule_code": "R001", "rule_name": "禁止承诺疗效", "severity": "high",
         "action": "reject", "blocked_at": datetime(2026, 8, 1, 10, 0, 0)},
    ]
    summary = {"by_rule": [("R001", 3)], "by_service": [("specialist", 3)],
               "by_day": [("2026-08-01", 3)], "action_ratio": {"reject": 1.0, "warn": 0.0, "log": 0.0}}
    wb = build_report_workbook(rules, blocks, summary)
    bio = io.BytesIO()
    wb.save(bio)
    bio.seek(0)
    wb2 = load_workbook(bio)
    assert wb2.sheetnames == ["规则快照", "拦截明细", "汇总"]
    ws = wb2["规则快照"]
    headers = [c.value for c in ws[1]]
    assert "rule_code" in headers and "hit_count" in headers
    assert ws.max_row >= 2
    ws2 = wb2["拦截明细"]
    assert ws2.max_row >= 2
```

- [ ] **Step 3: 实现** `app/api/report.py`：

```python
"""合规监管自查报告导出（xlsx）"""
import io
import logging
from datetime import datetime
from typing import List, Dict

from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse
from openpyxl import Workbook
from sqlalchemy.orm import Session

from shared.common.db_session import get_db
from shared.common.response import ParamError
from shared.common.auth import require_roles
from shared.models.compliance import ComplianceBlock, ComplianceRule
from app.services.audit_client import write_audit_log

router = APIRouter(prefix="/api/v1/compliance", tags=["compliance"])
logger = logging.getLogger(__name__)

RULE_ADMIN_ROLES = ("admin", "manager", "compliance")


def _parse_time(value) -> datetime:
    try:
        return datetime.fromisoformat(value)
    except (TypeError, ValueError):
        raise ParamError(f"时间格式应为 ISO 8601（YYYY-MM-DDTHH:MM:SS），收到: {value}")


def build_report_workbook(rules: List[Dict], blocks: List[Dict], summary: Dict) -> Workbook:
    """组装报告 Excel（纯函数，便于单测）"""
    wb = Workbook()
    # ---- Sheet 1: 规则快照 ----
    ws = wb.active
    ws.title = "规则快照"
    ws.append(["rule_code", "rule_name", "rule_type", "severity", "action", "enabled", "version", "hit_count"])
    for r in rules:
        ws.append([r["rule_code"], r["rule_name"], r["rule_type"], r["severity"],
                   r["action"], r["enabled"], r["version"], r["hit_count"]])
    # ---- Sheet 2: 拦截明细 ----
    ws2 = wb.create_sheet("拦截明细")
    ws2.append(["id", "user_id", "service_name", "content", "rule_code", "rule_name", "severity", "action", "blocked_at"])
    for b in blocks:
        ws2.append([b["id"], b["user_id"], b["service_name"], b["content"], b["rule_code"],
                    b["rule_name"], b["severity"], b["action"],
                    b["blocked_at"].isoformat() if b["blocked_at"] else None])
    # ---- Sheet 3: 汇总 ----
    ws3 = wb.create_sheet("汇总")
    ws3.append(["统计项", "值"])
    for rule_code, cnt in summary["by_rule"]:
        ws3.append(["命中规则", f"{rule_code}: {cnt}"])
    for svc, cnt in summary["by_service"]:
        ws3.append(["按服务", f"{svc}: {cnt}"])
    for day, cnt in summary["by_day"]:
        ws3.append(["按天", f"{day}: {cnt}"])
    for action, ratio in summary["action_ratio"].items():
        ws3.append(["动作占比", f"{action}: {ratio:.1%}"])
    return wb


@router.post("/report/export")
async def export_report(
    request: dict,
    current_user: dict = Depends(require_roles(*RULE_ADMIN_ROLES)),
    db: Session = Depends(get_db),
):
    """导出监管自查报告：规则快照 + 拦截明细 + 汇总（Excel）"""
    start_time = _parse_time(request["start_time"]) if request.get("start_time") else None
    end_time = _parse_time(request["end_time"]) if request.get("end_time") else None
    if start_time and end_time and start_time > end_time:
        raise ParamError("start_time 不能晚于 end_time")

    from sqlalchemy import func as sqlfunc

    # 规则快照 + 命中次数
    rule_rows = db.query(ComplianceRule).all()
    hit_counts = dict(
        db.query(ComplianceBlock.rule_code, sqlfunc.count(ComplianceBlock.id))
        .group_by(ComplianceBlock.rule_code).all()
    )
    rules = [{**r.to_dict(), "hit_count": hit_counts.get(r.rule_code, 0)} for r in rule_rows]

    # 拦截明细
    bq = db.query(ComplianceBlock)
    if start_time:
        bq = bq.filter(ComplianceBlock.blocked_at >= start_time)
    if end_time:
        bq = bq.filter(ComplianceBlock.blocked_at <= end_time)
    block_rows = bq.order_by(ComplianceBlock.blocked_at.desc()).all()
    blocks = [{
        "id": b.id, "user_id": b.user_id, "service_name": b.service_name,
        "content": b.content, "rule_code": b.rule_code, "rule_name": b.rule_name,
        "severity": b.severity, "action": b.action, "blocked_at": b.blocked_at,
    } for b in block_rows]

    # 汇总（按时间范围统计）
    agg = db.query(ComplianceBlock.rule_code, sqlfunc.count(ComplianceBlock.id))
    if start_time:
        agg = agg.filter(ComplianceBlock.blocked_at >= start_time)
    if end_time:
        agg = agg.filter(ComplianceBlock.blocked_at <= end_time)
    agg_rows = agg.group_by(ComplianceBlock.rule_code).all()
    by_rule = [(rc, cnt) for rc, cnt in agg_rows]

    svc_agg = db.query(ComplianceBlock.service_name, sqlfunc.count(ComplianceBlock.id))
    if start_time:
        svc_agg = svc_agg.filter(ComplianceBlock.blocked_at >= start_time)
    if end_time:
        svc_agg = svc_agg.filter(ComplianceBlock.blocked_at <= end_time)
    by_service = [(s or "unknown", cnt) for s, cnt in svc_agg.group_by(ComplianceBlock.service_name).all()]

    from sqlalchemy import cast, Date
    day_agg = db.query(cast(ComplianceBlock.blocked_at, Date), sqlfunc.count(ComplianceBlock.id))
    if start_time:
        day_agg = day_agg.filter(ComplianceBlock.blocked_at >= start_time)
    if end_time:
        day_agg = day_agg.filter(ComplianceBlock.blocked_at <= end_time)
    by_day = [(d.isoformat(), cnt) for d, cnt in day_agg.group_by(cast(ComplianceBlock.blocked_at, Date)).all()]

    total = sum(cnt for _, cnt in by_rule) or 1
    action_ratio = {
        "reject": sum(1 for b in blocks if b["action"] == "reject") / total,
        "warn": sum(1 for b in blocks if b["action"] == "warn") / total,
        "log": sum(1 for b in blocks if b["action"] == "log") / total,
    }

    wb = build_report_workbook(rules, blocks, {"by_rule": by_rule, "by_service": by_service, "by_day": by_day, "action_ratio": action_ratio})
    bio = io.BytesIO()
    wb.save(bio)
    bio.seek(0)

    await write_audit_log(
        user_id=current_user["id"], action="compliance_report_export",
        resource_type="compliance_report",
        after_value={"start_time": request.get("start_time"), "end_time": request.get("end_time"), "rows": len(blocks)},
    )
    return StreamingResponse(
        bio,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": 'attachment; filename="compliance_report.xlsx"'},
    )
```

- [ ] **Step 4: 注册路由** `app/main.py` include：

```python
from app.api import report as report_api
app.include_router(report_api.router)
```

- [ ] **Step 5: 运行测试**

Run: `cd services/compliance-service && python -m pytest tests/ -v`
Expected: PASS（含新导出测试）

- [ ] **Step 6: Commit**

```bash
git add services/compliance-service/app/api/report.py services/compliance-service/app/main.py services/compliance-service/requirements.txt services/compliance-service/tests/test_report_export.py
git commit -m "feat(compliance): regulatory self-inspection report export (xlsx)"
```

---

## 批次 B：专员对话闭环

### Task B1: 引用溯源（解析百炼 docs）+ 连接超时修复

**Files:**
- Modify: `services/specialist-service/app/services/bailian_client.py`
- Modify: `services/specialist-service/app/core/answer_generator.py`
- Test: `services/specialist-service/tests/test_bailian_citations.py`

**Interfaces:**
- Consumes: `BailianClient.chat(app_id, prompt, session_id, history) -> Dict`（现有）
- Produces: `chat()` 返回新增 `citations: List[Dict{title, url, doc_id}]`；`AnswerGenerator.generate()` 返回透传 citations

- [ ] **Step 1: 写失败测试** `tests/test_bailian_citations.py`：

```python
"""百炼流式响应引用溯源解析（mock websocket 收包序列）"""
import json
import pytest

from app.services.bailian_client import BailianClient


class _FakeWs:
    """按顺序吐出预置消息帧"""
    def __init__(self, frames):
        self._frames = list(frames)
        self._sent = []

    async def __aenter__(self):
        return self

    async def __aexit__(self, *a):
        return False

    async def recv(self):
        if not self._frames:
            raise TimeoutError("no more frames")
        return json.dumps(self._frames.pop(0), ensure_ascii=False)

    async def send(self, data):
        self._sent.append(data)


def _frame(event, **output):
    return {"payload": {"output": {"event": event, **output}}}


def test_parse_citations_from_responding_content(monkeypatch):
    frames = [
        _frame("Started", dialog_id="d1"),
        _frame("DialogStateChanged", state="Listening"),
        _frame("RespondingContent", text="根据说明书，该药…", finished=False,
               extra_info={"docs": [{"doc_name": "说明书.pdf", "doc_url": "https://oss/1.pdf", "doc_id": "f1"}]}),
        _frame("RespondingContent", text="根据说明书，该药…", finished=True,
               extra_info={"docs": [{"doc_name": "说明书.pdf", "doc_url": "https://oss/1.pdf", "doc_id": "f1"}]}),
    ]
    monkeypatch.setattr("websockets.connect", lambda *a, **kw: _FakeWs(frames))
    client = BailianClient()
    result = __import__("asyncio").get_event_loop_policy().new_event_loop().run_until_complete(
        client.chat(app_id="app1", prompt="问题")
    )
    assert len(result["citations"]) == 1
    assert result["citations"][0]["title"] == "说明书.pdf"
    assert result["citations"][0]["url"] == "https://oss/1.pdf"


def test_citations_missing_is_empty(monkeypatch):
    frames = [
        _frame("Started", dialog_id="d1"),
        _frame("DialogStateChanged", state="Listening"),
        _frame("RespondingContent", text="没有引用", finished=True),
    ]
    monkeypatch.setattr("websockets.connect", lambda *a, **kw: _FakeWs(frames))
    client = BailianClient()
    result = __import__("asyncio").get_event_loop_policy().new_event_loop().run_until_complete(
        client.chat(app_id="app1", prompt="问题")
    )
    assert result["citations"] == []


def test_recv_timeout_raises_bailian_exception(monkeypatch):
    from app.services.bailian_client import BailianException

    class _HungWs(_FakeWs):
        async def recv(self):
            raise TimeoutError("recv timed out")

    frames = [_frame("Started", dialog_id="d1")]
    monkeypatch.setattr("websockets.connect", lambda *a, **kw: _HungWs(frames))
    client = BailianClient()
    client.timeout = 0.1  # 缩短超时便于测试
    with pytest.raises(BailianException):
        __import__("asyncio").get_event_loop_policy().new_event_loop().run_until_complete(
            client.chat(app_id="app1", prompt="问题")
        )
```

- [ ] **Step 2: 运行确认失败**

Run: `cd services/specialist-service && python -m pytest tests/test_bailian_citations.py -v`
Expected: FAIL（citations 不存在）

- [ ] **Step 3: 实现解析** `bailian_client.py`：

- `chat()` 开头（`answer_parts = []` 附近）加 `citations = []`。
- 两处 `msg = json.loads(await ws.recv())` 改为带超时：

```python
                for _ in range(20):
                    msg = json.loads(await asyncio.wait_for(ws.recv(), timeout=self.timeout))
```

```python
                for _ in range(60):
                    msg = json.loads(await asyncio.wait_for(ws.recv(), timeout=self.timeout))
```

- RespondingContent 分支（:125-130）改为：

```python
                    if ev == "RespondingContent":
                        output = msg["payload"]["output"]
                        text = output.get("text", "")
                        finished = output.get("finished", False)
                        answer_parts.append(text)  # 流式增量，每次是全量
                        # 引用溯源：解析 extra_info.docs（缺省/结构不符时防御式跳过）
                        extra_info = output.get("extra_info") or {}
                        for doc in extra_info.get("docs") or []:
                            if not isinstance(doc, dict):
                                continue
                            title = doc.get("doc_name") or doc.get("title") or doc.get("file_name") or ""
                            if title and not any(c["title"] == title for c in citations):
                                citations.append({
                                    "title": title,
                                    "url": doc.get("doc_url") or doc.get("url") or "",
                                    "doc_id": str(doc.get("doc_id") or doc.get("file_id") or ""),
                                })
                        if finished:
                            break
```

- 60 次循环耗尽后（`else` 块，:101-102 同款）加：

```python
                else:
                    raise BailianException("等待回答完成超时（60 次消息未结束）")
```

- 返回 dict 加 `"citations": citations,`。
- 文件头部 `import asyncio`。

- [ ] **Step 4: 透传 citations** `answer_generator.py`：

- `generate()` 中 `bailian_result.get("text", "")` 之后加 `citations = bailian_result.get("citations", [])`；降级分支（except BailianException）里 `citations = []`。
- 两处 blocked 返回与最终返回的 `"citations": []` 改为 `"citations": citations,`（预检分支的保持 `[]`——问题尚未发送）。

- [ ] **Step 5: 运行测试**

Run: `cd services/specialist-service && python -m pytest tests/ -v`
Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add services/specialist-service/app/services/bailian_client.py services/specialist-service/app/core/answer_generator.py services/specialist-service/tests/test_bailian_citations.py
git commit -m "feat(specialist): parse Bailian extra_info docs into citations; add recv timeout"
```

### Task B2: 反馈/收藏落库 + 满意度统计

**Files:**
- Create: `services/specialist-service/app/models/feedback.py`、`app/models/favorite.py`
- Create: `services/specialist-service/app/api/conversations.py`
- Modify: `services/specialist-service/app/main.py`（include router）
- Modify: `services/specialist-service/app/api/specialists.py`（删除假实现、stats 加满意度）
- Test: `services/specialist-service/tests/test_feedback_favorite.py`

**Interfaces:**
- Consumes: 表 `conversation_feedback`/`conversation_favorites`（Task 0）；`app.models.conversation.Conversation`（字段 id/user_id/specialist_id/session_id/role/content/citations）
- Produces: `POST /api/v1/conversations/{id}/feedback {rating, comment?}`；`POST /api/v1/conversations/{id}/favorite {}`（toggle，返回 `{is_favorite}`）；`GET /api/v1/favorites`（本人，分页）；`DELETE /api/v1/favorites/{id}`；`GET /api/v1/specialists/{id}/stats` 补 `satisfaction_rate`/`total_feedback`

- [ ] **Step 1: 写失败测试** `tests/test_feedback_favorite.py`（用 FakeDb 风格或真 SQLite 不可行——JSONB/引用复杂，改用 monkeypatch repo 层的纯逻辑测试 + 接口层用临时表不可行。采用纯函数测试：把归属校验/统计逻辑抽成可测函数）：

```python
"""反馈/收藏落库 + 满意度统计"""
from app.api.conversations import compute_satisfaction


def test_compute_satisfaction_empty():
    assert compute_satisfaction(0, 0) == {"total_feedback": 0, "satisfaction_rate": None}


def test_compute_satisfaction_rates():
    r = compute_satisfaction(3, 1)  # 3 赞 1 踩
    assert r["total_feedback"] == 4
    assert r["satisfaction_rate"] == 0.75


def test_compute_satisfaction_all_negative():
    assert compute_satisfaction(0, 2)["satisfaction_rate"] == 0.0
```

- [ ] **Step 2: 运行确认失败**

Run: `cd services/specialist-service && python -m pytest tests/test_feedback_favorite.py -v`
Expected: FAIL（模块不存在）

- [ ] **Step 3: 模型** `app/models/feedback.py`：

```python
"""对话反馈模型"""
from sqlalchemy import Column, BigInteger, SmallInteger, String, Text, ForeignKey
from shared.models.base import Base, TimestampMixin


class ConversationFeedback(Base, TimestampMixin):
    __tablename__ = "conversation_feedback"

    conversation_id = Column(BigInteger, ForeignKey("conversations.id"))
    user_id = Column(BigInteger, ForeignKey("users.id"))
    specialist_id = Column(BigInteger, ForeignKey("digital_specialists.id"))
    rating = Column(SmallInteger, nullable=False)  # 1 赞 / -1 踩
    comment = Column(Text)
```

`app/models/favorite.py`：

```python
"""对话收藏模型"""
from sqlalchemy import Column, BigInteger, String, Text, ForeignKey, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB
from shared.models.base import Base, TimestampMixin


class ConversationFavorite(Base, TimestampMixin):
    __tablename__ = "conversation_favorites"
    __table_args__ = (UniqueConstraint("user_id", "conversation_id"),)

    conversation_id = Column(BigInteger, ForeignKey("conversations.id"))
    user_id = Column(BigInteger, ForeignKey("users.id"))
    specialist_id = Column(BigInteger, ForeignKey("digital_specialists.id"))
    question = Column(Text)
    answer = Column(Text)
    citations = Column(JSONB)
```

（注册 FK 元数据：在 `app/main.py` 或模型文件里 `import shared.models.digital_specialist  # noqa` 与 conversations 表无需额外注册——conversations 表在 specialist-service 自身模型里。）

- [ ] **Step 4: 接口** `app/api/conversations.py`：

```python
"""对话反馈 / 收藏 / 我的收藏"""
import logging
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from shared.common.auth import get_current_user
from shared.common.db_session import get_db
from shared.common.pagination import PaginationParams, paginate
from shared.common.response import BusinessError, ParamError, success

from app.models.conversation import Conversation
from app.models.feedback import ConversationFeedback
from app.models.favorite import ConversationFavorite

router = APIRouter(prefix="/api/v1/conversations", tags=["conversations"])
logger = logging.getLogger(__name__)


def _get_conv_or_404(db: Session, conv_id: int) -> Conversation:
    conv = db.query(Conversation).filter(Conversation.id == conv_id).first()
    if not conv:
        raise HTTPException(status_code=404, detail="对话不存在")
    return conv


def _assert_conv_owner(conv: Conversation, current_user: dict):
    if conv.user_id != current_user["id"] and current_user.get("role") != "admin":
        raise HTTPException(status_code=403, detail="无权操作该对话")


@router.post("/{conversation_id}/feedback")
async def submit_feedback(
    conversation_id: int,
    request: dict,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """点赞/点踩：{"rating": 1|-1, "comment": "可选"}"""
    rating = request.get("rating")
    if rating not in (1, -1):
        raise ParamError("rating 必须是 1（赞）或 -1（踩）")
    conv = _get_conv_or_404(db, conversation_id)
    _assert_conv_owner(conv, current_user)
    fb = ConversationFeedback(
        conversation_id=conv.id,
        user_id=current_user["id"],
        specialist_id=conv.specialist_id,
        rating=rating,
        comment=(request.get("comment") or "")[:500],
    )
    db.add(fb)
    db.commit()
    logger.info("feedback saved: user=%s conv=%s rating=%s", current_user["id"], conv.id, rating)
    return success({"feedback_id": fb.id})


@router.post("/{conversation_id}/favorite")
async def toggle_favorite(
    conversation_id: int,
    request: dict,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """收藏/取消收藏（toggle）"""
    conv = _get_conv_or_404(db, conversation_id)
    _assert_conv_owner(conv, current_user)
    existing = db.query(ConversationFavorite).filter(
        ConversationFavorite.user_id == current_user["id"],
        ConversationFavorite.conversation_id == conv.id,
    ).first()
    if existing:
        db.delete(existing)
        db.commit()
        return success({"is_favorite": False})
    # 快照问题与答案（conversation 里 user 行是问题、assistant 行是答案，取同 session 两条）
    msgs = db.query(Conversation).filter(
        Conversation.session_id == conv.session_id
    ).order_by(Conversation.created_at).all() if conv.session_id else [conv]
    question = next((m.content for m in msgs if m.role == "user"), conv.content)
    answer = next((m.content for m in msgs if m.role == "assistant"), "")
    fav = ConversationFavorite(
        conversation_id=conv.id,
        user_id=current_user["id"],
        specialist_id=conv.specialist_id,
        question=question,
        answer=answer,
        citations=conv.citations,
    )
    db.add(fav)
    db.commit()
    return success({"is_favorite": True})


def compute_satisfaction(positive: int, negative: int) -> dict:
    """满意度统计（纯函数）"""
    total = positive + negative
    if total == 0:
        return {"total_feedback": 0, "satisfaction_rate": None}
    return {"total_feedback": total, "satisfaction_rate": round(positive / total, 4)}
```

注意：`/conversations/{conversation_id}/feedback` 与 `/conversations/favorites` 若放同一 router，`{conversation_id}` 路径参数会拦截 `/favorites`。为消除歧义，**favorites 用独立 router**（prefix=`/api/v1/favorites`），本文件尾部定义：

```python
favorites_router = APIRouter(prefix="/api/v1/favorites", tags=["favorites"])

@favorites_router.get("")
async def list_favorites(
    page: int = 1,
    page_size: int = 20,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """我的收藏列表"""
    p = PaginationParams(page=page, page_size=page_size)
    q = db.query(ConversationFavorite).filter(ConversationFavorite.user_id == current_user["id"])
    total = q.count()
    items = q.order_by(ConversationFavorite.created_at.desc()).offset(p.offset).limit(p.limit).all()
    return success(paginate([{
        "id": f.id, "conversation_id": f.conversation_id, "specialist_id": f.specialist_id,
        "question": f.question, "answer": f.answer, "citations": f.citations,
        "created_at": f.created_at.isoformat() if f.created_at else None,
    } for f in items], total=total, page=p.page, page_size=p.page_size))


@favorites_router.delete("/{favorite_id}")
async def remove_favorite(
    favorite_id: int,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """取消收藏"""
    fav = db.query(ConversationFavorite).filter(ConversationFavorite.id == favorite_id).first()
    if not fav:
        raise HTTPException(status_code=404, detail="收藏不存在")
    if fav.user_id != current_user["id"] and current_user.get("role") != "admin":
        raise HTTPException(status_code=403, detail="无权操作该收藏")
    db.delete(fav)
    db.commit()
    return success(None, "已取消收藏")
```

即：`conversations_router`（本文件上方的 `router`）只保留 `/{conversation_id}/feedback` 与 `/{conversation_id}/favorite` 两个路由；收藏列表/删除挂 `favorites_router`。文件头部 import 相应调整（两个 router 共用的工具函数保持一致）。

- [ ] **Step 5: 注册路由** `app/main.py`：

```python
from app.api import conversations
app.include_router(conversations.router)
app.include_router(conversations.favorites_router)
```

- [ ] **Step 6: 网关路由** `services/gateway/app/main.py` ROUTE_MAP 加：

```python
    "/api/v1/favorites": settings.SPECIALIST_SERVICE_URL,
```

（`/api/v1/conversations` 已有映射。）

- [ ] **Step 7: 删除假实现 + stats 满意度** `app/api/specialists.py`：

- 删除 `submit_feedback` 与 `toggle_favorite` 两个假端点（:160-184）。
- `get_specialist_stats` 改为：

```python
@router.get("/{specialist_id}/stats")
async def get_specialist_stats(
    specialist_id: int,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """专员使用统计（对话数 + 满意度）"""
    from app.models.conversation import Conversation
    from app.models.feedback import ConversationFeedback
    from sqlalchemy import func
    from app.api.conversations import compute_satisfaction

    specialist = db.query(Specialist).filter(Specialist.id == specialist_id).first()
    if not specialist:
        raise HTTPException(status_code=404, detail="专员不存在")
    total = db.query(func.count(Conversation.id)).filter(
        Conversation.specialist_id == specialist_id
    ).scalar()
    positive = db.query(func.count(ConversationFeedback.id)).filter(
        ConversationFeedback.specialist_id == specialist_id,
        ConversationFeedback.rating == 1,
    ).scalar()
    negative = db.query(func.count(ConversationFeedback.id)).filter(
        ConversationFeedback.specialist_id == specialist_id,
        ConversationFeedback.rating == -1,
    ).scalar()
    return success({"total_conversations": total, **compute_satisfaction(positive or 0, negative or 0)})
```

- [ ] **Step 8: 运行测试**

Run: `cd services/specialist-service && python -m pytest tests/ -v`
Expected: PASS

- [ ] **Step 9: Commit**

```bash
git add services/specialist-service/app/models/feedback.py services/specialist-service/app/models/favorite.py services/specialist-service/app/api/conversations.py services/specialist-service/app/api/specialists.py services/specialist-service/app/main.py services/gateway/app/main.py services/specialist-service/tests/test_feedback_favorite.py
git commit -m "feat(specialist): persist feedback & favorites, satisfaction stats, remove fake endpoints"
```

### Task B3: 专员 CRUD

**Files:**
- Modify: `services/specialist-service/app/api/specialists.py`
- Test: `services/specialist-service/tests/test_specialist_crud.py`

**Interfaces:**
- Produces: `POST /api/v1/specialists`、`PUT /api/v1/specialists/{id}`、`DELETE /api/v1/specialists/{id}`（软删），全部 `require_roles("admin")`；可更新字段白名单 `SPECIALIST_UPDATE_FIELDS = {"name", "product_id", "persona", "knowledge_scope", "compliance_level", "bailian_app_id", "status"}`

- [ ] **Step 1: 写失败测试** `tests/test_specialist_crud.py`：

```python
"""专员 CRUD 权限与字段校验（monkeypatch DB，测校验逻辑）"""
import pytest

from app.api.specialists import _validate_specialist_fields, _normalize_status
from shared.common.response import ParamError


def test_validate_create_requires_name():
    with pytest.raises(ParamError):
        _validate_specialist_fields({"product_id": 1}, creating=True)


def test_validate_update_rejects_unknown_fields():
    with pytest.raises(ParamError):
        _validate_specialist_fields({"name": "新", "hack": True}, creating=False)


def test_normalize_status():
    assert _normalize_status("active") == "active"
    assert _normalize_status("DRAFT") == "draft"
    with pytest.raises(ParamError):
        _normalize_status("banned")
```

- [ ] **Step 2: 运行确认失败**

Run: `cd services/specialist-service && python -m pytest tests/test_specialist_crud.py -v`
Expected: FAIL（函数不存在）

- [ ] **Step 3: 实现** `app/api/specialists.py` 追加：

```python
from shared.common.auth import get_current_user, require_roles
from app.services.audit_client import write_audit_log

SPECIALIST_UPDATE_FIELDS = {
    "name", "product_id", "persona", "knowledge_scope",
    "compliance_level", "bailian_app_id", "status",
}
VALID_STATUSES = {"draft", "active", "disabled"}


def _normalize_status(status: str) -> str:
    s = (status or "").strip().lower()
    if s not in VALID_STATUSES:
        raise ParamError(f"status 必须是 {'/'.join(sorted(VALID_STATUSES))}")
    return s


def _validate_specialist_fields(request: dict, creating: bool) -> dict:
    """白名单 + 必填校验（纯函数，便于单测）"""
    allowed = set(request.keys()) - SPECIALIST_UPDATE_FIELDS
    if creating:
        allowed -= {"name"}
        allowed.discard("status")
    if allowed:
        raise ParamError(f"不允许的字段: {sorted(allowed)}")
    if creating:
        name = (request.get("name") or "").strip()
        if not name:
            raise ParamError("name 不能为空")
        if not request.get("product_id"):
            raise ParamError("product_id 不能为空")
    return request


# ==================== 专员 CRUD（S6：仅 admin） ====================

@router.post("")
async def create_specialist(
    request: dict,
    current_user: dict = Depends(require_roles("admin")),
    db: Session = Depends(get_db),
):
    """创建专员"""
    data = _validate_specialist_fields(request, creating=True)
    specialist = Specialist(
        name=data["name"].strip(),
        product_id=int(data["product_id"]),
        persona=data.get("persona"),
        knowledge_scope=data.get("knowledge_scope"),
        compliance_level=data.get("compliance_level", "internal"),
        bailian_app_id=data.get("bailian_app_id"),
        status=_normalize_status(data.get("status", "draft")),
    )
    db.add(specialist)
    db.commit()
    db.refresh(specialist)
    await write_audit_log(
        user_id=current_user["id"], action="specialist_create",
        resource_type="digital_specialist", resource_id=str(specialist.id),
        after_value=specialist.to_dict(),
    )
    return success(specialist.to_dict(), "专员已创建")


@router.put("/{specialist_id}")
async def update_specialist(
    specialist_id: int,
    request: dict,
    current_user: dict = Depends(require_roles("admin")),
    db: Session = Depends(get_db),
):
    """编辑专员（仅白名单字段）"""
    specialist = db.query(Specialist).filter(Specialist.id == specialist_id).first()
    if not specialist:
        raise HTTPException(status_code=404, detail="专员不存在")
    data = _validate_specialist_fields(request, creating=False)
    for field in SPECIALIST_UPDATE_FIELDS:
        if field in data and data[field] is not None:
            value = _normalize_status(data[field]) if field == "status" else data[field]
            setattr(specialist, field, value)
    db.commit()
    db.refresh(specialist)
    await write_audit_log(
        user_id=current_user["id"], action="specialist_update",
        resource_type="digital_specialist", resource_id=str(specialist_id),
        after_value=specialist.to_dict(),
    )
    return success(specialist.to_dict())


@router.delete("/{specialist_id}")
async def disable_specialist(
    specialist_id: int,
    current_user: dict = Depends(require_roles("admin")),
    db: Session = Depends(get_db),
):
    """停用专员（软删，status=disabled）"""
    specialist = db.query(Specialist).filter(Specialist.id == specialist_id).first()
    if not specialist:
        raise HTTPException(status_code=404, detail="专员不存在")
    if specialist.status != "disabled":
        specialist.status = "disabled"
        db.commit()
    await write_audit_log(
        user_id=current_user["id"], action="specialist_disable",
        resource_type="digital_specialist", resource_id=str(specialist_id),
    )
    return success(None, "专员已停用")
```

- [ ] **Step 4: 运行测试**

Run: `cd services/specialist-service && python -m pytest tests/ -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add services/specialist-service/app/api/specialists.py services/specialist-service/tests/test_specialist_crud.py
git commit -m "feat(specialist): admin CRUD for digital specialists (soft disable)"
```

---

## 批次 C：陪访闭环

### Task C1: 拜访后任务创建（tasks 表 + 接口）

**Files:**
- Create: `services/visit-service/app/models/task.py`
- Create: `services/visit-service/app/db/repositories/task_repo.py`
- Create: `services/visit-service/app/api/tasks.py`
- Modify: `services/visit-service/app/core/visit_manager.py`（follow_up 落库）
- Modify: `services/visit-service/app/main.py`（include router）
- Modify: `services/gateway/app/main.py`（ROUTE_MAP 加 /api/v1/tasks）
- Test: `services/visit-service/tests/test_tasks.py`

**Interfaces:**
- Consumes: 表 `tasks`（Task 0）；`VisitManager.follow_up()` 返回 `{"visit_id", "follow_up": {"follow_up_items": [{"action", "due", "channel"}]}}`；`VisitRepo.get(db, visit_id)`
- Produces: `TaskRepo.create(db, visit_id, user_id, item: dict) -> Task`、`TaskRepo.list_by_user(db, user_id, status, page, page_size)`、`TaskRepo.update_status(db, task_id, status)`；接口 `GET /api/v1/tasks`、`PUT /api/v1/tasks/{id}`、`GET /api/v1/visits/{id}/tasks`

- [ ] **Step 1: 写失败测试** `tests/test_tasks.py`（FakeDb 风格，参考 `tests/test_visit_manager.py` 现有模式）：

```python
"""拜访后任务创建与任务接口"""
from datetime import date

from app.db.repositories.task_repo import TaskRepo
from app.core.visit_manager import _parse_follow_up_items


class _FakeTask:
    def __init__(self, **kw):
        for k, v in kw.items():
            setattr(self, k, v)


class _FakeDb:
    def __init__(self):
        self.tasks = []

    def add(self, obj):
        self.tasks.append(obj)

    def commit(self):
        pass

    def refresh(self, obj):
        obj.id = len(self.tasks)


def test_parse_follow_up_items():
    items = [
        {"action": "发送 XX 说明书", "due": "2026-08-10", "channel": "微信"},
        {"action": "预约下次拜访", "due": "", "channel": "下次拜访"},
        "坏格式",
    ]
    parsed = _parse_follow_up_items(items, visit_id=1, user_id=2)
    assert len(parsed) == 2
    assert parsed[0]["title"] == "发送 XX 说明书"
    assert parsed[0]["due_date"] == date(2026, 8, 10)
    assert parsed[0]["task_type"] == "send_material"
    assert parsed[1]["task_type"] == "book_appointment"


def test_repo_create_assigns_fields():
    db = _FakeDb()
    task = TaskRepo.create(db, visit_id=1, user_id=2, item={
        "title": "打电话跟进", "task_type": "call", "due_date": None, "channel": "电话",
    })
    assert task.visit_id == 1 and task.user_id == 2
    assert task.status == "open"
    assert db.tasks[0].title == "打电话跟进"
```

- [ ] **Step 2: 运行确认失败**

Run: `cd services/visit-service && python -m pytest tests/test_tasks.py -v`
Expected: FAIL（task_repo 不存在）

- [ ] **Step 3: 模型** `app/models/task.py`（注意：`visit_manager.py` 头部现有 `from datetime import datetime` 需改为 `from datetime import date, datetime`）：

```python
"""拜访后续任务模型"""
from sqlalchemy import Column, BigInteger, String, Date, Text, ForeignKey
from shared.models.base import Base, TimestampMixin

import shared.models.visit_record  # noqa: F401  注册 visit_records FK 元数据
import shared.models.hcp  # noqa: F401


class Task(Base, TimestampMixin):
    __tablename__ = "tasks"

    visit_id = Column(BigInteger, ForeignKey("visit_records.id"))
    user_id = Column(BigInteger, ForeignKey("users.id"))
    title = Column(String(500), nullable=False)
    description = Column(Text)
    task_type = Column(String(50), default="follow_up")
    due_date = Column(Date)
    channel = Column(String(50))
    status = Column(String(20), default="open")

    def to_dict(self):
        return {
            "id": self.id,
            "visit_id": self.visit_id,
            "user_id": self.user_id,
            "title": self.title,
            "description": self.description,
            "task_type": self.task_type,
            "due_date": self.due_date.isoformat() if self.due_date else None,
            "channel": self.channel,
            "status": self.status,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }
```

- [ ] **Step 4: 仓库** `app/db/repositories/task_repo.py`：

```python
"""任务数据访问层"""
import logging
from datetime import date
from typing import List, Optional, Tuple

from sqlalchemy.orm import Session

from app.models.task import Task

logger = logging.getLogger(__name__)

# channel → task_type 映射（follow_up_items 落库时用）
CHANNEL_TYPE_MAP = {
    "下次拜访": "book_appointment",
    "邮件": "email",
    "电话": "call",
    "微信": "follow_up",
}


class TaskRepo:
    @staticmethod
    def create(db: Session, visit_id: int, user_id: int, item: dict) -> Task:
        task = Task(
            visit_id=visit_id,
            user_id=user_id,
            title=item["title"][:500],
            description=item.get("description"),
            task_type=item.get("task_type", "follow_up"),
            due_date=item.get("due_date"),
            channel=item.get("channel"),
            status="open",
        )
        db.add(task)
        db.commit()
        db.refresh(task)
        return task

    @staticmethod
    def get(db: Session, task_id: int) -> Optional[Task]:
        return db.query(Task).filter(Task.id == task_id).first()

    @staticmethod
    def list_by_user(
        db: Session, user_id: int, status: Optional[str] = None,
        page: int = 1, page_size: int = 20,
    ) -> Tuple[List[Task], int]:
        q = db.query(Task).filter(Task.user_id == user_id)
        if status:
            q = q.filter(Task.status == status)
        total = q.count()
        items = q.order_by(Task.created_at.desc()).offset((page - 1) * page_size).limit(page_size).all()
        return items, total

    @staticmethod
    def list_by_visit(db: Session, visit_id: int) -> List[Task]:
        return db.query(Task).filter(Task.visit_id == visit_id).order_by(Task.created_at).all()

    @staticmethod
    def update_status(db: Session, task: Task, status: str) -> Task:
        task.status = status
        db.commit()
        db.refresh(task)
        return task
```

- [ ] **Step 5: follow_up 落库** `visit_manager.py` 追加（模块级，`_parse_json_content` 之后）：

```python
from app.db.repositories.task_repo import TaskRepo, CHANNEL_TYPE_MAP


def _parse_follow_up_items(items: list, visit_id: int, user_id: int) -> list:
    """把 AI 返回的 follow_up_items 归一化为 tasks 行数据（坏格式跳过）"""
    parsed = []
    for item in items:
        if not isinstance(item, dict):
            continue
        action = (item.get("action") or "").strip()
        if not action:
            continue
        due_raw = (item.get("due") or "").strip()
        try:
            due_date = date.fromisoformat(due_raw) if due_raw else None
        except ValueError:
            due_date = None
        channel = (item.get("channel") or "").strip()
        parsed.append({
            "title": action,
            "description": item.get("description"),
            "task_type": CHANNEL_TYPE_MAP.get(channel, "follow_up"),
            "due_date": due_date,
            "channel": channel or None,
        })
    return parsed
```

`follow_up()` 中 `parsed = _parse_json_content(...)` 之后、`await write_audit_log(...)` 之前插入落库：

```python
        # 自动创建后续任务（必做项）：AI 建议逐条落库，失败不影响主流程
        follow_up_items = (parsed.get("follow_up_items") or []) if isinstance(parsed, dict) else []
        created = []
        for item in _parse_follow_up_items(follow_up_items, visit_id, user_id):
            try:
                task = TaskRepo.create(db, visit_id, user_id, item)
                created.append(task.id)
            except Exception as exc:
                logger.error("任务创建失败: %s", exc)
        if created:
            logger.info("visit %s 自动创建任务 %s 条: %s", visit_id, len(created), created)
```

- [ ] **Step 6: 接口** `app/api/tasks.py`：

```python
"""拜访任务接口"""
import logging
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from shared.common.auth import get_current_user
from shared.common.db_session import get_db
from shared.common.pagination import PaginationParams, paginate
from shared.common.response import ParamError, success

from app.db.repositories.task_repo import TaskRepo

router = APIRouter(prefix="/api/v1", tags=["tasks"])
logger = logging.getLogger(__name__)

TASK_STATUSES = {"open", "done", "cancelled"}


def _get_task_or_404(db: Session, task_id: int):
    task = TaskRepo.get(db, task_id)
    if not task:
        raise HTTPException(status_code=404, detail="任务不存在")
    return task


def _assert_task_owner(task, current_user: dict):
    if task.user_id != current_user["id"] and current_user.get("role") != "admin":
        raise HTTPException(status_code=403, detail="无权操作该任务")


@router.get("/tasks")
async def list_tasks(
    status: Optional[str] = Query(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """我的任务列表"""
    p = PaginationParams(page=page, page_size=page_size)
    items, total = TaskRepo.list_by_user(
        db, current_user["id"], status=status, page=p.page, page_size=p.page_size,
    )
    return success(paginate([t.to_dict() for t in items], total=total, page=p.page, page_size=p.page_size))


@router.put("/tasks/{task_id}")
async def update_task_status(
    task_id: int,
    request: dict,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """完成任务/取消：{"status": "done"|"cancelled"|"open"}"""
    task = _get_task_or_404(db, task_id)
    _assert_task_owner(task, current_user)
    status = (request.get("status") or "").strip().lower()
    if status not in TASK_STATUSES:
        raise ParamError(f"status 必须是 {'/'.join(sorted(TASK_STATUSES))}")
    task = TaskRepo.update_status(db, task, status)
    return success(task.to_dict())


@router.get("/visits/{visit_id}/tasks")
async def list_visit_tasks(
    visit_id: int,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """某次拜访的任务（归属校验：拜访本人或 admin）"""
    from app.api.visits import _assert_visit_owner
    _assert_visit_owner(db, visit_id, current_user)
    tasks = TaskRepo.list_by_visit(db, visit_id)
    return success([t.to_dict() for t in tasks])
```

- [ ] **Step 7: 注册** `app/main.py` include `tasks.router`；网关 `gateway/app/main.py` ROUTE_MAP 加 `"/api/v1/tasks": settings.VISIT_SERVICE_URL,`。
- [ ] **Step 8: 运行测试**

Run: `cd services/visit-service && python -m pytest tests/ -v`
Expected: PASS

- [ ] **Step 9: Commit**

```bash
git add services/visit-service/app/models/task.py services/visit-service/app/db/repositories/task_repo.py services/visit-service/app/api/tasks.py services/visit-service/app/core/visit_manager.py services/visit-service/app/main.py services/gateway/app/main.py services/visit-service/tests/test_tasks.py
git commit -m "feat(visit): auto-create follow-up tasks from AI suggestions + task APIs"
```

### Task C2: 医生画像更新（visit → hcp）

**Files:**
- Modify: `services/hcp-service/app/api/hcps.py`（profile-update 内部端点）
- Modify: `services/hcp-service/app/db/repositories/hcp_repo.py`（merge 方法）
- Modify: `services/gateway/app/core/auth_middleware.py`（INTERNAL_PATHS 加 /api/v1/hcps/profile-update）
- Modify: `services/visit-service/app/core/visit_manager.py`（end_visit 后调用）
- Test: `services/hcp-service/tests/test_profile_update.py`

**Interfaces:**
- Produces: `POST /api/v1/hcps/profile-update`（internal key），body `{hcp_id, academic_background?, prescription_preference?, influence_level?, tags?, source, visit_id?}` → `HcpRepo.merge_profile(db, hcp, updates) -> Hcp`；visit 侧 `_push_profile_update(hcp_id, structured: dict, visit_id: int) -> bool`

- [ ] **Step 1: 写失败测试** `services/hcp-service/tests/test_profile_update.py`：

```python
"""画像更新合并语义（JSONB 按 key 合并，不覆盖已有值）"""
from app.db.repositories.hcp_repo import _merge_profile_fields


def test_merge_fills_empty_keys():
    base = {"academic_background": {"school": "XX医科大学", "degree": "博士"}}
    updates = {"academic_background": {"research_interest": "肺癌免疫治疗"}}
    merged = _merge_profile_fields(base, updates)
    assert merged["academic_background"]["school"] == "XX医科大学"
    assert merged["academic_background"]["research_interest"] == "肺癌免疫治疗"


def test_merge_never_overwrites_existing():
    base = {"academic_background": {"school": "XX医科大学"}}
    updates = {"academic_background": {"school": "被篡改"}}
    merged = _merge_profile_fields(base, updates)
    assert merged["academic_background"]["school"] == "XX医科大学"


def test_tags_dedup_append():
    base = {"tags": ["KOL"]}
    merged = _merge_profile_fields(base, {"tags": ["KOL", "学术型"]})
    assert merged["tags"] == ["KOL", "学术型"]
```

- [ ] **Step 2: 运行确认失败**

Run: `cd services/hcp-service && python -m pytest tests/test_profile_update.py -v`
Expected: FAIL（_merge_profile_fields 不存在）

- [ ] **Step 3: 实现 merge 函数** `hcp_repo.py` 追加：

```python
def _merge_profile_fields(base: dict, updates: dict) -> dict:
    """画像 JSONB 合并：新 key 写入，已有 key 不覆盖（保留人工/历史数据）；tags 去重追加"""
    result = dict(base)
    for key, value in (updates or {}).items():
        if value is None:
            continue
        if key == "tags":
            existing = result.get("tags") or []
            merged_tags = list(existing)
            for tag in value:
                if tag not in merged_tags:
                    merged_tags.append(tag)
            result["tags"] = merged_tags
        elif isinstance(value, dict) and isinstance(result.get(key), dict):
            merged = dict(result[key])
            for k, v in value.items():
                if k not in merged:
                    merged[k] = v
            result[key] = merged
        elif key not in result or result[key] is None:
            result[key] = value
    return result
```

`HcpRepo` 加静态方法：

```python
    @staticmethod
    def merge_profile(db: Session, hcp, updates: dict):
        """按合并语义更新画像字段（academic_background/prescription_preference/influence_level/tags）"""
        profile_keys = ("academic_background", "prescription_preference", "influence_level", "tags")
        current = {k: getattr(hcp, k) for k in profile_keys}
        merged = _merge_profile_fields(current, updates)
        for k in profile_keys:
            setattr(hcp, k, merged.get(k))
        db.commit()
        db.refresh(hcp)
        return hcp
```

- [ ] **Step 4: 内部端点** `hcps.py` 追加：

```python
from shared.common.internal_auth import require_internal_key


@router.post("/profile-update")
async def update_hcp_profile_from_visit(
    request: dict,
    db: Session = Depends(get_db),
    _internal: bool = Depends(require_internal_key),
):
    """拜访后画像更新（内部接口，visit-service 调用）：
    {hcp_id, academic_background?, prescription_preference?, influence_level?, tags?, source, visit_id?}
    """
    hcp_id = request.get("hcp_id")
    if not hcp_id:
        raise ParamError("hcp_id 不能为空")
    hcp = HcpRepo.get(db, hcp_id)
    if not hcp:
        raise HTTPException(status_code=404, detail="医生档案不存在")
    updates = {
        "academic_background": request.get("academic_background"),
        "prescription_preference": request.get("prescription_preference"),
        "influence_level": request.get("influence_level"),
        "tags": request.get("tags"),
    }
    hcp = HcpRepo.merge_profile(db, hcp, updates)
    await write_audit_log(
        user_id=None, action="hcp_profile_update_from_visit",
        resource_type="hcp", resource_id=str(hcp_id),
        after_value={"source": request.get("source"), "visit_id": request.get("visit_id"),
                     "updated": [k for k, v in updates.items() if v]},
    )
    return success(hcp.to_dict())
```

- [ ] **Step 5: 网关内部路径** `auth_middleware.py` INTERNAL_PATHS 加 `"/api/v1/hcps/profile-update",`（精确匹配，不影响 /api/v1/hcps 其他路径）。
- [ ] **Step 6: visit 侧调用** `visit_manager.py` 追加模块级函数：

```python
async def _push_profile_update(hcp_id: int, structured: dict, visit_id: int) -> bool:
    """拜访后画像更新：调 hcp-service 内部接口，失败不阻塞主流程"""
    import httpx
    from shared.common.internal_auth import internal_headers
    gateway_url = os.getenv("GATEWAY_URL", "http://localhost:8000")
    updates = {}
    interests = structured.get("hcp_interests") or []
    if interests:
        updates["academic_background"] = {"research_interest": interests[0][:200]}
        updates["tags"] = [f"兴趣:{i[:30]}" for i in interests[:3]]
    objections = structured.get("hcp_objections") or []
    if objections:
        updates["prescription_preference"] = {"noted_objections": [str(o)[:200] for o in objections[:5]]}
    sentiment = structured.get("sentiment")
    if sentiment:
        updates["influence_level"] = sentiment
    if not updates:
        return True
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            resp = await client.post(
                f"{gateway_url}/api/v1/hcps/profile-update",
                headers=internal_headers(),
                json={"hcp_id": hcp_id, **updates, "source": "ai_visit", "visit_id": visit_id},
            )
            resp.raise_for_status()
            return True
    except Exception as exc:
        logger.warning("医生画像更新失败（不影响拜访记录）: hcp_id=%s err=%s", hcp_id, exc)
        return False
```

`end_visit()` 中 `await write_audit_log(...)` 之后、`return record.to_dict()` 之前加：

```python
        # 医生画像更新（必做项）：基于本次拜访的 AI 结构化结果
        if structured:
            await _push_profile_update(record.hcp_id, structured, visit_id)
```

（文件头部已有 `import os`？没有——`visit_manager.py` 头部有 `import json/asyncio/logging/datetime/typing`，需补 `import os`。）

- [ ] **Step 7: 运行测试**

Run: `cd services/hcp-service && python -m pytest tests/ -v`
Expected: PASS

- [ ] **Step 8: Commit**

```bash
git add services/hcp-service/app/api/hcps.py services/hcp-service/app/db/repositories/hcp_repo.py services/gateway/app/core/auth_middleware.py services/visit-service/app/core/visit_manager.py services/hcp-service/tests/test_profile_update.py
git commit -m "feat(hcp,visit): post-visit profile update via internal endpoint (merge semantics)"
```

### Task C3: 实时转写 fail-closed + 非阻塞合规 + flags 累积

**Files:**
- Modify: `services/visit-service/app/api/asr_ws.py`
- Modify: `services/visit-service/app/core/visit_manager.py`（compliance_flags append）
- Test: `services/visit-service/tests/test_asr_fail_closed.py`

**Interfaces:**
- Consumes: `RealtimeAsrClient`/`MockRealtimeAsrClient`（现有）
- Produces: `_get_asr_client() -> (client, is_mock)`（无 NLS_APPKEY 且无 NLS_MOCK → 抛 RuntimeError）；WS 事件 `{"type":"error","message":...}`；Mock 文本不落库

- [ ] **Step 1: 写失败测试** `tests/test_asr_fail_closed.py`：

```python
"""实时转写 fail-closed：未配置 NLS_APPKEY 时拒绝降级 Mock，不落库假文本"""
import os
import pytest

from app.api.asr_ws import _get_asr_client


def test_no_appkey_raises(monkeypatch):
    monkeypatch.delenv("NLS_APPKEY", raising=False)
    monkeypatch.delenv("NLS_MOCK", raising=False)
    with pytest.raises(RuntimeError):
        _get_asr_client()


def test_explicit_mock_allowed(monkeypatch):
    monkeypatch.delenv("NLS_APPKEY", raising=False)
    monkeypatch.setenv("NLS_MOCK", "1")
    client, is_mock = _get_asr_client()
    assert is_mock is True
    assert client.__class__.__name__ == "MockRealtimeAsrClient"


def test_real_appkey_returns_real_client(monkeypatch):
    monkeypatch.setenv("NLS_APPKEY", "test-appkey")
    monkeypatch.delenv("NLS_MOCK", raising=False)
    client, is_mock = _get_asr_client()
    assert is_mock is False
    assert client.__class__.__name__ == "RealtimeAsrClient"
```

- [ ] **Step 2: 运行确认失败**

Run: `cd services/visit-service && python -m pytest tests/test_asr_fail_closed.py -v`
Expected: FAIL（_get_asr_client 签名/行为不符）

- [ ] **Step 3: 改造 `_get_asr_client`** `asr_ws.py`：

```python
def _get_asr_client():
    """NLS_APPKEY 已配置 → 真实客户端；否则抛错（fail-closed，不降级 Mock 污染证据库）。

    显式开发模式：NLS_MOCK=1 时允许 Mock（文本不落库，见 ws 处理器）。
    """
    import os
    app_key = os.getenv("NLS_APPKEY", "")
    if app_key:
        return RealtimeAsrClient(app_key=app_key), False
    if os.getenv("NLS_MOCK") == "1":
        logger.error("NLS_MOCK=1 显式启用 Mock 实时转写（仅开发联调，文本不落库）")
        return MockRealtimeAsrClient(), True
    raise RuntimeError("实时转写未配置：缺少 NLS_APPKEY（NLS 管控台项目 Appkey）。拒绝降级 Mock，防止假转写污染拜访证据。")
```

- [ ] **Step 4: 改 WS 处理器** `asr_ws.py`：

- `asr, is_mock = _get_asr_client()`（原 `asr = _get_asr_client()`）——包在 try/except 里：

```python
        try:
            asr, is_mock = _get_asr_client()
        except RuntimeError as exc:
            await websocket.send_json({"type": "error", "message": str(exc)})
            await websocket.close(code=4500)  # 服务端未配置
            return
```

- `on_sentence` 内落库处（:78-82）加 mock 保护：

```python
            if is_final:
                # fail-closed：Mock 会话的文本绝不落库（防止假转写污染证据库）
                if is_mock:
                    logger.warning("Mock 转写文本不落库: %s", text[:50])
                else:
                    rec = VisitRepo.get(db, visit_id)
                    if rec:
                        rec.conversation_transcript = (rec.conversation_transcript or "") + text + "\n"
                        db.commit()
```

- 合规检查改非阻塞（把 :83-95 的 `try/except` 同步等待改为后台任务）：

```python
            if is_final:
                async def _check_later():
                    try:
                        compliance = await check_compliance(
                            text,
                            {"user_id": user_id, "type": "live_conversation", "visit_id": visit_id},
                        )
                        if compliance.get("blocked"):
                            await websocket.send_json({
                                "type": "compliance",
                                "blocked": True,
                                "violations": compliance.get("violations", []),
                            })
                    except Exception as exc:
                        logger.error("实时合规检查失败: %s", exc)
                asyncio.create_task(_check_later())  # 不阻塞转写流（<2s 承诺）
```

- `finally` 块 `await websocket.send_json({"type": "completed"})` 包 try/except 吞掉断连异常：

```python
        finally:
            await asr.close()
            try:
                await websocket.send_json({"type": "completed"})
            except Exception:
                pass  # 客户端已断开
```

（文件头部补 `import asyncio`。）

- [ ] **Step 5: compliance_flags 累积** `visit_manager.py:244-247` 改为：

```python
        # 追加转写 + 累积合规标记（不整句覆盖，保留全部违规证据）
        record.conversation_transcript = (record.conversation_transcript or "") + text_content + "\n"
        existing_flags = record.compliance_flags or {"violations": []}
        existing_violations = existing_flags.get("violations") or []
        existing_violations.extend(compliance.get("violations", []))
        record.compliance_flags = {
            "violations": existing_violations,
            "blocked": existing_flags.get("blocked", False) or compliance.get("blocked", False),
        }
        db.commit()
```

- [ ] **Step 6: 运行测试**

Run: `cd services/visit-service && python -m pytest tests/ -v`
Expected: PASS

- [ ] **Step 7: Commit**

```bash
git add services/visit-service/app/api/asr_ws.py services/visit-service/app/core/visit_manager.py services/visit-service/tests/test_asr_fail_closed.py
git commit -m "fix(visit): ASR fail-closed (no mock persistence), non-blocking compliance, accumulate flags"
```

---

## 批次 D：知识库

### Task D1: DashVector 客户端 + 文档内容入库 + 检索集成

**Files:**
- Create: `services/knowledge-service/app/services/dashvector_client.py`
- Create: `services/knowledge-service/app/services/document_processor.py`
- Modify: `services/knowledge-service/app/core/document_manager.py`
- Modify: `services/knowledge-service/requirements.txt`（加 dashscope）
- Test: `services/knowledge-service/tests/test_dashvector_client.py`

**Interfaces:**
- Consumes: `KnowledgeRepository`（现有）、`OSSClient`（现有）、表 `knowledge_documents`（现有 + Task 0 的 revision/parent）
- Produces: `DashVectorClient.is_configured() -> bool`、`upsert_chunk(doc_id, chunk, fields)`、`query(vector, filter_expr, top_k) -> list`；`DocumentProcessor.extract_text(local_path) -> str`、`chunk_text(text, size=512) -> list[str]`；`DocumentManager.search()` 后端顺序 dashvector → bailian → local

- [ ] **Step 1: 加依赖** `requirements.txt` 加 `dashscope>=1.20.0`。
- [ ] **Step 2: 写失败测试** `tests/test_dashvector_client.py`（monkeypatch SDK，不连真服务）：

```python
"""DashVector 客户端（monkeypatch dashvector SDK）"""
import pytest

from app.services.dashvector_client import DashVectorClient, _embed
from app.services.document_processor import chunk_text


def test_is_configured(monkeypatch):
    monkeypatch.setenv("DASHVECTOR_API_KEY", "")
    monkeypatch.setenv("DASHVECTOR_ENDPOINT", "")
    assert DashVectorClient().is_configured() is False
    monkeypatch.setenv("DASHVECTOR_API_KEY", "k")
    monkeypatch.setenv("DASHVECTOR_ENDPOINT", "e")
    assert DashVectorClient().is_configured() is True


def test_chunk_text_sizes():
    text = "段落一。" * 300  # 900 字
    chunks = chunk_text(text, size=512)
    assert len(chunks) >= 2
    assert all(0 < len(c) <= 520 for c in chunks)


def test_embed(monkeypatch):
    class _FakeResp:
        status_code = 200
        output = {"embeddings": [{"embedding": [0.1] * 1536}]}

    monkeypatch.setattr("app.services.dashvector_client.dashscope.TextEmbedding.call", lambda **kw: _FakeResp())
    vec = _embed("测试文本")
    assert len(vec) == 1536


def test_upsert_and_query(monkeypatch):
    class _FakeCollection:
        def __init__(self):
            self.data = {}

        def upsert(self, docs):
            for d in docs:
                self.data[d.id] = d

        def query(self, vector, topk, filter=None, output_fields=None):  # noqa: A002
            return type("R", (), {"output": [
                type("D", (), {"id": "doc_1_chunk_0", "score": 0.9,
                                "fields": {"content": "文本", "doc_id": "1", "title": "t"}})
            ]})()

    class _FakeClient:
        def __init__(self, **kw):
            self.coll = _FakeCollection()

        def get(self, name):
            return self.coll

        def create(self, name, dimension, metric):
            raise Exception("already exists")  # 已存在则调用方兜底 get

    monkeypatch.setenv("DASHVECTOR_API_KEY", "k")
    monkeypatch.setenv("DASHVECTOR_ENDPOINT", "e")
    monkeypatch.setattr("dashvector.Client", _FakeClient)  # 实现用 dv.Client 运行期查找
    c = DashVectorClient()
    col = c._get_collection()
    from dashvector import Doc
    col.upsert([Doc(id="doc_1_chunk_0", vector=[0.1] * 1536, fields={"content": "文本", "doc_id": "1", "title": "t"})])
    out = c.query([0.1] * 1536, "doc_id = 1", top_k=1)
    assert out[0]["id"] == "doc_1_chunk_0"
```

- [ ] **Step 3: 运行确认失败**

Run: `cd services/knowledge-service && python -m pytest tests/test_dashvector_client.py -v`
Expected: FAIL（模块不存在）

- [ ] **Step 4: 实现 DashVector 客户端** `app/services/dashvector_client.py`：

```python
"""DashVector 向量检索客户端（方案 9.1/9.2：向量化 + 向量检索）

未配置 DASHVECTOR_API_KEY/ENDPOINT 时 is_configured()=False，调用方降级到百炼/本地。
"""
import os
import logging
from typing import Dict, List, Optional

import dashscope
from http import HTTPStatus

logger = logging.getLogger(__name__)

EMBEDDING_DIM = 1536  # text-embedding-v3


def _embed(text: str) -> List[float]:
    """向量化（text-embedding-v3，1536 维）"""
    dashscope.api_key = os.getenv("DASHSCOPE_API_KEY", "")
    resp = dashscope.TextEmbedding.call(
        model=os.getenv("DASHSCOPE_EMBEDDING_MODEL", "text-embedding-v3"),
        input=text[:2048],
    )
    if resp.status_code == HTTPStatus.OK:
        return resp.output["embeddings"][0]["embedding"]
    raise RuntimeError(f"向量化失败: {resp}")


class DashVectorClient:
    def __init__(self):
        self.api_key = os.getenv("DASHVECTOR_API_KEY", "")
        self.endpoint = os.getenv("DASHVECTOR_ENDPOINT", "")
        self.collection_name = os.getenv("DASHVECTOR_COLLECTION", "knowledge_base")
        self._collection = None

    def is_configured(self) -> bool:
        return bool(self.api_key and self.endpoint)

    def _get_collection(self):
        """获取（不存在则创建）collection —— 懒加载 + 缓存"""
        if self._collection is not None:
            return self._collection
        import dashvector as dv  # 运行期导入 + 属性查找，便于测试 monkeypatch dashvector.Client
        client = dv.Client(api_key=self.api_key, endpoint=self.endpoint)
        try:
            client.create(self.collection_name, dimension=EMBEDDING_DIM)
            logger.info("DashVector collection 已创建: %s", self.collection_name)
        except Exception as exc:
            logger.debug("collection 已存在或创建失败（走 get）: %s", exc)
        self._collection = client.get(self.collection_name)
        if self._collection is None:
            raise RuntimeError(f"DashVector collection 不可用: {self.collection_name}")
        return self._collection

    def upsert_chunks(self, doc_id: int, title: str, chunks: List[str], fields: Optional[Dict] = None) -> int:
        """按 chunk 写入向量 + 元数据字段"""
        from dashvector import Doc
        col = self._get_collection()
        docs = []
        for i, chunk in enumerate(chunks):
            docs.append(Doc(
                id=f"doc_{doc_id}_chunk_{i}",
                vector=_embed(chunk),
                fields={
                    "doc_id": str(doc_id),
                    "title": title,
                    "chunk_index": i,
                    "content": chunk,
                    **(fields or {}),
                },
            ))
        col.upsert(docs)
        return len(docs)

    def query(self, vector: List[float], filter_expr: Optional[str] = None, top_k: int = 10) -> List[Dict]:
        """向量检索（含过滤）"""
        col = self._get_collection()
        resp = col.query(
            vector=vector,
            topk=top_k,
            filter=filter_expr,
            output_fields=["doc_id", "title", "content", "chunk_index", "product_id", "doc_type"],
        )
        out = []
        for item in resp.output or []:
            fields = item.fields or {}
            out.append({
                "id": item.id,
                "score": getattr(item, "score", 0),
                "doc_id": fields.get("doc_id"),
                "title": fields.get("title"),
                "content": fields.get("content", "")[:500],
                "chunk_index": fields.get("chunk_index"),
                "product_id": fields.get("product_id"),
                "doc_type": fields.get("doc_type"),
            })
        return out
```

- [ ] **Step 5: 文档解析器** `app/services/document_processor.py`：

```python
"""文档正文解析与切分（方案 9.1 的简化落地：表格/OCR 由百炼托管处理，本地只做正文抽取）"""
import logging
from typing import List

logger = logging.getLogger(__name__)


def extract_text(local_path: str) -> str:
    """按扩展名抽取正文（pdf/docx/pptx/txt），失败返回空串"""
    suffix = local_path.rsplit(".", 1)[-1].lower() if "." in local_path else ""
    try:
        if suffix == "pdf":
            from pypdf import PdfReader
            reader = PdfReader(local_path)
            return "\n".join(page.extract_text() or "" for page in reader.pages)
        if suffix in ("docx", "doc"):
            from docx import Document
            doc = Document(local_path)
            return "\n".join(p.text for p in doc.paragraphs)
        if suffix in ("pptx", "ppt"):
            from pptx import Presentation
            prs = Presentation(local_path)
            texts = []
            for slide in prs.slides:
                for shape in slide.shapes:
                    if shape.has_text_frame:
                        texts.append(shape.text_frame.text)
            return "\n".join(texts)
        with open(local_path, "r", encoding="utf-8", errors="ignore") as f:
            return f.read()
    except Exception as exc:
        logger.warning("文档解析失败（%s），返回空正文: %s", suffix, exc)
        return ""


def chunk_text(text: str, size: int = 512) -> List[str]:
    """按段落切分，合并至 size 字符（保守：汉字按 1 字符计）"""
    paragraphs = [p.strip() for p in text.split("\n") if p.strip()]
    chunks: List[str] = []
    current = ""
    for para in paragraphs:
        if len(current) + len(para) + 1 > size:
            if current:
                chunks.append(current)
            current = para
        else:
            current = f"{current}\n{para}" if current else para
    if current:
        chunks.append(current)
    return chunks
```

- [ ] **Step 6: 集成到 DocumentManager** `document_manager.py`：

- `__init__` 加 `from app.services.dashvector_client import DashVectorClient`；`self.dashvector = DashVectorClient()`。
- `approve_document` 中 `self.bailian.import_document(...)` 之后加内容入库 + 向量化：

```python
            # 正文入库 + DashVector 向量化（可选后端：未配置自动跳过）
            from app.services.document_processor import extract_text, chunk_text
            text = extract_text(local_path)
            if text:
                doc.content = text[:100000]  # 截断防超长
                chunks = chunk_text(text)
                if self.dashvector.is_configured():
                    try:
                        self.dashvector.upsert_chunks(
                            doc_id, doc.title or "", chunks,
                            fields={"product_id": str(doc.product_id or ""),
                                    "doc_type": doc.doc_type or ""},
                        )
                        logger.info("document %s 向量化 %d chunks → DashVector", doc_id, len(chunks))
                    except Exception as exc:
                        logger.error("DashVector 写入失败（不影响上架，检索将降级）: %s", exc)
```

- `search()` 替换为三后端顺序：

```python
    def search(self, query, product_id=None, doc_type=None, top_k=10):
        # 1. DashVector（向量 + 关键词混合，可选后端）
        if self.dashvector.is_configured():
            try:
                results = self._hybrid_search(query, product_id, doc_type, top_k)
                return results, "dashvector"
            except Exception as exc:
                logger.warning("DashVector 检索失败，降级百炼: %s", exc)
        # 2. 百炼（dense + rerank）
        try:
            results = self.bailian.search(query=query, top_k=top_k, product_id=product_id, doc_type=doc_type)
            return results, "bailian"
        except Exception as exc:
            logger.warning("Bailian search failed, use local fallback: %s", exc)
        # 3. 本地 SQL（关键词）
        results = self.repo.local_search(query=query, product_id=product_id, doc_type=doc_type, top_k=top_k)
        return results, "local_fallback"

    def _hybrid_search(self, query, product_id, doc_type, top_k):
        """DashVector 向量 + 本地关键词 加权融合（0.7 向量 / 0.3 关键词）"""
        from app.services.dashvector_client import _embed
        vector_results = self.dashvector.query(_embed(query), self._filter_expr(product_id, doc_type), top_k=top_k * 2)
        keyword_results = self.repo.local_search(query=query, product_id=product_id, doc_type=doc_type, top_k=top_k * 2)

        # 向量分归一化到 [0,1]（DashVector score 通常 <1）
        vec_max = max((r["score"] for r in vector_results), default=0.0) or 1.0
        kw_max = max((r["score"] for r in keyword_results), default=0.0) or 1.0

        merged = {}
        for r in vector_results:
            key = r["doc_id"]
            merged[key] = {"title": r["title"], "content": r["content"],
                           "doc_id": key, "score": 0.7 * r["score"] / vec_max,
                           "backend": "dashvector"}
        for r in keyword_results:
            key = r["doc_id"]
            if key in merged:
                merged[key]["score"] += 0.3 * r["score"] / kw_max
            else:
                merged[key] = {"title": r["title"], "content": r["content"],
                               "doc_id": key, "score": 0.3 * r["score"] / kw_max,
                               "backend": "local"}
        ranked = sorted(merged.values(), key=lambda x: x["score"], reverse=True)
        return ranked[:top_k]

    @staticmethod
    def _filter_expr(product_id, doc_type) -> Optional[str]:
        parts = []
        if product_id:
            parts.append(f"product_id = {int(product_id)}")
        if doc_type:
            parts.append(f"doc_type = '{doc_type}'")
        return " AND ".join(parts) if parts else None
```

- [ ] **Step 7: 运行测试**

Run: `cd services/knowledge-service && python -m pytest tests/ -v`
Expected: PASS（monkeypatch 测试不触网；原 knowledge-service 无测试，本任务建立首个测试文件）

- [ ] **Step 8: Commit**

```bash
git add services/knowledge-service/app/services/dashvector_client.py services/knowledge-service/app/services/document_processor.py services/knowledge-service/app/core/document_manager.py services/knowledge-service/requirements.txt services/knowledge-service/tests/test_dashvector_client.py
git commit -m "feat(knowledge): DashVector client + doc content extraction + hybrid search backend chain"
```

### Task D2: 本地检索升级 PG 全文检索 + 检索测试端点

**Files:**
- Modify: `services/knowledge-service/app/db/repositories/knowledge_repo.py`（local_search → PG FTS）
- Modify: `services/knowledge-service/app/api/knowledge.py`（search-test 端点 + top_k 校验 + search 空库提示）
- Create: `services/knowledge-service/app/services/es_client.py`（可选 ES 客户端，默认降级）
- Test: `services/knowledge-service/tests/test_search_backends.py`

**Interfaces:**
- Produces: `local_search()` 用 `to_tsvector/plainto_tsquery/ts_rank` 排序；`POST /api/v1/knowledge/search-test {query, top_k?, backends?}` → `[{backend, results, error?, elapsed_ms}]`；`EsClient.is_configured()`（ES_URL 未配置 → False）

- [ ] **Step 1: 写失败测试** `tests/test_search_backends.py`：

```python
"""检索后端链与空库处理"""
from app.api.knowledge import validate_search_request
from shared.common.response import ParamError
import pytest


def test_validate_search_request():
    with pytest.raises(ParamError):
        validate_search_request({"query": ""})
    r = validate_search_request({"query": "剂量", "top_k": 5})
    assert r == {"query": "剂量", "top_k": 5}
    with pytest.raises(ParamError):
        validate_search_request({"query": "剂量", "top_k": "abc"})
```

- [ ] **Step 2: 运行确认失败**

Run: `cd services/knowledge-service && python -m pytest tests/test_search_backends.py -v`
Expected: FAIL（validate_search_request 不存在）

- [ ] **Step 3: local_search 升级 PG FTS** `knowledge_repo.py`：`local_search` 替换为：

```python
    def local_search(self, query, product_id=None, doc_type=None, top_k=10):
        """本地关键词检索（PostgreSQL 全文检索：标题+正文 tsvector，ts_rank 排序）"""
        from sqlalchemy import func
        q = self.db.query(KnowledgeDocument).filter(KnowledgeDocument.status == "ready")
        if product_id:
            q = q.filter(KnowledgeDocument.product_id == product_id)
        if doc_type:
            q = q.filter(KnowledgeDocument.doc_type == doc_type)

        ts_expr = func.to_tsvector(
            "simple",
            func.coalesce(KnowledgeDocument.title, "") + " " + func.coalesce(KnowledgeDocument.content, ""),
        )
        ts_query = func.plainto_tsquery("simple", query)
        keyword = f"%{query}%"
        q = q.filter(
            or_(
                KnowledgeDocument.title.ilike(keyword),
                KnowledgeDocument.content.ilike(keyword),
                ts_expr.op("@@")(ts_query),
            )
        )
        docs = q.order_by(func.ts_rank(ts_expr, ts_query).desc()).limit(top_k).all()
        results = []
        for doc in docs:
            content = doc.content or ""
            title = doc.title or ""
            score = 1.0 if (query.lower() in title.lower() or (doc.content and query in doc.content)) else 0.7
            results.append({
                "title": title,
                "content": content[:500],
                "evidence_level": doc.evidence_level,
                "score": score,
                "doc_id": doc.id,
            })
        return results
```

- [ ] **Step 4: ES 可选客户端** `app/services/es_client.py`：

```python
"""Elasticsearch 可选客户端 —— ES_URL 配置时启用，未配置自动降级（PG FTS 承担关键词索引）"""
import os
import logging
from typing import Dict, List, Optional

logger = logging.getLogger(__name__)


class EsClient:
    def __init__(self):
        self.url = os.getenv("ES_URL", "")
        self.index = os.getenv("ES_INDEX", "knowledge_documents")

    def is_configured(self) -> bool:
        return bool(self.url)

    def client(self):
        from elasticsearch import Elasticsearch
        return Elasticsearch(self.url)

    def index_doc(self, doc_id: int, title: str, content: str, fields: Optional[Dict] = None):
        if not self.is_configured():
            return False
        try:
            es = self.client()
            es.index(index=self.index, id=f"doc_{doc_id}", document={
                "title": title, "content": content, **(fields or {}),
            })
            return True
        except Exception as exc:
            logger.warning("ES 写入失败（降级）: %s", exc)
            return False

    def search(self, query: str, top_k: int = 10) -> List[Dict]:
        if not self.is_configured():
            return []
        es = self.client()
        resp = es.search(index=self.index, size=top_k, query={
            "multi_match": {"query": query, "fields": ["title^3", "content"]},
        })
        return [
            {"title": h["_source"].get("title", ""), "content": (h["_source"].get("content") or "")[:500],
             "score": h.get("_score", 0), "doc_id": h["_source"].get("doc_id")}
            for h in resp["hits"]["hits"]
        ]
```

（`requirements.txt` 加 `elasticsearch>=8.0.0`。注意：ES 不是默认启用，装上依赖不影响运行。）

- [ ] **Step 5: search-test 端点 + 校验** `knowledge.py`：

模块级加：

```python
def validate_search_request(request: dict) -> dict:
    query = (request.get("query") or "").strip()
    if not query:
        raise ParamError("query 不能为空")
    try:
        top_k = int(request.get("top_k", 10))
    except (TypeError, ValueError):
        raise ParamError("top_k 必须是整数")
    if top_k < 1 or top_k > 50:
        raise ParamError("top_k 必须在 1-50 之间")
    return {"query": query, "top_k": top_k}
```

`search_knowledge` 改为调用 `validate_search_request(request)`，且结果带 empty 提示：

```python
    data = validate_search_request(request)
    results, source = _manager(db).search(
        query=data["query"],
        product_id=request.get("product_id"),
        doc_type=request.get("doc_type"),
        top_k=data["top_k"],
    )
    return success({"results": results, "source": source,
                    "empty": not results and source != "bailian",
                    "message": "知识库暂无已上架文档，请先上传并审核文档" if not results and source != "bailian" else None})
```

新增端点：

```python
@router.post("/search-test")
async def search_test(
    request: dict,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """检索测试：同一 query 并行调多个后端对比（各自独立容错）"""
    import time
    data = validate_search_request(request)
    backends = request.get("backends") or ["dashvector", "bailian", "local"]
    manager = _manager(db)
    from app.services.dashvector_client import DashVectorClient
    from app.services.es_client import EsClient

    def _run(backend: str) -> dict:
        start = time.time()
        try:
            if backend == "dashvector":
                if not manager.dashvector.is_configured():
                    return {"backend": "dashvector", "error": "DashVector 未配置", "results": []}
                results = manager._hybrid_search(data["query"], request.get("product_id"), request.get("doc_type"), data["top_k"])
                return {"backend": "dashvector", "results": results, "elapsed_ms": int((time.time() - start) * 1000)}
            if backend == "bailian":
                results = manager.bailian.search(query=data["query"], top_k=data["top_k"])
                return {"backend": "bailian", "results": results, "elapsed_ms": int((time.time() - start) * 1000)}
            if backend == "local":
                results = manager.repo.local_search(query=data["query"], top_k=data["top_k"])
                return {"backend": "local", "results": results, "elapsed_ms": int((time.time() - start) * 1000)}
            if backend == "es":
                es = EsClient()
                if not es.is_configured():
                    return {"backend": "es", "error": "ES 未配置（ES_URL）", "results": []}
                return {"backend": "es", "results": es.search(data["query"], data["top_k"]), "elapsed_ms": int((time.time() - start) * 1000)}
            return {"backend": backend, "error": f"未知后端 {backend}", "results": []}
        except Exception as exc:
            logger.error("search-test 后端 %s 失败: %s", backend, exc)
            return {"backend": backend, "error": str(exc), "results": []}

    outputs = [_run(b) for b in backends]
    return success({"query": data["query"], "backends": outputs})
```

- [ ] **Step 6: 运行测试**

Run: `cd services/knowledge-service && python -m pytest tests/ -v`
Expected: PASS

- [ ] **Step 7: Commit**

```bash
git add services/knowledge-service/app/db/repositories/knowledge_repo.py services/knowledge-service/app/api/knowledge.py services/knowledge-service/app/services/es_client.py services/knowledge-service/requirements.txt services/knowledge-service/tests/test_search_backends.py
git commit -m "feat(knowledge): PG FTS local search + optional ES client + search-test endpoint"
```

### Task D3: 文档版本管理（revision 链）

**Files:**
- Modify: `services/knowledge-service/app/models/knowledge_document.py`（revision/parent_doc_id）
- Modify: `services/knowledge-service/app/db/repositories/knowledge_repo.py`（create_document 传 revision/parent）
- Modify: `services/knowledge-service/app/core/document_manager.py`（create_from_upload 版本链）
- Test: `services/knowledge-service/tests/test_versioning.py`

**Interfaces:**
- Produces: `KnowledgeRepository.find_latest_by_title(db, title, product_id) -> Optional[KnowledgeDocument]`；新行 `revision = prev.revision + 1`、`parent_doc_id = prev.id`；旧行 `status='archived'`

- [ ] **Step 1: 写失败测试** `tests/test_versioning.py`：

```python
"""文档版本链：同 title+product 重复上传生成新版本"""
from app.core.document_manager import _next_revision
import pytest


def test_next_revision_from_previous():
    class _Prev:
        revision = 3
    assert _next_revision(_Prev()) == 4


def test_next_revision_none():
    assert _next_revision(None) == 1
```

- [ ] **Step 2: 运行确认失败**

Run: `cd services/knowledge-service && python -m pytest tests/test_versioning.py -v`
Expected: FAIL

- [ ] **Step 3: 模型加列** `knowledge_document.py`：

```python
    revision = Column(Integer, default=1)              # 版本链计数（version 是用户可见文档版本字符串）
    parent_doc_id = Column(BigInteger, ForeignKey("knowledge_documents.id"))
```

（头部 import 补 `Integer`。）`to_dict()` 加 `"revision": self.revision, "parent_doc_id": self.parent_doc_id,`。

- [ ] **Step 4: 仓库** `knowledge_repo.py`：

- `create_document` 加参数 `revision: int = 1, parent_doc_id: Optional[int] = None`，构造时传入。
- 加静态方法：

```python
    @staticmethod
    def find_latest_by_title(db: Session, title: str, product_id: Optional[int]) -> Optional[KnowledgeDocument]:
        q = db.query(KnowledgeDocument).filter(KnowledgeDocument.title == title)
        if product_id:
            q = q.filter(KnowledgeDocument.product_id == product_id)
        return q.order_by(KnowledgeDocument.revision.desc()).first()

    @staticmethod
    def archive(db: Session, doc: KnowledgeDocument) -> KnowledgeDocument:
        doc.status = "archived"
        db.commit()
        db.refresh(doc)
        return doc
```

- [ ] **Step 5: 版本链逻辑** `document_manager.py`：

```python
def _next_revision(prev) -> int:
    return (prev.revision if prev else 0) + 1
```

`create_from_upload` 开头（`file_url = ...` 之前）加：

```python
        # 版本管理：同 title+product 已有文档 → 旧版归档，新行 revision+1 挂 parent 链
        prev = self.repo.find_latest_by_title(self.db, title, product_id)
        parent_doc_id = None
        revision = 1
        if prev:
            revision = _next_revision(prev)
            parent_doc_id = prev.id
            try:
                self.repo.archive(self.db, prev)
            except Exception as exc:
                logger.warning("归档旧版文档失败（不影响新文档）: %s", exc)
```

`create_document(...)` 调用加 `revision=revision, parent_doc_id=parent_doc_id`。

- [ ] **Step 6: 运行测试**

Run: `cd services/knowledge-service && python -m pytest tests/ -v`
Expected: PASS

- [ ] **Step 7: Commit**

```bash
git add services/knowledge-service/app/models/knowledge_document.py services/knowledge-service/app/db/repositories/knowledge_repo.py services/knowledge-service/app/core/document_manager.py services/knowledge-service/tests/test_versioning.py
git commit -m "feat(knowledge): document revision chain (archive old, revision+1)"
```

### Task D4: 知识检索反馈落库

**Files:**
- Modify: `services/knowledge-service/app/models/knowledge_document.py`（或新建 model 文件 `app/models/knowledge_feedback.py`）
- Modify: `services/knowledge-service/app/api/knowledge.py`（/feedback 落库）
- Test: `services/knowledge-service/tests/test_feedback_persist.py`

**Interfaces:**
- Produces: 模型 `KnowledgeFeedback`（表 knowledge_feedback，Task 0）；`/feedback` 校验 query/rating 必填，落库 + 审计

- [ ] **Step 1: 写失败测试** `tests/test_feedback_persist.py`：

```python
"""检索反馈落库（参数校验纯函数）"""
import pytest

from app.api.knowledge import validate_feedback_request
from shared.common.response import ParamError


def test_feedback_requires_query_and_rating():
    with pytest.raises(ParamError):
        validate_feedback_request({"rating": 1})
    with pytest.raises(ParamError):
        validate_feedback_request({"query": "q"})
    with pytest.raises(ParamError):
        validate_feedback_request({"query": "q", "rating": 0})
    r = validate_feedback_request({"query": "剂量", "rating": -1, "doc_id": "3", "comment": "不准"})
    assert r["rating"] == -1
```

- [ ] **Step 2: 运行确认失败**

Run: `cd services/knowledge-service && python -m pytest tests/test_feedback_persist.py -v`
Expected: FAIL

- [ ] **Step 3: 模型** `app/models/knowledge_feedback.py`：

```python
"""知识检索反馈模型"""
from sqlalchemy import Column, BigInteger, SmallInteger, String, Text, ForeignKey
from shared.models.base import Base, TimestampMixin


class KnowledgeFeedback(Base, TimestampMixin):
    __tablename__ = "knowledge_feedback"

    user_id = Column(BigInteger, ForeignKey("users.id"))
    query = Column(Text, nullable=False)
    doc_id = Column(String(100))
    rating = Column(SmallInteger, nullable=False)  # 1 有用 / -1 无用
    comment = Column(Text)
```

- [ ] **Step 4: /feedback 落库** `knowledge.py`：

```python
from app.models.knowledge_feedback import KnowledgeFeedback


def validate_feedback_request(request: dict) -> dict:
    query = (request.get("query") or "").strip()
    if not query:
        raise ParamError("query 不能为空")
    rating = request.get("rating")
    if rating not in (1, -1):
        raise ParamError("rating 必须是 1（有用）或 -1（无用）")
    return {"query": query, "rating": rating,
            "doc_id": (request.get("doc_id") or "")[:100],
            "comment": (request.get("comment") or "")[:500]}


@router.post("/feedback")
async def submit_feedback(
    request: dict,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """反馈检索质量（真实落库）"""
    data = validate_feedback_request(request)
    fb = KnowledgeFeedback(
        user_id=current_user["id"], query=data["query"],
        doc_id=data["doc_id"], rating=data["rating"], comment=data["comment"],
    )
    db.add(fb)
    db.commit()
    await write_audit_log(
        user_id=current_user["id"], action="knowledge_feedback",
        resource_type="knowledge_document", resource_id=data["doc_id"],
        after_value=data,
    )
    return success({"feedback_id": fb.id}, "反馈已记录")
```

- [ ] **Step 5: 运行测试**

Run: `cd services/knowledge-service && python -m pytest tests/ -v`
Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add services/knowledge-service/app/models/knowledge_feedback.py services/knowledge-service/app/api/knowledge.py services/knowledge-service/tests/test_feedback_persist.py
git commit -m "feat(knowledge): persist search feedback with validation + audit"
```

### Task D5: 示例文档种子脚本

**Files:**
- Create: `scripts/seed_demo_docs.py`
- Modify: `services/knowledge-service/app/core/document_manager.py`（允许绕过百炼导入直接 ready —— 供种子/离线场景）

**Interfaces:**
- Produces: `python scripts/seed_demo_docs.py`：生成 3 个示例 txt（说明书/指南/竞品对比），走 create_from_upload → 解析正文 → DashVector upsert → status ready（跳过百炼导入）；打印每步结果

- [ ] **Step 1: 实现** `document_manager.py` 加：

```python
    def approve_without_bailian(self, doc_id: int, reviewer_id: int):
        """离线上架：仅本地正文入库 + 向量化，跳过百炼导入（种子/演示/无百炼凭证场景）"""
        from app.services.document_processor import extract_text, chunk_text
        doc = self.repo.get(doc_id)
        if not doc:
            raise BusinessError("文档不存在", code=4001)
        if doc.status not in ("draft", "rejected"):
            raise BusinessError(f"当前状态 {doc.status} 不允许审核", code=4001)
        if not doc.file_url:
            raise BusinessError("文档无 file_url", code=4001)
        import tempfile
        suffix = os.path.splitext(doc.file_url)[1]
        fd, local_path = tempfile.mkstemp(suffix=suffix)
        os.close(fd)
        try:
            self.oss.download_to_local(doc.file_url, local_path)
            text = extract_text(local_path)
        finally:
            if os.path.exists(local_path):
                os.unlink(local_path)
        if text:
            doc.content = text[:100000]
            if self.dashvector.is_configured():
                chunks = chunk_text(text)
                self.dashvector.upsert_chunks(
                    doc_id, doc.title or "", chunks,
                    fields={"product_id": str(doc.product_id or ""), "doc_type": doc.doc_type or ""},
                )
        return self.repo.update_status(doc_id, "ready", reviewer_id)
```

- [ ] **Step 2: 实现种子脚本** `scripts/seed_demo_docs.py`：

```python
"""知识库示例文档种子：生成 3 个示例 txt → 上传 → 离线上架（跳过百炼）→ 向量化

用法（在仓库根目录，需先建库 + 配置 .env 的 OSS/DASHVECTOR/DASHSCOPE）：
    python scripts/seed_demo_docs.py

输出：每个文档的 id/状态/向量化 chunk 数；失败项列出原因（不中断其余项）。
"""
import os
import sys
import logging
import tempfile

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from shared.common.db_session import SessionLocal  # noqa: E402

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)

DEMO_DOCS = [
    {
        "title": "示例产品说明书 v1",
        "doc_type": "product",
        "content": (
            "【药品名称】示例注射液\n"
            "【适应症】本品适用于 XX 肿瘤的辅助治疗。\n"
            "【用法用量】推荐剂量按体重计算，每 3 周一次静脉输注。\n"
            "【不良反应】常见：疲劳、恶心。严重：过敏反应（罕见）。\n"
            "【禁忌】对本品任何成分过敏者禁用。\n"
            "【证据等级】B\n"
            "请勿承诺疗效，具体方案由医生根据患者情况决定。"
        ),
    },
    {
        "title": "示例临床指南摘要",
        "doc_type": "guideline",
        "content": (
            "本指南基于 III 期临床试验数据制定。\n"
            "一线治疗推荐：免疫联合化疗。\n"
            "二线治疗：单药或联合方案需评估 PD-L1 表达水平。\n"
            "用药期间需监测肝功能。\n"
            "证据等级：A（随机对照试验荟萃分析）。"
        ),
    },
    {
        "title": "示例竞品对比材料（内部参考）",
        "doc_type": "competitor",
        "content": (
            "本品与竞品在主要终点上的对比：\n"
            "本品中位无进展生存期 11.2 个月，竞品 9.8 个月（III 期 RCT）。\n"
            "安全性：两组不良事件发生率无显著差异。\n"
            "结论仅供内部参考，禁止对外贬低竞品。"
        ),
    },
]


def main():
    from services.knowledge_service.app.core.document_manager import DocumentManager
    from services.knowledge_service.app.db.repositories.knowledge_repo import KnowledgeRepository

    db = SessionLocal()
    manager = DocumentManager(db)
    repo = KnowledgeRepository(db)

    uploaded = []
    for spec in DEMO_DOCS:
        try:
            with tempfile.NamedTemporaryFile("w", suffix=".txt", encoding="utf-8", delete=False) as f:
                f.write(spec["content"])
                local_path = f.name
            doc = manager.create_from_upload(
                local_path=local_path,
                title=spec["title"],
                doc_type=spec["doc_type"],
                uploader_id=None,
                evidence_level="B",
                source="demo-seed",
            )
            manager.approve_without_bailian(doc.id, reviewer_id=None)
            doc = repo.get(doc.id)
            uploaded.append({"id": doc.id, "title": doc.title, "status": doc.status, "has_content": bool(doc.content)})
            logger.info("OK 文档 %s → id=%s status=%s content=%d 字", spec["title"], doc.id, doc.status, len(doc.content or ""))
            os.unlink(local_path)
        except Exception as exc:
            logger.error("FAIL %s: %s", spec["title"], exc)
            uploaded.append({"title": spec["title"], "error": str(exc)})

    db.close()
    logger.info("种子完成：%s", uploaded)


if __name__ == "__main__":
    main()
```

- [ ] **Step 3: 运行验证（可选，依赖 .env 的 OSS/向量配置；跑不了不算失败）**

Run: `python scripts/seed_demo_docs.py`
Expected: 每个示例文档打印 OK + id/status/content 字数；或单个 FAIL 带原因。

- [ ] **Step 4: Commit**

```bash
git add scripts/seed_demo_docs.py services/knowledge-service/app/core/document_manager.py
git commit -m "feat(knowledge): demo seed script + offline approve path (skip Bailian)"
```

---

## 批次 E：工程基建

### Task E1: CI/CD workflow

**Files:**
- Create: `.github/workflows/ci.yml`
- Create: `.github/workflows/deploy.yml`

**Interfaces:**
- Produces: PR/push 到 master/develop 触发 ci；main 分支构建推阿里云 registry

- [ ] **Step 1: 写 ci.yml**：

```yaml
name: CI

on:
  push:
    branches: [master, develop]
  pull_request:
    branches: [master]

jobs:
  backend-test:
    runs-on: ubuntu-latest
    strategy:
      matrix:
        service: [auth-service, specialist-service, visit-service, knowledge-service, compliance-service, audit-service, hcp-service, gateway]
    steps:
      - uses: actions/checkout@v3
      - uses: actions/setup-python@v4
        with:
          python-version: '3.11'
      - name: Install
        run: |
          pip install -r services/${{ matrix.service }}/requirements.txt
          pip install pytest pytest-asyncio
      - name: Test
        env:
          JWT_SECRET: ci-test-secret
          INTERNAL_API_KEY: ci-test-internal-key
          DASHSCOPE_API_KEY: ${{ secrets.DASHSCOPE_API_KEY }}
          DATABASE_URL: postgresql://medagent:medagent123@localhost:5432/medagent
        run: |
          cd services/${{ matrix.service }}
          python -m pytest tests/ -v || exit 1
      - name: Import check
        run: |
          cd services/${{ matrix.service }}
          python -c "import app.main" || exit 1

  frontend-check:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v3
      - uses: actions/setup-node@v3
        with:
          node-version: '18'
      - name: Web build check
        run: |
          cd web && npm ci && npx tsc --noEmit || exit 1
      - name: Mobile type check
        run: |
          cd mobile && npm ci && npx tsc --noEmit || exit 1
```

- [ ] **Step 2: 写 deploy.yml**：

```yaml
name: Deploy

on:
  push:
    branches: [main]

jobs:
  build-and-push:
    runs-on: ubuntu-latest
    strategy:
      matrix:
        service: [auth-service, specialist-service, visit-service, knowledge-service, compliance-service, audit-service, hcp-service, gateway]
    steps:
      - uses: actions/checkout@v3
      - name: Build image
        run: |
          docker build -t registry.cn-hangzhou.aliyuncs.com/medagent/${{ matrix.service }}:${{ github.sha }} \
            -f services/${{ matrix.service }}/Dockerfile .
      - name: Push image
        run: |
          docker login --username=${{ secrets.ALIYUN_REGISTRY_USER }} \
            --password=${{ secrets.ALIYUN_REGISTRY_PASS }} \
            registry.cn-hangzhou.aliyuncs.com
          docker push registry.cn-hangzhou.aliyuncs.com/medagent/${{ matrix.service }}:${{ github.sha }}
```

- [ ] **Step 3: 语法校验**

Run: `python -c "import yaml,glob; [yaml.safe_load(open(f)) for f in glob.glob('.github/workflows/*.yml')]; print('YAML OK')"`
Expected: `YAML OK`

- [ ] **Step 4: Commit**

```bash
git add .github/workflows/ci.yml .github/workflows/deploy.yml
git commit -m "ci: add GitHub Actions CI (backend tests, frontend checks) and deploy workflow"
```

### Task E2: ARMS 监控脚本 + /metrics 端点

**Files:**
- Rewrite: `deploy/arms-monitor.py`
- Create: `deploy/arms-alerts.yaml`
- Create: `services/specialist-service/app/api/metrics.py`、`services/compliance-service/app/api/metrics.py`（core 服务模式）
- Modify: 两个服务的 `app/main.py`、`requirements.txt`（prometheus-client）
- Modify: `services/specialist-service/app/core/answer_generator.py`（延迟直方图埋点）、`services/compliance-service/app/core/checker.py`（拦截计数埋点）

**Interfaces:**
- Produces: `GET /metrics`（Prometheus 文本格式）；`python deploy/arms-monitor.py [--dry-run]`：AK 已配 → 调 ARMS API 创建/更新 3 条告警规则；未配/失败 → 打印指引 exit 1

- [ ] **Step 1: 加依赖** 两个服务 `requirements.txt` 加 `prometheus-client>=0.19.0`。
- [ ] **Step 2: metrics 路由** 两个服务各建 `app/api/metrics.py`（内容相同，service 名不同）：

```python
"""Prometheus 指标端点（方案 15.4 监控数据源）"""
from prometheus_client import Counter, Histogram, generate_latest, CONTENT_TYPE_LATEST
from fastapi import APIRouter
from fastapi.responses import Response

router = APIRouter(tags=["metrics"])

REQUESTS = Counter("http_requests_total", "HTTP 请求总数", ["service", "method"])
CHAT_LATENCY = Histogram(
    "specialist_chat_latency_seconds", "专员回答延迟（秒）",
    buckets=(0.1, 0.5, 1, 2, 5, 10, 30),
)
COMPLIANCE_BLOCKS = Counter("compliance_blocks_total", "合规拦截总数", ["action", "severity"])


@router.get("/metrics")
async def metrics():
    return Response(generate_latest(), media_type=CONTENT_TYPE_LATEST)
```

`app/main.py` 各加：

```python
from app.api import metrics as metrics_api
app.include_router(metrics_api.router)
```

- [ ] **Step 3: 埋点**

- specialist `answer_generator.py`：`latency_ms = int((time.time() - start_time) * 1000)` 两处之后加：

```python
        from app.api.metrics import CHAT_LATENCY
        CHAT_LATENCY.observe(latency_ms / 1000.0)
```

- compliance `checker.py` `check()` 的 `return self._result(blocked, violations)` 之前加：

```python
        from app.api.metrics import COMPLIANCE_BLOCKS
        for v in violations:
            COMPLIANCE_BLOCKS.labels(action=v["action"], severity=v["severity"]).inc()
```

- [ ] **Step 4: 重写 arms-monitor.py**：

```python
#!/usr/bin/env python3
"""ARMS 监控告警规则配置（方案 15.4）

真实调用阿里云 ARMS OpenAPI（RPC 签名，与 NLS token 同款 HMAC-SHA1）创建/更新告警规则。
未配置 ALIYUN_ACCESS_KEY_ID/SECRET 或调用失败 → 打印指引并以非零码退出（不假装成功）。

用法：
    python deploy/arms-monitor.py            # 创建/更新规则
    python deploy/arms-monitor.py --dry-run  # 只打印将执行的动作
"""
import argparse
import base64
import hashlib
import hmac
import json
import os
import sys
import time
import uuid
from urllib.parse import quote

import httpx

ALERTS = [
    {
        "name": "AI 回答延迟过高",
        "metric": "specialist_chat_latency_seconds",
        "threshold": "5",
        "op": ">",
        "notify": ["dev_team"],
    },
    {
        "name": "合规拦截率异常",
        "metric": "compliance_blocks_total",
        "threshold": "0.001|0.1",
        "op": "out_of_range",
        "notify": ["dev_team", "compliance_team"],
    },
    {
        "name": "数据库连接池满",
        "metric": "db_connection_pool_usage",
        "threshold": "0.8",
        "op": ">",
        "notify": ["dev_team"],
    },
]


def _percent_encode(value: str) -> str:
    return quote(str(value), safe="~")


def _sign(params: dict, secret: str) -> str:
    sorted_items = sorted(params.items())
    canonical = "&".join(f"{_percent_encode(k)}={_percent_encode(v)}" for k, v in sorted_items)
    string_to_sign = f"GET&%2F&{_percent_encode(canonical)}"
    digest = hmac.new(secret.encode(), string_to_sign.encode(), hashlib.sha1)
    return base64.b64encode(digest.digest()).decode()


def _call_arms(action: str, extra: dict) -> dict:
    ak = os.getenv("ALIYUN_ACCESS_KEY_ID", "")
    sk = os.getenv("ALIYUN_ACCESS_KEY_SECRET", "")
    if not ak or not sk:
        raise RuntimeError("未配置 ALIYUN_ACCESS_KEY_ID/ALIYUN_ACCESS_KEY_SECRET")
    params = {
        "AccessKeyId": ak,
        "Action": action,
        "Format": "JSON",
        "SignatureMethod": "HMAC-SHA1",
        "SignatureNonce": uuid.uuid4().hex,
        "SignatureVersion": "1.0",
        "Timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "Version": "2019-08-08",
        "RegionId": os.getenv("ALIYUN_REGION", "cn-hangzhou"),
        **extra,
    }
    params["Signature"] = _sign(params, sk)
    resp = httpx.get("https://arms.aliyuncs.com/", params=params, timeout=15.0)
    resp.raise_for_status()
    body = resp.json()
    if body.get("Code") not in (None, "200", "Success"):
        raise RuntimeError(f"ARMS API 错误: {body}")
    return body


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true", help="只打印动作，不调用 API")
    args = parser.parse_args()

    for alert in ALERTS:
        if args.dry_run:
            print(f"[dry-run] 将创建/更新告警规则: {alert['name']} ({alert['metric']} {alert['op']} {alert['threshold']})")
            continue
        try:
            body = _call_arms("CreatePrometheusAlertRule", {"AlertName": alert["name"]})
            print(f"OK 告警规则 {alert['name']}: {body}")
        except Exception as exc:
            print(f"FAIL 告警规则 {alert['name']}: {exc}", file=sys.stderr)
            print("请在阿里云控制台手动配置（ARMS → 告警规则），或补齐 AK 权限后重跑。", file=sys.stderr)
            sys.exit(1)
    print("ARMS 告警规则配置完成（或 dry-run 结束）")


if __name__ == "__main__":
    main()
```

（`deploy/arms-alerts.yaml`：与 ALERTS 列表同内容的 YAML 源文件，脚本的单一事实来源——留待后续用 YAML 替换硬编码列表；本轮脚本内列表为准。）

- [ ] **Step 5: 验证**

Run: `python deploy/arms-monitor.py --dry-run`
Expected: 打印 3 条规则动作，退出码 0。

- [ ] **Step 6: Commit**

```bash
git add deploy/arms-monitor.py deploy/arms-alerts.yaml services/specialist-service/app/api/metrics.py services/compliance-service/app/api/metrics.py services/specialist-service/app/main.py services/compliance-service/app/main.py services/specialist-service/app/core/answer_generator.py services/compliance-service/app/core/checker.py services/specialist-service/requirements.txt services/compliance-service/requirements.txt
git commit -m "feat(ops): ARMS alert config script + prometheus /metrics endpoints with latency/block gauges"
```

---

## 执行后验证（全部任务完成时）

Run:
```bash
cd services/compliance-service && python -m pytest tests/ -v
cd services/specialist-service && python -m pytest tests/ -v
cd services/visit-service && python -m pytest tests/ -v
cd services/knowledge-service && python -m pytest tests/ -v
cd services/hcp-service && python -m pytest tests/ -v
python deploy/arms-monitor.py --dry-run
python -c "import yaml,glob; [yaml.safe_load(open(f)) for f in glob.glob('.github/workflows/*.yml')]; print('YAML OK')"
```
Expected: 全部 PASS / 无报错；`git log --oneline` 出现 15 个对应 commit。
