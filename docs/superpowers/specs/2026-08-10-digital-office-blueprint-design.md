# 数字员工办公室 · 3D 俯视蓝图版（v3）设计

日期：2026-08-10
状态：设计已获用户确认，待实施

## 背景与目标

v2 正面房间场景（2026-08-10-digital-office-scene-design.md，已实施并推送）被老板否决。新要求：

> 画面中心是 **3D 俯视办公室工位布局平面图**，空间内整齐排布几排独立工位，每个工位固定放置 **1 个极简扁平化 3D 白色小人** 模型（代表在岗员工 / AI 数字坐席），工位用**浅蓝发光线条**划分过道与办公区域，3D 场景支持**轻微透视立体感**，不是纯 2D 平面图。

用户逐项确认的关键决策：
- **透视强度**：轻微俯视（地板 `rotateX` 约 15-20°），工位/小人 billboard 反旋转保持直立可读
- **状态表达**：小人保持纯白，**工位灯带变色**（工作蓝 / 空闲琥珀 / 离线灰）——与浅蓝发光线条同一视觉语言，过道里一眼可辨
- **场景处理**：**纯蓝图平面**——深色地板 + 浅蓝发光网格/过道分隔线，无墙钟/绿植/窗等装饰

## 范围

**做：**
- 蓝图平面场景组件：深色地板 + 浅蓝发光细分网格 + 过道分隔线，`perspective` + `rotateX` 轻微俯视 3D
- 工位卡座组件：深色半透明桌面卡座 + 浅蓝发光描边 + 状态灯带 + billboard 反旋转
- 极简白色小人组件：统一白色人形（头+躯干+描边+投影），保留眨眼/呼吸微动画
- 仪表盘状态条 MiniCharacter 同步白色化（视觉一致）
- 数据流、接口、交互逻辑（编辑/停用/数据/新增/切表）全部保留

**不做：**
- 不加新依赖（前后端都是）；零后端改动
- 不做真实 3D 引擎/库（Three.js 等）——纯 CSS 变换实现
- 不做等距（isometric）强 3D、不做可走动角色
- 移动端 RN 不改
- 不保留房间装饰元素（墙钟/绿植/窗）
- 小人不再有发型/肤色/眼镜多样性（身份由名牌区分）

## 架构

```
live-status 轮询（3s 办公室 / 5s 状态条，现有接口与逻辑不动）
  → OfficeScene（perspective 容器 + 蓝图地板平面）
    → 每工位 Workstation（rotateX(-18°) 反旋转直立；卡座 + 灯带 + 小人）
      → SpecialistCharacter（白色小人，状态驱动姿态/灰化）
      → 名牌 / 气泡 / 悬停操作条（复用现有事件：编辑拉 detail / 停用 toggle / 数据 Drawer）
```

## 组件设计

### 1. 场景 `web/src/components/office/OfficeScene.tsx`（重写）

- **透视容器**：`.office-floor-3d { perspective: 900px; }`（视点高度），内部地板平面 `transform: rotateX(18deg); transform-style: preserve-3d;`
- **地板**：深蓝灰底（约 `#101828`→`#1d2a3d` 渐变）+ 浅蓝发光细分网格（CSS 线性渐变画线，线色 `#58a6ff` 低透明度 + 浅发光），建筑图纸感
- **工位排布**：每排 **6 个**，`display:flex; flex-wrap` 自动换行；排间一条加粗浅蓝发光**过道分隔线**（`box-shadow` glow）；左右留过道边距；反旋转后俯视间距显密 → `gap` 加大到约 **38px**（视觉等距）
- **空态**：无专员时渲染空蓝图房间 +「暂无数字专员」+ 新增入口（复用现有 Empty 语义）

### 2. 工位卡座 `web/src/components/office/Workstation.tsx`（重写）

- **卡座**：深色半透明圆角块（约 150px 宽 × 110px 深），浅蓝发光描边（`border + box-shadow: 0 0 12px rgba(88,166,255,.35)`），随地板 `rotateX(18deg)` 被透视压扁 → 立体俯视感
- **billboard 反旋转**：工位内部内容层 `rotateX(-18deg)` 抵消透视，名牌/气泡/小人保持直立可读
- **状态灯带**（桌面下沿一条发光条，状态核心）：
  - `working`：`#1677ff`，呼吸脉动（opacity 0.6→1 循环）
  - `idle`：`#faad14`，常亮微光
  - `offline`：`#bfbfbf`，熄灭感（低透明度，不脉动）
  - 灯带 glow 用多层 `box-shadow`（避免 filter blur 性能损耗）
- **头顶气泡**：working → `phase_text` +「正在回答：{question_snippet}…」；idle → 「空闲中」；offline → 不显示
- **名牌**：专员名 + 状态色点 + 「今日 N 次」+ lifecycle Tag（disabled/draft 灰显）
- **悬停**：操作条（数据 / 编辑 / 停用·启用），`stopPropagation` 防误触；点击工位 = 数据看板
- **编辑**：仍先 `specialistAPI.detail(id)` 拉全量记录再开表单（防 persona 覆盖，既有修复保留）

### 3. 白色小人 `web/src/components/office/SpecialistCharacter.tsx`（重写）

- **统一白色极简人形**：纯白圆头 + 圆角躯干 + 细灰描边（`#666`），脚下椭圆投影（站立感）；约 40px 高，棋子感；`viewBox` 约 48×60
- **不再有变体**（无发型/肤色/眼镜/西装差异）——所有专员同一白色形象，身份靠名牌
- **微动画**（CSS keyframes，不引库）：
  - 眨眼：眼皮细线 4s 周期开合（白底上用灰色眼皮，保持可见）
  - 呼吸：躯干轻微 scale 3s 往复
  - offline：整体灰化半透明（opacity + grayscale）
- **MiniCharacter**（状态条头像，44×44 头+肩）：同步白色化，`state` 仍驱动灰化；状态色点由 `LiveStatusStrip.tsx` 现有逻辑提供（已恢复，保留）

### 4. 页面 `SpecialistOffice.tsx`（不动）

- 轮询、降级、空态、`toSpecialist` 映射、工具条、编辑 detail 防覆盖——全部原样保留

### 5. 仪表盘状态条 `LiveStatusStrip.tsx`（仅 MiniCharacter 视觉同步）

- 迷你角色头像白化，其余（5s 轮询 / 8 上限 / +N 折叠 / 状态色点 / 跳转）不动

## 视觉规范（精确值）

| 项 | 值 |
|---|---|
| 透视容器 | `perspective: 900px` |
| 地板旋转 | `rotateX(18deg)`，`transform-style: preserve-3d` |
| 地板底色 | `#101828` → `#1d2a3d` 渐变 |
| 网格/过道线 | `#58a6ff`（发光线条），过道线加粗 + glow |
| 工位排数 | 每排 6 个，flex-wrap 自动换行，`gap` ~38px |
| 卡座 | 约 150×110px，深色半透明，浅蓝发光描边 |
| 状态灯带 | working `#1677ff` 脉动 / idle `#faad14` 常亮 / offline `#bfbfbf` 熄灭 |
| 小人 | 纯白 + 描边 `#666`，约 40px 高（viewBox 48×60） |
| 动画 | 仅 opacity / transform / box-shadow（合成层属性） |

## 错误处理与降级

- live-status 轮询失败：场景保留上次数据，灯带/小人按 lifecycle 灰显；不阻塞页面（既有逻辑）
- 接口不可达首载失败：沿用现状（空态语义），不新增特殊处理

## 测试

**前端**：项目无 JS 测试框架 —— 验证 = `npm run build`（tsc -b && vite build）全绿；类型契约由 tsc 把关

**手工验证（Playwright 截图 + 浏览器）**：
- 俯视透视成立：地板有纵深、工位/小人/名牌直立可读、第二排布局正常
- 蓝图元素：细分网格、过道分隔线（发光）、卡座描边
- 三状态灯带：蓝脉动 / 琥珀常亮 / 灰熄灭；offline 小人灰化
- 气泡/名牌/悬停操作条/点击数据看板/编辑预填全量/停用后灰化——回归
- 仪表盘：白色迷你头像 + 状态色点、8 个折叠、点击跳转
- 与真实对话联动：聊天进行中灯带蓝光脉动 + 气泡流转，结束回空闲

## 参考

- v2 规格：`docs/superpowers/specs/2026-08-10-digital-office-scene-design.md`（数据流/交互全部复用，仅视觉重设计）
- 现有组件：`web/src/components/office/`（SpecialistCharacter / Workstation / OfficeScene）
- 状态模型：`LiveStatusItem`（state: working/idle/offline；phase/phase_text/question_snippet/today_conversations/last_active_at）
