# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

MedAgent 药企 AI 数字员工系统 — 五层架构的医药代表 SaaS 平台，提供数字学术专员、陪访助手、知识库管理、合规审核、审计追溯。七个微服务 + API 网关，部署在阿里云，AI 能力通过百炼多模态交互 App（WebSocket）+ 通义千问（OpenAI 兼容）+ 通义听悟（ASR）提供。

## Architecture

```
Web 管理后台 (React+Vite, web/, :3000) ─┐
                                          ├─→ Gateway (:8000) ─→ 微服务集群
移动端 (React Native, mobile/, 可构建) ───────┘
                                              ├─ auth(:8007)      认证 — 手机验证码/密码登录，签发 JWT
                                              ├─ specialist(:8001) 数字专员 — 每个专员=一个百炼多模态App
                                              ├─ visit(:8002)     陪访助手 — 听悟转写+合规实时检查+异议识别
                                              ├─ knowledge(:8003) 知识库管理 — 文档审核流+百炼App知识库同步
                                              ├─ compliance(:8004) 合规审核 — 三层审核(关键词→正则→LLM语义)
                                              ├─ audit(:8005)    审计日志 — 全链路留痕+Excel导出
                                              └─ hcp(:8006)      医生管理 — 档案CRUD+AI画像+Excel批量导入
```

**核心调用链路（数字专员问答）：**
用户提问 → Gateway → specialist → compliance 合规预检 → 百炼App WebSocket 知识检索+生成 → compliance 审核答案 → audit 日志 → 返回

**关键架构决策：** 每个数字专员 = 一个阿里云百炼多模态交互开发套件 App（自带知识库/文档解析/向量化/检索）。业务层不建文档处理流水线，百炼内部消化。陪访助手/医生管理不需要百炼App，全部通过千问直调（`DASHSCOPE_API_KEY`）或调用 specialist 的 chat 接口。

**网关 ROUTE_MAP（main.py:81-93）：** 除 7 个服务前缀外，还映射了五个跨服务路由 —— `/api/v1/conversations`、`/api/v1/favorites`（→specialist）、`/api/v1/tasks`（→visit）、`/api/v1/users`（→auth）、`/api/v1/nls`（→visit），前端按资源路径访问无需关心服务归属。

**2026-08-11 审计补记的服务端点（此前未入文档）**：audit `GET /api/v1/audit/stats`（仪表盘聚合：总数/风险分布/服务分布/按日趋势）、hcp `POST/DELETE /api/v1/hcps/{hcp_id}/tags`（标签增删）、visit `GET /api/v1/tasks` + `PUT /api/v1/tasks/{task_id}` + `GET /api/v1/visits/{visit_id}/tasks`（tasks 模块，follow_up 自动建任务后管理）、compliance `POST /api/v1/compliance/rules/test`（规则试跑）与 `GET /api/v1/compliance/redlines`（见 Compliance Rules 章节）、visit `GET /api/v1/nls/tts-token`（TTS 合成凭证：require_roles rep/admin/manager；未配 NLS_APPKEY → BusinessError 4xxx；移动端 TTS 凭证）。

## Commands

```bash
# 启动基础设施
docker-compose up -d postgres redis          # 先启数据库
docker exec -i medagent-postgres psql -U medagent medagent < scripts/init_db.sql  # 首次初始化

# 设置管理员密码（仓库里不放默认口令，必须跑一次才能登录）
python scripts/seed_admin.py                 # 随机生成并打印一次
python scripts/seed_admin.py --phone 13812345678   # 顺便设手机号（验证码登录需要）

# 旧库升级（补 users.password_hash + 手机号唯一索引）
docker exec -i medagent-postgres psql -U medagent medagent < scripts/migrations/001_add_user_password.sql

# 审计不可篡改落地（低权账号 + owner 分离 + medagent 降 superuser；只跑一次，密码必传）
docker exec -i medagent-postgres psql -U medagent medagent \
  -v audit_password='<强密码>' < scripts/migrations/002_audit_immutable.sql

# 前端（web/ 管理后台）
cd web && npm install
cd web && npm run dev              # http://localhost:3000，/api 代理到网关 localhost:8000
cd web && npm run build            # tsc -b && vite build

# 运行单个服务
cd services/specialist-service && python -m uvicorn app.main:app --port 8001 --reload

# 运行测试（必须在服务目录下运行，sys.path 依赖 cwd；2026-08-13 全项目审查修复批后 459 passed）
cd services/auth-service && python -m pytest tests/ -v        # 56 用例（含验证码并发 consume Lua 用例）
cd services/specialist-service && python -m pytest tests/ -v  # 85（含反馈明细角色/流式门禁全量帧）
cd services/hcp-service && python -m pytest tests/ -v         # 39
cd services/visit-service && python -m pytest tests/ -v       # 87（含取消/结束态拦截/直调 qwen/转写去重）
cd services/compliance-service && python -m pytest tests/ -v  # 64（语义网络错误 fail-closed/禁用规则生效）
cd services/knowledge-service && python -m pytest tests/ -v   # 57（ES 检索 status 过滤/索引后置写入）
cd services/audit-service && python -m pytest tests/ -v       # 19
cd services/gateway && python -m pytest tests/ -v             # 46（CORS 白名单/WS 首帧鉴权/信任代理）
cd shared && python -m pytest common/tests/ -v                # shared 层自测（test_internal_auth.py）

# 运行 A 的 AI 评估（需要真实百炼 App）
cd services/specialist-service && python tests/eval_specialist.py --app-id <百炼AppId>

# 联调冒烟（runbook 第 3 节：登录/专员/对话/R001/R003/审计，全走网关）
python scripts/smoke_runbook.py            # 需根 .env 的 INTERNAL_API_KEY + AUTH_DEV_MODE=true（验证码响应回传）+ SMOKE_PHONE（已注册手机号，未设则直接报错退出）
# 百炼 WS 协议探针（诊断 App 发布状态/返回帧：直连 dump Started→Listening→RespondingContent）
python scripts/probe_bailian_ws.py [app_id]
# 知识库示例文档种子（3 个 txt 上架 → 向量化；离线上架，可用于无真实文献时联调检索）
python scripts/seed_demo_docs.py

# 全部 8 个服务同时启动
docker-compose up -d

# ⚠️ 本机 Docker Hub 不可达（直连超时，需 127.0.0.1:7897 代理）：
#    8 个服务镜像从未构建过（python:3.11-slim 拉不下来）→ 用 native 直跑路径：
docker-compose up -d postgres redis        # postgres/redis 镜像本地已有，可正常起
# 然后每个服务目录下直跑（.env 里 DATABASE_URL 等就是宿主连接配置）：
cd services/auth-service && python -m uvicorn app.main:app --port 8007
cd services/gateway && python -m uvicorn app.main:app --port 8000
# 端口：auth 8007 / specialist 8001 / visit 8002 / knowledge 8003 /
#       compliance 8004 / audit 8005 / hcp 8006 / gateway 8000
# 全量启动参考：logs/native/ 下各服务日志；验证码在 logs/native/auth-service.log（ConsoleSender）

# 单独构建某个镜像：build context 必须是仓库根目录（镜像要 COPY shared/）
docker build -f services/auth-service/Dockerfile -t medagent/auth-service .

# 部署/CI 相关（deploy/ + scripts/ 下，CLAUDE.md 2026-08-11 补记；2026-08-13 更新）
#   deploy/docker-compose.prod.yml   生产 compose（DB_USER/DB_PASSWORD/REDIS_PASSWORD/AUDIT_DB_PASSWORD 必填校验；
#                                    env_file 为 ../.env（仓库根）；仓库根运行：docker compose --env-file .env -f deploy/docker-compose.prod.yml up -d）
#   deploy/arms-monitor.py           ARMS 监控上报（RPC 签名，HMAC 密钥 = AK Secret + "&"，--dry-run；2026-08-13 起
#                                    告警规则真实落地：PromQL Expression + List 同名则 Update 幂等；ClusterId 用 ARMS_CLUSTER_ID）
#   deploy/arms-alerts.yaml          ARMS 告警规则源文件（只保留有真实指标源的规则）
#   scripts/ci-pipeline.yaml         阿里云云效 Flow 流水线（2026-08-13 重写为合法 Flow YAML：version v1.0/stages 映射式/
#                                     needs 依赖，lint 真实生效，test 覆盖 8 服务+shared+web build+mobile jest）
#   scripts/docker-verify.sh Docker 验证脚本（8 服务含 auth）；scripts/smoke_runbook.py 冒烟（2026-08-13 起 R001/R003
#                                    真断言 blocked/violations，任一节失败非零退出，不再恒绿）

# 数据库备份/恢复（详见下方 "Backup & Restore" 小节）
python scripts/backup_db.py --local-only          # 本机备份+校验（开发）；ECS cron 每日 02:00 全流程
python scripts/restore_db.py --source local --yes # 恢复到临时库验证可恢复性
python scripts/restore_db.py --source oss --yes   # 从 OSS 取最近备份恢复（生产恢复演练）
```

**运行测试必须在服务目录下执行** — 所有测试用 `sys.path.insert(0, ...)` 回溯三层找到 shared 模块，路径依赖 cwd。

## Shared Layer (`shared/`)

所有微服务共用。统一响应格式：

```python
from shared.common.response import success, error, ParamError, AuthError, BusinessError
# success(data) → {"code":0,"message":"success","data":{...}}
# raise ParamError("question 不能为空") → {"code":1000,"message":"question 不能为空"}

from shared.common.auth import get_current_user, create_token, require_roles
# @router.get("/xxx") → async def api(current_user: dict = Depends(get_current_user)): ...
# @router.post("/rules") → async def api(current_user: dict = Depends(require_roles("admin", "manager"))): ...
#   require_roles 未登录 401、角色不符 403（code 3000）。角色：admin/manager/rep/compliance/medical/finance
#   （2026-08-11）受限端点**每次实时查库**（注入 db 会话）：token 里的 role/status 只是登录时刻快照
#   （最长 7 天），降级或停用后旧 token 立即失效——账号不存在/status != active → 403 "账号不存在或已停用"；
#   角色不符 → 403 "无权限"；403 统一抛 PermissionError（AppError）走共享 exception_handler 渲染 {code, message, data}

from shared.common.db_session import get_db
# async def api(db: Session = Depends(get_db)): ...

from shared.common.pagination import paginate, PaginationParams
from shared.common.exception_handler import register_exception_handlers
# register_exception_handlers(app)  # 在 main.py 中注册，自动转换 AppError → 统一响应

from shared.models.base import Base, TimestampMixin  # ORM 基类（id, created_at, updated_at）
```

错误码区间：1000-1999 参数 / 2000-2999 认证 / 3000-3999 权限 / 4000-4999 业务（含合规拦截）/ 5000-5999 系统 / 6000-6999 第三方。

shared 层自带测试 `shared/common/tests/`（test_internal_auth.py + conftest.py），从 `shared/` 目录跑：`python -m pytest common/tests/ -v`。

## main.py 标准模板

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
```

## Authentication

`auth-service`(:8007) 是唯一签发 JWT 的地方，两种登录方式共用一个 `/login`：

```
POST /api/v1/auth/send-code   {"phone":"138..."}                    → {expire_seconds}
POST /api/v1/auth/login       {"phone":"138...","code":"123456"}     → {token, user}   # 移动端
POST /api/v1/auth/login       {"username":"admin","password":"..."}  → {token, user}   # Web 后台
GET  /api/v1/auth/profile     (Bearer token)                        → user            # 移动端
GET  /api/v1/auth/me          (Bearer token)                        → user            # Web 后台，同一实现
```

约定：
- 错误信息统一模糊化（不区分"用户不存在"和"凭证错误"），避免账号枚举。
- 验证码一次性、5 分钟过期、60 秒重发冷却、单码最多校验 5 次（第 5 次仍有效，之后作废；用尽后响应文案与通用登录失败一致，防注册状态枚举）。
- `users.password_hash` 为 NULL 表示未设密码，任何密码都登录不了。用 `scripts/seed_admin.py` 设置。
- `profile`/`me` 每次从库里重读用户，被停用的账号即便持有有效 token 也会被拒。
- 短信通道可插拔（`app/services/sms.py`）：默认 `console` 只写日志；阿里云通道已实现（`AliyunSmsSender` 走 dysmsapi，缺 `AUTH_SMS_SIGN_NAME`/`AUTH_SMS_TEMPLATE_CODE` 或 `ALIYUN_ACCESS_KEY_ID`/`SECRET` 时构造即抛 `SmsSendError` fail-fast；配齐后 `AUTH_SMS_PROVIDER=aliyun` 生效，模板变量固定为 `{"code": ...}`）。

## Service-to-Service Communication

所有服务间调用**走 Gateway（`GATEWAY_URL`，默认 `http://localhost:8000`）**，不走直连端口。网关对三类路径区别对待（`auth_middleware.py`）：

```
# INTERNAL_PATHS —— 免 JWT，但必须带 X-Internal-Key 头（否则 403）
POST /api/v1/compliance/check
POST /api/v1/audit/log
POST /api/v1/hcps/profile-update
# PUBLIC_PATHS —— 真正公开（免 JWT 免 key）
POST /api/v1/auth/login
POST /api/v1/auth/send-code
# 另有 /health、/docs、/openapi.json、/redoc（网关自身路径；M11 缺口即指未认证可经 `..` 归一化拉 7 个后端 /docs/metrics）
```
（2026-08-06：`/api/v1/knowledge/search` 已移出 INTERNAL_PATHS —— 它是 web 检索的用户向接口，服务端挂 JWT 鉴权；`hcps/profile-update` 是 visit→hcp 的内部接口，双重校验齐全。）

- 内部接口是**双重校验**：网关要求 `X-Internal-Key`（`shared/common/internal_auth.py`），服务端路由还挂 `Depends(require_internal_key)` —— 防 8001-8006 端口直连绕过（历史上 audit/log 可被未认证者直接伪造）。
- 服务间客户端统一用 `internal_headers()` 加头（auth/specialist/visit/hcp 的 audit_client、compliance_client 都已接）。
- `INTERNAL_PATHS` 用"精确匹配或子路径"（`p + "/"`），不会像前缀匹配那样把 `/api/v1/audit/logs` 误判为内部路径；`PUBLIC_PATHS` 仍是前缀匹配，加条目前先确认不会顺带放开别的路由。`/api/v1/auth/profile` 和 `/api/v1/auth/me` 需要携带 token。

调用模式（内部客户端统一写法）：

```python
from shared.common.internal_auth import internal_headers
import httpx
async with httpx.AsyncClient(timeout=10.0) as client:
    resp = await client.post(
        f"{GATEWAY_URL}/api/v1/compliance/check",
        headers=internal_headers(),
        json={...},
    )
    return resp.json()["data"]
```

**降级策略：** 外部服务不可用时不得阻塞业务。合规客户端 fail-open（放行），审计客户端 fail-silent（记日志返回None），specialist 客户端返回 `degraded=True`。

## Database

PostgreSQL（Docker `postgres:15`），**14 张表**均在 `scripts/init_db.sql` 定义（users / products / digital_specialists / hcps / visit_records / conversations / knowledge_documents / audit_logs / compliance_rules / compliance_blocks / conversation_feedback / conversation_favorites / tasks / knowledge_feedback —— 后 4 张由迁移 003 补齐，已并入 init_db.sql；`visit_records.key_nodes`（006）与 `visit_records.status`（008）两列 2026-08-13 起也已并入 init_db.sql，旧库仍须按序执行 006/008）。连接通过 `shared/common/db_session.py` 的 `get_db` 依赖注入。常用 ORM 模式：

**审计表不可篡改（`scripts/migrations/002_audit_immutable.sql`）**：audit_logs 的 owner 是 NOLOGIN 占位角色 `medagent_audit_owner`；`medagent_audit`（审计服务专用，`AUDIT_DATABASE_URL` 配置）只有 INSERT/SELECT；`medagent` 只 SELECT。该 migration 还会把 medagent 从 superuser 降级（PostgreSQL 官方镜像默认把 `POSTGRES_USER` 设为 superuser，superuser 无视 REVOKE）。migration 只需执行一次（medagent 降级后无法重跑，补权限找表 owner 或单用户模式）。

```python
from shared.models.base import Base, TimestampMixin
class MyModel(Base, TimestampMixin):
    __tablename__ = "my_table"
    name = Column(String(100), nullable=False)
    tags = Column(JSONB)  # PostgreSQL JSONB
    status = Column(String(20), default="active")
```

## Compliance Rules

7 条规则（`shared/compliance-rules/rules.yaml`）：

| 规则 | 类型 | 动作 |
|------|------|------|
| R001 禁止承诺疗效 | keyword | **reject** |
| R002 禁止回扣暗示 | regex | **reject** |
| R003 禁止统方 | semantic (LLM) | **reject** |
| R004 禁止超适应症推广 | semantic | **reject** |
| R005 禁止贬低竞品 | semantic | **warn** (不拦截) |
| R006 禁止泄露患者信息 | semantic | **reject** |
| R007 禁止讨论未公开数据 | semantic | **warn** (不拦截) |

semantic 类规则依赖 `DASHSCOPE_API_KEY`（qwen-turbo），未配置时语义规则静默跳过。

**compliance 端点全集（2026-08-11 补记）：** `/check`（内部）、`/rules` + `/rules/reload` + `/rules/test`（admin/manager 管理，test 为规则试跑工具不入库）、`/redlines`（**净化版红线清单**——只含 rule_code/rule_name/rule_type/severity/action/description/enabled，绝不含 patterns/content，供 rep/移动端 HelpCenter 展示）、`/blocks` + `/blocks/{id}`（拦截记录）、`/blocks/stats?days=N&action=`（仪表盘热力图）、`/report/export`（3 Sheet 监管自查 xlsx）、`/stats`。2026-08-11 起除 /check /redlines 外全部 require_roles(*RULE_ADMIN_ROLES)。

**fast 模式（2026-08-11 流式门禁引入）**：`POST /api/v1/compliance/check` 支持 `fast` 参数（透传给 `checker.check(fast=True)`）——**跳过 LLM 语义层，只跑关键词/正则**（毫秒级），fast 命中不写 compliance_blocks、不计 COMPLIANCE_BLOCKS 指标（阻断时由调用方对完整文本做 full 复核统一记录）。供 specialist 流式逐帧门禁使用。

**语义检查安全行为（S7）**：内容包裹在 `<user_content>` 标记中（其中的任何指令都只是数据）；LLM 输出**解析失败**（JSON 错误/截断）时按违规拦截（R999, action=reject）——这是注入攻击与截断的迹象；**网络/API 错误同样 fail-closed**（2026-08-12 B5 批起 R999 收敛，此前"网络错误 fail-open"的描述已过时）。

## Bailian WebSocket Protocol

数字专员问答通过百炼多模态交互 WebSocket 协议实现（`specialist-service/app/services/bailian_client.py`），非 HTTP：

1. Connect → `wss://dashscope.aliyuncs.com/api-ws/v1/inference`
2. Start message: `{task_group: "aigc", task: "multimodal-generation", model: "multimodal-dialog"}`
3. 收到 `DialogStateChanged` → 发送 `RequestToRespond`
4. 接收 `RespondingContent` 流 → 解析答案
5. Stop → 完成

降级：百炼不可用时走通义千问直调（`qwen_client.py`，OpenAI 兼容接口），300 字符限制，不含知识库检索。需要 `BAILIAN_API_KEY`（与 `DASHSCOPE_API_KEY` 不同）。

**空答案兜底（2026-08-06 实测修复，commit 908af39）**：百炼 App **未发布**/知识库无内容时 WS 协议全程正常（Listening → 回声 → RespondingContent）但 `RespondingContent.text` 为空——`chat()` 无异常返回空串。`AnswerGenerator.generate/generate_stream` 现在对空答案抛 `BailianException` 统一走 qwen 降级（此前会空回答 + 合规审核对空 content 报 400）。排查：`python scripts/probe_bailian_ws.py` 直连 dump 帧；App 发布后降级 warning 应消失。

**聊天 WS 流式链路（2026-08-06 三批实施后，REST `/chat` 保留为降级；2026-08-11 加逐帧合规门禁）**：
- specialist：`BailianClient.chat_stream()`（逐帧 yield delta/done）→ `AnswerGenerator.generate_stream()`（合规预检 → 流式 → 答案合规审核 → 审计 → done 帧，字段与 REST 返回一致 + type）→ WS 端点 `/ws/specialists/{id}/chat?token=JWT`（`app/api/chat_ws.py`：token 无效关 4401、专员不存在关 4404、question 空/超时/异常关 4500；`start → delta* → done` 帧，done 前 `_persist_conversation` 落库并带 conversation_id；send 统一加锁防 ConcurrencyError）。
- **逐帧合规门禁（2026-08-11）**：delta 帧路径每帧对累积文本做 fast 检查（关键词/正则，毫秒级），命中即停——**违规帧不转发**；随后对完整文本 full 复核（含语义层，写 chat_blocked 审计 + compliance_blocks），产出 `compliance` 帧（blocked + violations）+ 掩码 done（"该问题建议直接咨询医学顾问。"）。降级路径（Bailian 异常 → qwen）整段输出前同样过门禁。chat_ws 不转发 compliance 帧（RN 端 default case 忽略未知帧，onDone 处理 blocked），协议与前端零改动。
- gateway：`/api/v1/specialists/{id}/chat/ws` 双向透传代理（token 原样转发，网关不重复鉴权——WS scope 不经 BaseHTTPMiddleware）。
- mobile：`mobile/src/services/wsChat.ts` 走网关 8000（question 帧缓冲到 onopen 后发送）；`ChatScreen` 流式渲染增量气泡，8s 未收到 start 自动降级 REST（specialistAPI.sendMessage），blocked/violations 按 REST 同款拼装展示。

## Frontend — web/（Web 管理后台）

Vite 5 + React 18 + TypeScript + AntD 5 + @ant-design/pro-components + @ant-design/charts，纯 SPA。开发时 vite 把 `/api` 和 `/health` 代理到网关 `localhost:8000`（`vite.config.ts`，/health 是 M54 网关状态卡探活），生产由反代同路径转发。

9 模块 11 路由（`web/src/constants/routes.ts`，懒加载）：仪表盘 `/dashboard`、数字专员 `/specialist/list` + `/specialist/create`、知识库 `/knowledge/list`、合规规则 `/compliance/list` + 拦截记录 `/compliance/blocks`、审计查询 `/audit/list`、医生管理 `/doctor/list` + `/doctor/:id`、用户管理 `/user/list`、系统配置 `/system/config`。另有登录页 `/login`。

API 约定：axios 实例 `web/src/services/client.ts`，`baseURL: '/api/v1'`；token 存 localStorage `medagent_token`，请求自动带 `Authorization: Bearer`。后端统一响应 `{code, message, data}`，分页接口的 data 是 `{items, total, page, page_size}`（见 `web/src/types/index.ts`）。非 401 的 4xx（含 403）由拦截器统一弹后端 message。

认证体系（2026-08-11 补记）：`context/AuthContext.tsx`（AuthProvider）持登录态，`pages/Login` 登录页，`components/RequireAuth.tsx` 路由守卫 + 401 跳登录，`services/auth.ts` 调 `/auth/login` + `/auth/me`；路由守卫只验登录态不验角色（M17 已知）。API 层按模块拆 `web/src/services/` 八文件（auth/audit/compliance/doctor/knowledge/specialist/system/user）。仪表盘另有 `components/LiveStatusStrip.tsx`（5s 轮询 live-status 迷你工位条，复用 `components/office/SpecialistCharacter.tsx` SVG 小人）。

**已知问题（2026-08-06 审计修复后，页面均已真实接线）**：
- 仪表盘：风险热力图（区域 × 近 7 天拦截量，数据来自 `GET /api/v1/compliance/blocks/stats`）、实时动态（审计日志 5s 轮询）、网关状态卡（真实探活 `/health`）
- 专员页：列表分页 + 创建/编辑/启停真实调用 + "数据"抽屉（stats）；知识库页：上传/审核/详情真实调用
- 系统配置页：只读展示配置状态（`GET /api/v1/system/config`，admin），配置经 .env 环境变量管理，不支持在线保存
- 新增端点：`/compliance/blocks/stats?days=N`（region join 失败自动降级 service 维度）、`/compliance/blocks/{id}`（完整内容+context）、`/system/config`（仅返回配置状态布尔，绝不返回密钥值）
- **医生管理缺口（2026-08-11 全文件审计确认）**：~~DoctorList「新增医生」按钮仅 message.info 占位~~（2026-08-11 已修 ModalForm 接线）；~~services/doctor.ts 的 AI 画像接口 GET /hcps/{id}/profile 已定义但无页面调用~~（2026-08-11 已修 DoctorDetail 画像卡片）；HealthDot.tsx 死代码（保留，可后续清理）；tsconfig.tsbuildinfo 残留（保留）

**数字员工办公室 3D 视图（2026-08-10 v4 完成 + 2026-08-11 视觉调优#2，已推 origin/master）**：专员列表页 `/specialist/list` Segmented 切换「办公室」视图 = 左侧 280px 出勤面板（AttendancePanel.tsx：环形出勤率/状态分布/今日对话/明细列表，与 3D 双向联动）+ 右侧 Three.js 3D 场景（**`three ^0.185.1` + `@types/three` 为唯一需老板拍板的额外依赖**，打破原零依赖约定；dependencies 常规项为 axios/dayjs/react-router-dom，注意 @types/three 在 dependencies 而非 devDependencies）。模块在 `web/src/components/office3d/`：
- `layout.ts` — 4×5=20 工位（COL_X 3.9 / ROW_Z 3.6，用户要求间距 1.5× 防拥挤；桌 2.08×1.17×0.96，人 1.3×）；`deskX/rowZ/sitPosOf/aislePosOf` 坐标函数
- `buildScene.ts` — CanvasTexture 深蓝网格地板 + 排间发光过道条
- `buildDesk.ts` — 白色工位（桌面 #f8fafc + 浅灰腿 + 浅蓝桌沿）+ 深色电脑；状态三色 emissive 脉动（working #1677ff 0.5↔1），offline 仅熄屏不变色
- `buildCharacter.ts` — 程序化白色人形（亮白主体 + 深炭四肢 #333），坐/站姿态插值 ≈0.4s（pose 0↔1）
- `simulation.ts` — 3s 轮询 `GET /api/v1/specialists/live-status` 数据驱动状态机：idle 过道巡逻 0.8u/s / working 走位 1.4u/s 到点坐下 / **offline 走回自己工位站立灰化**（target=sitPosOf(index)）；状态色 working #1677ff / idle #faad14 / offline #bfbfbf
- `labels.ts` — CSS2D 名牌（名字+状态色点+今日 N，y=2.0）
- `OfficeScene3D.tsx` — WebGL+CSS2DRenderer+rAF+raycast 选中操作卡（数据/编辑/停用·启用），相机 (0,13,12) / fov 45 / camTarget (0,0,0.5)

状态数据：后端 `live-status`（空时按 conversations 最近活跃推断，重启后 5 分钟降级窗口粗粒度报 working）。验证门 `cd web && npm run build`；E2E 在 `t10-office3d/e2e_v4.py`（**投影断言 project() 硬编码相机/布局常量，改相机或 layout.ts 必须同步改该脚本**）。

## Frontend — mobile/（React Native 移动端）

React Native 0.75 + TypeScript + react-navigation，原生工程已齐（2026-08-06 bring-up 完成，Pixel_7 模拟器全链路实测通过）。包名/bundle ID `com.medagent.mobile`，App 显示名 `MedAgent`，入口 `mobile/index.js` → `src/App.tsx`（app.json name 与 MainActivity/AppDelegate moduleName 必须一致，否则首启红屏）。

```bash
# 构建/运行（JDK 17 + ANDROID_HOME=D:\AndroidSDK + AVD Pixel_7 已就绪）
cd mobile/android && ./gradlew assembleDebug          # 出 app-debug.apk
"D:/AndroidSDK/emulator/emulator.exe" -avd Pixel_7 &  # 起模拟器
cd mobile && npx react-native start                   # Metro（Node v25 实测可用）
# git-bash 下 npx react-native run-android 调 gradlew.bat 会失败（'gradlew.bat' 不是内部或外部命令）→ 手动装：
cd mobile/android && ./gradlew.bat app:installDebug -PreactNativeDevServerPort=8081
adb shell am start -n com.medagent.mobile/.MainActivity
# 测试：cd mobile && npx jest（73 用例 = 契约 34 + wsChat 9 + asr 8 + tts 10 + asrStreaming 8 + date 4，锁 URL/method/body/响应形状；2026-08-13 核对）
```

结构：`mobile/src/navigation/AppNavigator.tsx`（Stack：登录 → 底部 4 Tab：工作台/对话/医生/我的 → 拜访/医生详情等子页）+ `navigation/types.ts`（导航参数类型；2026-08-13 确认旧记录的死路由 `HCPProfile`/`ComplianceRuleDetail` 已不存在，仅残留 HCPProfile 类型接口）；`mobile/src/api/` 按服务拆分（auth/compliance/content/hcp/specialist/visit 6 文件），统一走 `mobile/src/api/client.ts`：Android 模拟器 `http://10.0.2.2:8000`、iOS `localhost:8000`（都是网关）；登录态在 `mobile/src/store/AuthContext.tsx`（AsyncStorage 存 token，仅 401 才登出，网络抖动保留登录态）。**契约铁律：请求体/响应形状以 src/api/*.ts 为唯一映射点**（snake_case、分页解包都在这里做，不污染屏幕组件）；改动后端响应形状或端点后，先改 api 层 + 契约测试，再动屏幕。

其他模块（2026-08-11 全文件审计补记）：`src/components/` 六组件（Icon/EmptyState/EvidenceBadge/FAB/ProgressRing/VisitCard）、`src/constants/theme.ts`（设计令牌）、`src/utils/date.ts`（`formatLocalDate` 本地日期语义 + 4 测试）、`src/services/recorder.ts`（录音封装，`declare const atob` 绕 tsconfig 无 DOM lib）、`jest.setup.js`（mock AsyncStorage）。屏幕 17 个：Tab 4（Home/Specialists/HCPs——组件名 `HCPSearchScreen`/Profile）+ 子页 13（Chat/HCPDetail/VisitPrepare/VisitInProgress/VisitEnd/Content/ContentDetail/ComplianceManual/Settings/NotificationSettings/HelpCenter/VisitDetail/Login）。**Android Kotlin 目录是非标准布局**：`android/app/src/main/java/com/com.medagent.mobile/`（com 下直接套一个名为 `com.medagent.mobile` 的目录，非常规三段式）——Kotlin 不强制目录与包名一致，构建不受影响，但别按标准布局"整理"它。

**已知问题（2026-08-06 第四批后）**：
- 录音链路已接但 NLS_APPKEY 未配：`VisitInProgressScreen` 录音 → PCM 分片推 ASR WS，服务端未配置时发 error 帧 fail-closed（前端提示"NLS 识别通道未配置"，不产生假文本）；`ChatScreen` 语音按钮为入口提示 Alert（语音转写需在拜访中页使用——无拜访上下文），拜访中页为全链路流式语音输入。2026-08-12 真机联调已实测（Android 13+ 麦克风运行时权限 / message_id UUID / 流式三守卫等修复见 Known Gaps 已修批）；M19 已修复——轮询增量流式推流（录音中每 2s 读增量推送，stop 推完剩余并发 stop 帧）。
- 说话人标签已渲染（ASR 帧 speaker 字段，rep/doctor，缺省 rep）；服务端 NLS 分离参数名（enable_speaker_identity/speaker_diarization）待真机确认。
- 聊天 WS 流式已接（走网关 8000），未配真实百炼 key 时未做模拟器端到端冒烟。
- HelpCenter 已接合规规则接口（红线清单真实数据，reject 类规则）；联系方式仍为静态占位。
- iOS 未实际构建验证（本机无 Xcode；moduleName 已对齐，首次构建需实测）。

## Real-time ASR（实时转写）

> 配齐 NLS/百炼 key 后的真机联调步骤、待确认点与排障手册见 `docs/real-device-runbook.md`（真机需改 `mobile/src/config.ts` 的 `DEV_HOST` 为宿主机局域网 IP，见 runbook 2.4）。第 3 节后端冒烟基线已于 2026-08-06 实测回写（一键复跑：`python scripts/smoke_runbook.py`）。

实时转写链路已改用**阿里云实时语音识别**（听悟是离线批处理+3s 轮询，达不到方案的 <2s）：

- 服务端：`visit-service/app/services/realtime_asr.py`（`RealtimeAsrClient`：AK/SK 签名换 NLS 临时 Token → `wss://nls-gateway-cn-shanghai.aliyuncs.com/ws/v1?token=` → StartTranscription → 二进制 PCM 推流 → SentenceBegin/ResultChanged/SentenceEnd 事件；`enable_intermediate_result=true` 实时出字）。未配置 `NLS_APPKEY` 自动降级 `MockRealtimeAsrClient`（模拟文本，可联调）。
- WS 端点：`/ws/visits/{visit_id}/asr?token=<JWT>`（移动端推 PCM → 增量 JSON 回推 → 断句落库 conversation_transcript → 每句实时合规检查并回推 compliance 事件）。**注意 WS 不走网关**（网关 proxy 不支持升级），直连 visit-service:8002。
- 听悟客户端保留用于拜访后归档（完整音频离线转写）。
- 移动端接入点（已接，2026-08-06；M19 流式化 2026-08-11）：`react-native-audio-record` 录 WAV(16k/16bit/mono) → **流式推流**（M19 修复——录音期间每 2s 轮询读增量推送：Android 录音中读 `temp.pcm` 裸增量，iOS 读 WAV 增量；stop 后统一切 WAV，不再"录完再推"）→ 16KB 分片经 `mobile/src/services/asr.ts`（`connectAsrStreaming`）推 WS；`{"type":"stop"}` 结束；sentence 帧增量回填输入区，completed 帧回传末句全文走 `addTranscript` 落库。NLS_APPKEY 未配时服务端 fail-closed（error 帧 + 关 4500，不落假文本）。

## Known Gaps（后端已知缺口，勿误以为已实现）

已修（2026-08-04）：~~audit 零鉴权~~（S2）、~~"不可篡改"未生效~~（S3）、~~visit PUT 越权~~（S4）、~~零 RBAC~~（S6）、~~规则改动/审核不入审计~~、~~语义合规提示注入~~（S7）、~~prod 暴露公网~~（S8）、~~网关中间件顺序/预检 401~~（H10）、~~Excel 导出经网关 500~~（H11）、~~visit→specialist 401 永久 degraded~~（透传用户 JWT）、~~Web 仪表盘假数据~~、~~用户管理 404~~（`/api/v1/users`）、~~知识库 approve 反转~~、~~compliance_blocks 无写入方~~（check 端点拦截即入库，实测 R003 落表）、~~实时转写路线错误~~（服务端已切阿里云实时 ASR 流式链路 + WS 端点，实测 Mock 全链路；移动端录音待原生工程）。

已修（2026-08-05~06）：~~citations 恒空~~（百炼 extra_info.docs 解析引用溯源）、~~feedback/favorite 是桩~~（conversation_feedback/favorites 真落库，实测点赞 2 行 + 收藏 1 行含问答快照）、~~规则热更新只读 YAML~~（DB 规则加载，DB 覆盖 YAML + TTL 60s 重载）、~~移动端无法构建~~（RN 0.75.0 原生工程 + api 契约修复 7 处 + 契约测试 11 用例 + Pixel_7 实测全链路）、~~chat 无 conversation_id~~（前端反馈/收藏拿不到主键）、~~mobile 三处响应形状错位~~（specialist 纯数组、compliance 分页对象+字段名、favorite 必填 body 422）。

已修（2026-08-06 三批实施，23 提交本地未 push）：~~web 无登录页~~（AuthProvider + 登录页 + 路由守卫 + 401 跳转）、~~mobile 五屏零后端调用~~（VisitDetail/Profile/Settings 接真实接口、NotificationSettings AsyncStorage 持久化；HelpCenter 除外）、~~ContentScreen MOCK_CONTENT~~（接 knowledge API + 新增文档详情页）、~~移动端无录音/无 WS 客户端~~（录音库 + 权限 + asr.ts/wsChat.ts + 拜访页录音转写接线 + 聊天流式）、~~短信通道仅 ConsoleSender~~（AliyunSmsSender dysmsapi 真实现，缺配置 fail-fast，4 测试全 mock）、~~聊天一次性返回~~（specialist WS 端点 + 网关 WS 代理 + mobile 流式渲染 + 8s 降级 REST，question 帧缓冲到 onopen 发送）。

已修（2026-08-06 全仓审计三批修复，21 提交本地未 push，详见 docs/audit-report-2026-08-06.md）：
- ~~移动端拜访全流程断裂~~（start visit_id 契约/end 双调/假摘要删除/transcript 键位/WS 合规接线/VisitRecord 全字段映射）
- ~~分页契约错位~~（paginate 顶层 total/page/page_size 加法兼容）
- ~~互动历史两端必崩~~（hcp 返回裸数组 + 两端映射）；~~AI 画像/医生详情字段错位~~（mobile hcp 映射 + web 字段修复 + Android 标签弹窗）
- ~~会话历史 IDOR~~（归属校验三处）；~~compliance LLM 异常 fail-open~~（R999 收敛）；~~auth 审计客户端缺 before_value 致 PUT /users 500~~
- ~~INTERNAL_API_KEY 模板值绕过~~、~~网关 JWT_SECRET 默认回退~~（fail-fast）；~~manager 自授 admin~~（仅 admin 改角色 + 禁自改 + users 重读库）；~~验证码 off-by-one/枚举泄露~~；~~pre-visit 跨用户泄露~~；~~审计查询/导出无角色限制~~
- ~~knowledge/search 双向不可达~~（移出 INTERNAL_PATHS）；~~web 六页假动作~~（专员/合规/审计/用户/知识库/系统配置全部真实接线）；~~合规规则字段无校验~~；~~specialist 列表恒空/stats 双倍~~；~~gateway 限流 user_id 死代码/统一错误格式/WS 关闭码/health 假聚合~~
- ~~knowledge 审核流卡死/上传无校验/未上架泄露/ES 从未写入~~（ES 索引接线、驳回清索引、白名单+50MB、角色可见性）
- ~~dev/prod compose 审计写入失效~~（AUDIT_DATABASE_URL + :? 强校验）、~~deploy.yml 分支永不触发~~、~~e2e/debug 脚本过时~~、~~requirements.txt.tmp 残留~~

已修（2026-08-06 真机联调冒烟，commit 908af39/b7d2183）：
- ~~百炼空答案绕过降级~~（App 未发布时 RespondingContent.text 空 → 空回答 + 合规 400；现抛 BailianException 走 qwen 降级）
- 冒烟基线已建立（`scripts/smoke_runbook.py` 可一键复跑）：8 服务健康 / DEV_MODE 验证码登录 / 专员分页契约 / R001·R003 真实命中 / 审计 request_id 贯穿 —— 全部通过

已修（2026-08-11 四合规/安全债，commit e6c0d75..b63f736，已推 origin/master）：
- ~~require_roles 只信 token~~（降级/停用后旧 token 最长 7 天仍可访问受限端点 → 每次受限请求查库，role/status 以库为准，403 统一 PermissionError 渲染 {code,message,data}）
- ~~流式答案合规旁路~~（generate_stream 事后检查时违规文本已发出 → delta 逐帧 fast 门禁：跳语义层只跑关键词/正则，命中停发 + full 复核写审计/拦截记录 + compliance 帧 + 掩码 done；降级路径同门禁）
- ~~hcp mass assignment~~（create/update 白名单外字段 400 + repo _filter_writable 兜底，id/created_at/updated_at 不可覆盖，批量导入不受影响）
- ~~收藏多轮错配~~（toggle_favorite 以被收藏行为锚点取同轮问答，过滤 id<=锚点防快照到后续轮次）
- 配套测试：compliance TestFastMode、specialist 中流阻断/降级阻断、hcp repo+API 白名单、收藏 3 个多轮场景；8 服务回归全绿（audit 13/auth 44/compliance 43/specialist 70/hcp 27/visit 53/knowledge 44/gateway 26）（此为 2026-08-11 首批提交时的快照）

已修（2026-08-11 十项缺陷 + 向量链路根因，commit 012ab1a..2d0db2b + 6dce273，已推 origin/master；2026-08-11 全文件审计补记）：
- ~~十项缺陷 #1-#9~~：compliance /rules·/blocks·/stats 收紧 require_roles(*RULE_ADMIN_ROLES) + 新增净化版 `/redlines`（rep/移动端红线清单，无 patterns/content，mobile compliance.ts 已切换）；hcp /{id}/interactions 角色感知（rep 强制 user_id 过滤）；audit `logger.log()` 加 `**kwargs` 吸收未知键（原请求体未知键 → 500 审计静默丢失）；chat_ws 先 accept 再 close 4401/4404（旧实现 close 被握手 403 吞掉落 4500）；web 时间 3+1 处 UTC 解析；knowledge /feedback doc_id str() 强转；web UserList 编辑按角色（manager 不带 role / admin 禁自改）；mobile content.ts doc_type→type 映射（Tab 过滤恒空）；smoke_runbook 强制 SMOKE_PHONE + 冷却响应 data:null 防护
- ~~网关 WS 代理 websockets 15.x 适配~~（send_text/receive_text 在 15.x 改名 send/recv，AttributeError 被吞 → WS 流式转发实际一直坏的；_upstream_send/_upstream_recv 兼容适配，实机走网关 4401 + start→delta→done 全链路通过）
- ~~听悟 _parse_result 恒空~~（按真实 GetTaskInfo 结构解析 result.text/result.sentences，speaker_id=0 用 is not None；另驳回写审计、归档清索引、登录失败写审计一并补上）
- ~~**向量化链路从未真正生效**~~（EMBEDDING_DIM=1536 是错误假设，text-embedding-v3 最大 1024 维 → collection 以 1536 建库，每次 upsert 维度不匹配**静默失败**（DashVector 响应式 API 不抛异常 + 代码不查返回码），文档全部"上架成功但向量缺失"；已修 EMBEDDING_DIM=1024 + upsert/create 响应码检查（失败 raise）+ **删除重建 collection**；delete_doc 双 bug——Collection.delete 不支持 filter + filter 字符串必须双引号，改先 query(filter) 再 delete(ids=)）
- ~~网关 knowledge 路由超时 30s→120s~~（百炼导入 ~28s + 向量化，30s 网关先断 → "业务完成但客户端 504"）
- 测试基线（2026-08-11 快照）：audit 19 / auth 50 / compliance 59 / gateway 38 / hcp 36 / knowledge 51 / specialist 71 / visit 61 = **385 passed**；mobile jest 70；web build PASS

已修（2026-08-11 第二批：web 医生管理 + 移动端语音链路，用户逐项拍板后实施）：
- ~~web 新增医生占位 / AI 画像未展示~~（ModalForm 真实接线 POST /hcps；DoctorDetail 画像卡片含降级兼容；画像映射移植 mobile hcp.ts）
- ~~移动端语音输入 stub~~（真实链路已接：录音 → PCM → visit-service WS → NLS；M19 修复：录完突发推流改轮询增量流式推流，服务端 asr_ws.py 零改动）
- ~~听悟 TTS 未接~~（新端点 GET /api/v1/nls/tts-token 下发 {token, appkey, expires_at}，复用 realtime_asr.get_nls_token；mobile tts.ts 直调 NLS REST 合成 + react-native-sound 播放；未配 NLS_APPKEY 时 4xxx 报错、按钮禁用提示）
- ~~关键节点标记/话术建议实时推荐（后续版本）~~（visit-service process_transcript 节流 20s + ≥6 字触发 qwen-plus 生成 {key_nodes, suggestion}，失败降级不阻塞；落库 visit_records.key_nodes（迁移 006）；transcript 响应新增 key_nodes/ai_suggestion；mobile 拜访中「AI 实时推荐」区展示 + 话术朗读）
- ~~NLS_APPKEY 未配~~（.env 配置位就绪；NLS_MOCK=1 联调）
- ~~百炼 App 未发布 → 对话恒降级 qwen~~（用户确认已发布，降级解决）
- mobile host 集中：src/config.ts（API/ASR/聊天 WS 三处，真机改一处）

已修（2026-08-12 真机联调批，commit ff2db8d..6290e1f，已推 origin/master）：
- ~~end_visit 经专员链路中转~~（百炼 App 输出是聊天式散文，发布与否都满足不了 end_visit 的 JSON 契约，旧流程白付专员 ~8.4s + 二次生成 ~3.1s → 直调 qwen-max JSON prompt 一次生成 ~3-9s；**时间墙 = qwen-max 生成延迟**，qwen-flash ~2.4s 可把 `visit_manager.py` 的 `model="qwen-max"` 换名一键切换）
- ~~end_visit 空转写写出空总结/合规 400~~（qwen 返回合法 JSON 但 summary 为空（空转写偶发）→ 视为不可用写占位串可重试；无转写内容直接占位串不发 AI 调用；转写合规预检与 qwen 生成**并发**执行；画像更新 fire-and-forget 不阻塞主流程）
- ~~end_visit 请求体必填~~（移动端不带 body 422 弹"请求失败" → 改可选，接口签名兼容）
- ~~hcp /profile 同步 LLM 占死事件循环~~（画像生成 8s 期间同网关 /hcps/{id}、/interactions 全部排队 7.7s → asyncio.to_thread 线程池；test_profile_event_loop.py 回归）
- ~~specialist 空内容帧白等~~（App 未发布时空内容帧 150ms/帧 × 60 帧上限白等 ~9.2s → 连续 8 帧空文本提前降级 qwen ~1.2s；test_bailian_empty_fallback.py）
- ~~NLS message_id 非 UUID~~（真实联调发现 task_id-N 被网关 40000002 MESSAGE_INVALID 拒绝 → 32 位 hex UUID）
- ~~Android 录音静默失败~~（Android 13+ 麦克风运行时权限请求）+ ~~异议列表 key 冲突~~（全局唯一 key）
- ~~录音双按双会话泄漏~~（press 入口同步防重入）；~~TTS 合成无超时~~（30s 超时 + 播放初始化错误透传底层信息）；~~asr 流式推流三处竞态~~（轮询重入门禁 / 空块自旋终止 / flush 串行链）
- 测试基线（2026-08-12 全量修复批后）：audit 19 / auth 50 / compliance 59 / gateway 40 / hcp 38 / knowledge 51 / specialist 74 / visit 73 = **404 passed**；mobile jest 70（6 套件）；web build PASS

已修（2026-08-13 全项目审查修复批，9 域并行审查 320 文件 + 11 域并行修复，7 高 23 中全修）：
- ~~web manager 编辑用户必 403~~（UserList 仅手机号变化才带 phone + 非 admin 禁编辑手机号）；~~compliance 禁用 YAML 源规则无效~~（_load_db_rules 加载全量行、DB disabled 覆盖 YAML、单点过滤；update_rule content 非 dict 400 防毒化 DB 规则加载）
- ~~mobile 今日拜访恒空~~（date_to 传 T23:59:59）；~~聊天违规明细恒空~~（matched_text/reason 兜底）；~~AI 占位串误判 completed~~（识别占位串 retryable + VisitEnd 重试）；~~start_visit 静默丢字段~~（不发送 + UI 注明仅本次参考）
- ~~备份 OSS 30 天清理正则死~~（\d{6}）；~~init_db.sql 缺 006/008 列~~（visit_records 补 key_nodes/status，旧库仍跑 006/008）；~~restore 生产建库必挂~~（--pg-user + PG_ROOT_PASSWORD）；~~load_config .env 非空默认键覆盖失效~~；~~smoke 断言恒绿~~（blocked/violations 真断言 + 非零退出）；~~docker-verify 漏 auth~~；~~ci-pipeline 非法 Flow YAML~~（按官方语法重写，lint 不再 || true，测试覆盖 8 服务+shared+web+mobile）
- ~~visit qwen 无超时~~（60s/重试 1）；~~_llm_recommend 行锁跨 LLM~~（冷却无锁读、LLM 锁外、短持锁追加+populate_existing 真重读）；~~WS 丢 warn 违规~~（violations 非空即推帧+落库）；~~异议语义层畸形输出 500~~（形状校验坏项跳过）；~~末句 REST 双写~~（尾缀去重 duplicate:true）
- ~~specialist 流式门禁重复拼接~~（accumulated=帧全量）；~~流式传输异常绕过降级~~（chat_stream 统一转 BailianException）；~~降级同步调 qwen~~（to_thread+30s 超时）；~~/feedback 跨用户~~（require_roles admin/manager）
- ~~验证码并发复用~~（Lua consume-if-match：计数+比较+DEL 单脚本原子）；~~hcp 画像 qwen 无超时~~（30s）；~~网关 XFF 失真~~（TRUSTED_PROXY_CIDRS 信任代理才保留注入头，默认行为不变）；~~knowledge 索引先于终态写入~~（先 _finish_approve 后写索引）；~~knowledge 检索阻塞事件循环~~（to_thread）；~~prod compose env_file 指向不存在路径~~（../.env + 运行命令注释）；~~arms-monitor 告警死配置~~（PromQL+完整参数+List 后 Update 幂等）
- 测试基线（2026-08-13 修复批后）：audit 19 / auth 56 / compliance 64 / gateway 46 / hcp 39 / knowledge 57 / specialist 85 / visit 87 = **459 passed**；mobile jest 73；web build PASS
- 已修（2026-08-12 全量修复批，B1-B7，本地未提交）：~~拜访无显式取消~~（POST /visits/{id}/cancel + visit_records.status 列，迁移 008 待实跑）、~~end_visit 重复结束报错~~（行锁 + 移动端 getById fallback）、~~follow_up 依赖专员链路常 degraded~~（直调 qwen）、~~模拟输入注入假转写~~（删 simulateInput 改真实文本输入）、~~拜访任务/收藏无移动端页面~~（TaskList/Favorites 新页 + Profile 真实计数）、~~web 无拜访管理页~~（VisitList + 任务展示）、~~专员数据抽屉无反馈明细~~（新接口 GET /specialists/{id}/feedback）、~~manager 可改他人手机号接管账号~~（仅 admin）、~~合规检查 fail-open~~（两处 client 抛异常 + 语义层网络错误 R999 拦截）、~~验证码并发可重放~~（Redis Lua 原子消耗）、~~生产可用 console 短信打印验证码~~（非 dev 禁 console 通道）、~~网关 CORS 全放行~~（env 白名单）、~~网关 WS 零鉴权 + token 明文 query~~（网关验 token + 首帧 auth 帧协议，保留 query 兜底）、~~XFF 伪造透传~~（网关覆盖为真实对端）、~~默认 DB 密码生产可用~~（shared/db_session 启动守卫）、~~审计 keyword 参数被忽略~~（ILIKE 多字段搜索）、~~HCP 标签仅 admin/manager~~（放开任意登录用户）、~~live-status 泄露他人问题内容~~（非 admin 剥离 snippet）、~~ES 检索含未上架文档~~（status=ready 过滤）、~~knowledge search product_id 非 int 500~~（显式校验）、~~备份静默回退默认密码~~（DB_USER/DB_PASSWORD + fail-fast + 秒级时间戳）、~~pg_restore 部分失败假成功~~（--exit-on-error）、~~docker-verify 构建失败被 tail 掩盖~~（pipefail）、~~通知页 4 个死开关~~（改"即将上线"）

**仍为假数据/未实现（勿误以为已做，2026-08-06 第四批后更新）**：
- 需求级缺口（用户暂缓）：飞书导入/双向同步、知识库内容库（`knowledge-base/` 空目录，方案要求 100-300 篇文献）、ES 真实实例（ES_URL 配置才启用，索引接线已做；ES_URL 未进 .env.example）、表格/图片 OCR 自动解析（依赖百炼云）、web 检索测试页
- ~~web 医生管理：DoctorList「新增医生」按钮仅占位提示（无真实新增）；AI 画像接口 GET /hcps/{id}/profile 已定义但页面未展示（2026-08-11 全文件审计确认）~~（2026-08-11 已修：ModalForm 真实接线 + DoctorDetail AI 画像卡片）
- 移动端：~~语音输入仍是 stub~~（2026-08-11 已修：真实链路已接 + 流式推流）；~~关键节点标记/话术建议实时推荐（需求标"后续版本"）~~（2026-08-11 已做 LLM 版：visit-service 节流推荐 + mobile 推荐区）；~~听悟 TTS 未接~~（2026-08-11 已接：NLS REST 合成 + mobile 朗读按钮）
- NLS_APPKEY 已在 .env 配置位就绪（用户填真实 AppKey 后生效；开发联调 NLS_MOCK=1，Mock 文本不落库）；说话人分离参数名（enable_speaker_identity/speaker_diarization）待真机确认
- ~~百炼 App 未发布（对话恒降级 qwen）~~（用户确认已发布，对话降级已解决）
- 真机端到端部分实测（2026-08-12：录音流式推流 / TTS / 麦克风权限 / message_id 已真机联调并修复，见 Known Gaps 已修批；说话人分离参数名待最终确认；host 已集中 mobile/src/config.ts，见 runbook 2.4）
- 短信默认仍 console（未配签名/模板 CODE 时，验证码捞 `logs/native/auth-service.log`；配齐后 `AUTH_SMS_PROVIDER=aliyun` 生效）
- 系统配置经 .env 环境变量管理（web 只读展示配置状态，不支持在线保存——见 `GET /api/v1/system/config`）
- ~~网关限流为单进程内存版（--workers 2 时每 worker 独立限额）~~（486d440 接 Redis 分布式滑动窗口，内存版仅降级兜底）；compliance 的 REQUESTS 计数未接线（可照 specialist 中间件扩展）

**审计确认的技术债（2026-08-06，勿误以为已修；划线=已修，2026-08-11）**：
- ~~**听悟离线归档转写必然失败**：`visit-service/app/services/tingwu_client.py:83-96` 的 `_parse_result` 未处理 GetTaskInfo 返回的"带签名 URL 的 dict/JSON 字符串"结果（dict 取 None、str 抛 AttributeError）~~（6dce273 已按真实 GetTaskInfo 结构重写 `_parse_result`）
- ~~**流式答案合规审核旁路**：`specialist-service` 的 `generate_stream` 边生成边推送，答案合规审核在全文推送后才执行——被拦时违规内容已展示（REST 路径语义正确）~~（e6c0d75 起逐帧 fast 门禁，违规帧不转发）
- ~~**收藏多轮错配**：`conversations.py:77-82` 收藏锚定某轮 assistant 行，但 question/answer 取 session 第一条 → 多轮会话收藏展示错对问答~~（b63f736 以被收藏行为锚点取同轮问答）
- **无整体超时熔断**：bailian_client 每帧 wait_for 30s × 60 帧上限，最坏单条 chat 可挂约 30 分钟；证据等级为被动正则，降级（qwen）模式恒 None
- ~~**hcp mass assignment**：`hcp_repo.py:99-103` update 用 hasattr 放行任意列（可改主键/时间戳）~~（61144da API 层白名单 400 + repo 层 _filter_writable 兜底）；~~**AI 画像无缓存**（每次 /profile 付费调 qwen-max 且不落库）~~（2485943 HcpCache Redis 缓存 hcp:{id}+profile:{id}，TTL 300s，写路径失效）；`update_hcp_profile_from_visit` 的 tags 字符串按字符迭代
- ~~**knowledge 审核同步阻塞**：`review_document`/`upload_document` 在 async 端点同步执行百炼轮询（最长 1h），阻塞事件循环~~（7422a74 线程池 + 原子抢占）；PG 'simple' 分词不切中文（ts_rank 恒 0）
- ~~**compliance service_name 失真**：`rules.py:68` 把内容类型（user_input/ai_output）写进 service_name 列（调用方不传 service_name）→ 监管报告"按服务"统计显示的是内容类型；`checked_rules` 是假数据（全量规则 id 覆盖，含未执行的语义规则）~~（4e770a6 specialist/visit 客户端请求体显式传 service_name、缺省 unknown；checked_rules 只列实际执行的规则——keyword/regex 全跑、semantic 仅 LLM 真会调用时列入，无违规也返回真实覆盖面）；~~warn/log 违规也计入拦截计数~~（85aebf3 compliance_blocks_total 只计 reject，新增 violations_total 全量 + semantic 缺 key 剔除可观测，/blocks/stats 加 action 参数）
- **audit 导出 1 万条静默截断**（logs.py:155）、~~`logger.log()` 无 `**kwargs`（调用方新增字段键会 TypeError 被吞）~~（2026-08-11 十项缺陷 #3 已加 **kwargs 吸收）；~~`AUDIT_LOG_RETENTION_DAYS` 死配置~~（f50a8de lifespan 定时清理 + medagent_audit_cleanup 专职角色，迁移 005 需 superuser）
- 网关 JSON 分支内容长度经 `response.json()` 重序列化后透传上游 content-length（当前全栈 FastAPI 字节一致，属潜在失配）

**2026-08-11 全量审计（8 域 8 代理并行，60 发现合并去重，用户确认仅归档暂缓修复；划线=已修）**：
- ~~**H1 JWT_SECRET 静默默认回退 + 6 业务服务无 fail-fast 守卫**：`shared/common/auth.py:29,48` `os.getenv("JWT_SECRET", "dev-secret-change-me")` 同时用于 create_token/verify_token，specialist/visit/knowledge/compliance/hcp/audit 均无启动守卫（仅 auth/gateway 有）→ 漏配时可用公开密钥伪造任意角色 token 直连 8001-8007。修法：守卫下沉 shared 或各服务 main.py 统一 fail-fast，默认回退从 shared 移除~~（2026-08-11 已修：shared `WEAK_JWT_SECRETS` + `validate_jwt_secret` fail-fast，6 服务 main.py 启动守卫，config 默认值删除，test_jwt_failfast.py 回归）
- ~~**H2 停用/降级账号旧 token 7 天内仍有效**（require_roles 实时查库只覆盖受限端点）：`get_current_user`（auth.py:64-74）只信 token 快照 → 停用 admin 旧 token 可经 admin 旁路操作他人收藏/对话（`conversations.py:30,163` 的 `current_user.get("role") != "admin"`）、knowledge 未上架文档可见性（`_can_view_all_documents` 读 token role）、visit WS/REST 归属与 admin 判定、specialist/visit 两个 WS 端点。修法：状态/角色查库下沉 get_current_user 与 WS 鉴权公共路径~~（2026-08-11 已修：get_current_user 每次请求主键查库 401 code 2003，chat_ws/asr_ws 同语义 4401，specialist/visit/audit/auth 停用用例）
- ~~**H3 hcp /profile 画像跨用户泄露**：`hcps.py:93-125` 只挂 get_current_user（无角色限制）；`profile_generator.py:46` 调 `list_interactions(db, hcp.id)` 不传 user_id（SQL `:user_id IS NULL` 不过滤，注释写明"仅 admin/manager 使用"但接口未接角色校验）→ 任意 rep 可拉含全部代表互动细节（ai_summary/key_points/objections）的画像，profile:{id} 全用户共享缓存。修法：接口挂 require_roles 或按 user_id 过滤~~（2026-08-11 已修：admin/manager 全量 :all，rep 本人 :u{uid}，缓存分键 + scan_iter 前缀失效，profile_generator user_id 过滤）
- ~~**H4 knowledge 审核状态机竞态**：`document_manager.py:142` approve 抢占 processing（百炼导入最长 1h）后 `update_status(doc_id, "ready")` 无条件写终态；reject 允许 draft/processing/ready 驳回（:190）→ 审核期间驳回/归档被 1h 后翻回 ready 重新上架。修法：终态条件更新（`WHERE status='processing'`），驳回同样原子抢占~~（2026-08-11 已修：try_mark_final/try_restore_status 条件更新，approve_without_bailian 补同锁，竞态单测 2 例）
- **H5 mobile 全链路明文 HTTP/WS**：`client.ts:10`/`wsChat.ts:7`/`asr.ts:10` JWT 与患者对话明文传输可被中间人截获
- **H6 WS token 明文 query string + 网关 WS 零鉴权零限流**：`gateway main.py:362-381` proxy_chat_ws accept 前不验 token 不限流，token 原样透传上游；mobile `wsChat.ts:42`/`asr.ts:33` 拼 URL；specialist `chat_ws.py:58`、visit `asr_ws.py:73-85` 依赖 query token。修法：网关握手前验 token + 按 user_id 限流，token 改 Sec-WebSocket-Protocol 或首帧
- **M1 compliance 语义层 fail-open 覆盖"内容拒审"**：`checker.py:336-352` fail-closed 元组只收 (JSONDecodeError, KeyError, TypeError, ValueError)，内容过滤/拒答以 HTTP 400（BadRequestError，属 Exception）落入宽 except fail-open → R003/R004/R006 整体跳过，与 S7 口径冲突。修法：4xx 内容策略类异常归 R999 fail-closed，仅超时/连接类 fail-open
- **M2 compliance Unicode 变体绕过**：`checker.py:232-243` 匹配前无 NFKC/零宽字符剥离 → "１００％有效"、插 U+200B、"返 点"绕过 R001/R002，且 fast 流式门禁只跑文本层整体跳过
- **M3 compliance 同步 LLM 阻塞事件循环**：`checker.py:287-295` 同步 create 跑 async 端点（默认超时 600s）→ LLM 变慢时 specialist/visit 调用方 10s 超时系统性 fail-open。修法：asyncio.to_thread + timeout 15s
- **M4 compliance xlsx 导出公式注入**：`report.py:43-47` 拦截明细/规则快照原样写入 → `=HYPERLINK(...)`/`=cmd|` 开头内容按公式执行；audit 导出（logs.py:178-190）字符串列同理。修法：`= + - @ \t \r` 开头前置单引号或强制 data_type='s'
- **M5 visit full_transcript 可覆盖真实转写**：`visit_manager.py:515-517` 客户端提交整段覆盖 conversation_transcript 且覆盖后不再过合规检查 → 被标记过 R002/R006 的对话可被洗白。修法：提交前全量合规检查并累加 compliance_flags，或仅允许追加 + 前缀匹配校验
- **M6 visit follow_up 结构化输出零合规检查**：`visit_manager.py:561-569` 只查 ai_summary，key_points/hcp_interests/hcp_objections/follow_up_suggestions/next_visit_plan 及自动建任务完全不过合规
- **M7 visit LLM prompt 注入**：`visit_manager.py:336-359/519-537/622-636`、`objection_detector.py:92-93` 用户可控转写/画像/历史无 `<user_content>` 定界直接内插（与 compliance S7 已修标准不一致）
- **M8 specialist fast 门禁不覆盖语义层**：违规内容在 full 复核前到达客户端（fast 只跑 keyword/regex）
- **M9 密码登录无账号级失败锁定**：`auth.py:263-272` 仅受网关 60/min/IP 限流，轮换 IP 可无限试弱密码。修法：Redis 账号级失败计数 + 临时锁定
- **M10 网关限流不读 X-Forwarded-For**：`rate_limiter.py:154-158` 取 request.client.host → 反代部署下全站共享一桶，刷 login/send-code 可整体 DoS
- **M11 网关 `..` 路径归一化绕过公开前缀**：`main.py:257` + `auth_middleware.py:110-116`，`/api/v1/auth/login/../../docs` 命中 PUBLIC_PATHS 免 JWT 且 httpx 建连归一化 → 未认证可拉全部 7 后端 /docs、/openapi.json、/metrics
- **M12 knowledge 解压炸弹**：50MB 只管压缩体积，`document_processor.py:8-33` 解压/渲染到内存无输出上限 → approve 线程池撑爆。修法：页数/文本长度硬上限 + 解析超时
- **M13 hcp Excel 批量导入无大小限制**（zip 炸弹）
- **M14 visit ASR WS 直连 8002 无连接数/帧大小/时长限制**（绕过网关限流，每条连接拉一条 NLS 付费会话 + conversation_transcript 无限追加 + 无界并发合规调用）
- **M15 visit 合规内部调用与用户请求共用网关 IP 限流配额**：`rate_limiter.py:145-171` 内部路径无豁免 → 多 ASR 并发超 60/min 后合规 429 → 客户端 fail-open 静默放行且无告警
- **M16 specialist chat 无长度/并发限制**（网关 WS 绕过限流）
- **M17 web localStorage JWT 无 CSP + 前端零角色访问控制**（`client.ts:10`/`AuthContext.tsx:37`；`App.tsx:43-64` 路由守卫只验登录态）
- **M18 specialist /live-status question_snippet 跨用户**（`specialists.py:101` + `activity_registry.py:54`）
- **Low 批**（归档）：mobile release debug 签名（build.gradle:53-60）/AsyncStorage 明文 JWT/无 FLAG_SECURE/~~401 无全局登出~~（已实现：client.ts onUnauthorized + AuthContext 全局登出，仅 401/2000-2003 触发）；web CORS `*`+credentials（gateway main.py:68-69）、/health 泄露 backends 内网拓扑（:147-165）；specialist draft/disabled 专员配置对所有登录用户可见、默认 DB 口令硬编码（db_session.py:13-16）、/metrics 无鉴权；knowledge 上传仅校验扩展名不校验魔数（XSS 载体）、/search-test 泄露内部异常、/stats 泄露云资源 ID 与未上架计数、检索参数健壮性（product_id 非法值静默丢过滤/无长度限制）、feedback doc_id 不校验、被驳回文档百炼索引未清理（降级路径仍可命中）；compliance 报告导出无上限（report.py:90）、正则 ReDoS 可入库（rules.py:90-95）、审计 client_ip 信 XFF 首段（logs.py:280-285）、拦截记录/审计 JSONB 明文留存敏感片段；visit audio_url 无 scheme/域名校验（tingwu_client.py:50-53 SSRF/费用滥用）、end_visit 状态锁非原子 + 任务幂等 TOCTOU、NLS 会话失败静默吞掉无 error 帧、任务状态变更无审计日志；auth 验证码取号/作废非原子（code_store.py:92-111 并发可用两次）、审计 client_ip 可被 XFF 伪造

## Backup & Restore（2026-08-12 新增）

- **每日自动备份**：`scripts/backup_db.py` —— pg_dump -Fc 全量 → pg_restore --list 校验 → OSS 上传（ACL 私有）→ 本地 7 天 / OSS 30 天过期清理。ECS crontab：
  `0 2 * * * cd /opt/medagent && python scripts/backup_db.py`
  （**不要加 `>> logs/backup.log 2>&1`**：脚本 log() 已自写 backup.log，加重定向每行日志双写）
- **ECS 上线顺序**：① 以 medagent_root 执行 `scripts/migrations/007_grant_audit_seq.sql`（002 降级后 medagent 无 superuser 无法自行 GRANT，缺了首次备份必挂）→ ② .env 填 OSS_* 凭证 → ③ 配 cron → ④ 手动跑一次 `backup_db.py` 验证
- **失败留痕**：`logs/backup.log` 追加 + `logs/backup-failed` 标记文件 + 非零退出码。可用 cron MAILTO 或阿里云 CloudMonitor 自定义监控检查标记文件感知失败；开发环境无 OSS 凭证时用 `--local-only`（本地备份+校验，不上传）
- **恢复验证**：`python scripts/restore_db.py --source local|oss [--dump 文件] [--target-db 库] [--yes] [--pg-user 用户]` —— 默认恢复到 `medagent_restore` 临时库并校验 users/conversations/audit_logs 行数，**不自动覆盖生产库**；`--target-db` 仅允许 `[A-Za-z0-9_]+`（防注入）。恢复生产库：停服务 → `DROP DATABASE medagent WITH (FORCE)` → restore --target-db medagent --yes → 启服务
- **2026-08-13 修复**：ensure_target_db 的 CREATE DATABASE 改用 `--pg-user`（默认 medagent）。生产已执行 002 降级后 medagent 无 CREATEDB，恢复演练/灾备必须 `--pg-user medagent_root` 并配置 `PG_ROOT_PASSWORD`（.env.example 已有配置位；未配时 RuntimeError 不静默回退）。OSS 30 天过期清理正则已与秒级文件名一致（\d{6}）
- **恢复后注意**：audit_logs 所有权/权限（002 审计不可篡改迁移）需在新库重新执行；Redis 不备份（缓存数据可重建）；二进制输出经 docker exec 直写文件（Windows CRLF 安全）
- **2026-08-12 已验证**（本机全链路真实）：备份→校验→OSS 上传/过期清理（含删除测试对象无残留）→ 恢复 local+oss 双源三表行数一致（users 2/conversations 178/audit_logs 1418）→ 失败留痕三路径（dump 损坏/取消/非法库名均非零退出）→ 007 幂等重跑

## Gotchas

- **Docker build context 是仓库根目录**：所有镜像都要 `COPY shared/`，所以 Dockerfile 里的路径都写成 `services/<name>/...`，构建时用 `docker build -f services/<name>/Dockerfile .`。docker-compose 里已配好 `context: .`。
- **容器内不能用 localhost**：`.env` 里的 `DATABASE_URL`/`REDIS_URL`/`GATEWAY_URL` 是给宿主机直跑 uvicorn 用的。docker-compose 用 `environment` 覆盖成 compose 服务名（`postgres`/`redis`/`gateway`）。
- **`JWT_SECRET` 必须配**：auth-service 检测到未配置或仍是默认值会拒绝启动（否则会签出可伪造的 token）。生成：`openssl rand -hex 32`。
- **`INTERNAL_API_KEY` 必须配**：`shared/common/internal_auth.py` 检测到未配置或默认值会抛 RuntimeError —— 网关/所有服务都依赖它做内部接口鉴权。生成：`openssl rand -hex 32`，网关与所有服务必须一致（`env_file: .env` 天然保证）。
- **`AUTH_DEV_MODE=true` 只能本地用**：打开后 `send-code` 会在响应体里回传验证码。
- **验证码存 Redis，不 fail-open**：Redis 挂了 `send-code`/`login` 直接返回 5004，不放行。
- **Windows GBK 控制台**：不能输出 ✓ / ✔ / emoji，否则 `UnicodeEncodeError`。用中文标记代替（如"达标"）。
- **测试从服务目录跑**：`sys.path` 依赖 `os.path.join(__file__, "..", "..", "..")` 找到 shared，从项目根目录执行会 `ModuleNotFoundError: No module named 'app'`。
- **SQLite 单测建表要限定表名**：`shared.models` 里 products/hcps 等用了 PostgreSQL 的 JSONB，SQLite 渲染不了；且 `TimestampMixin` 的 `BigInteger` 主键在 SQLite 下不自增，需显式给 id。内存 SQLite 还要用 `StaticPool` 才能跨 session 共享。参考 `services/auth-service/tests/test_auth.py`。
- **JWT 用 PyJWT（`import jwt`）**：`requirements.txt` 里声明的是 `PyJWT>=2.8.0`。历史上写过 `python-jose[cryptogram]`（拼写错误的空 extra，且代码从未 import jose），已全部清除，不要加回来。
- **服务间调用绕网关**：不要在代码里写 `http://localhost:8004` 调合规服务，走 `GATEWAY_URL + /api/v1/compliance/check`，否则 JWT 认证会拦截（除非已加入 Gateway 白名单）。
- **合规规则文件路径**：`RULES_YAML_PATH` 环境变量指定，容器内是 `/app/shared/compliance-rules/rules.yaml`。加载到 0 条规则会打 ERROR —— 那是"全部放行"的危险状态。
- **`.env` 在 `.gitignore` 中**：根目录 `.env` 不会被提交，模板见 `.env.example`。
- **hcp-service 的 visit_interaction_repo**：同库直读 `visit_records` 表（避免循环依赖），表不存在时降级为空列表。如果 visit-service 和 hcp-service 不在同一个 DB，需要改为 HTTP 调用。
- **visit_records 有 status 列**（迁移 008 新增，2026-08-13 起已并入 init_db.sql）：completed/in_progress 语义仍从 ai_summary 推导（占位串 ≠ 已结束，可重试 end），cancelled 是显式状态；旧库须跑 006/008。
- **前端字段 camelCase、后端 snake_case**：映射统一收在 `mobile/src/api/*.ts`（`prepareVisit` 等已修，2026-08-06 实测 pre-visit 200）。改后端 schema 或响应形状时，同步改 api 层 + 契约测试，屏幕组件只消费 api 层的映射结果，不直接碰请求体。
- **跨服务 FK 需要注册元数据**：`visit_records` 的 FK 引用 hcps/products/digital_specialists，visit-service 必须 import `shared.models.hcp`/`product`/`digital_specialist`（见 `services/visit-service/app/models/visit_record.py`），否则 SQLAlchemy 报 `NoReferencedTableError`。共享模型放 `shared/models/`，各服务 `app/models/*.py` 是 re-export。
- **Commit 格式**：遵循 conventional commits `feat(scope): subject`，末尾 `Co-Authored-By: Claude <noreply@anthropic.com>`。
- **005 迁移（audit 清理角色）需 superuser**：002 后无 superuser，GRANT DELETE 会失败；现场已用 `postgres --single` 单用户模式建 `medagent_root`（rolsuper=t，NOLOGIN）与 `medagent_audit_cleanup`（仅 SELECT+DELETE on audit_logs），应用账号仍仅 INSERT/SELECT。新环境跑 005 前先造 superuser（停容器 → `echo "SQL" | postgres --single -D <datadir> medagent`，-c 参数会被 entrypoint 截胡）。配套环境变量 `AUDIT_CLEANUP_DATABASE_URL`（medagent_audit_cleanup 账号专用连接串，.env.example 已有，默认占位密码 medagent123）。
- **EMBEDDING_DIM 已硬编码 1024**（`knowledge-service/app/services/dashvector_client.py`）：text-embedding-v3 最大 1024 维，collection 已按 1024 重建；别改回 1536，改维度必须删除重建 collection（删了会自动重建）。**ES_URL 未进 .env.example**（代码 `os.getenv("ES_URL", "")` 读取，配了才启用 ES 检索路径，现环境未启用）。
- **shared/prompts/oncology_specialist.yaml 是孤儿资源**：话术模板文件，目前无任何服务加载（main.py 均未引用），改动它不会影响任何行为。
- **web/ three 是唯一需拍板的额外依赖**：3D 办公室引入（老板拍板打破零依赖约定；axios/dayjs/react-router-dom 属常规框架依赖），新增前端依赖需同样先问；@types/three 在 dependencies 而非 devDependencies；`t10-office3d/e2e_v4.py` 的 `project()` 与布局/相机强耦合，改了 `OfficeScene3D.tsx` 相机或 `layout.ts` 布局常量必须同步改 E2E 投影，否则 sit 断言必挂。
- **Metro 打包失败 = App 白屏/无法加载**：任何相对路径 import 解析失败（如 `SettingsScreen.tsx` 的 `require('../../package.json')` 少一层 `../`，2026-08-11 623a6cb 修复）会让整个 bundle 挂掉，`metro.log` 里 `Unable to resolve module ... from <file>` 即定位点；改完代码 App 不会自动重拉 bundle，需 `adb shell am force-stop com.medagent.mobile` 后重启 App。
- **NLS TTS 合成**：mobile 直调 `https://nls-gateway-cn-shanghai.aliyuncs.com/stream/v1/tts?appkey&token&text&format=wav&sample_rate=16000`（REST 一次性合成，非流式）；appkey 非机密可放客户端，AK/SK 永不出服务端
- **mobile/ react-native-sound 是首个音频播放依赖**（TTS 朗读；原生模块需重新 run-android）
- **transcript 响应含 key_nodes/ai_suggestion**（LLM 推荐节流 20s/句；失败返回空数组/null 不阻塞）
