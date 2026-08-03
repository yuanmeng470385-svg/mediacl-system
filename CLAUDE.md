# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

MedAgent 药企 AI 数字员工系统 — 五层架构的医药代表 SaaS 平台，提供数字学术专员、陪访助手、知识库管理、合规审核、审计追溯。六个微服务 + API 网关，部署在阿里云，AI 能力通过百炼多模态交互 App（WebSocket）+ 通义千问（OpenAI 兼容）+ 通义听悟（ASR）提供。

## Architecture

```
移动端 (React Native) → Gateway (:8000) → 微服务集群
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

# 运行单个服务
cd services/specialist-service && python -m uvicorn app.main:app --port 8001 --reload

# 运行测试（必须在服务目录下运行，sys.path 依赖 cwd）
cd services/specialist-service && python -m pytest tests/ -v
cd services/hcp-service && python -m pytest tests/ -v
cd services/visit-service && python -m pytest tests/ -v
cd services/compliance-service && python -m pytest tests/ -v

# 运行 A 的 AI 评估（需要真实百炼 App）
cd services/specialist-service && python tests/eval_specialist.py --app-id <百炼AppId>

# 全部 7 个服务同时启动
docker-compose up -d
```

**运行测试必须在服务目录下执行** — 所有测试用 `sys.path.insert(0, ...)` 回溯三层找到 shared 模块，路径依赖 cwd。

## Shared Layer (`shared/`)

所有微服务共用。统一响应格式：

```python
from shared.common.response import success, error, ParamError, AuthError, BusinessError
# success(data) → {"code":0,"message":"success","data":{...}}
# raise ParamError("question 不能为空") → {"code":1000,"message":"question 不能为空"}

from shared.common.auth import get_current_user, create_token
# @router.get("/xxx") → async def api(current_user: dict = Depends(get_current_user)): ...

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

## Service-to-Service Communication

所有服务间调用**走 Gateway（`GATEWAY_URL`，默认 `http://localhost:8000`）**，不走直连端口。Gateway 白名单豁免了以下内部路径的 JWT 认证（`auth_middleware.py` → `PUBLIC_PATHS`）：

```
POST /api/v1/compliance/check
POST /api/v1/audit/log
POST /api/v1/knowledge/search
```

调用模式（内部客户端统一写法）：

```python
import httpx
async with httpx.AsyncClient(timeout=10.0) as client:
    resp = await client.post(f"{GATEWAY_URL}/api/v1/compliance/check", json={...})
    return resp.json()["data"]
```

**降级策略：** 外部服务不可用时不得阻塞业务。合规客户端 fail-open（放行），审计客户端 fail-silent（记日志返回None），specialist 客户端返回 `degraded=True`。

## Database

PostgreSQL（Docker `postgres:15`），10 张表均在 `scripts/init_db.sql` 定义。连接通过 `shared/common/db_session.py` 的 `get_db` 依赖注入。常用 ORM 模式：

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

## Bailian WebSocket Protocol

数字专员问答通过百炼多模态交互 WebSocket 协议实现（`specialist-service/app/services/bailian_client.py`），非 HTTP：

1. Connect → `wss://dashscope.aliyuncs.com/api-ws/v1/inference`
2. Start message: `{task_group: "aigc", task: "multimodal-generation", model: "multimodal-dialog"}`
3. 收到 `DialogStateChanged` → 发送 `RequestToRespond`
4. 接收 `RespondingContent` 流 → 解析答案
5. Stop → 完成

降级：百炼不可用时走通义千问直调（`qwen_client.py`，OpenAI 兼容接口），300 字符限制，不含知识库检索。需要 `BAILIAN_API_KEY`（与 `DASHSCOPE_API_KEY` 不同）。

## Gotchas

- **Windows GBK 控制台**：不能输出 ✓ (✓)，否则 `UnicodeEncodeError`。用中文标记代替（如"达标"）。
- **测试从服务目录跑**：`sys.path` 依赖 `os.path.join(__file__, "..", "..", "..")` 找到 shared，从项目根目录执行会 `ModuleNotFoundError: No module named 'app'`。
- **python-jose extras**：`requirements.txt` 中 `python-jose[cryptography]` 不能写成 `[cryptogram]`（后者 pip 不报错但功能缺失）。
- **服务间调用绕网关**：不要在代码里写 `http://localhost:8004` 调合规服务，走 `GATEWAY_URL + /api/v1/compliance/check`，否则 JWT 认证会拦截（除非已加入 Gateway 白名单）。
- **`.env` 在 `.gitignore` 中**：根目录 `.env` 不会被提交，模板见 `.env.example`。
- **hcp-service 的 visit_interaction_repo**：同库直读 `visit_records` 表（避免循环依赖），表不存在时降级为空列表。如果 visit-service 和 hcp-service 不在同一个 DB，需要改为 HTTP 调用。
- **visit_records 表无 status 字段**：状态派生自 `ai_summary IS NULL → in_progress`，非独立字段。
- **Commit 格式**：遵循 conventional commits `feat(scope): subject`，末尾 `Co-Authored-By: Claude <noreply@anthropic.com>`。
