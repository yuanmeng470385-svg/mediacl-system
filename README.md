# ============================================
# MedAgent 数字员工系统
# 面向医药代表的 AI 智能助手系统
# ============================================

## 项目简介

MedAgent 数字员工系统是一套面向医药代表、医生与药企管理方的 AI 数字员工平台。
三端架构：Web 管理后台（药企市场部/医学部/合规部）+ 代表端 APP（医药代表）+ 医生端 APP（临床医生），
数据互通、统一合规管控。给每个代表配一个懂产品、懂医生、懂合规的随身数字专员。

### 核心模块

| 模块 | 服务 | 端口 | 说明 |
|------|------|------|------|
| 数字学术专员 | specialist-service | 8001 | 每个产品一个 AI 专员，学术问答、多轮对话、医学问答 |
| 陪访助手 | visit-service | 8002 | 拜访前准备、拜访中实时辅助（语音转写）、拜访后自动记录 |
| 知识库 | knowledge-service | 8003 | 文档解析、向量化、混合检索 |
| 合规审核 | compliance-service | 8004 | 三层审核引擎（关键词+正则+LLM语义） |
| 审计留痕 | audit-service | 8005 | 不可篡改审计日志、监管报告导出 |
| 医生管理 | hcp-service | 8006 | 医生档案、画像、互动历史 |
| 认证服务 | auth-service | 8007 | 手机验证码/密码登录、用户管理、JWT 签发、备案/医师认证审核 |
| API 网关 | gateway | 8000 | 统一入口、路由转发、认证限流 |

### 三端与一期功能矩阵（2026-08-17 一期 MVP 完成）

| 端 | 载体 | 已交付能力 |
|------|------|------|
| 管理后台 | web/（React + Ant Design Pro） | 仪表盘、数字专员、拜访管理、知识库、合规规则/拦截记录、审计查询、医生管理、用户管理、备案管理、医生认证、系统配置、3D 数字员工办公室 |
| 代表端 | mobile/（React Native） | 登录、数字专员对话（流式）、拜访全流程（语音转写/异议/报告）、语音笔记、医生档案、知识库/资讯、合规手册、任务/收藏、**备案资质提交与个人合规中心**、**分身分享链接**、**分身夜间简报** |
| 医生端 | mobile-doctor/（React Native） | 登录、医师资格认证上传、医学 AI 问答（带引用与免责声明）、分身订阅（知情同意弹窗）、分身对话、深链激活 |

一期四个子系统（备案资质、医生端、22 项禁止行为映射、分身分享+夜间简报）均已在 CLAUDE.md 完整记录（端点/表/基线/挂账）。

### 三期 J Skill 生态闭环（2026-08-20）

| 端 | 载体 | 已交付能力 |
|------|------|------|
| 管理后台 | web/（React + Ant Design Pro） | Skill 资产列表（含代表发布，creator_name/creator_role）、资产审核、Skill 下架（合规下架/作者申请下架双类） |
| 代表端 | mobile/（React Native） | Skill 发布（代表发布到公共空间 → 审核）、我的 Skill（审核状态/热度/好评率/下架状态） |

### 三期 M 患教专区审核流（2026-08-20）

| 端 | 载体 | 已交付能力 |
|------|------|------|
| 管理后台 | web/（React + Ant Design Pro） | 患教内容审核（审核队列 + approve/reject，驳回必填原因） |
| 医生端 | mobile-doctor/（React Native） | 患教分享到专区（→ 审核流）、撤回分享、患教专区浏览（仅审核通过内容） |

### 三期 N 陪练 LLM 深度评分（2026-08-20）

| 端 | 载体 | 已交付能力 |
|------|------|------|
| 代表端 | mobile/（React Native） | 陪练 LLM 逐句反馈与进步曲线（complete 有 transcript 时 LLM 深度评分四维 + per_turn 逐句反馈 + summary 改进建议，失败降级轮数基线） |

### 技术栈

- **后端**: Python FastAPI
- **大模型**: 通义千问 (Qwen-Max/Plus/Turbo)
- **业务编排**: 阿里云百炼
- **语音**: 通义听悟 / 阿里云 NLS (ASR/TTS)
- **向量检索**: 阿里云 DashVector
- **数据库**: PostgreSQL 15 + Redis 7（20 张表，见 scripts/init_db.sql）
- **对象存储**: 阿里云 OSS
- **移动端**: React Native 0.75（mobile 代表端 + mobile-doctor 医生端）
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
# 编辑 .env，填入阿里云 AccessKey、百炼 API Key、JWT_SECRET、INTERNAL_API_KEY 等
# 首次启动前设置管理员密码：
python scripts/seed_admin.py
```

### 4. 启动开发环境

```bash
# 启动基础设施（PostgreSQL + Redis）
docker-compose up -d postgres redis
# 首次初始化数据库
docker exec -i medagent-postgres psql -U medagent medagent < scripts/init_db.sql
# 旧库升级需按序执行 scripts/migrations/ 下的迁移（009/010/011/012 见各文件头注释）

# 启动全部服务（本机 Docker Hub 不可达时按下方"本地开发"直跑）
docker-compose up -d
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
curl http://localhost:8007/health  # auth
```

### 6. 本地开发（不使用 Docker）

```bash
# 1. 启动 PostgreSQL 和 Redis（可以用 Docker 只启这两个）
docker-compose up -d postgres redis

# 2. 安装 Python 依赖（每个服务目录下）
pip install -r services/auth-service/requirements.txt
# ... 依此类推

# 3. 逐个启动服务（端口见模块表）
cd services/auth-service && python -m uvicorn app.main:app --port 8007
cd services/gateway && python -m uvicorn app.main:app --port 8000
# ... 依此类推
```

### 7. 前端

```bash
# Web 管理后台（web/）
cd web && npm install && npm run dev        # http://localhost:3000
# 验证门：cd web && npm run build

# 代表端（mobile/，Android 构建）
cd mobile && npm install
cd mobile/android && ./gradlew assembleDebug
# 测试：cd mobile && npx jest

# 医生端（mobile-doctor/，Android 构建）
cd mobile-doctor && npm install
cd mobile-doctor/android && ./gradlew assembleDebug
# 测试：cd mobile-doctor && npx jest
```

## 项目结构

```
medagent/
├── services/                  # 微服务
│   ├── specialist-service/    # 数字学术专员（含医学问答/分身订阅/分享/简报）
│   ├── visit-service/         # 陪访助手
│   ├── knowledge-service/     # 知识库
│   ├── compliance-service/    # 合规审核（11 条规则 R001-R011，见 docs/compliance-2026-22items-matrix.md）
│   ├── audit-service/         # 审计留痕
│   ├── hcp-service/           # 医生管理
│   ├── auth-service/          # 认证服务（登录/JWT/备案资质/医师认证）
│   └── gateway/               # API 网关
├── mobile/                    # 代表端 (React Native)
├── mobile-doctor/             # 医生端 (React Native，2026-08-17 一期 B)
├── web/                       # Web 管理后台 (React + Ant Design Pro)
├── shared/                    # 共享代码
│   ├── common/                # 通用工具 (响应格式、JWT、分页)
│   ├── models/                # 数据模型基类
│   ├── prompts/               # 数字专员话术模板
│   └── compliance-rules/      # 合规规则文件（rules.yaml）
├── knowledge-base/            # 知识库原始资料
├── scripts/                   # 运维脚本 & 数据库初始化 & 迁移
├── docs/                      # 文档（含各实施计划、22 项映射矩阵）
├── .env.example               # 环境变量模板
├── docker-compose.yml         # 本地开发编排
└── README.md
```

## 开发约定

### API 规范

- 协议: HTTP/HTTPS
- 格式: JSON
- 编码: UTF-8
- 认证: JWT (Authorization: Bearer <token>)；内部接口另需 X-Internal-Key
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

### 角色

`admin` / `manager` / `rep`（医药代表）/ `compliance` / `medical` / `finance` / `doctor`（医生端，2026-08-17 新增）。
角色与账号状态以库为准（token 只是登录快照），停用/降级即时生效。

### Git 规范

- Commit: `feat(module):`, `fix(module):`, `docs:`, `refactor:`, `test:`
- 示例: `feat(specialist): add multi-round conversation support`

### 服务间调用

所有服务间调用统一走网关，不直连：

```
http://gateway:8000/api/v1/knowledge/search
http://gateway:8000/api/v1/compliance/check
```

### 数据库备份（每日自动）

ECS 上 crontab 配置（每天 02:00，需先 pip install oss2 并把 .env 的 OSS_* 配置填好）：

    0 2 * * * cd /opt/medagent && python scripts/backup_db.py

备份文件：本地 ./backups（保留 7 天）+ OSS <OSS_BUCKET>/backups/（保留 30 天，ACL 私有）。
失败会写 logs/backup-failed 标记文件并以非零码退出，可用 CloudMonitor/MAILTO 监控。
恢复演练：python scripts/restore_db.py --source oss --yes（恢复到 medagent_restore 临时库校验行数）。

## 相关文档

- [完整方案文档](./AI数字员工系统-完整方案.md)
- [5人任务分配清单](./MedAgent-任务分配.md)
- [开发/运维细节（端点、表、基线、已知缺口）](./CLAUDE.md)

## 团队

5 人开发团队，详见任务分配清单。

---

**项目代号**: MedAgent
**版本**: v1.0.0
