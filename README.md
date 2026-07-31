# ============================================
# MedAgent 数字员工系统
# 面向医药代表的 AI 智能助手系统
# ============================================

## 项目简介

数字员工系统是一套面向医药代表日常工作场景的智能助手系统。
给每个代表配一个懂产品、懂医生、懂合规的随身数字专员。

### 核心模块

| 模块 | 服务 | 端口 | 说明 |
|------|------|------|------|
| 数字学术专员 | specialist-service | 8001 | 每个产品一个 AI 专员，学术问答，多轮对话 |
| 陪访助手 | visit-service | 8002 | 拜访前准备、拜访中实时辅助、拜访后自动记录 |
| 知识库 | knowledge-service | 8003 | 文档解析、向量化、混合检索 |
| 合规审核 | compliance-service | 8004 | 三层审核引擎（关键词+正则+LLM语义） |
| 审计留痕 | audit-service | 8005 | 不可篡改审计日志、监管报告导出 |
| 医生管理 | hcp-service | 8006 | 医生档案、画像、互动历史 |
| API 网关 | gateway | 8000 | 统一入口、路由转发、认证限流 |

### 技术栈

- **后端**: Python FastAPI
- **大模型**: 通义千问 (Qwen-Max/Plus/Turbo)
- **业务编排**: 阿里云百炼
- **语音**: 通义听悟 (ASR/TTS)
- **向量检索**: 阿里云 DashVector
- **数据库**: PostgreSQL 15 + Redis 7
- **对象存储**: 阿里云 OSS
- **移动端**: React Native (iOS + Android)
- **Web 后台**: React + Ant Design Pro
- **监控**: 阿里云 ARMS / SLS

## 快速开始

### 1. 环境要求

- Python 3.11+
- Node.js 18+
- Docker Desktop

### 2. 克隆项目

```bash
git clone <仓库地址>
cd medagent
```

### 3. 配置环境变量

```bash
cp .env.example .env
# 编辑 .env，填入阿里云 AccessKey、百炼 API Key 等
```

### 4. 启动开发环境

```bash
# 启动所有服务（PostgreSQL + Redis + 7 个微服务）
docker-compose up -d

# 查看日志
docker-compose logs -f

# 查看运行状态
docker-compose ps
```

### 5. 验证

```bash
# 网关健康检查
curl http://localhost:8000/health

# 各服务健康检查
curl http://localhost:8001/health  # specialist
curl http://localhost:8002/health  # visit
curl http://localhost:8003/health  # knowledge
curl http://localhost:8004/health  # compliance
curl http://localhost:8005/health  # audit
curl http://localhost:8006/health  # hcp
```

### 6. 本地开发（不使用 Docker）

```bash
# 1. 启动 PostgreSQL 和 Redis（可以用 Docker 只启这两个）
docker-compose up -d postgres redis

# 2. 安装 Python 依赖
pip install -r services/specialist-service/requirements.txt
# ... 依此类推

# 3. 逐个启动服务
cd services/specialist-service && python -m app.main
cd services/visit-service && python -m app.main
# ...
```

## 项目结构

```
medagent/
├── services/                  # 微服务
│   ├── specialist-service/    # 数字学术专员
│   ├── visit-service/         # 陪访助手
│   ├── knowledge-service/     # 知识库
│   ├── compliance-service/    # 合规审核
│   ├── audit-service/         # 审计留痕
│   ├── hcp-service/           # 医生管理
│   └── gateway/               # API 网关
├── mobile/                    # 移动端 (React Native)
├── web/                       # Web 后台 (React + Ant Design Pro)
├── shared/                    # 共享代码
│   ├── common/                # 通用工具 (响应格式、JWT、分页)
│   ├── models/                # 数据模型基类
│   ├── prompts/               # 数字专员话术模板
│   └── compliance-rules/      # 合规规则文件
├── knowledge-base/            # 知识库原始资料
├── scripts/                   # 运维脚本 & 数据库初始化
├── docs/                      # 文档
├── .env.example               # 环境变量模板
├── docker-compose.yml         # 本地开发编排
└── README.md
```

## 开发约定

### API 规范

- 协议: HTTP/HTTPS
- 格式: JSON
- 编码: UTF-8
- 认证: JWT (Authorization: Bearer <token>)
- 前缀: `/api/v1/`
- 请求 ID: `X-Request-ID` (UUID)

### 统一响应格式

```json
// 成功
{ "code": 0, "message": "success", "data": {} }

// 错误
{ "code": 4001, "message": "合规拦截", "data": { "rule_code": "R001" } }
```

### 错误码区间

| 区间 | 含义 |
|------|------|
| 0 | 成功 |
| 1000-1999 | 参数错误 |
| 2000-2999 | 认证错误 |
| 3000-3999 | 权限错误 |
| 4000-4999 | 业务错误（含合规拦截） |
| 5000-5999 | 系统错误 |
| 6000-6999 | 第三方服务错误 |

### Git 规范

- 分支: `feature/xxx`, `fix/xxx`, `refactor/xxx`
- Commit: `feat(module):`, `fix(module):`, `docs:`, `refactor:`, `test:`
- 示例: `feat(specialist): add multi-round conversation support`

### 服务间调用

所有服务间调用统一走网关，不直连：

```
http://gateway:8000/api/v1/knowledge/search
http://gateway:8000/api/v1/compliance/check
```

## 相关文档

- [完整方案文档](./AI数字员工系统-完整方案.md)
- [5人任务分配清单](./MedAgent-任务分配.md)

## 团队

5 人开发团队，详见任务分配清单。

---

**项目代号**: MedAgent
**版本**: v1.0.0
