# MedAgent 数字员工系统 · 5人任务分配清单

> **版本：v3.2 · 2026-08-03**
> **重大架构决策：每个数字专员 = 一个阿里云百炼多模态交互开发套件 App。百炼 App 自带知识库（文档上传→解析→向量化→多模态检索），我们的系统负责合规审核、审计日志、业务编排。**
> **v3.2 更新：C（陪访助手 + 医生管理）已完成，新增"C 已完成的工作（A/D/E 必读）"小节。**
> **v3.1 更新：A（数字专员服务）已完成，新增"A 已完成的工作（B/C/E 必读）"小节。**

---

## 架构说明（AI 必读）

```
┌──────────────────────────────────────────────────┐
│                    移动端 (E)                     │
│              React Native 4 Tab                  │
└────────────────────┬─────────────────────────────┘
                     │
┌────────────────────▼─────────────────────────────┐
│               API 网关 (D 已完成)                 │
│         路由转发 / JWT 认证 / 限流                │
└────┬──────────┬──────────┬──────────┬────────────┘
     │          │          │          │
┌────▼───┐ ┌───▼────┐ ┌───▼────┐ ┌───▼──────────┐
│  A✅    │ │   B    │ │  C✅   │ │  D (已完成)   │
│ 专员服务│ │ 知识库 │ │ 陪访+  │ │ 合规+审计     │
│ :8001  │ │ :8003  │ │ 医生   │ │ :8004/:8005   │
│        │ │        │ │ :8002  │ │               │
└──┬─────┘ └───┬────┘ │ :8006  │ └───────────────┘
   │           │      └───┬────┘
   │           │          │
   ▼           ▼          ▼
┌──────────────────────────────────────────────────┐
│           阿里云百炼（多模态交互套件）             │
│  每产品一个 App，自带知识库 + 通义千问 + Qwen-VL  │
│  文档解析 / 向量化 / 多模态检索均由百炼托管        │
└──────────────────────────────────────────────────┘
```

**调用链路（以数字专员问答为例）：**

```
用户提问 → 网关 → specialist-service(A)
  → compliance-service(D) 合规预检
  → 百炼 App 知识检索 + LLM 生成答案
  → compliance-service(D) 合规审核答案
  → audit-service(D) 审计日志
  → 返回用户
```

---

## 人员总览

| 代号 | 负责模块 | 端口 | 核心技术 | 状态 |
|------|---------|------|---------|------|
| D（组长） | 合规 + 审计 + 共享层 + 网关 | 8004/8005/8000 | Python FastAPI | ✅ 已完成 |
| A | 数字专员服务 | 8001 | FastAPI + 百炼 App | ✅ 已完成 |
| B | 知识库管理服务 | 8003 | FastAPI + 百炼 App 知识库 | 🔴 待开发 |
| C | 陪访助手 + 医生管理 | 8002/8006 | FastAPI + 通义听悟 | ✅ 已完成 |
| E | 移动端 + DevOps | — | React Native + Docker + CI/CD | 🔴 待开发 |

---

## 阿里云服务已开通清单

| 服务 | 配置项 | 状态 | 谁用 |
|------|--------|------|------|
| 百炼 | BAILIAN_API_KEY | ✅ | A, B |
| 通义千问 | DASHSCOPE_API_KEY | ✅ | A, C |
| 通义听悟 | TINGWU_APP_KEY + TOKEN | ✅ | C |
| DashVector | KEY + Endpoint | ✅ | B（备用） |
| OSS | KEY + Bucket `medagent-files` | ✅ | B |
| PostgreSQL + Redis | 本地 Docker | ✅ | 全员 |

> **Key 分配见文档末尾。**

---

# D 已完成的工作（A/B/C/E 必读）

以下模块已经实现并通过测试（15个测试用例全部通过），可以直接使用。

## 1. 共享层 (`shared/`)

```python
# === 统一响应（所有 API 必须用这个返回）===
from shared.common.response import success, error, AppError, ParamError, AuthError, BusinessError
# success(data={"name": "张三"}) → {"code":0, "message":"success", "data":{"name":"张三"}}
# raise ParamError("question 不能为空") → {"code":1000, "message":"question 不能为空"}

# === JWT 认证 ===
from shared.common.auth import get_current_user, create_token
# @router.get("/xxx")
# async def api(current_user: dict = Depends(get_current_user)):
#     user_id = current_user["id"]  # int

# === 数据库 ===
from shared.common.db_session import get_db
# async def api(db: Session = Depends(get_db)): ...

# === 分页 ===
from shared.common.pagination import paginate, PaginationParams

# === 全局异常处理（main.py 中注册）===
from shared.common.exception_handler import register_exception_handlers
# register_exception_handlers(app)  # 自动将 AppError 转为统一错误响应
```

## 2. 合规服务 (`compliance-service:8004`)

**已实现 API：**

| 接口 | 方法 | 说明 |
|------|------|------|
| `/api/v1/compliance/check` | POST | **核心接口**：三层审核（关键词→正则→LLM语义） |
| `/api/v1/compliance/rules` | GET/POST/PUT | 规则 CRUD |
| `/api/v1/compliance/rules/reload` | POST | 规则热更新 |
| `/api/v1/compliance/rules/test` | POST | 规则测试 |
| `/api/v1/compliance/blocks` | GET | 拦截记录 |
| `/api/v1/compliance/stats` | GET | 统计 |

**调用方式（A 和 C 需要）：**
```python
import httpx
async with httpx.AsyncClient() as client:
    resp = await client.post("http://gateway:8000/api/v1/compliance/check", json={
        "content": "待审核文本",
        "context": {"user_id": 1, "type": "user_input"}
    })
    result = resp.json()["data"]
    # → {"blocked": false, "violations": [], "risk_level": "none"}
```

## 3. 审计服务 (`audit-service:8005`)

**已实现 API：**

| 接口 | 方法 | 说明 |
|------|------|------|
| `/api/v1/audit/log` | POST | 写入审计日志 |
| `/api/v1/audit/logs` | GET | 高级搜索 |
| `/api/v1/audit/logs/{id}` | GET | 日志详情 |
| `/api/v1/audit/export` | POST | 导出 Excel 报告 |
| `/api/v1/audit/stats` | GET | 统计 |

**调用方式：**
```python
await client.post("http://gateway:8000/api/v1/audit/log", json={
    "service_name": "specialist-service",
    "user_id": 1, "action": "chat_response",
    "ai_involved": True, "ai_model": "qwen-max",
    "ai_prompt": "...", "ai_response": "...",
    "compliance_result": {...}, "request_id": "..."
})
```

## 4. API 网关 (`gateway:8000`)

**路由表：**

| 路径前缀 | → 后端服务 |
|---------|-----------|
| `/api/v1/specialists`, `/api/v1/conversations` | specialist-service:8001 |
| `/api/v1/knowledge` | knowledge-service:8003 |
| `/api/v1/visits` | visit-service:8002 |
| `/api/v1/hcps` | hcp-service:8006 |
| `/api/v1/compliance` | compliance-service:8004 |
| `/api/v1/audit` | audit-service:8005 |
| `/api/v1/auth` | specialist-service:8001 |

**中间件：** JWT 认证（白名单：`/health`, `/api/v1/auth/*`, `/docs`）+ 限流（每用户每分钟 60 次）

## 5. 数据库

10 张表已通过 `scripts/init_db.sql` 初始化（Docker PostgreSQL 中），含种子数据（管理员 admin、示例产品 ONC-001、4 条合规规则）。

## 6. 合规规则

`shared/compliance-rules/rules.yaml` 含 7 条规则（R001-R007），覆盖关键词、正则、LLM 语义三类。

---

## main.py 标准模板（A/B/C 都按这个写）

```python
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", ".."))

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from shared.common.exception_handler import register_exception_handlers
from app.config import settings

app = FastAPI(title="MedAgent - XXX服务", version="1.0.0")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_credentials=True, allow_methods=["*"], allow_headers=["*"])
register_exception_handlers(app)

from app.api.xxx import router
app.include_router(router)

@app.get("/health")
async def health():
    return {"status": "ok", "service": settings.SERVICE_NAME, "version": "1.0.0"}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=settings.SERVICE_PORT)
```

---

# A · 数字专员服务（specialist-service:8001）

> **核心引擎。每个数字专员 = 一个百炼多模态交互开发套件 App。**
> **前置依赖：** B 创建并配置好的百炼 App（含知识库）

## ✅ 已完成（B/C/E 必读）

specialist-service 已实现（commit `114907d`），B/C/E 可以直接联调。

**已实现：**
- `app/services/bailian_client.py` — 百炼多模态交互 **WebSocket** 客户端（Connect → Start → Listening → RequestToRespond → Stop，支持 dialog_id 续传）
- `app/services/qwen_client.py` — 通义千问直调（百炼不可用时的降级方案）
- `app/services/compliance_client.py` / `audit_client.py` — 调 D 的合规检查 + 审计日志（失败不阻塞业务）
- `app/core/answer_generator.py` — 完整流水线：合规预检 → 百炼生成 → 合规审核答案 → 审计日志 → 返回 `{answer, evidence_level, session_id, request_id, latency_ms, blocked}`
- `app/api/specialists.py` — 7 个接口：专员列表/详情、`chat`（核心）、会话历史、使用统计、反馈、收藏
- `app/main.py` — 标准模板（异常处理器 + CORS + JWT）
- `tests/eval_specialist.py` + `tests/eval_sets/oncology_v1.json` — 24 条评估用例（覆盖 R001-R007 全部规则），冒烟验证通过

**C 联调方式（生成准备包/拜访总结）：**
```bash
POST http://gateway:8000/api/v1/specialists/{id}/chat
{"question": "为张主任生成拜访准备包", "session_id": null}
→ {"code":0, "data":{"answer":"...", "blocked":false, ...}}
```

**已知限制（后续版本处理）：**
- `citations` 暂返回空数组（百炼未解析独立引用，后续从 RespondingContent.extra_info 解析）
- `feedback` / `favorite` 仅记录日志，未入库
- 数据层未建独立 repo 类（任务 3.4/3.5），API 直接内联 SQLAlchemy query

**待办（不影响 B/C/E 联调）：**
- 1.1-1.6 百炼控制台创建 App（每产品一个），App ID 写入 `digital_specialists.bailian_app_id`
- 7.2 真实评估：配好 App 后跑 `python tests/eval_specialist.py --app-id <你的App ID>`，目标通过率 ≥ 80%
- 7.3 与 D 联调合规+审计的端到端验证

## AI 指导摘要（喂给 AI）

```
你是 A，负责 specialist-service (端口 8001)。
项目是 MedAgent 药企数字员工系统。

架构：每个数字专员对应一个百炼多模态交互 App。
百炼 App 自带知识库、文档解析、向量检索、多轮对话、多模态理解。
你的服务是百炼 App 的业务编排层。

答案生成流水线：
  用户提问
  → compliance-service 合规预检 (D已实现)
  → 调百炼 App 对话接口（百炼内部完成知识检索+LLM生成）
  → compliance-service 合规审核答案 (D已实现)
  → audit-service 审计日志 (D已实现)
  → 返回 {answer, citations, evidence_level, ...}

你在百炼控制台需要创建的（每产品一个）：
  - 创建"多模态交互开发套件"应用
  - 应用名：如"肿瘤产品专员-小K"
  - 选模型：qwen-max
  - 配知识库：上传该产品的说明书、文献、指南
  - 配 System Prompt（参考 shared/prompts/oncology_specialist.yaml）
  - 记录下 App ID → 写入数据库 digital_specialists 表

已完工可参考的代码：
  - shared/common/  统一响应/认证/分页/数据库
  - services/compliance-service/  合规服务的完整实现（做参考）
  - services/specialist-service/app/  已有骨架（main.py/config.py/requirements.txt/Dockerfile）

你要调的外部服务（都已实现）：
  1. 合规检查: POST http://gateway:8000/api/v1/compliance/check
  2. 审计日志: POST http://gateway:8000/api/v1/audit/log
  3. 百炼多模态交互 WebSocket API（已测试通过）：
     wss://dashscope.aliyuncs.com/api-ws/v1/inference
     参考 services/specialist-service/app/services/bailian_client.py
```

## 任务清单

### 第 1 步：在百炼控制台创建数字专员 App

- [ ] 1.1 浏览器打开 https://bailian.console.aliyun.com/
- [ ] 1.2 左侧菜单 → "应用管理" → "创建应用" → 选"多模态交互开发套件"
- [ ] 1.3 填写：
  - 应用名称：如 `肿瘤产品专员-小K`（按产品命名，一个产品一个 App）
  - 模型：qwen-max
  - System Prompt：参考 `shared/prompts/oncology_specialist.yaml`
  - 知识库：关联该产品的知识库（由 B 创建和维护）
- [ ] 1.4 创建完成 → 记录 **App ID**
- [ ] 1.5 将 App ID 写入数据库 `digital_specialists` 表的 `bailian_app_id` 字段
- [ ] 1.6 在百炼控制台测试 App 对话效果

### 第 2 步：外部服务客户端

- [x] 2.1 写 `app/services/bailian_client.py`（已实现为 WebSocket 多模态交互客户端）
  ```python
  class BailianClient:
      def __init__(self):
          self.api_key = os.getenv("BAILIAN_API_KEY")
          self.base_url = "https://bailian.aliyuncs.com/v2"
      
      def chat(self, app_id: str, prompt: str, session_id: str = None, biz_params: dict = None) -> dict:
          """调百炼 App 对话接口"""
          url = f"{self.base_url}/app/{app_id}/completion"
          payload = {"input": {"prompt": prompt}, "parameters": {}, "debug": {}}
          if session_id:
              payload["input"]["session_id"] = session_id
          # ... 含超时(30s)、异常处理、百炼不可用时的降级方案
  ```
- [x] 2.2 写 `app/services/qwen_client.py`（通义千问直调，百炼不可用时的降级方案）
  - OpenAI 兼容接口：`base_url=https://dashscope.aliyuncs.com/compatible-mode/v1`
  - `chat(messages, model, temperature, max_tokens)` 和 `chat_stream()`
- [x] 2.3 写 `app/services/compliance_client.py`
  ```python
  async def check(content: str, context: dict) -> dict:
      async with httpx.AsyncClient() as client:
          resp = await client.post(
              "http://gateway:8000/api/v1/compliance/check",
              json={"content": content, "context": context}
          )
          return resp.json()["data"]
  ```
- [x] 2.4 写 `app/services/audit_client.py`（同理，调 `http://gateway:8000/api/v1/audit/log`）

### 第 3 步：数据层

- [x] 3.1 用 `shared/common/db_session.py` 的 `get_db`（不需要自己写）
- [x] 3.2 写 `app/models/specialist.py` → ORM 映射 `digital_specialists` 表（id, name, product_id, persona, knowledge_scope, compliance_level, bailian_app_id, prompt_version, status）
- [x] 3.3 写 `app/models/conversation.py` → ORM 映射 `conversations` 表（id, user_id, specialist_id, session_id, role, content, citations, compliance_result, tokens_used, latency_ms）
- [ ] 3.4 写 `app/db/repositories/specialist_repo.py`（list_all, get_by_id, create, update）— 未实现，API 直接内联 SQLAlchemy query
- [ ] 3.5 写 `app/db/repositories/conversation_repo.py`（save_message, get_session_history）— 未实现，API 直接内联 SQLAlchemy query

### 第 4 步：核心业务——答案生成器

- [x] 4.1 写 `app/core/answer_generator.py`：
  ```python
  class AnswerGenerator:
      def __init__(self):
          self.bailian = BailianClient()
          self.qwen = QwenClient()       # 降级备用
          self.compliance = ComplianceClient()
          self.audit = AuditClient()
      
      async def generate(self, question, specialist, user_id, session_id=None):
          request_id = str(uuid.uuid4())
          start = time.time()
          
          # Step 1: 合规预检（问题本身是否违规）
          check1 = await self.compliance.check(question, {"user_id": user_id, "type": "user_input"})
          if check1["blocked"]:
              return {"answer": "您的问题包含不合规内容，请调整后重试", "blocked": True, ...}
          
          # Step 2: 调百炼 App 生成答案（百炼内部完成知识检索+LLM）
          try:
              result = await self.bailian.chat(
                  app_id=specialist.bailian_app_id,
                  prompt=question,
                  session_id=session_id
              )
              answer = result.get("text", "")
              citations = result.get("docs", [])
          except BailianException:
              # 降级：直接调通义千问（不带知识库检索）
              answer = self._fallback_generate(question, specialist)
              citations = []
          
          # Step 3: 合规审核 AI 答案
          check2 = await self.compliance.check(answer, {"user_id": user_id, "type": "ai_output"})
          if check2["blocked"]:
              return {"answer": "该问题建议直接咨询医学顾问", "blocked": True, ...}
          
          # Step 4: 审计日志
          latency_ms = int((time.time() - start) * 1000)
          await self.audit.log(
              service_name="specialist-service", user_id=user_id,
              action="chat_response", ai_involved=True, ai_model="qwen-max",
              ai_prompt=question, ai_response=answer,
              compliance_result=check2, request_id=request_id
          )
          
          return {"answer": answer, "citations": citations, "evidence_level": self._extract_evidence_level(answer),
                  "session_id": session_id, "request_id": request_id, "latency_ms": latency_ms, "blocked": False}
  ```

### 第 5 步：API 路由

- [x] 5.1 `GET /api/v1/specialists` — 专员列表（返回 id, name, product_id, status）
- [x] 5.2 `GET /api/v1/specialists/{id}` — 专员详情
- [x] 5.3 `POST /api/v1/specialists/{id}/chat` — **核心接口**
  ```json
  Request:  {"question": "肺癌用药注意事项", "session_id": "可选"}
  Response: {"code":0, "data":{"answer":"...", "citations":[{"title":"...","url":"..."}], "evidence_level":"B", "session_id":"...", "latency_ms":1234, "blocked":false}}
  ```
- [x] 5.4 `GET /api/v1/conversations/{session_id}` — 会话历史
- [x] 5.5 `GET /api/v1/specialists/{id}/stats` — 使用统计
- [x] 5.6 `POST /api/v1/specialists/{id}/feedback` — 点赞/点踩（记录日志，未入库，见已知限制）
- [x] 5.7 `POST /api/v1/specialists/{id}/favorite` — 收藏/取消收藏（记录日志，未入库，见已知限制）
- [x] 5.8 每个路由加 `Depends(get_current_user)` + 全局异常处理

### 第 6 步：更新 main.py

- [x] 6.1 按标准模板更新 `app/main.py`：挂载路由 + 注册异常处理器 + CORS

### 第 7 步：测试

- [x] 7.1 写 `tests/eval_specialist.py` + `tests/eval_sets/oncology_v1.json`（24 条评估用例，冒烟验证通过）
- [ ] 7.2 评估目标：通过率 ≥ 80%（需百炼 App 配置完成后跑真实评估）
- [ ] 7.3 与 D 联调合规+审计 → 端到端验证（待真实评估一并验证）
- [ ] 7.4 与 E 联调移动端对话接口

---

# B · 知识库管理服务（knowledge-service:8003）

> **关键变化：B 不再自建文档解析/向量化/检索管道。百炼多模态 App 自带知识库，B 的角色是管理知识生命周期——文档上传、审核、版本管理、检索效果验证。**

## AI 指导摘要（喂给 AI）

```
你是 B，负责 knowledge-service (端口 8003)。
项目是 MedAgent 药企数字员工系统。

重要：不再自建文档处理流水线！
百炼多模态交互 App 自带知识库（文档上传→解析→向量化→检索），
你的服务是知识库管理门户，负责：
  1. 文档上传到 OSS + 同步到对应产品的百炼 App 知识库
  2. 文档审核流（上传→待审核→医学顾问审核→上线/驳回）
  3. 文档版本管理
  4. 检索效果测试（调用百炼 App 的 API 测试问答效果）
  5. 用户反馈收集

每个产品在百炼有一个 App，每个 App 有自己的知识库。
你的工作是把正确的文档推送到正确的 App 知识库。

已完工：
  - shared/ 全部共享工具
  - 合规服务、审计服务（参考代码风格）
  - services/knowledge-service/ 骨架（main.py/config.py/requirements.txt/Dockerfile）

阿里云服务：
  - OSS Bucket: medagent-files (oss-cn-hangzhou.aliyuncs.com) — 存原始文档
  - 百炼 API: https://bailian.aliyuncs.com/v2 — 管理 App 知识库
  - DashVector: 已开通（如果将来需要自建检索再用）
```

## 任务清单

### 第 1 步：在百炼控制台创建知识库

- [ ] 1.1 确认 A 创建了百炼 App（每产品一个）
- [ ] 1.2 进入百炼 App → "知识库" → 创建知识库 → 上传该产品的文档
  - 支持格式：PDF、Word、PPT、TXT
  - 百炼自动完成：解析、切分、向量化、索引
- [ ] 1.3 手动上传几篇测试文档（说明书、临床文献、指南各一篇），验证检索效果
- [ ] 1.4 记录知识库 ID 和 App ID 的对应关系

### 第 2 步：OSS 客户端

- [ ] 2.1 写 `app/services/oss_client.py`
  ```python
  class OSSClient:
      def __init__(self):
          self.bucket = oss2.Bucket(
              oss2.Auth(os.getenv("OSS_ACCESS_KEY_ID"), os.getenv("OSS_ACCESS_KEY_SECRET")),
              os.getenv("OSS_ENDPOINT"),
              os.getenv("OSS_BUCKET")
          )
      def upload(self, local_path: str, oss_path: str) -> str: ...
      def download(self, oss_path: str, local_path: str): ...
      def get_url(self, oss_path: str, expires: int = 3600) -> str: ...
  ```

### 第 3 步：数据层

- [ ] 3.1 写 `app/models/knowledge_document.py` → ORM 映射 `knowledge_documents` 表
  - 字段：id, title, doc_type, source, content(摘要), file_url(OSS地址), product_id, evidence_level, publish_date, version, status(draft/processing/ready/rejected), reviewer_id, review_date, tags(JSONB)
- [ ] 3.2 写 `app/db/repositories/knowledge_repo.py` — CRUD + 状态流转

### 第 4 步：核心业务

- [ ] 4.1 写 `app/core/document_manager.py`
  ```python
  class DocumentManager:
      def __init__(self):
          self.oss = OSSClient()
      
      async def upload_document(self, file, meta: dict, db: Session) -> int:
          """上传文档：存 OSS → 写 DB(status=draft) → 返回 doc_id"""
          # 1. 上传到 OSS
          oss_url = self.oss.upload(file, f"knowledge/{meta['product_id']}/{file.filename}")
          # 2. 写入 DB
          doc = KnowledgeDocument(title=meta["title"], doc_type=meta["doc_type"], ...)
          db.add(doc); db.commit()
          return doc.id
      
      async def submit_review(self, doc_id: int, db: Session):
          """提交审核：draft → pending"""
      
      async def approve(self, doc_id: int, reviewer_id: int, db: Session):
          """审核通过：pending → ready，触发同步到百炼知识库"""
          doc = db.query(KnowledgeDocument).filter_by(id=doc_id).first()
          doc.status = "ready"
          doc.reviewer_id = reviewer_id
          # TODO: 调百炼 API 将文档 URL 同步到对应 App 知识库
          db.commit()
      
      async def reject(self, doc_id: int, reviewer_id: int, db: Session):
          """驳回：pending → rejected"""
  ```

- [ ] 4.2 写 `app/services/bailian_knowledge_client.py` — 调百炼 API 管理知识库
  ```python
  class BailianKnowledgeClient:
      # 百炼知识库 API（具体接口以百炼文档为准）
      def add_document(self, app_id: str, file_url: str, doc_meta: dict): ...
      def delete_document(self, app_id: str, doc_id: str): ...
      def search(self, app_id: str, query: str, top_k: int = 10) -> list: ...
  ```

### 第 5 步：API 路由

- [ ] 5.1 `POST /api/v1/knowledge/upload` — 上传文档
  ```json
  Request (multipart): file + meta{"title":"XX说明书","doc_type":"product","product_id":1,"evidence_level":"A","publish_date":"2026-01-01"}
  Response: {"code":0, "data":{"doc_id":123}}
  ```
- [ ] 5.2 `GET /api/v1/knowledge/documents` — 文档列表（分页，按类型/状态/产品筛选）
- [ ] 5.3 `GET /api/v1/knowledge/documents/{id}` — 文档详情
- [ ] 5.4 `POST /api/v1/knowledge/documents/{id}/review` — 审核（通过/驳回）
- [ ] 5.5 `POST /api/v1/knowledge/search` — 检索测试（调百炼 API）
  ```json
  Request: {"query":"肺癌用药","product_id":1,"top_k":10}
  Response: {"code":0,"data":{"results":[{"title":"...","content":"...","evidence_level":"B","score":0.95}]}}
  ```
- [ ] 5.6 `POST /api/v1/knowledge/feedback` — 检索质量反馈
- [ ] 5.7 `GET /api/v1/knowledge/stats` — 统计（文档数/审核中/上线数）
- [ ] 5.8 全局异常处理 + JWT 认证

### 第 6 步：更新 main.py

- [ ] 6.1 按标准模板：挂载路由 + 异常处理器

### 第 7 步：准备测试数据

- [ ] 7.1 准备 3-5 篇模拟医药文档（说明书、III期文献、指南、法规各一）
- [ ] 7.2 通过 upload API 上传 → 审核通过 → 同步到百炼 App
- [ ] 7.3 通过 search API 测试检索效果

---

# C · 陪访助手 + 医生管理（visit-service:8002 + hcp-service:8006）

> **前置依赖：A 的数字专员对话接口（用于生成准备包）、D 的合规检查+审计日志接口**

## ✅ 已完成（A/D/E 必读）

C 的两个服务已全部实现（25 个测试全部通过），A/D/E 可以直接联调。

**hcp-service (`:8006`) — 医生档案与画像：**
- `app/models/hcp.py` — Hcp ORM（映射 hcps 表，to_dict 含所有字段）
- `app/db/repositories/hcp_repo.py` — CRUD + 分页搜索（支持 name/hospital/department/title/region/status/tag 全维度筛选）+ 标签增删（去重）+ 批量导入（逐行创建，单行失败不阻塞）
- `app/services/profile_generator.py` — 画像生成器：聚合互动历史 → 千问生成 JSON（学术画像/处方偏好/沟通建议/合规风险提示）；LLM 不可用时降级为基础数据聚合
- `app/services/excel_parser.py` — Excel 批量导入解析（openpyxl，中文表头→模型字段映射，影响力中→英转换）
- `app/services/audit_client.py` — 调 D 的审计日志（画像生成留痕）
- `app/db/repositories/visit_interaction_repo.py` — 互动历史只读查询（同库直读 visit_records，表不存在时降级为空列表）
- `app/api/hcps.py` — 9 个接口全部实现：列表(分页+筛选)/详情/画像(含AI降级)/互动历史/新增/编辑/批量导入Excel/添加标签/删除标签
- 11 个单元测试（Excel 解析 4 + 仓库逻辑 5 + 画像降级 2）

**visit-service (`:8002`) — 陪访助手全流程：**
- `app/services/tingwu_client.py` — 通义听悟真实客户端（SDK 延迟导入、create_task + get_result 轮询、容错解析）+ TingwuMockClient（文本模拟，开发调试/测试用）
- `app/services/specialist_client.py` / `compliance_client.py` / `audit_client.py` — 调 A/D 的三个客户端（60s 超时、fail-open/fail-silent 降级策略）
- `app/services/qwen_client.py` — 千问直调（异议识别语义分析，qwen-plus 默认）
- `app/core/objection_detector.py` — 异议识别器（两级：规则层 5 类正则 + 语义层千问分析兴趣点/情感；语义不可用自动降级为仅规则层）
- `app/models/visit_record.py` + `app/db/repositories/visit_repo.py` — 数据层（status 派生自 ai_summary 是否为空）
- `app/core/visit_manager.py` — 核心编排（770行）：
  - `prepare_visit()` — 获取医生画像+历史 → 调 A chat 生成准备包（推荐话题/红线提醒/开场白/跟进项），A 不可用时降级
  - `start_visit()` — 创建拜访记录 + 审计日志
  - `process_transcript()` — 听悟转写（或 text 直传）+ 合规实时检查(D) + 异议识别 + 应对话术建议（按异议类型匹配模板）
  - `end_visit()` — 调 A 生成结构化记录（摘要/关键点/兴趣/异议/情感/下次计划）→ AI 输出合规审核(D) → 审计日志；合规拦截时用模板话术替换
  - `follow_up()` — 调 A 生成跟进计划
- `app/api/visits.py` — 8 个接口全部实现：pre-visit/start/{id}/transcript/{id}/end/{id}/follow-up/列表/详情/编辑
- 14 个测试（异议识别 8 + 完整流程 6：准备包降级/开始/转写+违规检测/结束生成/拦截替换/跟进建议）

**C 不需要百炼 App** — 准备包/总结/跟进建议全部走 A 的 chat 接口，百炼由 A 内部消化。C 自己的 AI 能力（异议语义分析/画像生成）走千问直调（DASHSCOPE_API_KEY 全员通用）。

**已知限制（后续版本处理）：**
- 异议识别的应对话术为规则层模板，尚未引入产品级知识库定制
- 医生画像每次调用实时生成（无缓存），高频场景可加 Redis 缓存
- visit_manager 同库直读 hcps/digital_specialists 表（RO），不如走 API 解耦，但避免了循环依赖
- 通义听悟真实调用未集成测试（需可访问的录音 URL）
- 拜访中合规实时检查为后处理模式（转写完成后整段检查），非流式逐句检查

**待办（不影响 E 联调）：**
- 与 A 联调（需要 A 侧完成 1.1-1.6 百炼 App 创建）
- 与 D 联调合规审核+审计日志端到端验证（D 已完成，启动即联调）
- 通义听悟真实转写端到端验证（需 alibabacloud_tingwu20230930 SDK 和一端可访问的录音 URL）

## AI 指导摘要（喂给 AI）

```
你是 C，负责 visit-service (8002) 和 hcp-service (8006)。
项目是 MedAgent 药企数字员工系统。

visit-service 核心流程：
  拜访前：prepare_visit() → 获取医生画像+历史 → 调A的专员生成准备包
  拜访中：process_transcript() → 通义听悟ASR → 合规实时检查 → 异议识别
  拜访后：end_visit() → 调A的专员生成结构化记录 → 审计日志

hcp-service：医生档案CRUD、画像、标签、批量导入

你要调的 3 个外部服务（都已实现）：
  1. 合规检查: POST http://gateway:8000/api/v1/compliance/check
  2. 审计日志: POST http://gateway:8000/api/v1/audit/log
  3. 数字专员(A): POST http://gateway:8000/api/v1/specialists/{id}/chat
     （用于生成准备包、拜访总结、跟进建议等）

阿里云通义听悟：AppKey=<找组长获取 TINGWU_APP_KEY>, Token=<找组长获取 TINGWU_ACCESS_TOKEN>

已完工可参考：
  - shared/ 全部共享工具
  - compliance-service 和 audit-service 的完整实现（代码风格参考）
  - visit-service/ 和 hcp-service/ 的骨架
```

## 第一部分：陪访助手（visit-service:8002）

### 1. 通义听悟客户端

- [x] 1.1 写 `app/services/tingwu_client.py`（TingwuClient + TingwuMockClient）
- [x] 1.2 写 mock 版本（TingwuMockClient.transcribe 文本模拟）

### 2. 外部服务客户端

- [x] 2.1 写 `app/services/specialist_client.py`（调 A，60s 超时，A 不可用时降级）
- [x] 2.2 写 `app/services/compliance_client.py`（调 D，fail-open 安全放行）
- [x] 2.3 写 `app/services/audit_client.py`（调 D，fail-silent 不阻塞业务）

### 3. 核心业务

- [x] 3.1 写 `app/core/visit_manager.py`（已实现 5 方法：prepare / start / process_transcript / end_visit / follow_up）

### 4. 数据层

- [x] 4.1 写 `app/models/visit_record.py` → ORM 映射 `visit_records` 表（status 派生自 ai_summary）
- [x] 4.2 写 `app/db/repositories/visit_repo.py`（分页列表含日期/状态筛选）

### 5. API 路由（8 个）

- [x] 5.1 `POST /api/v1/visits/pre-visit` — 拜访前准备包
- [x] 5.2 `POST /api/v1/visits/start` — 开始拜访
- [x] 5.3 `POST /api/v1/visits/{id}/transcript` — 实时转写（audio_url 或 text 直传）
- [x] 5.4 `POST /api/v1/visits/{id}/end` — 结束拜访，生成记录
- [x] 5.5 `GET /api/v1/visits/{id}` — 详情
- [x] 5.6 `GET /api/v1/visits` — 列表（分页+user/hcp/product/status/日期筛选）
- [x] 5.7 `PUT /api/v1/visits/{id}` — 编辑
- [x] 5.8 `POST /api/v1/visits/{id}/follow-up` — 跟进建议

## 第二部分：医生管理（hcp-service:8006）

### 6. 数据层

- [x] 6.1 写 `app/models/hcp.py` → ORM 映射 `hcps` 表（15 字段 + to_dict）
- [x] 6.2 写 `app/db/repositories/hcp_repo.py`（全维度筛选 + 标签管理 + 批量导入）

### 7. 业务逻辑

- [x] 7.1 医生画像生成/更新（聚合互动历史 + 千问 → LLM 不可用时降级基础数据聚合）
- [x] 7.2 医生搜索（姓名/医院/科室/职称/区域/状态/标签 全维度筛选）
- [x] 7.3 标签管理（add_tags/remove_tags，去重，保留原标签）
- [x] 7.4 批量导入（Excel → openpyxl 解析 → 逐行创建，单行失败不阻塞）

### 8. API 路由（9 个）

- [x] 8.1 `GET /api/v1/hcps` — 列表（分页+name/hospital/department/title/region/status/tag 7 维筛选）
- [x] 8.2 `GET /api/v1/hcps/{id}` — 详情
- [x] 8.3 `GET /api/v1/hcps/{id}/profile` — 画像（AI 含降级 + 审计留痕）
- [x] 8.4 `GET /api/v1/hcps/{id}/interactions` — 互动历史（同库读 visit_records）
- [x] 8.5 `POST /api/v1/hcps` — 新增
- [x] 8.6 `PUT /api/v1/hcps/{id}` — 编辑（仅更新传入字段）
- [x] 8.7 `POST /api/v1/hcps/batch-import` — 批量导入（Excel，返回成功数+失败明细）
- [x] 8.8 `POST /api/v1/hcps/{id}/tags` — 添加标签（去重）
- [x] 8.9 `DELETE /api/v1/hcps/{id}/tags` — 删除标签

### 9. main.py + 测试

- [x] 9.1 两个服务均按标准模板更新 main.py（register_exception_handlers + 路由挂载 + CORS）
- [x] 9.2 测试：hcp 11 通过 + visit 14 通过（异议识别 8 + 完整流程 6），共 25 通过

---

# E · 移动端 + DevOps

> **前置依赖：A 和 C 的后端 API（可先用 mock 数据开发界面）**

## AI 指导摘要（喂给 AI）

```
你是 E，负责 React Native 移动端 + DevOps。
项目是 MedAgent 药企数字员工系统。

移动端 4 个 Tab：工作台 | 对话 | 医生 | 我的
页面要求参见 AI数字员工系统-完整方案.md 第 3.1 节。

已有脚手架：
  - mobile/package.json, tsconfig.json
  - mobile/src/App.tsx (4 Tab 导航已配置)
  - mobile/src/api/client.ts (API客户端已写好：Base URL + JWT + X-Request-ID + 错误处理)
  - mobile/src/screens/ 下 4 个占位页面 (Home/Specialists/HCPSearch/Profile)

后端 API 全部通过网关 (gateway:8000) 访问。
开发阶段可先用 mock 数据，等 A 和 C 接口就绪后再联调。

DevOps：
  - docker-compose.yml 已完成
  - .env.example 已完成
  - CI/CD 用阿里云云效
```

## 第一部分：移动端开发

### 1. 登录页
- [ ] 1.1 写 `src/screens/Login/LoginScreen.tsx`
  - 手机号输入（校验格式）+ 验证码（60s 倒计时）+ 登录按钮 + 协议勾选
  - 登录状态持久化（AsyncStorage）

### 2. 工作台（改进现有 HomeScreen）
- [ ] 2.1 今日进度环（X/Y）、拜访列表卡片（待开始/进行中/已完成 三态）、FAB 添加拜访

### 3. 数字专员模块
- [ ] 3.1 专员列表（改进现有 SpecialistListScreen）
- [ ] 3.2 对话页 `ChatScreen.tsx`：气泡（用户蓝/ AI 白）、引用来源卡片、证据等级、反馈/收藏/分享按钮、语音输入、多轮对话、键盘自适应

### 4. 拜访流程（3 个新页面）
- [ ] 4.1 `VisitPrepareScreen.tsx`：医生信息、推荐话题（可勾选）、红线提醒（红底）、开场白、"开始拜访"按钮
- [ ] 4.2 `VisitInProgressScreen.tsx`：录音状态+计时、实时转写（医/代分离）、异议弹出、话术卡片、红线拦截弹窗、"结束拜访"按钮
- [ ] 4.3 `VisitEndScreen.tsx`：AI 摘要、关键点、兴趣点、异议、情感判断、下次拜访推荐、跟进建议、"确认完成"

### 5. 医生模块
- [ ] 5.1 医生搜索（改进现有 HCPSearchScreen，加筛选+字母索引）
- [ ] 5.2 医生详情 `HCPDetailScreen.tsx`：基本信息+学术背景+处方偏好+标签+互动历史

### 6. 其他页面
- [ ] 6.1 学术内容 `ContentScreen.tsx`
- [ ] 6.2 我的（改进现有 ProfileScreen）
- [ ] 6.3 合规手册 `ComplianceScreen.tsx`

### 7. API 对接
- [ ] 7.1 在 `src/api/` 下补充 `auth.ts`, `specialist.ts`, `visit.ts`, `hcp.ts`, `compliance.ts`
- [ ] 7.2 所有请求用已有的 `apiClient.request<T>(method, path, data)` 封装

## 第二部分：DevOps

### 8. Docker
- [ ] 8.1 验证 `docker-compose up -d` 所有 7 个服务能启动
- [ ] 8.2 验证网关路由正确转发

### 9. CI/CD
- [ ] 9.1 阿里云云效配置流水线：lint → test → build image → push → deploy
- [ ] 9.2 分 dev/staging/prod 三套环境

### 10. 监控
- [ ] 10.1 阿里云 ARMS + SLS 日志采集 + 告警规则配置

---

# 依赖关系 & 开发顺序

```
              D (已完成 ✅)
        共享层 / 合规 / 审计 / 网关
              │
    ┌─────────┼─────────┐
    │         │         │
    ▼         ▼         ▼
    B         A✅       C✅
 (建知识库) (调百炼)  (调A+D)
    │         │         │
    └────┬────┘         │
         │              │
         ▼              ▼
         E (移动端，调 A + C)
```

**B 和 A 紧密协作：** B 在百炼建知识库 → A 在百炼建 App 关联知识库 → A 调 App 对话接口

**并行开发：** E 可以先用 mock 数据开发所有页面，不等任何人。

---

# 协作约定

## 1. 服务间调用走网关

```
A调合规:  POST http://gateway:8000/api/v1/compliance/check
A调审计:  POST http://gateway:8000/api/v1/audit/log
C调A:    POST http://gateway:8000/api/v1/specialists/{id}/chat
C调合规:  POST http://gateway:8000/api/v1/compliance/check
C调审计:  POST http://gateway:8000/api/v1/audit/log
```

## 2. 统一响应格式

```json
{"code": 0, "message": "success", "data": {}}
{"code": 4001, "message": "合规拦截", "data": {"rule_code": "R001"}}
```

用 `from shared.common.response import success, error` 构建。

## 3. 遇到阻塞先 mock，不等

---

# API Key 分配

## 全员通用（每个人都配）

```env
DASHSCOPE_API_KEY=<找组长获取 DASHSCOPE_API_KEY>
QWEN_MAX_MODEL=qwen-max
QWEN_PLUS_MODEL=qwen-plus
QWEN_TURBO_MODEL=qwen-turbo
QWEN_VL_MODEL=qwen-vl-max
DATABASE_URL=postgresql://medagent:medagent123@localhost:5432/medagent
REDIS_URL=redis://localhost:6379/0
JWT_SECRET=<找组长获取 JWT_SECRET>
JWT_EXPIRES_IN=7d
SPECIALIST_SERVICE_PORT=8001
VISIT_SERVICE_PORT=8002
KNOWLEDGE_SERVICE_PORT=8003
COMPLIANCE_SERVICE_PORT=8004
AUDIT_SERVICE_PORT=8005
HCP_SERVICE_PORT=8006
GATEWAY_PORT=8000
LOG_LEVEL=INFO
```

## A（数字专员）额外

```env
# 百炼多模态交互（WebSocket）— 注意和 DASHSCOPE_API_KEY 不同！
BAILIAN_API_KEY=<找组长获取 BAILIAN_API_KEY>
BAILIAN_WS_URL=wss://dashscope.aliyuncs.com/api-ws/v1/inference
BAILIAN_WORKSPACE_ID=<找组长获取 WORKSPACE_ID>
```

## B（知识库）额外

```env
# 百炼多模态交互（管理 App 知识库）
BAILIAN_API_KEY=<找组长获取 BAILIAN_API_KEY>
BAILIAN_WS_URL=wss://dashscope.aliyuncs.com/api-ws/v1/inference
BAILIAN_WORKSPACE_ID=<找组长获取 WORKSPACE_ID>
OSS_ACCESS_KEY_ID=<找组长获取 ACCESS_KEY_ID>
OSS_ACCESS_KEY_SECRET=<找组长获取 ACCESS_KEY_SECRET>
OSS_BUCKET=medagent-files
OSS_ENDPOINT=oss-cn-hangzhou.aliyuncs.com
ALIYUN_ACCESS_KEY_ID=<找组长获取 ACCESS_KEY_ID>
ALIYUN_ACCESS_KEY_SECRET=<找组长获取 ACCESS_KEY_SECRET>
ALIYUN_REGION=cn-hangzhou
# DashVector 已开通（备用）
DASHVECTOR_API_KEY=<找组长获取 DASHSCOPE_API_KEY>
DASHVECTOR_ENDPOINT=vrs-cn-mtn4w7txo0001w.dashvector.cn-hangzhou.aliyuncs.com
```

## C（陪访+医生）额外

```env
TINGWU_APP_KEY=<找组长获取 TINGWU_APP_KEY>
TINGWU_ACCESS_TOKEN=<找组长获取 TINGWU_ACCESS_TOKEN>
```

## E（移动端）额外

```env
# 无额外配置，用全员通用的即可
```

---

> **参考文档**：[AI数字员工系统-完整方案.md](./AI数字员工系统-完整方案.md)
> **已完工代码参考**：`shared/`、`services/compliance-service/`、`services/audit-service/`、`services/gateway/`
