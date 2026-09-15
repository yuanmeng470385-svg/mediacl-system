# 2026-09-15 代表端修复 + 三端 AI 助手 + 管理端待办中心

用户 6 项需求，三批交付（A 代表端 / B AI 助手 / C 待办中心）。

## A. 代表端 4 项

### A1 引导按钮越界（双端 GuideController.tsx）
- 根因：召回卡一行 3 按钮（上一个/先收起/下一个 ≈324px）> 卡内可用宽 ≈280px，`btnRow` 无 flexWrap
- 修法：召回卡改两行（ghost 行 + 主按钮整行）；讲解卡 btnRow 加 flexWrap 兜底；双端同构修改

### A2 分身管理重构（hub + 我的分身 + 创建向导）
- TwinManageScreen 改双入口 hub：「我的分身」/「创建分身」
- 新 MyTwinsScreen：列表（过滤 disabled）+ 风格设置 + 暂停/恢复 + **删除**（二次确认）
- 新 CreateTwinWizardScreen 三步：5 题问卷 → 选真实记录（可跳过=纯问卷路径；选了但发言 <10 条禁下一步）→ 起名 → 一次建成
- 后端：
  - DELETE /specialists/{id} 扩归属分支：rep 本人可删（软删 status=disabled + 审计 twin_delete，对话/审计历史留存——合规留存口径）；admin 行为不变（specialist_disable）
  - style-from-records 扩可选 `answers`（5 题 0-2）：有 sources 走 LLM 提取画像、answers 映射的三枚举优先（用户显式意图 > LLM 推断）；纯 answers 无 sources = 原 style-test 语义（不调 LLM、不限额）；**style-test 端点删除合并**（mobile 唯一调用方改走合并端点）
  - 删除分身后：rep 列表过滤 status=disabled；医生侧订阅分身 chat 已被「仅 active 可对话」天然拦截
- 删 StyleSourceScreen + 路由（向导第 2 步收编其逻辑，避免死页）

### A3 陪练直接选 Skill
- PracticeListScreen 加「Skill 模版（可选）」卡：Modal 单选（GET /skill-packages/public），选中显示名称+热度+可移除；route params skillId 初始值兼容（广场加载链路不变）

### A4 删演示专员
- 本地 PG：`DELETE FROM digital_specialists WHERE name LIKE '演示专员%' OR name LIKE '高度测试%'`（21 行，已验证零 FK 引用）
- 服务器同款数据（09-15 开发库 restore 过去）：出 SQL 由用户执行或后续给 SSH 后补（本机无该主机 SSH 配置）

## B. 三端 AI 助手（产品使用问答）
- 后端 specialist：`POST /api/v1/assistant/qa`——system prompt 内置三端功能地图（按 JWT 角色定制 rep/doctor/管理端视角），QwenClient qwen-turbo 直调不检索；只答产品使用问题、拒绝医学咨询；审计 assistant_qa；无状态不落会话表
- 网关：ROUTE_MAP 加 `/api/v1/assistant` → specialist（30s 默认超时）
- web：AI 球与「?」引导球组 FloatButton.Group（避免右下角重叠）→ Drawer 聊天
- mobile / mobile-doctor：Profile「AI 助手」入口 + 聊天屏（仿 MedicalQA 范式，会话仅本地 state）

## C. 管理端待办中心
- 后端：`GET /api/v1/auth/todo-summary`（资质/医生认证/隐私请求/考试题 pending 计数）+ `GET /api/v1/specialists/todo-summary`（Skill/患教/异议话术/数据导出 pending 计数）；require_roles 四管理角色
- web：左侧菜单顶部「待办中心」+ menuItemRender 包 Badge 红色计数（60s 轮询）；页面按角色（canAccess）过滤 8 类待办，每行数量 + 「去处理」带 pending 过滤参数跳对应审核页
- routeAccess 27→28 + test 数量断言 + menu 三处同步；tourSteps 自动派生新菜单页步骤（PAGE_GUIDES 补文案）

## 验收基线
- specialist pytest / auth pytest / gateway pytest 全绿
- mobile jest + tsc 0 / mobile-doctor jest + tsc 0 / web vitest + tsc + build
- 8 服务重启 + 接口走查（删分身/向导创建/陪练选 Skill/assistant 问答/todo-summary）
- 本地演示专员 21 行删除后 doctors 广场/分身监控回归正常
