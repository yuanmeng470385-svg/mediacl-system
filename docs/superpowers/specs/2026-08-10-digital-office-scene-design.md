# 数字员工办公室 · 活人版（办公室场景升级）设计

日期：2026-08-10
状态：已评审通过（用户逐节确认），待实施

## 背景与目标

老板验收第一版数字员工办公室（Marvis 风格状态卡）后提出：专员不应该只是「冷冰冰的服务名卡片」，要把所有专员放进**同一间办公室**，以「活的」团队成员形象同处一室 —— 一眼能看出谁在工作、谁在休息、谁不在。

本设计升级现有办公室视图（`web/src/pages/Specialist/SpecialistOffice.tsx`）为正面房间场景 + 活人角色，并同步将仪表盘状态条（`web/src/components/LiveStatusStrip.tsx`）角色化。

## 范围

**做：**
- 办公室正面场景组件（房间插画 + 工位排布）
- 商务角色 SVG 组件（形象变体 + 状态姿态 + 微动画）
- 信息承载改造（头顶气泡 + 名牌 + 悬停操作条）
- 仪表盘状态条迷你角色头像化
- 数据流、接口、交互逻辑（编辑/停用/数据/新增/切表）全部保留

**不做：**
- 不加新依赖（前后端都是）；零后端改动
- 不做真实数字人/头像上传（角色变体确定性分配，不接上传）
- 移动端 RN 不改
- 不加音效、不做可走动角色（工位固定在桌后）

## 架构

```
live-status 轮询（3s 办公室 / 5s 状态条，现有接口与逻辑不动）
  → OfficeScene（场景布局）→ 每工位 SpecialistCharacter（角色，状态驱动姿态）
  → 头顶气泡/名牌/悬停操作条（复用现有事件：编辑拉 detail / 停用 toggle / 数据 Drawer）
```

## 组件设计

### 1. 场景 `web/src/components/office/OfficeScene.tsx`（新）

- 横向扁平插画房间容器：背景墙 + 地板线、两扇窗（淡蓝天 + 云朵）、左侧墙钟（显示真实当前时间）、绿植点缀；全部内联 SVG/纯 CSS，企业色（蓝灰 + 低饱和）
- 工位排布：每排最多 5 个，超出自动换行第二排（`display:flex; flex-wrap`）；每工位固定宽约 170px
- 空态：无专员时渲染空房间 +「暂无数字专员」+ 新增入口（复用现有 Empty 语义）

### 2. 角色 `web/src/components/office/SpecialistCharacter.tsx`（新）

纯内联 SVG 组件（约 120×140 viewBox），一个输入 `variant`（确定性变体）+ `state`：

**形象变体**（按 `specialist.id` 确定性取模分配，保证同一专员每次长相一致）：
- 发型：短发 / 长发 / 发髻 / 寸头 / 卷发（5 种）
- 发色：黑 / 棕 / 金 / 红（4 种）
- 肤色：2 种
- 眼镜：约 1/4 概率
- 着装：深蓝 / 深灰西装衬衫，胸前色条跟随状态色（working 蓝 / idle 琥珀 / offline 灰）

**姿态（状态驱动）**：
- `working`：身体前倾、双手在键盘上；显示器亮屏泛蓝光脉动
- `idle`：后靠椅背、手捧咖啡杯（杯口蒸汽动画）；显示器息屏
- `offline`：角色灰化半透明（opacity + grayscale），工位暗淡，空位感

**微动画**（CSS keyframes 写在组件内 `<style>`，不引动画库）：
- 眨眼：SVG 眼皮矩形 0.5s 周期开合，错开随机延迟
- 呼吸：躯干 group `scale(1→1.02)` 3s 往复
- 打字：键盘上 3 个指尖矩形交替 opacity（working 时）
- 蒸汽：两股上升淡出（idle 时）
- 动画按工位索引加 `animation-delay` 错开，避免同频

### 3. 工位组合 `web/src/components/office/Workstation.tsx`（新）

一个工位 = 场景背景元素（桌 + 显示器 + 椅）+ `SpecialistCharacter` + 名牌 + 头顶气泡：

- **头顶气泡**：working → `phase_text` + 「正在回答：{question_snippet}…」；idle → 「空闲中」；offline → 不显示
- **名牌**：专员名 + 状态色点 + 「今日 N 次」
- **悬停**：浮出操作条（数据 / 编辑 / 停用·启用），`stopPropagation` 防误触；**点击工位 = 数据看板**（复用现有 `onViewData`）
- **编辑**：仍先 `specialistAPI.detail(id)` 拉全量记录再开表单（防 persona 覆盖，既有修复保留）

### 4. 页面改造 `SpecialistOffice.tsx`

- 卡片网格 → `OfficeScene` 场景；顶部工具条（汇总 Tag / 3s 刷新开关 / 刷新 / 新增专员 / Segmented 切表）原样保留
- 轮询、降级、空态、`toSpecialist` 映射逻辑不动

### 5. 仪表盘状态条 `LiveStatusStrip.tsx`

- 每个专员：迷你角色头像（角色组件缩小版 28px，仅头部+肩部，简化渲染）+ 状态色点 + 名字截断
- 5s 轮询、最多 8 个 +「+N」折叠、点击跳转 `/specialist/list` 全部保留

## 错误处理与降级

- live-status 轮询失败：场景保留上次数据，角色按 lifecycle 灰显；不阻塞页面（既有逻辑）
- 接口不可达首载失败：沿用现状（空态语义），不新增特殊处理

## 测试

**前端**：项目无 JS 测试框架 —— 验证 = `npm run build`（tsc -b && vite build）全绿；类型契约（组件 props / LiveStatusItem 字段）由 tsc 把关

**手工验证**：
- 办公室页：多专员（含 >5 个触发第二排）渲染、三种状态姿态/动画、气泡文案、悬停操作条、点击数据看板、编辑预填全量、停用后角色灰化
- 仪表盘：迷你头像、8 个折叠、点击跳转
- 与真实对话联动：聊天进行中观察敲键盘/蓝光流转，结束回空闲姿态

## 参考

- 现有办公室视图：`web/src/pages/Specialist/SpecialistOffice.tsx`（轮询/状态映射/事件处理全部复用）
- 现有状态条：`web/src/components/LiveStatusStrip.tsx`
- 状态模型：`LiveStatusItem`（state: working/idle/offline；phase/phase_text/question_snippet/today_conversations/last_active_at）
- 第一版规格：`docs/superpowers/specs/2026-08-06-digital-office-design.md`
