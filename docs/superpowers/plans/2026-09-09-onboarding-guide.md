# 三端新人引导（Onboarding Guide）计划书

日期：2026-09-09　状态：**已实施完成**（当日交付，实施记录见文末）

## 0. 背景与目标

三端（web 管理后台 / mobile 代表端 / mobile-doctor 医生端）功能多且入口深（如代表端培训考试藏在
「我的→用户卡→设置→备案与资质→页面最底部」），新用户/演示观众需要引导。目标：教会核心动线，不是功能说明书。

**非目标**：不做后端下发配置（演示阶段无运营需求，省迁移/端点/审核链）；不做每页逐屏 Tour（只做全局开场 + 3 处深藏入口气泡）；不新增任何 npm 依赖。

## 1. 设计原则

1. **教动线不教菜单**：每端一条主线，价值叙事开场（"你的数字员工在替你值守"）→ 操作说明收尾（第 N 步点哪里）。
2. **首登自动触发 + 全程可跳过 + 常驻重看入口**（演示时给老板重放是刚需）。
3. **不挡关键流程**：医生端深链激活（pendingToken）优先于引导；引导不拦截任何网络请求。
4. **存储全本地**：web localStorage / RN AsyncStorage，key 前缀 `onboarding`，与既有惯例一致。

## 2. web 端（antd Tour，四角色）

### 2.1 基建事实（已调研核实）

- antd ^5.20.0（lockfile 5.29.3）自带 `Tour` 组件（4.20+），零新依赖。
- `AdminLayout.tsx`：ProLayout，`headerContentRender` 右上角（Dropdown 旁）加 "?" 按钮；已有自定义 `menuItemRender`，可给菜单 `<a>` 按 path 注入 `data-tour-menu="<path>"` 属性（稳定 target selector，不依赖 ProLayout 内部 DOM 结构）。
- `useAuth().user.role` ∈ admin/manager/compliance/medical；`ROUTE_ACCESS` 是路由×角色单一事实源。
- 登录落地 `/dashboard`（index Navigate），Tour 首步从 dashboard 起。

### 2.2 组件

新增 `web/src/components/onboarding/`：

- `tourSteps.ts`——四角色步骤配置 + 纯函数 `getStepsForRole(role)`。步骤结构：
  - **叙事步 ×2-3**（无 target，居中卡片）：各角色定制价值主线。
  - **菜单步 ×2-3**（target = `[data-tour-menu="<path>"]`，指向该角色可访问的菜单项）：讲动线「从这里进 X」。
  - **收尾步 ×1**（target "?" 按钮 `data-tour="help-btn"`）：操作说明——随时点这里重看引导。
- `AppTour.tsx`——Tour 封装：读 localStorage `onboarding.web.<role>.v1` 决定是否展示；完成/跳过均置位（跳过=完成，不再骚扰）；`indicatorsRender` 简洁圆点。

改动 `AdminLayout.tsx`：
- headerContentRender 加 `QuestionCircleOutlined` 按钮（`data-tour="help-btn"`）+ Dropdown：「重看功能引导」「不再自动弹出」（清/置 localStorage）。
- 菜单 menuItemRender 注入 data-tour-menu。
- 布局内挂 `<AppTour />`（登录态才有 layout，天然满足触发条件）。

### 2.3 四角色叙事主线（文案要点）

| 角色 | 叙事开场 | 动线菜单步 | 收尾 |
|---|---|---|---|
| admin | 你管理着一支 AI 数字员工团队，3D 办公室里实时看它们值守 | 专员列表→办公室 / 知识库→上架知识 / 用户/备案审核 | "?" 重看 |
| manager | 拜访数据自动汇总，AI 总结每天替你读完全部拜访 | 拜访列表 / 专员监控 / 医生档案 | 同上 |
| compliance | 每一句 AI 输出都过三层合规门禁，风险在这里闭环 | 风控看板→待复核→冻结 / 对话检索 / 监管报告导出 | 同上 |
| medical | 医学内容从上架到触达医生全程留痕 | 知识库 / 患教审核 / 触达统计 | 同上 |

**防漂移断言（vitest）**：`tourSteps` 里引用的每个 menu path 必须 ∈ `ROUTE_ACCESS` 中该角色的允许集合——角色权限表变更时测试会炸出来（对齐 M17 单一事实源哲学）。

## 3. 代表端（mobile）

### 3.1 基建事实（已调研核实）

- `src/App.tsx` → `navigation/AppNavigator.tsx`：isLoggedIn 条件渲染 MainTabs（4 Tab：工作台/对话/医生/我的）；screens 目录制（`screens/Onboarding/` 新增同构）。
- AsyncStorage 惯例：api/client.ts token、NotificationSettings 同款。
- 已有 `HelpCenterScreen`、`SettingsScreen`（重看入口挂点）。
- 深藏入口三处：Profile→Settings→ComplianceCenter（培训/考试/承诺书）、ShareScreen（分身分享）、BriefingListScreen（夜间简报）。

### 3.2 组件

- `screens/Onboarding/OnboardingScreen.tsx`——4 屏轮播（ScrollView pagingEnabled + 圆点指示器 + 跳过/开始按钮，纯 RN 零依赖）：
  1. 价值：你的 AI 数字员工 7×24 替你值守医学问答，拜访后自动写总结
  2. 主线：工作台发起拜访→录音转写→AI 总结与任务
  3. 地图：四个 Tab 各是什么
  4. 收尾操作说明：合规培训在「我的→设置→备案与资质」；设置里可重看引导
- 触发：AppNavigator isLoggedIn 分支渲染 `<OnboardingGate>` 包 MainTabs——读 AsyncStorage `onboarding.rep.v1`，未看过先盖轮播，完成/跳过 setItem 后放行（首次登录与冷启动恢复均覆盖；登出重登不再弹）。
- `components/FirstUseTip.tsx`——可复用一次性气泡（Modal：标题+正文+「知道了」），props `{storageKey, title, content}`，已看过不渲染。挂三处：
  - ProfileScreen（首访）：「备案资质与合规培训从这里进：顶部用户卡→设置→备案与资质」
  - ShareScreen（首访）：分身分享链接发给医生，医生加你分身后对话回流
  - BriefingListScreen（首访）：夜间简报每天早晨自动生成，汇总昨日医生动态
- SettingsScreen 加一行「功能引导」（重看轮播，清 `onboarding.rep.v1` 再进）。

## 4. 医生端（mobile-doctor）

- 同构 `screens/Onboarding/OnboardingScreen.tsx` 4 屏：① 认证（医师认证后解锁完整功能）② 问答（引用知识库可溯源）③ 分身（订阅官方数字员工，对话经代表知情同意）④ 收件箱/患教/偏好（简报早间推送；收尾操作说明：设置里重看）。
- 触发条件多一条：`isLoggedIn && !pendingToken` 才弹——深链激活流程优先（F2 语义：token 暂存待消费，不能被引导打断）；pendingToken 消费完后的下一次冷启动仍会补弹（可接受，激活完成正是需要引导的时刻）。
- ProfileScreen 设置区加「功能引导」重看入口（清 `onboarding.doctor.v1`）。

## 5. 测试与验收

- **web**：vitest 新增 tourSteps 防漂移断言（menu path × 4 角色 ∈ ROUTE_ACCESS）+ getStepsForRole 返回结构（首步无 target/末步指向 help-btn）；tsc + build PASS。
- **mobile / mobile-doctor**：jest 新增 OnboardingScreen 渲染/翻页/完成回调写存储、FirstUseTip 只首访弹、OnboardingGate 判定（已看过直接放行）；tsc 0 错。
- **模拟器走查**：双端首登弹轮播→跳过/完成两种路径→重看入口生效→深链场景（医生端 pendingToken 存在时不弹）；web 四角色各走一遍 Tour + "?" 重看。
- 基线回归：既有 vitest 19 / jest 105+36 不回归。

## 6. 风险

| 风险 | 缓解 |
|---|---|
| antd Tour 遮罩被 ProLayout header 盖住 | Tour `zIndex` 调高（antd Tour 支持传 zIndex，默认 1001，ProLayout header 无更高层） |
| 菜单 target 时序（折叠/未渲染） | target 用 `() => document.querySelector(...)` 惰性查找；找不到时 antd Tour 自动居中显示（降级不崩） |
| RN 轮播盖住 Tab 首帧闪动 | OnboardingGate 先 render null 直至 AsyncStorage 读毕（loading 态），避免 MainTabs 闪现 |
| 登出→登入重复弹 | key 只写一次不清除；重看入口主动清 key |

## 7. 任务拆分

1. **T1 web**：onboarding 组件 + AdminLayout 接线 + vitest。
2. **T2 mobile**：OnboardingScreen + Gate + FirstUseTip×3 + Settings 入口 + jest。
3. **T3 mobile-doctor**：OnboardingScreen + Gate（pendingToken 条件）+ Profile 入口 + jest。
4. **T4 收尾**：CLAUDE.md 补记 + 全量回归 + 模拟器走查。

## 8. 实施记录（2026-09-09 当日）

全量交付，与计划的偏差两处：

1. **web "?" 入口改 FloatButton（原计划顶栏按钮）**——实施时 Playwright 实机走查发现
   `headerContentRender` 是死代码：本 ProLayout 纯侧边布局不渲染顶栏（DOM 无 header 元素，
   原有退出登录 Dropdown 同样从未显示过）。改 antd FloatButton 固定右下角悬浮球（零新依赖）。
2. **菜单高亮步降级确认**——侧边菜单分组未展开时 menuItemRender 不被调用（data-tour-menu
   只挂到顶级项），Tour target 判空自动降级居中显示；文案自含路径（「左侧菜单 → 数字专员 → 专员列表」），
   不高亮也不误导，接受现状。

走查结论：双端模拟器全路径过（首启弹/翻页/完成回落/冷启不重弹/重看/跳过）+ web Playwright
注入 admin token 7 断言全 PASS。基线：web vitest 22 / mobile jest 108 / mobile-doctor jest 39，
三端 tsc 0、web build PASS，后端零改动。

记坑：mobile-doctor types.ts 的 RootStack/MainTab 两个 ParamList 都有 Profile 键，新增路由要
确认插对列表（本次插错一次 tsc 炸出）；uiautomator dump_ui.py 的 [click] 与真实点击有竞态，
坐标要手动 input tap；RN 轮播自动化翻页用 swipe（连点按钮会被 onMomentumScrollEnd 吞）。
