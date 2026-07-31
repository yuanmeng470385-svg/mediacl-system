# MedAgent 数字员工系统 · 5人任务分配清单

> 版本：v1.0 · 2026-07-31
> 基于《AI数字员工系统-完整方案 v4.0》

---

## 人员总览

| 代号 | 负责模块 | 端口 | 技术栈 |
|------|---------|------|--------|
| A | 数字专员服务 (specialist-service) | 8001 | Python FastAPI + 百炼 + 通义千问 |
| B | 知识库服务 (knowledge-service) | 8003 | Python FastAPI + DashVector + 文档解析 |
| C | 陪访助手 + 医生管理 (visit + hcp) | 8002/8006 | Python FastAPI + 通义听悟 |
| D | 合规 + 审计 + 共享层 + 网关 | 8004/8005/8000 | Python FastAPI + 规则引擎 |
| E | 移动端 + DevOps | — | React Native + Docker + CI/CD |

---

> **公共起步任务（全员第 1 天）**
>
> - [ ] 1. 克隆仓库，搭建本地环境（Python 3.11+ / Node.js 18+ / Docker）
> - [ ] 2. 配置 `.env` 文件（阿里云 AK、百炼 Key、数据库连接等）
> - [ ] 3. `docker-compose up -d` 跑通 PostgreSQL + Redis
> - [ ] 4. 跑通健康检查 `curl http://localhost:8001/health`
> - [ ] 5. 跑通通义千问 API 测试脚本

---

# A · 数字专员服务（specialist-service）

> 核心引擎。所有对 AI 的调用都从这里走。

## 1. 项目骨架（第 1 天）

- [ ] 1.1 创建 `services/specialist-service/` 目录结构（按文档 8.1.1）
- [ ] 1.2 写 `app/main.py` FastAPI 入口（健康检查、CORS）
- [ ] 1.3 写 `app/config.py`（读环境变量）
- [ ] 1.4 写 `requirements.txt`（fastapi, uvicorn, openai, requests, pydantic 等）
- [ ] 1.5 写 `Dockerfile`
- [ ] 1.6 确保 `docker-compose up specialist-service` 能启动

## 2. 外部服务客户端（第 2-3 天）

- [ ] 2.1 写 `app/services/bailian_client.py`（百炼 App 对话接口，含超时和异常处理）
- [ ] 2.2 写 `app/services/qwen_client.py`（通义千问 OpenAI 兼容接口，含流式）
- [ ] 2.3 写 `app/services/knowledge_client.py`（调 B 的知识检索接口）
- [ ] 2.4 写 `app/services/compliance_client.py`（调 D 的合规检查接口）
- [ ] 2.5 写 `app/services/audit_client.py`（调 D 的审计日志接口）
- [ ] 2.6 每个 client 写一个测试脚本验证连通性

## 3. 核心业务逻辑（第 4-6 天）

- [ ] 3.1 写 `app/core/answer_generator.py`（答案生成流水线）：
  - 步骤 1：调 knowledge_client 检索知识
  - 步骤 2：调 compliance_client 做问题合规预检
  - 步骤 3：调百炼生成答案，失败则降级到通义千问
  - 步骤 4：调 compliance_client 审核 AI 答案
  - 步骤 5：调 audit_client 记录审计日志
  - 步骤 6：提取证据等级
- [ ] 3.2 写降级方案 `_fallback_generate()`：百炼不可用时用通义千问 + 检索结果直接拼 prompt
- [ ] 3.3 写证据等级提取 `_extract_evidence_level()`
- [ ] 3.4 单元测试：正常流程、合规拦截、百炼超时降级

## 4. 数据层（第 5-6 天）

- [ ] 4.1 写 `app/db/session.py`（数据库连接、依赖注入）
- [ ] 4.2 写 `app/models/specialist.py`（专员 ORM 模型）
- [ ] 4.3 写 `app/models/conversation.py`（对话记录 ORM 模型）
- [ ] 4.4 写 `app/db/repositories/specialist_repo.py`（专员 CRUD）
- [ ] 4.5 写 `app/db/repositories/conversation_repo.py`（对话记录增删查）

## 5. API 路由（第 7-8 天）

- [ ] 5.1 `GET /api/v1/specialists` — 专员列表（按状态筛选）
- [ ] 5.2 `GET /api/v1/specialists/{id}` — 专员详情
- [ ] 5.3 `POST /api/v1/specialists/{id}/chat` — 与专员对话（核心接口）
  - 入参：question, session_id
  - 出参：answer, citations, evidence_level, blocked, violations, latency_ms
- [ ] 5.4 `GET /api/v1/conversations/{session_id}` — 会话历史
- [ ] 5.5 `GET /api/v1/specialists/{id}/stats` — 专员使用统计
- [ ] 5.6 `POST /api/v1/specialists/{id}/feedback` — 点赞/点踩反馈
- [ ] 5.7 `POST /api/v1/specialists/{id}/favorite` — 收藏/取消收藏问答
- [ ] 5.8 每个接口加 JWT 认证中间件 `Depends(get_current_user)`

## 6. 话术模板（第 8 天）

- [ ] 6.1 写 `shared/prompts/oncology_specialist.yaml`（参考文档 9.3，按产品配置）
- [ ] 6.2 写模板加载器：启动时读取 YAML，注入 system prompt

## 7. 评估与联调（第 9-10 天）

- [ ] 7.1 写 `tests/eval_specialist.py`（自动评估脚本，参考文档 9.4）
- [ ] 7.2 准备评估用例 `tests/eval_sets/oncology_v1.json`（≥20 条问答）
- [ ] 7.3 跑评估，目标通过率 ≥ 80%
- [ ] 7.4 与 B 联调知识检索
- [ ] 7.5 与 D 联调合规检查和审计日志
- [ ] 7.6 与 E 联调移动端对话接口

## 8. 文档（收尾）

- [ ] 8.1 写本服务的 README（启动方式、环境变量、API 文档）

---

# B · 知识库服务（knowledge-service）

> AI 能力底座。所有 AI 回答的知识来源。

## 1. 项目骨架（第 1 天）

- [ ] 1.1 创建 `services/knowledge-service/` 目录结构
- [ ] 1.2 写 `app/main.py` FastAPI 入口
- [ ] 1.3 写 `app/config.py`
- [ ] 1.4 写 `requirements.txt`（fastapi, pypdf, python-docx, dashscope, requests 等）
- [ ] 1.5 写 `Dockerfile`
- [ ] 1.6 `docker-compose up knowledge-service` 启动验证

## 2. OSS 客户端（第 2 天）

- [ ] 2.1 写 `app/services/oss_client.py`：
  - 文件上传（支持本地路径和流式上传）
  - 生成可访问 URL
  - 文件下载

## 3. 文档处理流水线（第 3-5 天）

- [ ] 3.1 写 `app/services/document_processor.py`（参考文档 9.1）：
  - `_download()` — 从 OSS 下载文件
  - `_parse_pdf()` — 用 pypdf 解析 PDF
  - `_parse_docx()` — 用 python-docx 解析 Word
  - `_parse_ppt()` — 用 python-pptx 解析 PPT（附加题）
  - `_parse_txt()` — 纯文本读取
- [ ] 3.2 写 `_split()` — 按段落+语义切分（chunk_size=512 字），支持：
  - 按章节标题切分
  - 表格保留结构化
  - 重叠窗口避免截断
- [ ] 3.3 写 `_embed()` — 调通义千问 text-embedding-v3 向量化
- [ ] 3.4 写入库逻辑：切分块逐条写入 DashVector + PostgreSQL 文档表
- [ ] 3.5 写 `process_document()` 主流程串联

## 4. DashVector 客户端（第 4 天）

- [ ] 4.1 写 `app/services/dashvector_client.py`：
  - 连接 DashVector 集群
  - `create_collection()` — 创建集合
  - `upsert()` — 插入/更新向量
  - `query()` — 向量检索（支持 filter：product_id, doc_type, evidence_level）
  - `delete()` — 删除向量

## 5. 知识检索（第 6 天）

- [ ] 5.1 写 `app/services/knowledge_retriever.py`（参考文档 9.2）：
  - 向量化查询文本
  - DashVector 混合检索（向量 + 关键词过滤）
  - 重排（`_rerank()`）：向量相似度 × 0.7 + 关键词匹配 × 0.3
- [ ] 5.2 支持按 product_id、doc_type、evidence_level 筛选

## 6. 数据层（第 5 天）

- [ ] 6.1 写 `app/models/knowledge_document.py`
- [ ] 6.2 写 `app/db/repositories/knowledge_repo.py`（文档 CRUD + 状态流转）

## 7. API 路由（第 7-8 天）

- [ ] 7.1 `POST /api/v1/knowledge/search` — 检索知识（给 A 和 C 调用的核心接口）
  - 入参：query, product_id?, doc_type?, top_k?
  - 出参：results[{title, content, doc_type, evidence_level, score}]
- [ ] 7.2 `POST /api/v1/knowledge/upload` — 上传文档
  - 接收文件 + 元信息（title, doc_type, product_id, evidence_level, source, publish_date）
  - 上传到 OSS → 写 DB → 触发异步处理流水线
- [ ] 7.3 `GET /api/v1/knowledge/documents` — 文档列表（分页、按类型/状态/产品筛选）
- [ ] 7.4 `GET /api/v1/knowledge/documents/{id}` — 文档详情
- [ ] 7.5 `POST /api/v1/knowledge/documents/{id}/review` — 文档审核（通过/驳回）
- [ ] 7.6 `POST /api/v1/knowledge/feedback` — 检索质量反馈
- [ ] 7.7 `GET /api/v1/knowledge/stats` — 知识库统计（文档数/chunk数/标签数）

## 8. 知识库构建脚本（第 9 天）

- [ ] 8.1 写 `scripts/build_knowledge_base.py`（参考文档 12.2）：
  - 扫描 `knowledge-base/{product}/` 目录
  - 自动推断文档类型（说明书→product，指南→guideline 等）
  - 自动推断证据等级（meta分析→A，III期→B 等）
  - 批量处理并入库
- [ ] 8.2 准备示例知识库资料（≥5 篇不同类别文档）

## 9. 异步任务（第 8-9 天）

- [ ] 9.1 文档上传后异步处理（用 FastAPI BackgroundTasks 或 Celery）
- [ ] 9.2 处理状态追踪（draft → processing → ready / failed）
- [ ] 9.3 处理失败重试机制

## 10. 测试与联调（第 9-10 天）

- [ ] 10.1 单元测试：PDF 解析、切分、向量化
- [ ] 10.2 集成测试：上传→处理→检索全流程
- [ ] 10.3 检索效果测试（≥10 个查询用例，人工评估准确率）
- [ ] 10.4 与 A 联调知识检索接口
- [ ] 10.5 与 D 联调审计日志

---

# C · 陪访助手 + 医生管理（visit-service + hcp-service）

> 代表日常使用最频繁的两个模块。

---

## 第一部分：陪访助手（visit-service:8002）

### 1. 项目骨架（第 1 天）

- [ ] 1.1 创建 `services/visit-service/` 目录结构
- [ ] 1.2 写 `app/main.py`、`config.py`、`requirements.txt`、`Dockerfile`
- [ ] 1.3 `docker-compose up visit-service` 启动验证

### 2. 通义听悟客户端（第 2-3 天）

- [ ] 2.1 写 `app/services/tingwu_client.py`：
  - 创建实时转写任务
  - 上传音频流
  - 获取转写结果（含说话人分离）
  - 转写结果回调处理
- [ ] 2.2 写 mock 版本供开发调试（不需要真实音频时用文本模拟）
- [ ] 2.3 验证延迟 < 2 秒

### 3. 外部服务客户端（第 2-3 天）

- [ ] 3.1 写 `app/services/specialist_client.py`（调 A 的对话接口，用于生成准备包、拜访记录等）
- [ ] 3.2 写 `app/services/compliance_client.py`（调 D 的合规检查）
- [ ] 3.3 写 `app/services/audit_client.py`（调 D 的审计日志）

### 4. 核心业务逻辑（第 4-7 天）

- [ ] 4.1 写 `app/core/visit_manager.py`（参考文档 8.2）：

  **4.1.1 拜访前 `prepare_visit()`：**
  - 获取医生画像（调 HCP 服务）
  - 获取最近 3 次互动历史
  - 调 AI 生成：3-5 个推荐话题、1-2 条红线提醒、1 段开场白、上次跟进事项
  - 组装准备包返回

  **4.1.2 拜访中 `start_visit()` + `process_transcript()`：**
  - 创建拜访记录（状态：in_progress）
  - 接收通义听悟转写结果
  - 合规实时检查（最近一段对话）
  - 异议识别（正则匹配+AI）
  - 话术建议生成
  - 红线拦截

  **4.1.3 拜访后 `end_visit()`：**
  - 调 AI 生成结构化记录：摘要（≤100字）、关键点、医生兴趣点、异议、情感判断、下次拜访计划、跟进建议
  - 自动生成后续任务（送资料、预约等）
  - 触发生成医生画像更新
  - 记录审计日志

### 5. 异议识别（第 5 天）

- [ ] 5.1 写 `_detect_objections()` — 正则匹配 + LLM 辅助
- [ ] 5.2 异议类型分类：价格异议、疗效异议、安全性异议、竞品异议
- [ ] 5.3 每种异议配话术建议模板

### 6. 数据层（第 4 天）

- [ ] 6.1 写 `app/models/visit_record.py`
- [ ] 6.2 写 `app/db/repositories/visit_repo.py`

### 7. API 路由（第 7-8 天）

- [ ] 7.1 `POST /api/v1/visits/pre-visit` — 生成拜访前准备包
  - 入参：hcp_id, product_id
  - 出参：hcp_profile, history, recommendations{topics, red_lines, opening, follow_ups}
- [ ] 7.2 `POST /api/v1/visits/start` — 开始拜访
  - 入参：hcp_id, product_id
  - 出参：visit_id, start_time, status
- [ ] 7.3 `POST /api/v1/visits/{id}/transcript` — 上传实时转写片段
  - 入参：transcript_text 或 audio_url
  - 出参：compliance_result, objections, suggestions
- [ ] 7.4 `POST /api/v1/visits/{id}/end` — 结束拜访，生成记录
  - 入参：full_transcript
  - 出参：完整拜访记录
- [ ] 7.5 `GET /api/v1/visits/{id}` — 查看拜访记录详情
- [ ] 7.6 `GET /api/v1/visits` — 拜访列表（按日期/医生筛选）
- [ ] 7.7 `PUT /api/v1/visits/{id}` — 编辑拜访记录
- [ ] 7.8 `POST /api/v1/visits/{id}/follow-up` — 获取跟进建议

---

## 第二部分：医生管理（hcp-service:8006）

### 8. 项目骨架（第 1 天，与 visit 并行）

- [ ] 8.1 创建 `services/hcp-service/` 目录结构
- [ ] 8.2 写 `app/main.py`、`config.py`、`requirements.txt`、`Dockerfile`
- [ ] 8.3 `docker-compose up hcp-service` 启动验证

### 9. 数据层（第 2 天）

- [ ] 9.1 写 `app/models/hcp.py`（医生 ORM）
- [ ] 9.2 写 `app/db/repositories/hcp_repo.py`

### 10. 业务逻辑（第 3-4 天）

- [ ] 10.1 医生画像生成/更新：聚合互动历史 + AI 分析 → 学术背景/处方偏好/沟通风格
- [ ] 10.2 医生搜索：支持姓名、医院、科室、标签搜索
- [ ] 10.3 标签管理：添加/删除标签
- [ ] 10.4 批量导入：从 Excel/CSV 解析并写入

### 11. API 路由（第 5-6 天）

- [ ] 11.1 `GET /api/v1/hcps` — 医生列表（分页、筛选：医院/科室/区域/标签）
- [ ] 11.2 `GET /api/v1/hcps/{id}` — 医生详情（完整档案）
- [ ] 11.3 `GET /api/v1/hcps/{id}/profile` — 医生画像
- [ ] 11.4 `GET /api/v1/hcps/{id}/interactions` — 互动历史
- [ ] 11.5 `POST /api/v1/hcps` — 新增医生
- [ ] 11.6 `PUT /api/v1/hcps/{id}` — 编辑医生
- [ ] 11.7 `POST /api/v1/hcps/batch-import` — 批量导入
- [ ] 11.8 `POST /api/v1/hcps/{id}/tags` — 添加标签
- [ ] 11.9 `DELETE /api/v1/hcps/{id}/tags` — 删除标签

### 12. 联调与测试（第 7-8 天）

- [ ] 12.1 与 A 联调（拜访过程中调数字专员接口）
- [ ] 12.2 与 D 联调（合规检查、审计日志）
- [ ] 12.3 与 E 联调（移动端拜访页、医生页）
- [ ] 12.4 集成测试：完整拜访流程（准备→开始→转写→结束）

---

# D · 合规 + 审计 + 共享层 + 网关

> 系统横切面，所有服务都依赖你。

---

## 第一部分：共享层（第 1-2 天，优先做！）

### 1. 共享代码（第 1 天）

- [ ] 1.1 创建 `shared/` 目录结构：
  - `shared/common/` — 通用工具（JWT 验证、分页、统一响应格式）
  - `shared/models/` — 共享 ORM 基类、Pydantic schema
  - `shared/compliance-rules/` — 合规规则 YAML
  - `shared/prompts/` — 话术模板占位
- [ ] 1.2 写 `shared/common/response.py` — 统一响应格式封装：
  ```python
  def success(data): return {"code": 0, "message": "success", "data": data}
  def error(code, message, data=None): return {"code": code, "message": message, "data": data}
  ```
- [ ] 1.3 写 `shared/common/auth.py` — JWT 验证工具（生成 token、解析 token、依赖注入 `get_current_user`）
- [ ] 1.4 写 `shared/common/pagination.py` — 分页工具
- [ ] 1.5 写 `shared/models/base.py` — ORM 基类（id, created_at, updated_at）

### 2. 数据库初始化（第 1-2 天）

- [ ] 2.1 写 `scripts/init_db.sql` — 全部 10 张表的建表语句（参考文档 6.2）
- [ ] 2.2 写 Alembic 配置，生成首次 migration
- [ ] 2.3 审计日志表加 `REVOKE UPDATE, DELETE` 不可篡改约束
- [ ] 2.4 写种子数据脚本（管理员账号、示例产品、示例合规规则）

### 3. 合规规则文件（第 2 天）

- [ ] 3.1 写 `shared/compliance-rules/rules.yaml`（参考文档 10.1，至少 4 条初始规则）：
  - R001 禁止承诺疗效（关键词）
  - R002 禁止回扣暗示（正则）
  - R003 禁止统方（语义）
  - R004 禁止超适应症推广（语义）
- [ ] 3.2 后续可追加：禁止贬低竞品、禁止泄露患者信息、禁止讨论未公开数据等

---

## 第二部分：合规审核服务（compliance-service:8004）

### 4. 项目骨架（第 2 天）

- [ ] 4.1 创建 `services/compliance-service/` 目录结构
- [ ] 4.2 写 `app/main.py`、`config.py`、`requirements.txt`、`Dockerfile`

### 5. 合规审核引擎（第 3-5 天）

- [ ] 5.1 写 `app/core/checker.py`（参考文档 10.2）：

  **三层审核流水线：**
  - 第 1 关：关键词匹配（直接字符串包含判断）
  - 第 2 关：正则匹配（预编译正则，批量扫描）
  - 第 3 关：LLM 语义审核（通义千问 turbo，仅对"语义类"规则触发，降低成本）

- [ ] 5.2 规则加载器：启动时从 YAML + DB 加载规则，合并去重
- [ ] 5.3 规则编译器：预编译关键词和正则，缓存
- [ ] 5.4 审核结果结构：
  ```json
  {
    "blocked": true/false,
    "violations": [{ "rule_code", "rule_name", "severity", "action", "matched_text" }],
    "risk_level": "high/medium/low",
    "checked_rules": ["R001", "R002", ...]
  }
  ```
- [ ] 5.5 拦截动作实现：
  - `reject`：拒绝，blocked=true
  - `warn`：警告，blocked=false 但带 violations
  - `log`：仅记录，blocked=false
- [ ] 5.6 规则热更新：提供 reload 接口，重新加载 YAML + DB 规则，不重启服务

### 6. 数据层（第 3 天）

- [ ] 6.1 写 `app/models/compliance_rule.py`
- [ ] 6.2 写 `app/models/compliance_block.py`
- [ ] 6.3 写 `app/db/repositories/compliance_repo.py`

### 7. API 路由（第 5-6 天）

- [ ] 7.1 `POST /api/v1/compliance/check` — 合规检查（所有服务都调的接口）
  - 入参：content, context{user_id, type, specialist_id?, visit_id?}
  - 出参：审核结果（blocked, violations, risk_level）
  - ⚠️ 这个接口要扛住所有服务的调用量，注意性能
- [ ] 7.2 `GET /api/v1/compliance/rules` — 规则列表
- [ ] 7.3 `POST /api/v1/compliance/rules` — 新增规则
- [ ] 7.4 `PUT /api/v1/compliance/rules/{id}` — 编辑规则
- [ ] 7.5 `DELETE /api/v1/compliance/rules/{id}` — 删除/禁用规则
- [ ] 7.6 `POST /api/v1/compliance/rules/reload` — 热更新（重载规则缓存）
- [ ] 7.7 `POST /api/v1/compliance/rules/test` — 规则测试（输入文本，查看命中哪些规则）
- [ ] 7.8 `GET /api/v1/compliance/blocks` — 拦截记录查询
- [ ] 7.9 `GET /api/v1/compliance/stats` — 合规统计（拦截次数、拦截率、Top 规则）

### 8. 测试（第 6 天）

- [ ] 8.1 写 `tests/test_compliance.py`（参考文档 14.1）：
  - 关键词拦截测试
  - 正则拦截测试
  - 安全内容放行测试
  - 空内容边界测试
  - LLM 语义审核测试
- [ ] 8.2 目标：拦截率 100%（已知违规），误拦率 < 5%（正常内容）

---

## 第三部分：审计服务（audit-service:8005）

### 9. 项目骨架（第 3 天）

- [ ] 9.1 创建 `services/audit-service/` 目录结构
- [ ] 9.2 写 `app/main.py`、`config.py`、`requirements.txt`、`Dockerfile`

### 10. 审计日志引擎（第 4-5 天）

- [ ] 10.1 写 `app/core/logger.py`（参考文档 10.3）：
  - 记录字段：service_name, user_id, action, resource_type, resource_id, before/after_value, ai_involved, ai_model, ai_prompt_hash, ai_response_hash, compliance_result, risk_level, client_ip, user_agent, request_id
  - Prompt/Response 存 hash 不存原文（安全+节省空间）
  - 异步写入，不阻塞主业务
- [ ] 10.2 不可篡改：数据库层面 REVOKE UPDATE/DELETE，代码层面无修改/删除接口
- [ ] 10.3 数据保留策略：按配置的天数自动归档（默认 3 年）

### 11. 数据层（第 4 天）

- [ ] 11.1 写 `app/models/audit_log.py`
- [ ] 11.2 写 `app/db/repositories/audit_repo.py`

### 12. API 路由（第 6-7 天）

- [ ] 12.1 `POST /api/v1/audit/log` — 写审计日志（内部接口，其他服务调）
- [ ] 12.2 `GET /api/v1/audit/logs` — 高级搜索：
  - 筛选条件：时间范围、用户、服务、操作类型、风险等级
  - 支持分页
- [ ] 12.3 `GET /api/v1/audit/logs/{id}` — 日志详情
- [ ] 12.4 `POST /api/v1/audit/export` — 导出监管报告（Excel 格式）：
  - 按筛选条件导出
  - 包含所有字段
  - 含 AI 决策日志、合规检查记录
- [ ] 12.5 `GET /api/v1/audit/stats` — 审计统计：
  - 总记录数
  - 按服务/操作类型的分布
  - 按风险等级的分布
  - 按时间段的变化趋势

---

## 第四部分：API 网关（gateway:8000）

### 13. 网关（第 7-8 天）

- [ ] 13.1 创建 `services/gateway/` 目录结构
- [ ] 13.2 写路由配置：把 `/api/v1/specialists` → specialist-service:8001 等
- [ ] 13.3 写 JWT 认证中间件（所有请求过网关时统一验证 token）
- [ ] 13.4 写限流中间件（每用户每分钟 N 次请求）
- [ ] 13.5 写 X-Request-ID 注入（链路追踪）
- [ ] 13.6 写 CORS 配置
- [ ] 13.7 写健康检查聚合 `/health`
- [ ] 13.8 更新 `docker-compose.yml`：所有服务通过 gateway 对外暴露，内部服务不暴露端口

### 14. 联调与文档（第 9-10 天）

- [ ] 14.1 与 A、B、C 逐个验证网关路由
- [ ] 14.2 写网关 README
- [ ] 14.3 写 API 总文档（Swagger 聚合或手动整理）

---

# E · 移动端 + DevOps

> 代表每天打开的那个 App + 整个系统的部署运维。

---

## 第一部分：移动端（React Native）

### 1. 项目脚手架（第 1-2 天）

- [ ] 1.1 `npx react-native init MedAgentMobile --template react-native-template-typescript`
- [ ] 1.2 创建 `mobile/src/` 目录结构（按文档 11.1）
- [ ] 1.3 安装依赖：React Navigation、AsyncStorage、Axios/API 客户端
- [ ] 1.4 配置底部 Tab 导航（4 个 Tab：工作台/对话/医生/我的）
- [ ] 1.5 配置主题色、通用样式、字体

### 2. API 客户端（第 2 天）

- [ ] 2.1 写 `src/api/client.ts`（参考文档 11.3）：
  - Base URL 配置（开发/生产环境切换）
  - JWT Token 管理（存储到 AsyncStorage）
  - 统一请求封装（header 注入、X-Request-ID 生成）
  - 统一错误处理（按错误码分类提示）
- [ ] 2.2 写各模块 API 封装：
  - `src/api/auth.ts` — 登录/登出/获取用户信息
  - `src/api/specialist.ts` — 专员列表/对话/反馈/收藏
  - `src/api/visit.ts` — 拜访前/开始/转写/结束
  - `src/api/hcp.ts` — 医生列表/详情/搜索
  - `src/api/compliance.ts` — 合规检查
  - `src/api/content.ts` — 学术内容

### 3. 登录页（第 3 天）

- [ ] 3.1 写 `src/screens/Login/LoginScreen.tsx`
  - Logo 展示
  - 手机号输入（自动校验格式）
  - 验证码输入 + 获取按钮（60 秒倒计时）
  - 登录按钮
  - 协议勾选
- [ ] 3.2 登录状态管理（token 持久化，自动登录）
- [ ] 3.3 登录成功后导航到工作台

### 4. 工作台（第 4-5 天）

- [ ] 4.1 写 `src/screens/Home/HomeScreen.tsx`
  - 顶部欢迎栏（日期、天气占位、通知图标、设置入口）
  - 今日进度环（已完成 X/Y）
  - 今日拜访列表（按时间排序的卡片）：
    - 每张卡片：医生姓名、医院、时间、状态标签（待开始/进行中/已完成）
    - 待开始卡片有"准备包"按钮 → 跳转拜访前准备页
    - 进行中卡片有"继续"按钮 → 跳转拜访中页
    - 已完成卡片显示完成时间
  - FAB 按钮：手动添加临时拜访
  - 快捷功能区：问答/内容/医生 3 个入口
- [ ] 4.2 下拉刷新 + 上拉加载更多

### 5. 数字专员对话（第 5-6 天）

- [ ] 5.1 写 `src/screens/Specialists/SpecialistListScreen.tsx` — 专员列表
  - 每个专员一张卡片（名称、产品图、状态、今日回答次数）
  - 点击进入对话
- [ ] 5.2 写 `src/screens/Chat/ChatScreen.tsx`（参考文档 11.2.1）
  - 对话气泡（用户右对齐蓝色、AI 左对齐白色）
  - 消息包含：引用来源卡片、证据等级标注
  - 每条 AI 消息底部：反馈按钮（点赞/点踩）、收藏按钮、分享按钮
  - 长按消息：复制文本/反馈
  - 输入区：文本输入框 + 语音输入按钮 + 发送按钮
  - 发送中显示 loading 状态
- [ ] 5.3 多轮对话（session_id 维持上下文）
- [ ] 5.4 键盘弹出时自动滚到最新消息

### 6. 拜访流程（第 6-8 天）

- [ ] 6.1 写 `src/screens/VisitPrepare/VisitPrepareScreen.tsx`（参考文档 11.2.2）
  - 医生基本信息卡片
  - 推荐话题卡片（可勾选/编辑）
  - 红线提醒卡片（红色背景，醒目）
  - 开场白建议卡片（斜体引用样式）
  - 上次跟进卡片
  - "开始拜访"按钮 → 调 API 创建拜访记录 → 跳转拜访中
- [ ] 6.2 写 `src/screens/VisitInProgress/VisitInProgressScreen.tsx`
  - 顶部状态栏：录音中动画 + 计时器
  - 实时转写区（滚动，医生/代表分离显示，不同颜色）
  - 实时提示区（核心功能）：
    - 异议识别弹窗
    - 话术建议卡片（可展开/收起）
    - 红线拦截弹窗（红色警告样式）
  - 关键节点标记（AI 自动 + 手动标记按钮）
  - "结束拜访"按钮（需二次确认）
- [ ] 6.3 写 `src/screens/VisitEnd/VisitEndScreen.tsx`
  - AI 摘要（≤100 字，可编辑）
  - 关键点列表（可编辑/删除）
  - 医生兴趣点
  - 医生异议
  - 情感判断（积极/中性/消极，可修改）
  - 下次拜访时间推荐
  - 跟进建议 + 自动任务（一键执行）
  - "确认完成"按钮 → 提交 → 返回工作台

### 7. 医生模块（第 7-8 天）

- [ ] 7.1 写 `src/screens/HCPSearch/HCPSearchScreen.tsx`
  - 顶部搜索框（姓名/医院/科室）
  - 快速筛选项（医院、科室、标签）
  - 最近浏览
  - 字母索引滚动
- [ ] 7.2 写 `src/screens/HCPDetail/HCPDetailScreen.tsx`
  - 基本信息（姓名、医院、科室、职称、电话）
  - 快捷操作按钮（打电话、发消息、预约）
  - 学术背景
  - 处方偏好
  - 标签列表
  - 互动历史时间线（每次拜访简要信息）

### 8. 其他页面（第 8-9 天）

- [ ] 8.1 写 `src/screens/Content/ContentScreen.tsx` — 学术内容
  - 分类 Tab（指南/文献/产品/病例/视频/合规）
  - 推荐内容 + 最新内容
  - 搜索
- [ ] 8.2 写 `src/screens/Profile/ProfileScreen.tsx` — 我的
  - 个人信息（头像、姓名、职位、区域）
  - 统计概览（对话数/拜访数/收藏数）
  - 功能列表（个人资料、团队、统计、通知、帮助、合规手册、退出登录）
- [ ] 8.3 写 `src/screens/Compliance/ComplianceScreen.tsx` — 合规手册
  - 红线清单
  - 错误 vs 正确对比
  - 联系方式

### 9. 测试与联调（第 9-10 天）

- [ ] 9.1 iOS 模拟器 + Android 模拟器验证所有页面
- [ ] 9.2 与 A 联调对话接口
- [ ] 9.3 与 C 联调拜访接口
- [ ] 9.4 与 D 联调登录认证
- [ ] 9.5 全流程走通：登录 → 工作台 → 准备包 → 拜访 → 生成记录 → 对话

---

## 第二部分：DevOps

### 10. Docker 编排（第 1-2 天）

- [ ] 10.1 完善 `docker-compose.yml`（参考文档 5.4）：
  - PostgreSQL 15 + 初始化 SQL
  - Redis 7
  - 7 个服务（6 微服务 + 1 网关）
  - 健康检查配置
  - 网络隔离（内部网络 + 网关暴露）
- [ ] 10.2 写 `.env.example` 模板
- [ ] 10.3 验证 `docker-compose up -d` 所有服务启动 + 互相可达

### 11. CI/CD（第 8-9 天）

- [ ] 11.1 写 `.github/workflows/test.yml` — PR 时跑 lint + 单元测试
- [ ] 11.2 写 `.github/workflows/deploy.yml`（参考文档 15.3）：
  - 测试 → 构建 Docker 镜像 → 推送到阿里云容器镜像仓库
  - 分 dev/staging/prod 三个环境
- [ ] 11.3 配置 GitHub Secrets（阿里云 AK、镜像仓库密码等）
- [ ] 11.4 写部署脚本（或配置阿里云云效流水线）

### 12. 监控告警（第 9-10 天）

- [ ] 12.1 配置阿里云 ARMS 应用监控（各服务接入）
- [ ] 12.2 配置告警规则（参考文档 15.4）：
  - AI 回答延迟 P95 > 5000ms
  - 合规拦截率异常（< 0.1% 或 > 10%）
  - 数据库连接池 > 80%
  - 服务宕机
- [ ] 12.3 配置 SLS 日志采集

### 13. 文档（收尾）

- [ ] 13.1 写项目根目录 README（项目介绍、快速开始、架构图）
- [ ] 13.2 写部署文档（如何部署到阿里云）
- [ ] 13.3 写移动端打包发布文档（iOS App Store + Android 应用商店）

---

# 公共里程碑 & 检查点

| 时间 | 里程碑 | 验收标准 |
|------|--------|---------|
| 第 1 周结束 | 基础搭建完成 | 所有服务能启动、网关能路由、数据库表创建完成 |
| 第 2 周结束 | 核心接口可用 | A 的 chat 接口能返回 AI 答案、B 的 search 接口能检索到文档、D 的 check 接口能拦截违规内容 |
| 第 3 周结束 | 业务闭环 | 完整的"知识检索→合规检查→AI生成答案→审计日志"链路走通 |
| 第 4 周结束 | 移动端核心可用 | 登录→工作台→对话→拜访全流程走通 |
| 第 5 周结束 | 功能完备 | 所有 P0 功能完成开发 |
| 第 6 周结束 | 测试通过 + 部署 | 评估通过率 ≥ 80%、staging 环境部署验证通过 |

---

# 协作约定

## 1. 接口契约

每个人写完 API 后，**立即**更新到共享的 API 文档（用 Swagger 或飞书文档），其他人不用等代码写完就能按契约开发。格式：

```
POST /api/v1/specialists/{id}/chat
Request: { "question": "string", "session_id": "string?" }
Response: { "code": 0, "data": { "answer": "...", "citations": [...], "evidence_level": "..." } }
Error: { "code": 4001, "message": "合规拦截", "data": { "rule_code": "R001" } }
```

## 2. 外部服务依赖

服务间调用全部走网关（gateway:8000），不直连：
```
A调B: http://gateway:8000/api/v1/knowledge/search
A调D: http://gateway:8000/api/v1/compliance/check
C调A: http://gateway:8000/api/v1/specialists/{id}/chat
C调D: http://gateway:8000/api/v1/compliance/check
```

## 3. 日会制度

每天 15 分钟站立会，每个人说三件事：
- 昨天做了什么
- 今天要做什么
- 有没有阻塞

## 4. 阻塞处理

遇到阻塞（比如等别人的接口），不要等：
- 先写 mock 数据继续开发
- 在日会上说出来
- 优先 unblock 上游依赖

---

> **所有任务细节以《AI数字员工系统-完整方案 v4.0》为准。**
