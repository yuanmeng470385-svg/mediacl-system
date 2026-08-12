# visit-service TTS token + LLM 实时推荐 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** visit-service 新增 NLS TTS token 下发端点（移动端语音合成用），并在转写处理链路加 LLM 实时推荐（关键节点标记 + 话术建议，节流 + 降级），落库 `visit_records.key_nodes`。

**Architecture:** TTS token 端点复用 `app/services/realtime_asr.py` 已有的模块级 `get_nls_token()`（AK/SK 签名换 token，24h 进程内缓存，无需重构）；LLM 推荐复用 `app/services/qwen_client.py` 的 `QwenClient`（OpenAI 兼容 dashscope，qwen-plus）在 `process_transcript` 内节流触发、异步降级、结果写 `key_nodes` JSONB 列（迁移 006）。

**Tech Stack:** FastAPI + SQLAlchemy（JSONB）+ 阿里云 NLS（REST TTS token）/ DashScope qwen-plus。测试从服务目录跑：`cd services/visit-service && python -m pytest tests/ -v`（conftest 已把仓库根加入 sys.path）。

## Global Constraints

- 测试命令：`cd services/visit-service && python -m pytest tests/ -v`（从服务目录跑，原因见 CLAUDE.md gotcha）
- 端点失败降级铁律：LLM 实时推荐任何异常不得阻塞 `process_transcript` 主流程（转写/合规/异议照常返回）
- 迁移文件放 `scripts/migrations/006_add_visit_key_nodes.sql`，格式参照 005（`\set ON_ERROR_STOP on` + 头部注释）
- 错误码：业务错误用 `BusinessError`（4000-4999 区间，shared/common/response.py）；success 包装用 `shared.common.response.success`
- 网关 `ROUTE_MAP`（`services/gateway/app/main.py:81-93` 附近）加 `/api/v1/nls` → visit-service；网关测试必须全绿
- 提交格式遵循 conventional commits

---

### Task 1: NLS TTS token 端点 + 网关路由

**Files:**
- Create: `services/visit-service/app/api/nls.py`
- Modify: `services/visit-service/app/main.py`（include_router，参照 visits_router 模式）
- Modify: `services/gateway/app/main.py`（ROUTE_MAP 加 `/api/v1/nls`）
- Create: `services/visit-service/tests/test_nls_tts.py`
- Modify: `.env`（本地，gitignore；加 `NLS_APPKEY=` 占位注释 + `NLS_MOCK=1` 联调开关）

**Interfaces:**
- Consumes: `app.services.realtime_asr.get_nls_token()`（异步，返回 str token，24h 缓存）、`app.services.realtime_asr.nls_token_expire_at()`（本任务新增，返回缓存过期 epoch 或 None）、`shared.common.auth.get_current_user`、`shared.common.auth.require_roles`、`shared.common.response.success/BusinessError`
- Produces: `GET /api/v1/nls/tts-token` → `success({"token": str, "appkey": str, "expires_at": float|None})`；未配 NLS_APPKEY → `BusinessError("NLS 语音合成未配置（缺 NLS_APPKEY）")`；下游移动端 `mobile/src/services/tts.ts` 消费

- [ ] **Step 1: realtime_asr.py 加过期时间辅助函数**

`services/visit-service/app/services/realtime_asr.py` 的 `get_nls_token`（L68-102）之后追加：

```python
def nls_token_expire_at() -> Optional[float]:
    """当前进程缓存的 NLS token 过期时刻（epoch 秒）；尚未换过 token 返回 None"""
    cached = _token_cache.get("nls")
    return cached["expire_at"] if cached else None
```

（`Optional` 已在 L29 import）

- [ ] **Step 2: 新建 `app/api/nls.py`**

```python
"""NLS 语音能力端点（移动端 TTS 合成用）

移动端拿 {token, appkey} 后直调 NLS REST 合成
（https://nls-gateway-cn-shanghai.aliyuncs.com/stream/v1/tts）。
appkey 是项目标识非机密，token 是 AK/SK 换发的短期凭证（24h），
AK/SK 永不离开服务端。
"""
import logging
import os

from fastapi import APIRouter, Depends

from shared.common.auth import require_roles
from shared.common.response import success, BusinessError
from app.services.realtime_asr import get_nls_token, nls_token_expire_at

router = APIRouter(prefix="/api/v1/nls", tags=["nls"])
logger = logging.getLogger(__name__)


@router.get("/tts-token")
async def get_tts_token(
    current_user: dict = Depends(require_roles("rep", "admin", "manager")),
):
    """下发 NLS TTS 合成所需的临时 token + appkey"""
    app_key = os.getenv("NLS_APPKEY", "").strip()
    if not app_key:
        raise BusinessError("NLS 语音合成未配置（缺 NLS_APPKEY）")
    token = await get_nls_token()
    return success({
        "token": token,
        "appkey": app_key,
        "expires_at": nls_token_expire_at(),
    })
```

- [ ] **Step 3: main.py 挂载路由**

`services/visit-service/app/main.py` 中 `app.include_router(tasks_router)`（L55）之后追加：

```python
from app.api.nls import router as nls_router
app.include_router(nls_router)
```

- [ ] **Step 4: 网关 ROUTE_MAP 加路由**

`services/gateway/app/main.py` 的 ROUTE_MAP 中 `/api/v1/hcps` 行附近追加：

```python
    "/api/v1/nls": settings.VISIT_SERVICE_URL,
```

（注意保持字典格式与相邻行一致，行尾逗号）

- [ ] **Step 5: 写测试 `tests/test_nls_tts.py`**

（风格参照 test_visit_manager.py：直接调 handler，不走 TestClient；`conftest.py` 已加 sys.path）

```python
"""NLS TTS token 端点测试"""
import asyncio
import sys
import os
from unittest.mock import AsyncMock

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", ".."))

import pytest

from shared.common.response import BusinessError
import app.api.nls as nls_mod


def _call(user=None):
    user = user or {"id": 1, "role": "rep"}
    return asyncio.run(nls_mod.get_tts_token(user))


def test_tts_token_missing_appkey_raises(monkeypatch):
    """未配 NLS_APPKEY → BusinessError（移动端据此禁用朗读按钮）"""
    monkeypatch.delenv("NLS_APPKEY", raising=False)
    with pytest.raises(BusinessError) as ei:
        _call()
    assert "NLS_APPKEY" in str(ei.value)


def test_tts_token_ok(monkeypatch):
    """已配 NLS_APPKEY → 返回 {token, appkey, expires_at}"""
    monkeypatch.setenv("NLS_APPKEY", "appkey-123")
    monkeypatch.setattr(nls_mod, "get_nls_token", AsyncMock(return_value="tok-abc"))
    monkeypatch.setattr(nls_mod, "nls_token_expire_at", lambda: 1234567890.0)
    data = _call()
    assert data["token"] == "tok-abc"
    assert data["appkey"] == "appkey-123"
    assert data["expires_at"] == 1234567890.0
```

- [ ] **Step 6: 跑测试验证通过**

Run: `cd services/visit-service && python -m pytest tests/test_nls_tts.py -v`
Expected: 2 passed

- [ ] **Step 7: 跑 visit-service 全量回归**

Run: `cd services/visit-service && python -m pytest tests/ -v`
Expected: 现有 53 + 新增 2 = 55 passed（若现有失败先停，说明环境问题）

- [ ] **Step 8: 跑网关测试**

Run: `cd services/gateway && python -m pytest tests/ -v`
Expected: 38 passed

- [ ] **Step 9: .env 加配置位（本地文件，不提交）**

`.env` 末尾追加（`NLS_APPKEY` 值用户后续填真实 AppKey；`NLS_MOCK=1` 仅开发联调，Mock 文本不落库）：

```
# NLS 实时语音（ASR 转写 + TTS 合成；appkey 填 NLS 管控台项目 Appkey）
NLS_APPKEY=
# 开发联调：无 AppKey 时用 Mock 转写（Mock 文本不落库）；配真 AppKey 后删除
NLS_MOCK=1
```

- [ ] **Step 10: 提交**

```bash
git add services/visit-service/app/services/realtime_asr.py services/visit-service/app/api/nls.py services/visit-service/app/main.py services/gateway/app/main.py services/visit-service/tests/test_nls_tts.py
git commit -m "feat(visit): NLS TTS token 端点 + 网关路由（移动端语音合成凭证）"
```

---

### Task 2: 迁移 006 + VisitRecord.key_nodes 列

**Files:**
- Create: `scripts/migrations/006_add_visit_key_nodes.sql`
- Modify: `services/visit-service/app/models/visit_record.py`（加列 + to_dict 输出）

**Interfaces:**
- Consumes: 无
- Produces: `visit_records.key_nodes` JSONB 列（数组，元素 `{type, label, quote, created_at}`）；`VisitRecord.key_nodes` 属性；`to_dict()` 输出 `key_nodes` 键；下游 Task 3 读写

- [ ] **Step 1: 创建迁移文件**

`scripts/migrations/006_add_visit_key_nodes.sql`：

```sql
-- 006_add_visit_key_nodes.sql
-- LLM 实时推荐（2026-08-11）落库列：AI 关键节点标记（决策点/兴趣点）+ 话术建议引用。
-- 数组元素形状：{"type": "decision_point|interest_point", "label": str, "quote": str,
--                "created_at": "ISO8601"}；无 AI 推荐时为 NULL。
--
-- 用法：
--   docker exec -i medagent-postgres psql -U medagent medagent \
--     < scripts/migrations/006_add_visit_key_nodes.sql
-- （ALTER TABLE 只需表 owner/应用账号；无 superuser 前置条件，与 002/005 不同）

\set ON_ERROR_STOP on

ALTER TABLE visit_records ADD COLUMN IF NOT EXISTS key_nodes JSONB;
```

- [ ] **Step 2: 模型加列**

`services/visit-service/app/models/visit_record.py` 的 `attachments` 列（L38）之后追加：

```python
    key_nodes = Column(JSONB)                         # LLM 实时推荐：关键节点标记数组
```

`to_dict()`（L63 `"attachments": self.attachments,` 之后）追加：

```python
            "key_nodes": self.key_nodes,
```

- [ ] **Step 3: 跑 visit-service 测试确认无回归**

Run: `cd services/visit-service && python -m pytest tests/ -v`
Expected: 55 passed（模型加列不影响既有用例）

- [ ] **Step 4: 提交**

```bash
git add scripts/migrations/006_add_visit_key_nodes.sql services/visit-service/app/models/visit_record.py
git commit -m "feat(visit): 迁移 006 visit_records.key_nodes 列（LLM 实时推荐落库）"
```

---

### Task 3: process_transcript 加 LLM 实时推荐（节流 + 降级 + 落库）

**Files:**
- Modify: `services/visit-service/app/core/visit_manager.py`（`__init__` 注入 qwen；`process_transcript` 末尾追加推荐；新增 `_llm_recommend` 方法）
- Create: `services/visit-service/tests/test_recommendation.py`

**Interfaces:**
- Consumes: `QwenClient`（`app/services/qwen_client.py`，`chat(messages, model=None, temperature=0.1, max_tokens=2000) -> {"content": str, "usage": {...}}`，**同步**接口）、`VisitRepo.get(db, visit_id)`、`VisitRecord.key_nodes`
- Produces: `process_transcript` 返回值追加 `"key_nodes": [...]`（空数组表示本句无触发）与 `"ai_suggestion": {...} | None`；`_llm_recommend(db, visit_id, user_id, text) -> Dict | None`；下游移动端 `mapTranscriptResult` 消费 `key_nodes`/`ai_suggestion`

- [ ] **Step 1: `__init__` 注入 QwenClient**

`visit_manager.py` 的 `__init__`（L266-272，参数含 `detector=None` 等）追加参数与赋值（参照 `self.detector = detector or ObjectionDetector()` 的注入模式）：

```python
        qwen: Optional["QwenClient"] = None,
```
（在参数列表末尾；并确保 import：文件头部已 import `ObjectionDetector`，追加 `from app.services.qwen_client import QwenClient`）

```python
        self.qwen = qwen or QwenClient()
```

（放在 `self.detector = detector or ObjectionDetector()` 之后）

- [ ] **Step 2: `process_transcript` 返回追加推荐**

`process_transcript` 的 `return {...}`（L455-461）改为：

```python
        # LLM 实时推荐（关键节点 + 话术建议）：节流触发、失败降级不阻塞
        rec = await self._llm_recommend(db, visit_id, user_id, text_content)
        return {
            "visit_id": visit_id,
            "transcript": text_content,
            "compliance": compliance,
            "objections": objection_result,
            "suggestions": self._generate_suggestions(objection_result, compliance),
            "key_nodes": (rec or {}).get("key_nodes", []),
            "ai_suggestion": (rec or {}).get("ai_suggestion"),
        }
```

- [ ] **Step 3: 新增 `_llm_recommend` 方法**

在 `_generate_suggestions`（L463）之后追加：

```python
    # ==================== 拜访中：LLM 实时推荐（关键节点 + 话术建议） ====================

    _LLM_REC_COOLDOWN_SECONDS = 20.0
    _LLM_REC_MIN_LENGTH = 6

    async def _llm_recommend(
        self, db: Session, visit_id: int, user_id: int, text: str,
    ) -> Optional[Dict]:
        """LLM 实时推荐：生成关键节点标记（决策点/兴趣点）与话术建议

        触发条件：新句去空白后 ≥6 字；同 visit 冷却 20s（以 key_nodes 最后一条的
        created_at 计，进程重启/换实例同样生效）。
        降级：LLM 超时/异常/解析失败 → 记 warning 日志并返回 None，不阻塞主流程。
        """
        stripped = text.strip()
        if len(stripped) < self._LLM_REC_MIN_LENGTH:
            return None

        record = VisitRepo.get(db, visit_id)
        if not record:
            return None
        nodes = list(record.key_nodes or [])
        now = datetime.now()
        if nodes and nodes[-1].get("created_at"):
            try:
                last = datetime.fromisoformat(str(nodes[-1]["created_at"]))
                if (now - last).total_seconds() < self._LLM_REC_COOLDOWN_SECONDS:
                    return None
            except ValueError:
                pass

        recent_quotes = [str(n.get("quote", "")) for n in nodes[-3:] if n.get("quote")]
        prompt = [
            {"role": "system", "content": (
                "你是医药代表拜访的实时陪访助手。根据刚发生的对话片段，标记关键节点并给应对话术。"
                "只输出一个 JSON 对象，不要任何其他文字："
                '{"key_nodes":[{"type":"decision_point|interest_point","label":"≤10字短标签",'
                '"quote":"引用原话≤40字"}],"suggestion":{"topic":"异议主题",'
                '"advice":"应对话术建议≤80字"} 或 null}。'
                "没有值得标记的内容时 key_nodes 给空数组；没有异议时 suggestion 给 null。"
                "type 只能是 decision_point（医生做决策表态/询问决策相关）或 interest_point（医生表现出兴趣/认可）。"
            )},
            {"role": "user", "content": (
                f"对话片段：{stripped}\n"
                f"最近已标记：{'；'.join(recent_quotes) if recent_quotes else '无'}"
                "\n（不要重复标记已标记过的引用）"
            )},
        ]
        try:
            result = await asyncio.to_thread(
                self.qwen.chat, prompt, temperature=0.2, max_tokens=800,
            )
            content = str(result.get("content", "") or "")
            parsed = self._parse_recommendation_json(content)
            if parsed is None:
                logger.warning("visit %s LLM 推荐输出无法解析: %.200s", visit_id, content)
                return None
            key_nodes = []
            for n in parsed.get("key_nodes") or []:
                if not isinstance(n, dict):
                    continue
                ntype = n.get("type")
                label = str(n.get("label", "")).strip()
                quote = str(n.get("quote", "")).strip()
                if ntype not in ("decision_point", "interest_point") or not label:
                    continue
                key_nodes.append({
                    "type": ntype, "label": label[:20], "quote": quote[:60],
                    "created_at": now.isoformat(),
                })
            suggestion = parsed.get("suggestion")
            if not (isinstance(suggestion, dict) and suggestion.get("advice")):
                suggestion = None
            else:
                suggestion = {
                    "topic": str(suggestion.get("topic", "")).strip()[:50] or "对话要点",
                    "advice": str(suggestion.get("advice", "")).strip()[:200],
                }
            if key_nodes:
                record.key_nodes = nodes + key_nodes
                db.commit()
            await write_audit_log(
                user_id=user_id, action="visit_llm_recommend",
                resource_type="visit", resource_id=str(visit_id),
                ai_involved=True, ai_model="qwen-plus",
                ai_response=json.dumps({"key_nodes": key_nodes, "suggestion": suggestion}, ensure_ascii=False)[:2000],
            )
            return {"key_nodes": key_nodes, "ai_suggestion": suggestion}
        except Exception as e:
            # 降级铁律：推荐失败绝不影响转写/合规/异议主流程
            logger.warning("visit %s LLM 实时推荐失败（不阻塞）: %s", visit_id, e)
            return None

    @staticmethod
    def _parse_recommendation_json(content: str) -> Optional[Dict]:
        """从 LLM 输出提取 JSON 对象：容忍 ```json 代码块与前后缀杂讯"""
        text = content.strip()
        # 去 markdown 代码块围栏
        if text.startswith("```"):
            text = text.split("\n", 1)[-1] if "\n" in text else text[3:]
            if text.endswith("```"):
                text = text[:-3]
            text = text.strip()
        start = text.find("{")
        end = text.rfind("}")
        if start == -1 or end <= start:
            return None
        try:
            parsed = json.loads(text[start:end + 1])
            return parsed if isinstance(parsed, dict) else None
        except json.JSONDecodeError:
            return None
```

（注意：`write_audit_log` 已 import（L32）；`json` 已 import（L15）；`datetime` 已 import（L19）；`Dict/Optional` 已 import（L20）；`asyncio` 已 import（L17））

- [ ] **Step 4: 写测试 `tests/test_recommendation.py`**

```python
"""LLM 实时推荐测试（假 Qwen，不连真实服务）"""
import sys
import os
from datetime import datetime, timedelta

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", ".."))

import pytest
import asyncio

import app.core.visit_manager as vm_module
from app.models.visit_record import VisitRecord

# 复用 test_visit_manager.py 的 FakeDb（同目录 import）
from test_visit_manager import FakeDb


class FakeQwen:
    """假 QwenClient：可注入返回内容或抛异常"""
    def __init__(self, content=None, error=None, call_count=None):
        self._content = content
        self._error = error
        self.calls = [] if call_count is None else call_count

    def chat(self, messages, model=None, temperature=0.1, max_tokens=2000):
        self.calls.append(messages)
        if self._error:
            raise self._error
        return {"content": self._content, "usage": {}}


def make_manager(fake_qwen):
    return vm_module.VisitManager(qwen=fake_qwen)


def make_record():
    rec = VisitRecord()
    rec.id = 1
    rec.visit_time = datetime.now()
    return rec


def test_short_sentence_not_triggered():
    q = FakeQwen(content='{"key_nodes":[]}')
    m = make_manager(q)
    db = FakeDb()
    rec = make_record()
    db.add(rec)
    result = asyncio.run(m._llm_recommend(db, rec.id, 1, "好的"))
    assert result is None
    assert q.calls == []  # 短句不触发


def test_throttled_within_cooldown():
    q = FakeQwen(content='{"key_nodes":[]}')
    m = make_manager(q)
    db = FakeDb()
    rec = make_record()
    rec.key_nodes = [{"type": "interest_point", "label": "认可", "quote": "x",
                      "created_at": datetime.now().isoformat()}]  # 刚标记过 → 冷却中
    db.add(rec)
    result = asyncio.run(m._llm_recommend(db, rec.id, 1, "这句话超过六个字了"))
    assert result is None
    assert q.calls == []


def test_llm_failure_degrades():
    q = FakeQwen(error=RuntimeError("LLM 挂了"))
    m = make_manager(q)
    db = FakeDb()
    rec = make_record()
    db.add(rec)
    result = asyncio.run(m._llm_recommend(db, rec.id, 1, "这句话超过六个字了"))
    assert result is None  # 降级：返回 None 而非抛异常


def test_success_returns_and_persists():
    content = ('{"key_nodes":[{"type":"decision_point","label":"决策表态",'
               '"quote":"主任表示考虑使用"}],"suggestion":{"topic":"价格",'
               '"advice":"建议强调药物经济学优势"}}')
    q = FakeQwen(content=content)
    m = make_manager(q)
    db = FakeDb()
    rec = make_record()
    db.add(rec)
    result = asyncio.run(m._llm_recommend(db, rec.id, 1, "主任表示考虑使用我们的产品"))
    assert result is not None
    assert result["key_nodes"][0]["type"] == "decision_point"
    assert result["ai_suggestion"]["advice"] == "建议强调药物经济学优势"
    assert len(rec.key_nodes) == 1  # 已落库
    assert rec.key_nodes[0]["created_at"]


def test_unparseable_output_degrades():
    q = FakeQwen(content="抱歉我无法处理")
    m = make_manager(q)
    db = FakeDb()
    rec = make_record()
    db.add(rec)
    result = asyncio.run(m._llm_recommend(db, rec.id, 1, "这句话超过六个字了"))
    assert result is None


def test_process_transcript_includes_recommendation(monkeypatch):
    """集成：process_transcript 响应含 key_nodes/ai_suggestion"""
    q = FakeQwen(content='{"key_nodes":[{"type":"interest_point","label":"认可","quote":"q"}],"suggestion":null}')
    m = make_manager(q)
    monkeypatch.setattr(vm_module, "check_compliance", lambda text, ctx: {"blocked": False, "violations": []})
    db = FakeDb()
    rec = make_record()
    db.add(rec)
    result = asyncio.run(m.process_transcript(db, rec.id, 1, text_content="这句话超过六个字了"))
    assert "key_nodes" in result
    assert result["key_nodes"][0]["type"] == "interest_point"
    assert "ai_suggestion" in result
```

注意：`check_compliance` 在 visit_manager 以 `from app.services.compliance_client import check_compliance` 引入（L30），monkeypatch 目标为 `vm_module.check_compliance`；`ObjectionDetector` 默认构造不连网（规则版可用，语义版 mock 不可用时自动降级——若 test 报网络错，改为注入 FakeDetector：`VisitManager(detector=FakeDetector(), qwen=q)`，FakeDetector 返回 `{"objections": []}`）。

- [ ] **Step 5: 跑测试验证通过**

Run: `cd services/visit-service && python -m pytest tests/test_recommendation.py -v`
Expected: 6 passed（若 FakeDetector 需要，按 Step 4 尾注处理）

- [ ] **Step 6: 全量回归**

Run: `cd services/visit-service && python -m pytest tests/ -v`
Expected: 55 + 6 = 61 passed

- [ ] **Step 7: 提交**

```bash
git add services/visit-service/app/core/visit_manager.py services/visit-service/tests/test_recommendation.py
git commit -m "feat(visit): 转写链路 LLM 实时推荐（关键节点+话术建议，节流20s+失败降级+落库）"
```
