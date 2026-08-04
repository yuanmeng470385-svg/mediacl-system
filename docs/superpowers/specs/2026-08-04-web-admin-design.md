# Web 管理后台 - 设计文档

> 项目：MedAgent 数字员工系统
> 日期：2026-08-04
> 版本：v1.0

---

## 1. 概述

为管理者、医学顾问、合规/法务、系统管理员提供 Web 管理后台，覆盖仪表盘、专员管理、知识库、合规规则、审计查询、医生管理、用户管理、系统配置 8 个模块。

## 2. 技术栈

| 层 | 选型 | 说明 |
|----|------|------|
| 构建工具 | Vite 5 | 快速 HMR，ESBuild 打包 |
| 框架 | React 18 + TypeScript | 文档指定，与移动端 React Native 同生态 |
| UI 组件库 | Ant Design 5 + ProComponents | 文档指定 Ant Design Pro |
| 路由 | React Router 6 | 懒加载，每模块独立 chunk |
| 图表 | @ant-design/charts | 仪表盘数据可视化 |
| HTTP | axios | 统一拦截器处理 token 和错误 |
| API 基地址 | `http://gateway:8000/api/v1` | 所有请求走网关 |

## 3. 目录结构

```
web/
├── src/
│   ├── layouts/
│   │   └── AdminLayout.tsx        # ProLayout：侧边栏菜单+顶栏+内容区
│   ├── pages/
│   │   ├── Dashboard/             # 仪表盘
│   │   │   └── index.tsx
│   │   ├── Specialist/            # 专员管理
│   │   │   ├── SpecialistList.tsx
│   │   │   └── SpecialistForm.tsx
│   │   ├── Knowledge/             # 知识库管理
│   │   │   ├── KnowledgeList.tsx
│   │   │   └── KnowledgeUpload.tsx
│   │   ├── Compliance/            # 合规规则管理
│   │   │   └── ComplianceList.tsx
│   │   ├── Audit/                 # 审计查询
│   │   │   └── AuditList.tsx
│   │   ├── Doctor/                # 医生管理
│   │   │   ├── DoctorList.tsx
│   │   │   └── DoctorDetail.tsx
│   │   ├── User/                  # 用户管理
│   │   │   └── UserList.tsx
│   │   └── System/                # 系统配置
│   │       └── SystemConfig.tsx
│   ├── services/                  # API 层（axios + 网关）
│   │   ├── client.ts              # axios 实例（baseURL+拦截器）
│   │   ├── auth.ts                # 登录/登出
│   │   ├── specialist.ts          # 专员 CRUD
│   │   ├── knowledge.ts           # 知识库 CRUD
│   │   ├── compliance.ts          # 合规规则 CRUD
│   │   ├── audit.ts               # 审计查询+导出
│   │   ├── doctor.ts              # 医生 CRUD
│   │   └── user.ts                # 用户 CRUD
│   ├── components/                # 共享组件
│   │   ├── StatCard.tsx           # 统计卡片
│   │   ├── StatusTag.tsx          # 状态标签
│   │   └── HealthDot.tsx          # 服务健康指示灯
│   ├── hooks/
│   │   └── useAuth.ts             # 认证 hook
│   ├── types/
│   │   └── index.ts               # 全局 TypeScript 类型
│   ├── constants/
│   │   ├── routes.ts              # 路由定义
│   │   └── menu.ts                # 侧边栏菜单配置
│   └── App.tsx                    # 入口：路由+ProLayout
├── index.html
├── package.json
├── tsconfig.json
└── vite.config.ts
```

## 4. 路由设计（10 条）

| 路径 | 页面 | 模块 |
|------|------|------|
| `/dashboard` | 仪表盘 | Dashboard |
| `/specialist/list` | 专员列表 | Specialist |
| `/specialist/create` | 新建专员 | Specialist |
| `/knowledge/list` | 知识库列表 | Knowledge |
| `/compliance/list` | 合规规则列表 | Compliance |
| `/audit/list` | 审计查询 | Audit |
| `/doctor/list` | 医生列表 | Doctor |
| `/doctor/:id` | 医生详情 | Doctor |
| `/user/list` | 用户列表 | User |
| `/system/config` | 系统配置 | System |

## 5. 侧边栏菜单

```
📊 仪表盘
🤖 数字专员
📚 知识库
🛡️ 合规规则
📋 审计查询
👨‍⚕️ 医生管理
👥 用户管理
⚙️ 系统配置
```

## 6. 页面详情

### 6.1 仪表盘

- 4 个 StatCard（活跃用户数、今日对话量、违规拦截率、用户满意度）
- 对话量趋势折线图（7 天/30 天切换）
- 风险热力图（区域 × 产品矩阵）
- 合规拦截 Top 5 柱状图
- 服务健康状态灯

### 6.2 专员管理（2 页）

**列表页：** ProTable + 顶栏（统计卡片：专员数、在线数）+ 操作（新增、编辑、启用/停用、删除）+ 状态标签
**新建/编辑：** ProForm 弹窗——名称、关联产品、百炼 App ID、能力范围、人设风格、话术模板

### 6.3 知识库管理（2 页）

**列表页：** ProTable + 顶栏统计（文档数、标签数、chunk 数）+ 筛选（类型/状态/产品）+ 状态标签（待审核/已上线/已过期）
**上传弹窗：** 拖拽上传区 + 表单（标题、类型、产品、证据等级、来源、日期）+ 自动解析选项

### 6.4 合规规则管理（1 页）

**列表页：** ProTable + 统计条（启用规则数、今日拦截数、拦截率）+ 筛选（类型/严重程度/动作）
**行内操作：** 启用/停用、编辑弹窗、删除
**右上角：** 新增规则 + 规则测试抽屉（输入内容→显示命中结果）

### 6.5 审计查询（1 页）

**列表页：** 高级搜索栏（时间范围/用户/服务/操作类型/风险等级）+ 统计（总数/命中数）
**ProTable：** 时间、用户、服务、操作、风险等级、IP
**行展开：** 详情面板（对话内容、合规结果）
**导出：** 一键 Excel

### 6.6 医生管理（2 页）

**列表页：** 搜索框 + 筛选（医院/科室/标签）+ ProTable（姓名/医院/职称/标签/拜访次数/满意度）
**详情页：** 基本信息卡片 + 学术背景 + 处方偏好 + 标签管理 + 互动历史时间线

### 6.7 用户管理（1 页）

**列表页：** 角色筛选 + ProTable（姓名/手机号/角色/区域/状态）
**弹窗：** 新增/编辑（姓名/手机号/角色下拉/区域/状态开关）

### 6.8 系统配置（1 页）

**卡片分组：** 阿里云配置 + 通知配置 + 日志配置
**表单：** ProForm，分组展示，保存按钮

## 7. API 对接

所有 API 通过网关 `http://gateway:8000/api/v1/` 调用，已完成后端实现：

| 模块 | API 端点 | 后端服务 |
|------|----------|----------|
| 仪表盘 | `/audit/stats`, `/compliance/stats` 聚合 | audit + compliance |
| 专员 | `/specialists/*` | specialist-service |
| 知识库 | `/knowledge/*` | knowledge-service |
| 合规 | `/compliance/*` | compliance-service |
| 审计 | `/audit/*` | audit-service |
| 医生 | `/hcp/*` | hcp-service |
| 用户 | `/auth/*` | gateway |

## 8. 视觉风格

- **色调**：深色底 + 蓝白主色 + 红/橙告警色（专业临床风）
- **布局**：Ant Design Pro Layout（侧边栏深色 + 内容区浅灰底）
- **图表**：暗色主题图表，数据突出
- **字体**：系统默认中文（苹方/Microsoft YaHei），代码块用 monospace
