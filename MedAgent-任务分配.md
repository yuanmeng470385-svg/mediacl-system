# MedAgent 数字员工系统 · 5人任务分配清单

> 版本：v2.0 · 2026-07-31
> 状态：D（共享层+合规+审计+网关）✅ 已完成，A/B/C/E 待开发

---

## 人员总览

| 代号 | 负责模块 | 端口 | 技术栈 | 状态 |
|------|---------|------|--------|------|
| D（组长） | 合规 + 审计 + 共享层 + 网关 | 8004/8005/8000 | Python FastAPI | ✅ 已完成 |
| A | 数字专员服务 (specialist-service) | 8001 | FastAPI + 百炼 + 通义千问 | 🔴 待开发 |
| B | 知识库服务 (knowledge-service) | 8003 | FastAPI + DashVector + 文档解析 | 🔴 待开发 |
| C | 陪访助手 + 医生管理 (visit + hcp) | 8002/8006 | FastAPI + 通义听悟 | 🔴 待开发 |
| E | 移动端 + DevOps | — | React Native + Docker + CI/CD | 🔴 待开发 |

---

# D 已完成的工作（A/B/C/E 必读）

以下模块已经实现并通过测试，可以直接使用。

## 共享层 (`shared/`)

**所有人 import 路径：**

```python
# 统一响应格式（重要！所有 API 都用这个返回）
from shared.common.response import success, error, AppError, ParamError, AuthError, BusinessError

# 用法1：成功响应
return success(data={"name": "张三"})
# → {"code": 0, "message": "success", "data": {"name": "张三"}}

# 用法2：分页响应
return success(paginate(items, total=100, page=1, page_size=20))

# 用法3：抛出业务异常（会被全局异常处理器自动转换为错误响应）
raise ParamError("question 不能为空")
# → {"code": 1000, "message": "question 不能为空", "data": null}

# JWT 认证（在路由上加 Depends 即可）
from shared.common.auth import get_current_user, create_token

@router.get("/api/v1/xxx")
async def my_api(current_user: dict = Depends(get_current_user)):
    user_id = current_user["id"]       # int
    username = current_user["username"] # str
    role = current_user["role"]         # str

# 数据库连接
from shared.common.db_session import get_db
from sqlalchemy.orm import Session

@router.get("/api/v1/xxx")
async def my_api(db: Session = Depends(get_db)):
    ...

# 分页
from shared.common.pagination import paginate, PaginationParams

# 全局异常处理
from shared.common.exception_handler import register_exception_handlers
# 在 main.py 中：register_exception_handlers(app)
```

**重要提醒：** 所有 API 必须走网关（端口 8000），不要直连其他服务。服务间调用用 `http://gateway:8000/api/v1/xxx`。

## 合规服务 (`compliance-service:8004`)

**已实现的 API：**

| 接口 | 用途 | 谁会调 |
|------|------|--------|
| `POST /api/v1/compliance/check` | 检查内容合规性 | A、C |
| `GET/POST/PUT/DELETE /api/v1/compliance/rules` | 规则 CRUD | — |
| `POST /api/v1/compliance/rules/reload` | 规则热更新 | — |
| `POST /api/v1/compliance/rules/test` | 规则测试 | — |
| `GET /api/v1/compliance/blocks` | 拦截记录 | — |
| `GET /api/v1/compliance/stats` | 合规统计 | — |

**调用示例（A 和 C 需要）：**

```python
import httpx

# 合规检查
async def check_compliance(content: str, user_id: int, check_type: str):
    async with httpx.AsyncClient() as client:
        resp = await client.post(
            "http://gateway:8000/api/v1/compliance/check",
            json={
                "content": content,
                "context": {"user_id": user_id, "type": check_type}
            }
        )
        return resp.json()["data"]
# 返回: {"blocked": false, "violations": [], "risk_level": "none"}
```

**7 条合规规则已内置：**
- R001 禁止承诺疗效（关键词）→ reject
- R002 禁止回扣暗示（正则）→ reject
- R003 禁止统方（语义LLM）→ reject
- R004 禁止超适应症推广（语义LLM）→ reject
- R005 禁止贬低竞品（语义LLM）→ warn
- R006 禁止泄露患者信息（语义LLM）→ reject
- R007 禁止讨论未公开数据（语义LLM）→ warn

## 审计服务 (`audit-service:8005`)

**已实现的 API：**

| 接口 | 用途 | 谁会调 |
|------|------|--------|
| `POST /api/v1/audit/log` | 写入审计日志 | A、C |
| `GET /api/v1/audit/logs` | 高级搜索 | — |
| `GET /api/v1/audit/logs/{id}` | 日志详情 | — |
| `POST /api/v1/audit/export` | 导出 Excel 报告 | — |
| `GET /api/v1/audit/stats` | 审计统计 | — |

**调用示例（A 和 C 需要）：**

```python
import httpx

async def write_audit(**kwargs):
    async with httpx.AsyncClient() as client:
        await client.post(
            "http://gateway:8000/api/v1/audit/log",
            json={
                "service_name": "specialist-service",  # 填自己的服务名
                "user_id": kwargs.get("user_id"),
                "action": kwargs.get("action"),
                "resource_type": kwargs.get("resource_type"),
                "resource_id": kwargs.get("resource_id"),
                "ai_involved": kwargs.get("ai_involved", False),
                "ai_model": kwargs.get("ai_model"),
                "ai_prompt": kwargs.get("ai_prompt"),    # 自动存 hash
                "ai_response": kwargs.get("ai_response"), # 自动存 hash
                "compliance_result": kwargs.get("compliance_result"),
                "request_id": kwargs.get("request_id"),
            }
        )
```

## 网关 (`gateway:8000`)

**路由表（所有请求走网关）：**

| 路径前缀 | 转发到 |
|---------|--------|
| `/api/v1/specialists`, `/api/v1/conversations` | specialist-service:8001 |
| `/api/v1/visits` | visit-service:8002 |
| `/api/v1/knowledge` | knowledge-service:8003 |
| `/api/v1/compliance` | compliance-service:8004 |
| `/api/v1/audit` | audit-service:8005 |
| `/api/v1/hcps` | hcp-service:8006 |
| `/api/v1/auth` | specialist-service:8001 |

**中间件：** JWT 认证（白名单：`/health`, `/api/v1/auth/*`, `/docs`）+ 限流（每用户每分钟 60 次）

## 数据库

**10 张表已创建（Docker PostgreSQL 中）：**
`users`, `products`, `digital_specialists`, `hcps`, `visit_records`, `conversations`, `knowledge_documents`, `audit_logs`, `compliance_rules`, `compliance_blocks`

**种子数据：** 管理员账号 `admin`、示例产品 `ONC-001`、4 条初始合规规则

---

# 环境准备（全员公共）

> **状态：✅ 已完成，每人 clone 后即可开始**

1. `git clone https://codeup.aliyun.com/6a6c3e94e69c408bf87d8b1a/mediaclsystem.git`
2. `cp .env.example .env`（填入阿里云 AK、百炼 Key 等，找组长要）
3. 安装 Docker Desktop 并启动
4. `docker compose up -d postgres redis`（数据库 10 张表自动初始化）
5. 自己的服务目录下 `pip install -r requirements.txt`
6. `python -m uvicorn app.main:app --host 127.0.0.1 --port 8xxx` 启动验证
7. 浏览器访问 `http://127.0.0.1:8xxx/health`，看到 `{"status":"ok"}` 即成功

---

# A · 数字专员服务（specialist-service:8001）

> 核心引擎。所有对 AI 的调用都从这里走。
> **前置依赖：B的知识检索接口、D的合规检查和审计日志接口**

## AI 指导摘要（喂给 AI 用）

```
你是 A，负责 specialist-service (端口 8001)。
项目是药企数字员工系统 MedAgent。

你的服务是核心引擎，所有 AI 问答从这里走。
答案生成流水线：知识检索 → 合规预检 → LLM生成答案 → 合规审核答案 → 审计日志。

已完工并有代码可参考：
- shared/common/  统一响应/认证/分页/数据库连接 用 from shared.common.xxx import
- shared/models/  ORM 模型
- 路由骨架在 services/specialist-service/app/main.py（已写好）
- 配置文件在 services/specialist-service/app/config.py（已写好）

你要调的 3 个外部服务（都已部署）：
1. 知识检索: POST http://gateway:8000/api/v1/knowledge/search
   入参 {query, product_id?, top_k?}
   出参 {results: [{title, content, evidence_level, score}]}

2. 合规检查: POST http://gateway:8000/api/v1/compliance/check
   入参 {content, context: {user_id, type}}
   出参 {blocked, violations: [{rule_code, rule_name, severity, action, matched_text}], risk_level}

3. 审计日志: POST http://gateway:8000/api/v1/audit/log
   入参 {service_name, user_id, action, resource_type, resource_id, ...}

所有 API 返回统一格式: {code: 0, message: "success", data: {...}}
用 shared.common.response 的 success() 和 error() 函数返回。
JWT 认证: from shared.common.auth import get_current_user
```

## 任务清单

### 1. 外部服务客户端（第 1-2 天）

- [ ] 1.1 写 `app/services/bailian_client.py`（百炼 App 对话，参考完整方案 8.1.2）
  - `chat(app_id, prompt, session_id, biz_params)` → Dict
  - 超时 30s，含异常处理
- [ ] 1.2 写 `app/services/qwen_client.py`（通义千问 OpenAI 兼容，参考完整方案 8.1.3）
  - `chat(messages, model, temperature, max_tokens)` → Dict
  - `chat_stream(messages, model)` → Generator
  - model 默认 "qwen-max"，从环境变量 QWEN_MAX_MODEL 读取
- [ ] 1.3 写 `app/services/knowledge_client.py`（调 B 的知识检索）
  - `search(query, product_id, top_k)` → List[Dict]
  - 地址：`http://gateway:8000/api/v1/knowledge/search`
- [ ] 1.4 写 `app/services/compliance_client.py`（调 D 的合规检查）
  - `check(content, context)` → Dict
  - 地址：`http://gateway:8000/api/v1/compliance/check`
- [ ] 1.5 写 `app/services/audit_client.py`（调 D 的审计日志）
  - `log(**kwargs)` → Dict
  - 地址：`http://gateway:8000/api/v1/audit/log`
- [ ] 1.6 写 `app/services/__init__.py`，每个 client 用 httpx.AsyncClient

### 2. 数据层（第 2 天）

- [ ] 2.1 写 `app/db/session.py`（直接用 `from shared.common.db_session import get_db`）
- [ ] 2.2 写 `app/models/specialist.py` — ORM，映射 `digital_specialists` 表
  - 字段：id, name, product_id, persona(JSONB), knowledge_scope(JSONB), compliance_level, bailian_app_id, prompt_version, status
- [ ] 2.3 写 `app/models/conversation.py` — ORM，映射 `conversations` 表
  - 字段：id, user_id, specialist_id, session_id, role, content, citations(JSONB), compliance_result(JSONB), tokens_used, latency_ms
- [ ] 2.4 写 `app/db/repositories/specialist_repo.py` — CRUD
- [ ] 2.5 写 `app/db/repositories/conversation_repo.py` — 增删查

### 3. 核心业务逻辑（第 3-5 天）

- [ ] 3.1 写 `app/core/answer_generator.py`（参考完整方案 8.1.4）：
  ```
  generate(question, specialist, user_id, session_id) 主流程：
    step 1: knowledge_client.search(query, product_id, top_k=10) → 检索知识
    step 2: compliance_client.check(question, context) → 问题合规预检
            如果 blocked → 直接返回 "您的问题不合规"
    step 3: bailian_client.chat(app_id, prompt, session_id, biz_params) → LLM生成答案
            如果百炼失败 → 降级 _fallback_generate() 用通义千问
    step 4: compliance_client.check(answer, context) → 审核AI答案
            如果 blocked → 返回 "建议咨询医学顾问"
    step 5: audit_client.log(...) → 记录审计日志
    step 6: _extract_evidence_level(answer) → 提取证据等级
    return {answer, citations, evidence_level, blocked, violations, latency_ms}
  ```
- [ ] 3.2 写 `_fallback_generate()` — 百炼不可用时，用通义千问 + 检索结果拼 prompt
- [ ] 3.3 写 `_extract_evidence_level()` — 正则匹配【证据等级】

### 4. API 路由（第 5-6 天）

- [ ] 4.1 `GET /api/v1/specialists` — 专员列表
- [ ] 4.2 `GET /api/v1/specialists/{id}` — 专员详情
- [ ] 4.3 `POST /api/v1/specialists/{id}/chat` — 核心接口
  ```json
  Request: {"question": "...", "session_id": "..."}
  Response: {"code":0, "data":{"answer":"...", "citations":[...], "evidence_level":"B", "blocked":false, "latency_ms":1234}}
  ```
- [ ] 4.4 `GET /api/v1/conversations/{session_id}` — 会话历史
- [ ] 4.5 `GET /api/v1/specialists/{id}/stats` — 使用统计
- [ ] 4.6 `POST /api/v1/specialists/{id}/feedback` — 点赞/点踩
- [ ] 4.7 `POST /api/v1/specialists/{id}/favorite` — 收藏
- [ ] 4.8 每个路由加 `Depends(get_current_user)` 认证，加 `from shared.common.exception_handler import register_exception_handlers` 注册全局异常处理

### 5. 话术模板（第 6 天）

- [ ] 5.1 查看 `shared/prompts/oncology_specialist.yaml`（已写好模板）
- [ ] 5.2 写模板加载器：启动时读取 YAML，注入 system prompt 到百炼/通义千问

### 6. main.py 更新

- [ ] 6.1 在 `app/main.py` 中挂载路由、注册异常处理器（参考 compliance-service 的 main.py 写法）
- [ ] 6.2 `uvicorn app.main:app --port 8001` 能启动并通过 health 检查

### 7. 测试（第 7 天）

- [ ] 7.1 写 `tests/eval_specialist.py`（参考完整方案 9.4）
- [ ] 7.2 准备 ≥20 条评估用例
- [ ] 7.3 与 B 联调知识检索、与 D 联调合规+审计

---

# B · 知识库服务（knowledge-service:8003）

> AI 能力底座。所有 AI 回答的知识来源。
> **前置依赖：D的审计日志接口、阿里云 OSS/DashVector/通义千问 API Key**

## AI 指导摘要

```
你是 B，负责 knowledge-service (端口 8003)。
项目是药企数字员工系统 MedAgent。

你的服务是 AI 能力底座，提供文档上传→解析→向量化→检索的完整流水线。

已完工并有代码可参考：
- shared/common/  统一响应/认证/分页/数据库连接
- shared/models/  Product、User、AuditLog ORM
- 路由骨架在 services/knowledge-service/app/main.py

你要调的外部服务：
1. 审计日志: POST http://gateway:8000/api/v1/audit/log

阿里云服务（需要 Key）：
- OSS: 文件存储，用 oss2 SDK
- DashVector: 向量检索，用 dashvector SDK
- 通义千问 Embedding: text-embedding-v3，用 dashscope SDK

核心检索接口要被 A 和 C 调用：
POST /api/v1/knowledge/search
入参 {query, product_id?, doc_type?, top_k?}
出参 {results: [{title, content, evidence_level, score}]}
```

## 任务清单

### 1. OSS 客户端（第 1 天）

- [ ] 1.1 写 `app/services/oss_client.py`
  - `upload_local_file(local_path)` → 上传到 OSS，返回 URL
  - `download_to_local(url, local_path)` → 下载文件
  - 环境变量：OSS_ACCESS_KEY_ID, OSS_ACCESS_KEY_SECRET, OSS_BUCKET, OSS_ENDPOINT

### 2. 文档处理流水线（第 2-4 天）

- [ ] 2.1 写 `app/services/document_processor.py`（参考完整方案 9.1）：
  - `_parse_pdf(path)` — pypdf
  - `_parse_docx(path)` — python-docx
  - `_parse_ppt(path)` — python-pptx
  - `_parse_txt(path)` — 直接读
  - `_split(content, chunk_size=512)` — 按段落切分
  - `_embed(text)` — 调 text-embedding-v3 向量化
  - `process_document(file_url, doc_meta)` → doc_id — 主流程串联

### 3. DashVector 客户端（第 3 天）

- [ ] 3.1 写 `app/services/dashvector_client.py`
  - `upsert(collection, doc_id, vector, fields)` — 插入向量
  - `query(collection, vector, topk, filter)` — 向量检索
  - `delete(collection, doc_id)` — 删除向量

### 4. 知识检索（第 4-5 天）

- [ ] 4.1 写 `app/services/knowledge_retriever.py`（参考完整方案 9.2）
  - 查询文本向量化
  - DashVector 检索 + 关键词重排（向量0.7 + 关键词0.3）
  - 支持 filter：product_id, doc_type, evidence_level

### 5. 数据层（第 3 天）

- [ ] 5.1 写 `app/models/knowledge_document.py` — ORM，映射 `knowledge_documents` 表
- [ ] 5.2 写 `app/db/repositories/knowledge_repo.py`

### 6. API 路由（第 5-6 天）

- [ ] 6.1 `POST /api/v1/knowledge/search` — 核心接口（给 A 和 C 用）
  ```json
  Request: {"query":"肺癌用药注意事项","product_id":1,"top_k":10}
  Response: {"code":0,"data":{"results":[{"title":"...","content":"...","evidence_level":"B","score":0.95}]}}
  ```
- [ ] 6.2 `POST /api/v1/knowledge/upload` — 上传文档（接收文件 + 元信息，异步处理）
- [ ] 6.3 `GET /api/v1/knowledge/documents` — 文档列表（分页、筛选）
- [ ] 6.4 `GET /api/v1/knowledge/documents/{id}` — 文档详情
- [ ] 6.5 `POST /api/v1/knowledge/documents/{id}/review` — 审核文档
- [ ] 6.6 `POST /api/v1/knowledge/feedback` — 检索质量反馈
- [ ] 6.7 `GET /api/v1/knowledge/stats` — 统计
- [ ] 6.8 全局异常处理 + JWT 认证

### 7. 知识库构建脚本（第 6 天）

- [ ] 7.1 写 `scripts/build_knowledge_base.py`（参考完整方案 12.2）
  - 扫描 `knowledge-base/{product}/` 目录
  - 自动推断文档类型和证据等级
  - 批量处理入库

### 8. main.py 更新

- [ ] 8.1 挂载路由、注册异常处理器

### 9. 测试（第 7 天）

- [ ] 9.1 PDF解析、切分、向量化单元测试
- [ ] 9.2 上传→处理→检索全流程集成测试
- [ ] 9.3 与 A 联调知识检索接口

---

# C · 陪访助手 + 医生管理（visit-service:8002 + hcp-service:8006）

> 代表日常使用最频繁的两个模块，共两个服务。
> **前置依赖：D的合规检查+审计日志接口、A的数字专员对话接口（用于生成准备包等）**

## AI 指导摘要

```
你是 C，负责 visit-service (8002) 和 hcp-service (8006)。
项目是药企数字员工系统 MedAgent。

visit-service: 拜访前准备包 → 拜访中实时辅助（ASR转写+合规+异议识别） → 拜访后自动生成记录
hcp-service: 医生档案管理、画像生成、批量导入

已完工并有代码可参考：
- shared/common/  统一响应/认证/分页/数据库连接
- shared/models/  User 模型
- 路由骨架已写好

你要调的 3 个外部服务：
1. 合规检查: POST http://gateway:8000/api/v1/compliance/check
  {content, context: {user_id, type: "live_conversation"}}
  → {blocked, violations, risk_level}

2. 审计日志: POST http://gateway:8000/api/v1/audit/log

3. 数字专员（A）: POST http://gateway:8000/api/v1/specialists/{id}/chat
  用于生成准备包的推荐话题、开场白、红线提醒等

通义听悟: 阿里云 ASR，创建实时转写任务 → 获取转写结果（含说话人分离），延迟 < 2s
```

## 任务清单

### 第一部分：陪访助手（visit-service:8002）

### 1. 通义听悟客户端（第 1-2 天）

- [ ] 1.1 写 `app/services/tingwu_client.py`
  - `create_task(audio_url)` → task_id
  - `get_result(task_id)` → 转写文本 + 说话人分离
  - 环境变量：TINGWU_APP_KEY, TINGWU_ACCESS_TOKEN
- [ ] 1.2 写 mock 版本（用文本模拟，不需要真实音频时开发用）

### 2. 外部服务客户端（第 2 天）

- [ ] 2.1 写 `app/services/specialist_client.py`（调 A 的对话接口）
- [ ] 2.2 写 `app/services/compliance_client.py`（调 D 的合规检查，参考 A 任务里的写法）
- [ ] 2.3 写 `app/services/audit_client.py`（调 D 的审计日志，参考 A 任务里的写法）

### 3. 核心业务逻辑（第 3-5 天）

- [ ] 3.1 写 `app/core/visit_manager.py`（参考完整方案 8.2）：
  **`prepare_visit(hcp_id, user_id, product_id)`：**
  - 获取医生画像
  - 获取最近 3 次互动历史
  - 调 A 的 specialist 对话生成：3-5 个推荐话题、1-2 条红线提醒、1 段开场白、上次跟进事项

  **`start_visit(hcp_id, user_id, product_id)`：** 创建拜访记录（状态 in_progress）

  **`process_transcript(visit_id, audio_url)`：**
  - 通义听悟转写
  - 合规实时检查
  - 异议识别（正则 + LLM）
  - 话术建议生成

  **`end_visit(visit_id, full_transcript)`：**
  - 调 AI 生成结构化记录：摘要(≤100字)、关键点、兴趣点、异议、情感判断、下次拜访计划、跟进建议
  - 自动生成后续任务
  - 记录审计日志

- [ ] 3.2 写 `_detect_objections()` — 正则匹配异议：价格/疗效/安全性/竞品

### 4. 数据层（第 3 天）

- [ ] 4.1 写 `app/models/visit_record.py` — ORM，映射 `visit_records` 表
- [ ] 4.2 写 `app/db/repositories/visit_repo.py`

### 5. API 路由（第 5-6 天）

- [ ] 5.1 `POST /api/v1/visits/pre-visit` — 拜访前准备包
- [ ] 5.2 `POST /api/v1/visits/start` — 开始拜访
- [ ] 5.3 `POST /api/v1/visits/{id}/transcript` — 上传转写
- [ ] 5.4 `POST /api/v1/visits/{id}/end` — 结束拜访
- [ ] 5.5 `GET /api/v1/visits/{id}` — 详情
- [ ] 5.6 `GET /api/v1/visits` — 列表
- [ ] 5.7 `PUT /api/v1/visits/{id}` — 编辑
- [ ] 5.8 `POST /api/v1/visits/{id}/follow-up` — 跟进建议
- [ ] 5.9 全局异常处理 + JWT 认证

### 第二部分：医生管理（hcp-service:8006）

### 6. 数据层（第 1-2 天）

- [ ] 6.1 写 `app/models/hcp.py` — ORM，映射 `hcps` 表
- [ ] 6.2 写 `app/db/repositories/hcp_repo.py`

### 7. 业务逻辑（第 2-3 天）

- [ ] 7.1 医生画像生成/更新（聚合互动历史 + AI）
- [ ] 7.2 医生搜索（姓名/医院/科室/标签）
- [ ] 7.3 标签管理
- [ ] 7.4 批量导入（Excel/CSV → openpyxl 解析）

### 8. API 路由（第 3-4 天）

- [ ] 8.1 `GET /api/v1/hcps` — 列表（分页+筛选）
- [ ] 8.2 `GET /api/v1/hcps/{id}` — 详情
- [ ] 8.3 `GET /api/v1/hcps/{id}/profile` — 画像
- [ ] 8.4 `GET /api/v1/hcps/{id}/interactions` — 互动历史
- [ ] 8.5 `POST /api/v1/hcps` — 新增
- [ ] 8.6 `PUT /api/v1/hcps/{id}` — 编辑
- [ ] 8.7 `POST /api/v1/hcps/batch-import` — 批量导入
- [ ] 8.8 `POST/DELETE /api/v1/hcps/{id}/tags` — 标签管理

### 9. main.py 更新

- [ ] 9.1 两个服务的 main.py 都挂载路由、注册异常处理器

### 10. 测试（第 5-6 天）

- [ ] 10.1 完整拜访流程集成测试（准备→开始→转写→结束）
- [ ] 10.2 与 A 联调、与 D 联调、与 E 联调

---

# E · 移动端 + DevOps

> 代表每天打开的那个 App + 整个系统的部署运维。
> **前置依赖：A/C 的后端 API（可以先用 mock 数据开发界面）**

## AI 指导摘要

```
你是 E，负责 React Native 移动端 (mobile/) 和 DevOps。
项目是药企数字员工系统 MedAgent。

移动端 4 个 Tab：工作台 | 对话 | 医生 | 我的
页面要求参考完整方案文档第 3.1 节。

项目已有脚手架：
- mobile/package.json, tsconfig.json 已写好
- mobile/src/App.tsx 4 Tab 导航已配置
- mobile/src/api/client.ts API 客户端已写好（Base URL + JWT + X-Request-ID）
- mobile/src/screens/ 下有 Home/Specialists/HCPSearch/Profile 四个占位页面

后端 API 全部通过网关 (gateway:8000) 访问。
开发阶段可以先用 mock 数据，等 A 和 C 接口就绪后再联调。

DevOps：docker-compose.yml 已写好，CI/CD 用阿里云云效。
```

## 任务清单

### 第一部分：移动端

### 1. 页面开发

- [ ] 1.1 **登录页** `src/screens/Login/LoginScreen.tsx`
  - 手机号输入、验证码（60s倒计时）、登录按钮、协议勾选
- [ ] 1.2 **工作台** `src/screens/Home/HomeScreen.tsx`（改进现有占位页）
  - 今日进度环、拜访列表卡片（待开始/进行中/已完成三种状态）、FAB 添加拜访、快捷功能区
- [ ] 1.3 **专员对话** `src/screens/Chat/ChatScreen.tsx`
  - 对话气泡（用户蓝色右对齐、AI白色左对齐）
  - AI消息含：引用来源卡片、证据等级标注
  - 反馈按钮（点赞/点踩）、收藏、分享
  - 输入区（文本+语音+发送）、多轮对话、键盘自适应
- [ ] 1.4 **专员列表** `src/screens/Specialists/SpecialistListScreen.tsx`（改进现有）
- [ ] 1.5 **拜访前准备** `src/screens/VisitPrepare/VisitPrepareScreen.tsx`
  - 医生信息、推荐话题（可勾选）、红线提醒（红色背景）、开场白建议、"开始拜访"按钮
- [ ] 1.6 **拜访中** `src/screens/VisitInProgress/VisitInProgressScreen.tsx`
  - 录音状态栏+计时、实时转写区（医/代分离）、异议识别弹窗、话术建议卡片、红线拦截弹窗、"结束拜访"按钮
- [ ] 1.7 **拜访后** `src/screens/VisitEnd/VisitEndScreen.tsx`
  - AI摘要、关键点、兴趣点、异议、情感判断、下次拜访推荐、跟进建议、"确认完成"按钮
- [ ] 1.8 **医生搜索** `src/screens/HCPSearch/HCPSearchScreen.tsx`（改进现有）
- [ ] 1.9 **医生详情** `src/screens/HCPDetail/HCPDetailScreen.tsx`
- [ ] 1.10 **学术内容** `src/screens/Content/ContentScreen.tsx`
- [ ] 1.11 **我的** `src/screens/Profile/ProfileScreen.tsx`（改进现有）
- [ ] 1.12 **合规手册** `src/screens/Compliance/ComplianceScreen.tsx`

### 2. API 对接

- [ ] 2.1 在 `src/api/` 下补充 `auth.ts`, `specialist.ts`, `visit.ts`, `hcp.ts`, `compliance.ts`, `content.ts`
- [ ] 2.2 参考已有的 `src/api/client.ts`，用 `apiClient.request<T>(method, path, data)` 封装所有接口调用

### 3. 状态管理

- [ ] 3.1 Token 持久化（已有 AsyncStorage）
- [ ] 3.2 登录状态管理

### 第二部分：DevOps

### 4. Docker（第 1-2 天）

- [ ] 4.1 `docker-compose.yml` 已写好，验证所有服务能启动
- [ ] 4.2 `.env.example` 已写好

### 5. CI/CD（第 8-9 天）

- [ ] 5.1 在阿里云云效配置流水线：测试 → 构建镜像 → 推送 → 部署
- [ ] 5.2 分 dev/staging/prod 三套环境

### 6. 监控告警（第 9-10 天）

- [ ] 6.1 配置阿里云 ARMS + 告警规则
- [ ] 6.2 配置 SLS 日志采集

---

# 依赖关系速查

```
                    D (已完成 ✅)
                    │
          ┌─────────┼─────────┐
          │         │         │
    共享层+合规+审计+网关      │
          │         │         │
          ▼         ▼         ▼
          A         C         B
     (调B和D)   (调A和D)   (调D)
          │         │         │
          └─────────┼─────────┘
                    │
                    ▼
                    E
            (调A和C的API)
```

B 的知识检索接口最先被需要 → B 优先开发检索接口
A 依赖 B 的检索 + D 的合规/审计
C 依赖 A 的对话 + D 的合规/审计
E 依赖 A 和 C 的 API（但可先用 mock 开发界面）

---

# 协作约定

## 1. 服务间调用走网关

```
A调B: POST http://gateway:8000/api/v1/knowledge/search
A调D: POST http://gateway:8000/api/v1/compliance/check
C调A: POST http://gateway:8000/api/v1/specialists/{id}/chat
C调D: POST http://gateway:8000/api/v1/compliance/check
所有人调D: POST http://gateway:8000/api/v1/audit/log
```

## 2. 统一响应格式

```json
{"code": 0, "message": "success", "data": {}}
{"code": 4001, "message": "合规拦截", "data": {"rule_code": "R001"}}
```

用 `from shared.common.response import success, error` 构建。

## 3. main.py 模板（每个服务都一样）

```python
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", ".."))

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from shared.common.exception_handler import register_exception_handlers
from app.config import settings

app = FastAPI(title="...", version="1.0.0")
app.add_middleware(CORSMiddleware, allow_origins=["*"], ...)
register_exception_handlers(app)

# 挂载路由
from app.api.xxx import router
app.include_router(router)

@app.get("/health")
async def health():
    return {"status": "ok", "service": settings.SERVICE_NAME}
```

## 4. 遇到阻塞

- 先写 mock 数据继续开发
- 日会上抛出来
- 优先 unblock 上游依赖

---

> **参考文档**：[AI数字员工系统-完整方案.md](./AI数字员工系统-完整方案.md)
> **已完工代码**：查看 `shared/`, `services/compliance-service/`, `services/audit-service/`, `services/gateway/` 作为参考
