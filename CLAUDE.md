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

# 运行测试（必须在服务目录下运行，sys.path 依赖 cwd）
cd services/auth-service && python -m pytest tests/ -v
cd services/specialist-service && python -m pytest tests/ -v
cd services/hcp-service && python -m pytest tests/ -v
cd services/visit-service && python -m pytest tests/ -v
cd services/compliance-service && python -m pytest tests/ -v

# 运行 A 的 AI 评估（需要真实百炼 App）
cd services/specialist-service && python tests/eval_specialist.py --app-id <百炼AppId>

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

from shared.common.db_session import get_db
# async def api(db: Session = Depends(get_db)): ...

from shared.common.pagination import paginate, PaginationParams
from shared.common.exception_handler import register_exception_handlers
# register_exception_handlers(app)  # 在 main.py 中注册，自动转换 AppError → 统一响应

from shared.models.base import Base, TimestampMixin  # ORM 基类（id, created_at, updated_at）
```

错误码区间：1000-1999 参数 / 2000-2999 认证 / 3000-3999 权限 / 4000-4999 业务（含合规拦截）/ 5000-5999 系统 / 6000-6999 第三方。

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
- 验证码一次性、5 分钟过期、60 秒重发冷却、单码最多校验 5 次。
- `users.password_hash` 为 NULL 表示未设密码，任何密码都登录不了。用 `scripts/seed_admin.py` 设置。
- `profile`/`me` 每次从库里重读用户，被停用的账号即便持有有效 token 也会被拒。
- 短信通道可插拔（`app/services/sms.py`）：默认 `console` 只写日志；阿里云通道已实现（`AliyunSmsSender` 走 dysmsapi，缺 `AUTH_SMS_SIGN_NAME`/`AUTH_SMS_TEMPLATE_CODE` 或 `ALIYUN_ACCESS_KEY_ID`/`SECRET` 时构造即抛 `SmsSendError` fail-fast；配齐后 `AUTH_SMS_PROVIDER=aliyun` 生效，模板变量固定为 `{"code": ...}`）。

## Service-to-Service Communication

所有服务间调用**走 Gateway（`GATEWAY_URL`，默认 `http://localhost:8000`）**，不走直连端口。网关对三类路径区别对待（`auth_middleware.py`）：

```
# INTERNAL_PATHS —— 免 JWT，但必须带 X-Internal-Key 头（否则 403）
POST /api/v1/compliance/check
POST /api/v1/audit/log
POST /api/v1/knowledge/search
# PUBLIC_PATHS —— 真正公开（免 JWT 免 key）
POST /api/v1/auth/login
POST /api/v1/auth/send-code
```

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

PostgreSQL（Docker `postgres:15`），10 张表均在 `scripts/init_db.sql` 定义。连接通过 `shared/common/db_session.py` 的 `get_db` 依赖注入。常用 ORM 模式：

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

**语义检查安全行为（S7）**：内容包裹在 `<user_content>` 标记中（其中的任何指令都只是数据）；LLM 输出**解析失败**（JSON 错误/截断）时按违规拦截（R999, action=reject）——这是注入攻击与截断的迹象，fail-closed；只有**网络/API 错误**才 fail-open 降级。

## Bailian WebSocket Protocol

数字专员问答通过百炼多模态交互 WebSocket 协议实现（`specialist-service/app/services/bailian_client.py`），非 HTTP：

1. Connect → `wss://dashscope.aliyuncs.com/api-ws/v1/inference`
2. Start message: `{task_group: "aigc", task: "multimodal-generation", model: "multimodal-dialog"}`
3. 收到 `DialogStateChanged` → 发送 `RequestToRespond`
4. 接收 `RespondingContent` 流 → 解析答案
5. Stop → 完成

降级：百炼不可用时走通义千问直调（`qwen_client.py`，OpenAI 兼容接口），300 字符限制，不含知识库检索。需要 `BAILIAN_API_KEY`（与 `DASHSCOPE_API_KEY` 不同）。

**聊天 WS 流式链路（2026-08-06 三批实施后，REST `/chat` 保留为降级）**：
- specialist：`BailianClient.chat_stream()`（逐帧 yield delta/done）→ `AnswerGenerator.generate_stream()`（合规预检 → 流式 → 答案合规审核 → 审计 → done 帧，字段与 REST 返回一致 + type）→ WS 端点 `/ws/specialists/{id}/chat?token=JWT`（`app/api/chat_ws.py`：token 无效关 4401、专员不存在关 4404、question 空/超时/异常关 4500；`start → delta* → done` 帧，done 前 `_persist_conversation` 落库并带 conversation_id；send 统一加锁防 ConcurrencyError）。
- gateway：`/api/v1/specialists/{id}/chat/ws` 双向透传代理（token 原样转发，网关不重复鉴权——WS scope 不经 BaseHTTPMiddleware）。
- mobile：`mobile/src/services/wsChat.ts` 走网关 8000（question 帧缓冲到 onopen 后发送）；`ChatScreen` 流式渲染增量气泡，8s 未收到 start 自动降级 REST（specialistAPI.sendMessage），blocked/violations 按 REST 同款拼装展示。

## Frontend — web/（Web 管理后台）

Vite 5 + React 18 + TypeScript + AntD 5 + @ant-design/pro-components + @ant-design/charts，纯 SPA。开发时 vite 把 `/api` 代理到网关 `localhost:8000`（`vite.config.ts`），生产由反代同路径转发。

8 模块 10 路由（`web/src/constants/routes.ts`，懒加载）：仪表盘 `/dashboard`、数字专员 `/specialist/list` + `/specialist/create`、知识库 `/knowledge/list`、合规规则 `/compliance/list`、审计查询 `/audit/list`、医生管理 `/doctor/list` + `/doctor/:id`、用户管理 `/user/list`、系统配置 `/system/config`。

API 约定：axios 实例 `web/src/services/client.ts`，`baseURL: '/api/v1'`；token 存 localStorage `medagent_token`，请求自动带 `Authorization: Bearer`。后端统一响应 `{code, message, data}`，分页接口的 data 是 `{items, total, page, page_size}`（见 `web/src/types/index.ts`）。

**已知问题（页面存在 ≠ 功能已实现）**：
- 部分操作（系统配置保存、上传等）只弹 toast，无真实调用。

## Frontend — mobile/（React Native 移动端）

React Native 0.75 + TypeScript + react-navigation，原生工程已齐（2026-08-06 bring-up 完成，Pixel_7 模拟器全链路实测通过）。包名/bundle ID `com.medagent.mobile`，App 显示名 `MedAgent`，入口 `mobile/index.js` → `src/App.tsx`（app.json name 与 MainActivity/AppDelegate moduleName 必须一致，否则首启红屏）。

```bash
# 构建/运行（JDK 17 + ANDROID_HOME=D:\AndroidSDK + AVD Pixel_7 已就绪）
cd mobile/android && ./gradlew assembleDebug          # 出 app-debug.apk
"D:/AndroidSDK/emulator/emulator.exe" -avd Pixel_7 &  # 起模拟器
cd mobile && npx react-native start                   # Metro（Node v25 实测可用）
adb install -r mobile/android/app/build/outputs/apk/debug/app-debug.apk
adb shell am start -n com.medagent.mobile/.MainActivity
# 测试：cd mobile && npx jest（契约测试 11 用例锁 URL/method/body/响应形状）
```

结构：`mobile/src/navigation/AppNavigator.tsx`（Stack：登录 → 底部 4 Tab：工作台/对话/医生/我的 → 拜访/医生详情等子页）；`mobile/src/api/` 按服务拆分，统一走 `mobile/src/api/client.ts`：Android 模拟器 `http://10.0.2.2:8000`、iOS `localhost:8000`（都是网关）；登录态在 `mobile/src/store/AuthContext.tsx`（AsyncStorage 存 token）。**契约铁律：请求体/响应形状以 src/api/*.ts 为唯一映射点**（snake_case、分页解包都在这里做，不污染屏幕组件）；改动后端响应形状或端点后，先改 api 层 + 契约测试，再动屏幕。

**已知问题（2026-08-06 三批实施后）**：
- 录音链路已接但 NLS_APPKEY 未配：`VisitInProgressScreen` 录音 → PCM 分片推 ASR WS，服务端未配置时发 error 帧 fail-closed（前端提示"NLS 识别通道未配置"，不产生假文本）；`ChatScreen` 语音按钮仅提示（无拜访上下文，避免伪造 visit）。模拟器无麦克风，录音链路只验证到单测 + 构建，真机待实测。
- HelpCenter 屏仍零后端调用（其余四屏已接真实数据/持久化）。
- 聊天 WS 流式已接（走网关 8000），未配真实百炼 key 时未做模拟器端到端冒烟。
- iOS 未实际构建验证（本机无 Xcode；moduleName 已对齐，首次构建需实测）。

## Real-time ASR（实时转写）

实时转写链路已改用**阿里云实时语音识别**（听悟是离线批处理+3s 轮询，达不到方案的 <2s）：

- 服务端：`visit-service/app/services/realtime_asr.py`（`RealtimeAsrClient`：AK/SK 签名换 NLS 临时 Token → `wss://nls-gateway-cn-shanghai.aliyuncs.com/ws/v1?token=` → StartTranscription → 二进制 PCM 推流 → SentenceBegin/ResultChanged/SentenceEnd 事件；`enable_intermediate_result=true` 实时出字）。未配置 `NLS_APPKEY` 自动降级 `MockRealtimeAsrClient`（模拟文本，可联调）。
- WS 端点：`/ws/visits/{visit_id}/asr?token=<JWT>`（移动端推 PCM → 增量 JSON 回推 → 断句落库 conversation_transcript → 每句实时合规检查并回推 compliance 事件）。**注意 WS 不走网关**（网关 proxy 不支持升级），直连 visit-service:8002。
- 听悟客户端保留用于拜访后归档（完整音频离线转写）。
- 移动端接入点（已接，2026-08-06）：`react-native-audio-record` 录 WAV(16k/16bit/mono) → `readWavPcm` 跳过 44 字节头 → 16KB 分片经 `mobile/src/services/asr.ts` 推 WS（"录完再推"，非流式——audio-record 无流式回调）；`{"type":"stop"}` 结束；sentence 帧增量回填输入区，completed 帧回传末句全文走 `addTranscript` 落库。NLS_APPKEY 未配时服务端 fail-closed（error 帧 + 关 4500，不落假文本）。

## Known Gaps（后端已知缺口，勿误以为已实现）

已修（2026-08-04）：~~audit 零鉴权~~（S2）、~~"不可篡改"未生效~~（S3）、~~visit PUT 越权~~（S4）、~~零 RBAC~~（S6）、~~规则改动/审核不入审计~~、~~语义合规提示注入~~（S7）、~~prod 暴露公网~~（S8）、~~网关中间件顺序/预检 401~~（H10）、~~Excel 导出经网关 500~~（H11）、~~visit→specialist 401 永久 degraded~~（透传用户 JWT）、~~Web 仪表盘假数据~~、~~用户管理 404~~（`/api/v1/users`）、~~知识库 approve 反转~~、~~compliance_blocks 无写入方~~（check 端点拦截即入库，实测 R003 落表）、~~实时转写路线错误~~（服务端已切阿里云实时 ASR 流式链路 + WS 端点，实测 Mock 全链路；移动端录音待原生工程）。

已修（2026-08-05~06）：~~citations 恒空~~（百炼 extra_info.docs 解析引用溯源）、~~feedback/favorite 是桩~~（conversation_feedback/favorites 真落库，实测点赞 2 行 + 收藏 1 行含问答快照）、~~规则热更新只读 YAML~~（DB 规则加载，DB 覆盖 YAML + TTL 60s 重载）、~~移动端无法构建~~（RN 0.75.0 原生工程 + api 契约修复 7 处 + 契约测试 11 用例 + Pixel_7 实测全链路）、~~chat 无 conversation_id~~（前端反馈/收藏拿不到主键）、~~mobile 三处响应形状错位~~（specialist 纯数组、compliance 分页对象+字段名、favorite 必填 body 422）。

已修（2026-08-06 三批实施，23 提交本地未 push）：~~web 无登录页~~（AuthProvider + 登录页 + 路由守卫 + 401 跳转）、~~mobile 五屏零后端调用~~（VisitDetail/Profile/Settings 接真实接口、NotificationSettings AsyncStorage 持久化；HelpCenter 除外）、~~ContentScreen MOCK_CONTENT~~（接 knowledge API + 新增文档详情页）、~~移动端无录音/无 WS 客户端~~（录音库 + 权限 + asr.ts/wsChat.ts + 拜访页录音转写接线 + 聊天流式）、~~短信通道仅 ConsoleSender~~（AliyunSmsSender dysmsapi 真实现，缺配置 fail-fast，4 测试全 mock）、~~聊天一次性返回~~（specialist WS 端点 + 网关 WS 代理 + mobile 流式渲染 + 8s 降级 REST，question 帧缓冲到 onopen 发送）。

**仍为假数据/未实现（勿误以为已做）**：
- web 部分增删改假动作（系统配置保存、上传等只弹 toast）
- NLS_APPKEY 未配（录音链路已接，未配置时识别 fail-closed 提示）；ASR/聊天 WS 未真机联调（模拟器无麦克风，E2E 冒烟需真实百炼 key）
- HelpCenter 屏零后端调用
- 短信默认仍 console（未配签名/模板 CODE 时，验证码捞 `logs/native/auth-service.log`；配齐后 `AUTH_SMS_PROVIDER=aliyun` 生效）
- `knowledge-base/` 空目录（方案要求 100-300 篇文献）、ES 真实实例未接（ES_URL 配置才启用）
- X-Request-ID 链路未贯穿；REQUESTS 计数器无 .inc() 接线（http_requests_total 恒 0）

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
- **visit_records 表无 status 字段**：状态派生自 `ai_summary IS NULL → in_progress`，非独立字段。
- **前端字段 camelCase、后端 snake_case**：映射统一收在 `mobile/src/api/*.ts`（`prepareVisit` 等已修，2026-08-06 实测 pre-visit 200）。改后端 schema 或响应形状时，同步改 api 层 + 契约测试，屏幕组件只消费 api 层的映射结果，不直接碰请求体。
- **跨服务 FK 需要注册元数据**：`visit_records` 的 FK 引用 hcps/products/digital_specialists，visit-service 必须 import `shared.models.hcp`/`product`/`digital_specialist`（见 `services/visit-service/app/models/visit_record.py`），否则 SQLAlchemy 报 `NoReferencedTableError`。共享模型放 `shared/models/`，各服务 `app/models/*.py` 是 re-export。
- **Commit 格式**：遵循 conventional commits `feat(scope): subject`，末尾 `Co-Authored-By: Claude <noreply@anthropic.com>`。
