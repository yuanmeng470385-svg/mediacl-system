# MedAgent 缺口补齐设计文档（2026-08-05）

> 对应《AI数字员工系统-完整方案》v4.0 审计发现的 14 项缺口，分 5 批次实施。
> 基线：2026-08-05 全项目审计（specialist 55% / visit 60% / knowledge 50% / compliance 70% / audit 85% / gateway 75% / auth 80% / hcp 80% / mobile 50% / web 30% / infra 55%）

## 0. 已确认的决策

| 决策点 | 结论 |
|---|---|
| 外部服务策略 | **真实客户端 + 优雅降级**：写真实代码，未配置/失败时降级到现有可用链路并明确告警，不静默假数据 |
| 实时转写范围 | 本轮做**服务端真实链路 + fail-closed**；mobile 端录音等原生工程补齐后再接 |
| 知识库为空 | 空库所有端点返回友好提示；新增示例文档种子脚本做端到端验证 |
| 任务/反馈等新表 | 走 `scripts/migrations/003_gap_closure.sql`，同步更新 `scripts/init_db.sql`（新库与旧库一致） |

通用原则：
- 统一响应 `{code, message, data}`，沿用 `shared/common/response.py`
- 权限：业务接口 JWT + 归属校验（S4：本人或 admin）；管理接口 `require_roles`；内部接口 `require_internal_key`
- 所有写操作过 `write_audit_log`
- 每批次附最小 pytest 单测 + 可运行的验证命令

---

## 批次 A：合规闭环（compliance-service）

### A1. 规则热更新 DB 加载

现状：`checker.py:53-55` DB 加载被注释，CRUD 写库但引擎只认 YAML。

变更：
1. `checker.py` 实现 `_load_db_rules()`：读 `compliance_rules` 表，字段映射 `rule_type→type`、`content JSONB→patterns`（content 取 `{"patterns": [...]}`，无则空）。同 rule_code **DB 覆盖 YAML**，DB 没有的规则用 YAML 补齐（R005-R007 不必改种子即生效）。
2. **TTL 缓存（60s）**：`checker` 记录 `_rules_loaded_at`；`check()` 时过期自动 `_reload_rules()`（双 worker 下各自最多延迟 60s 生效）；CRUD 端点成功后主动调 `checker.reload()` 立即刷新本 worker。
3. **坏正则隔离**：`_compile_rules` 中 `re.compile` 包 try/except，单条失败跳过 + `logger.error`，不影响其他规则和服务启动。
4. DB 不可用（启动时）：回退 YAML + error 日志（维持现有危险状态告警）。
5. 顺手修：`create_rule` 缺字段 `request["rule_code"]` 直接下标 → `.get` + `ParamError`；`test_rule` 语义结果校验 rule_code 与 `hits` 对齐（checker.py:271-272）。

### A2. 监管自查报告导出

新增 `POST /api/v1/compliance/report/export`，角色 `RULE_ADMIN_ROLES`，参数 `{start_time, end_time}`，openpyxl 真实 xlsx（参考 audit-service 导出实现），3 个 Sheet：
- 规则快照：rule_code/rule_name/rule_type/severity/action/enabled/version/命中次数（命中数 = compliance_blocks 按 rule_code 计数）
- 拦截明细：时间范围内 compliance_blocks 全量（blocked_at/user_id/service_name/content/rule_code/severity/action）
- 汇总：按规则聚合、按服务聚合、按天聚合、reject/warn/log 占比

测试：`compliance-service/tests/test_report_export.py`（构造 ComplianceBlock 数据 → 导出 → openpyxl 读回断言 Sheet 与行数）。

---

## 批次 B：专员对话闭环（specialist-service）

### B1. 引用溯源解析百炼 docs

- `bailian_client.py` RespondingContent 分支（:125-130）：解析 `payload.output.extra_info.docs`，防御式兼容（docs 缺省/结构不符 → `[]`），提取 `[{title, url, doc_id}]`，`chat()` 返回新增 `citations` 字段。
- `answer_generator.py`：把 `bailian_result.get("citations", [])` 透传进返回；千问降级路径保持空 citations + 注释说明。
- 顺手修：`ws.recv()` 包 `asyncio.wait_for(..., timeout=self.timeout)`（现有 `self.timeout=30` 未使用）；60 次循环耗尽未收 finished 时抛 `BailianException` 而非静默截断。

测试：`tests/test_bailian_citations.py`（mock websocket 收包序列，断言 citations 解析；异常/缺字段分支）。

### B2. 反馈/收藏落库

新表（003 迁移 + init_db.sql）：

```sql
CREATE TABLE conversation_feedback (
    id BIGSERIAL PRIMARY KEY,
    conversation_id BIGINT REFERENCES conversations(id),
    user_id BIGINT REFERENCES users(id),
    specialist_id BIGINT REFERENCES digital_specialists(id),
    rating SMALLINT NOT NULL CHECK (rating IN (-1, 1)),
    comment TEXT,
    created_at TIMESTAMP DEFAULT NOW()
);
CREATE INDEX idx_feedback_conversation ON conversation_feedback(conversation_id);
CREATE INDEX idx_feedback_user ON conversation_feedback(user_id);

CREATE TABLE conversation_favorites (
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
```

端点（替换现有假实现 specialists.py:160-184）：
- `POST /api/v1/conversations/{id}/feedback` `{rating: -1|1, comment?}` — 校验 conversation 存在 + 归属（本人或 admin），rating 枚举校验
- `POST /api/v1/conversations/{id}/favorite` — toggle，返回 `{is_favorite}`
- `GET /api/v1/favorites` — 我的收藏列表（分页）
- `DELETE /api/v1/favorites/{id}` — 取消收藏（本人或 admin）
- `GET /api/v1/specialists/{id}/stats` 补 `satisfaction_rate`（positive/(positive+negative)）

模型：`app/models/` 新增 ConversationFeedback / ConversationFavorite；`init_db.sql` 同步表。

测试：`tests/test_feedback_favorite.py`（落库/重复点赞校验/toggle/归属校验/满意度统计）。

### B3. 专员 CRUD

端点（全部 `require_roles("admin")` + 审计日志）：
- `POST /api/v1/specialists` `{name, product_id, persona?, knowledge_scope?, compliance_level?, bailian_app_id?, status}` — 校验 name 非空、product_id 存在
- `PUT /api/v1/specialists/{id}` — 白名单字段更新（name/product_id/persona/knowledge_scope/compliance_level/bailian_app_id/status）
- `DELETE /api/v1/specialists/{id}` — 软删 `status='disabled'`（幂等）
- 顺手修：`stats` 校验专员存在

测试：`tests/test_specialist_crud.py`（创建/更新/软删/非 admin 403）。

---

## 批次 C：陪访闭环（visit + hcp）

### C1. 任务创建

新表（003 迁移 + init_db.sql）：

```sql
CREATE TABLE tasks (
    id BIGSERIAL PRIMARY KEY,
    visit_id BIGINT REFERENCES visit_records(id),
    user_id BIGINT REFERENCES users(id),
    title VARCHAR(500) NOT NULL,
    description TEXT,
    task_type VARCHAR(50) DEFAULT 'follow_up',  -- book_appointment/send_material/call/email/follow_up/other
    due_date DATE,
    channel VARCHAR(50),
    status VARCHAR(20) DEFAULT 'open',           -- open/done/cancelled
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW()
);
CREATE INDEX idx_tasks_user_status ON tasks(user_id, status);
CREATE INDEX idx_tasks_visit ON tasks(visit_id);
```

- `follow_up()`（visit_manager.py:379-418）：解析 `follow_up_items` 逐条落库 tasks（`due`→due_date、`channel`→task_type 映射）；AI 降级/解析失败 → 打日志不建任务，不阻塞。
- 端点（S4 归属校验）：
  - `GET /api/v1/tasks?status=&page=&page_size=` — 我的任务（本人，admin 可带 user_id）
  - `PUT /api/v1/tasks/{id}` `{status: open|done|cancelled}`
  - `GET /api/v1/visits/{id}/tasks`

模型：visit-service `app/models/task.py`；路由 `app/api/tasks.py`。

测试：`tests/test_tasks.py`（follow_up 落库/状态流转/归属校验/降级不阻塞）。

### C2. 医生画像更新（visit → hcp）

- hcp-service 新增 `POST /api/v1/hcps/{id}/profile-update`（`require_internal_key`，走网关 internal 路由）：参数 `{academic_background?, prescription_preference?, influence_level?, tags?, source, visit_id?}`，**JSONB 按 key 合并**（新值非空且旧值为空/缺 key 才写入，已有值不覆盖），tags 去重追加；审计日志。
- visit-service `end_visit()` 成功后推导画像增量（hcp_interests → 学术倾向/兴趣、sentiment 与 key_points → prescription_preference 备注、objections → tags），经网关 internal 调 profile-update；失败仅 `logger.warning` 不影响主流程。

测试：hcp `tests/test_profile_update.py`（合并语义/审计/tags 去重）；visit 侧以 mock 客户端验证调用参数。

### C3. 实时转写真实链路 + fail-closed

- `asr_ws.py:_get_asr_client()`：无 `NLS_APPKEY` → 抛 `RuntimeError`，WS 回推 `{"type":"error","message":"实时转写未配置（NLS_APPKEY）"}` 后关闭，**不写任何转写文本落库**（fail-closed）。
- Mock 客户端保留，仅 `NLS_MOCK=1` 显式启用（开发联调，启动时打红色告警日志）；Mock 会话的文本**不落库**（`asr_ws.py:81` 落库前检查来源非 mock）。
- 合规检查非阻塞：`on_sentence` 中 `check_compliance` 改为 `asyncio.create_task` 后台执行，结果通过 WS 回推（不串行等待，保住 <2s）。
- 顺手修：`visit_manager.py:247` compliance_flags 整句覆盖 → append 累积；`asr_ws.py:123` 断连后 finally 中 send 失败吞掉。

测试：`tests/test_asr_fail_closed.py`（无 APPKEY → error 事件且 transcript 不变；有 NLS_MOCK=1 → 文本不落库）。

---

## 批次 D：知识库（knowledge-service，空库适配）

### D1. DashVector 客户端

- 新增 `services/dashvector_client.py`：`DashVectorClient`（SDK `dashvector>=1.0.0` 已在 requirements），collection 不存在自动创建（维度 1536，`DASHVECTOR_COLLECTION` 默认 knowledge_base）；`upsert_chunk(doc_id, vector, fields)` / `query(vector, filter, top_k)`。
- embedding 复用 dashscope `text-embedding-v3`（`.env` 已有 DASHSCOPE_API_KEY）。
- 集成：审核通过（`document_manager.py` ready 路径）→ 解析正文写入 `knowledge_documents.content`（现在恒 NULL；正文来源：OSS 下载后 pypdf/python-docx 解析，或百炼 parse 返回文本，优先本地解析失败用百炼文本）→ 512 字段落切分 → DashVector upsert（fields 含 doc_id/title/doc_type/product_id/evidence_level/chunk_index/content）。
- `search()`：后端顺序 **DashVector → 百炼 retrieve → 本地 SQL**；DashVector 路径真实支持 product_id/doc_type 过滤。
- 空库：无数据时返回 `{"results": [], "backend": "dashvector", "empty": true}` + 提示文案。

### D2. ES 可选接入 + 混合检索

- 新增 `services/es_client.py`：`ES_URL` 配置时启用（真实 ES 客户端，bulk index + query），未配置返回 None 由调用方降级。
- 降级关键词索引：`local_search` 从假评分（命中标题 0.9/否则 0.6）升级为 **PostgreSQL 全文检索**：`to_tsvector('simple', coalesce(title,'') || ' ' || coalesce(content,'')) @@ plainto_tsquery('simple', :q)`，相关度 `ts_rank` 排序，附带 content ilike 兜底。
- 混合检索：DashVector 向量 + PG FTS 关键词 → 加权融合（score 归一化后 0.7/0.3，沿用方案 9.2 的加权思路）。
- 顺手修：`search()` 的 product_id/doc_type 过滤在本地路径真实生效；`int(top_k)` 包 try/except → ParamError。

### D3. 版本管理

- 注意：`knowledge_documents.version` 已存在且是 String(20)（用户可见的文档版本号，如 "1.0"），不可复用。加列（003 迁移 + init_db.sql）：`revision INT DEFAULT 1`（版本链计数）、`parent_doc_id BIGINT REFERENCES knowledge_documents(id)`。
- 上传（`create_from_upload`）：查同 title + 同 product 现存文档 → 有则旧文档 status='archived'，新行 revision=旧行.revision+1 且 parent_doc_id=旧行 id；无则 revision=1。
- 列表/详情返回 revision 与 parent_doc_id。

### D4. 反馈落库

新表（003 + init_db.sql）：

```sql
CREATE TABLE knowledge_feedback (
    id BIGSERIAL PRIMARY KEY,
    user_id BIGINT REFERENCES users(id),
    query TEXT,
    doc_id VARCHAR(100),
    rating SMALLINT NOT NULL CHECK (rating IN (-1, 1)),
    comment TEXT,
    created_at TIMESTAMP DEFAULT NOW()
);
```

- `/feedback` 改为真实落库（校验 query/rating 必填）+ 审计日志，替换只打日志的实现（knowledge.py:175-181）。

### D5. 检索测试 + 空库适配 + 种子脚本

- 新增 `POST /api/v1/knowledge/search-test`：`{query, top_k?, backends?: ["bailian","dashvector","local"]}` → 并行调各后端（各自 try/except 独立容错）返回 `[{backend, results, error?, elapsed_ms}]`；空库后端返回 empty 提示。
- 新增 `scripts/seed_demo_docs.py`：生成 2-3 个示例文档（产品说明书风格 txt，含 R001 敏感词与正常内容各一份），走知识库上传 API + 直接调审核接口置 ready，用于端到端验证"上传→审核→向量化→检索→版本"链路。用法：`python scripts/seed_demo_docs.py`。

测试：`tests/test_search_backends.py`（空库提示/多后端容错/过滤生效/版本链）。

---

## 批次 E：工程基建

### E1. CI/CD

- `.github/workflows/ci.yml`（push/PR 到 master、develop）：8 个服务 `pip install -r requirements.txt && pytest`；web `npm ci && tsc --noEmit && eslint`；mobile `npm ci && tsc --noEmit`。**不允许 `|| true` 吞错**。
- `.github/workflows/deploy.yml`：main 分支构建 8 个镜像推阿里云 registry（secrets: ALIYUN_REGISTRY_USER/PASS、DASHSCOPE_API_KEY 等），沿用方案 15.3 结构。
- 依赖服务注入 `.env` 用 `env` map（JWT_SECRET、DATABASE_URL 等测试值）。

### E2. ARMS 监控

- 重写 `deploy/arms-monitor.py`：用 ALIYUN AK（`ALIYUN_ACCESS_KEY_ID/SECRET`）调 ARMS OpenAPI（`aliyun-python-sdk-arms`，`AddPrometheusIntegration`/`CreatePrometheusAlertRule` 类接口）创建/更新方案 15.4 三条告警（AI 回答延迟 >5s、合规拦截率 <0.1% 或 >10%、DB 连接池 >80%）；AK 未配置 → 打印配置指引并以非零码退出（不假装成功）。
- 各服务新增 `/metrics` 端点（`prometheus-client`）：请求计数/延迟直方图/合规拦截率/chat 次数（core 服务 specialist/visit/knowledge/compliance 必做，其余可选）。未装 prometheus-client 的服务 requirements 补依赖。
- 告警规则文件 `deploy/arms-alerts.yaml` 与脚本同源。

---

## 实施顺序与验证

| 批次 | 验证方式 |
|---|---|
| A | pytest（checker DB 加载/报告导出）；`docker compose up` 后 curl 规则 CRUD → check 命中 |
| B | pytest（citations/feedback/favorites/CRUD）；curl stats 满意度 |
| C | pytest（tasks/画像合并/ASR fail-closed）；WS 无 APPKEY 连接断言 error 事件 |
| D | `python scripts/seed_demo_docs.py` 跑通全链路；pytest 多后端 |
| E | 本地跑 actions 无法实测，语法校验 + 脚本 `--dry-run` 分支 |

数据库：迁移 003 与 init_db.sql 同步；旧库执行 `psql -f scripts/migrations/003_gap_closure.sql`。

## 不在本轮范围

- mobile 端真实录音、web 前端契约修复/登录页、短信通道接入、ES 真实实例、审计导出合规统计合并、X-Request-ID 链路、web 页面功能——留待后续批次。
