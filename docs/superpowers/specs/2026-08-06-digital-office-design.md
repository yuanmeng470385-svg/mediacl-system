# 数字员工办公室（Marvis 风格）设计

日期：2026-08-06
状态：已评审通过，待实施

## 背景与目标

老板看到腾讯 Marvis 的「虚拟办公室」——6 个数字 Agent 动态显示在工作还是休息——要求在 MedAgent Web 管理后台复刻该体验。本设计聚焦**数字专员**（数字员工）的实时工作状态可视化：每个专员显示当前动作（合规预检 / 知识检索 / 生成回答 / 合规审核 / 空闲 / 离线），并在数字专员页与仪表盘两处展示。

## 范围

**做：**
- 后端 specialist-service：活动注册表 + 对话链路动作点埋点 + `GET /specialists/live-status` 接口
- 前端数字专员页：办公室视图（默认）+ 原表格视图切换
- 前端仪表盘：顶部「数字员工实时状态」状态条

**不做：**
- 移动端 RN 不改
- 不做摸鱼小剧场动画（企业化风格，非卡通）
- 不动其他 7 个服务（gateway/auth/visit/knowledge/compliance/audit/hcp）
- 不加新依赖（前后端都是）

## 架构

```
对话链路（REST chat / WS chat 共用 AnswerGenerator）
  → 阶段切换时写入 activity_registry（进程内单例 dict）
  → GET /api/v1/specialists/live-status 读取注册表 + conversations 表降级推断
  → Web 后台 3s/5s 轮询渲染办公室视图 / 仪表盘状态条
```

## 后端设计（specialist-service）

### 活动注册表 `app/core/activity_registry.py`（新文件）

进程内单例，`specialist_id → ActivitySnapshot`：

```python
@dataclass
class ActivitySnapshot:
    state: str            # "working" | "idle"
    phase: str            # "compliance_precheck" | "generating" | "compliance_review" | "done"
    phase_since: datetime
    question_snippet: str  # 问题截断 20 字
```

接口：`set_working(specialist_id, phase, question_snippet)` / `set_idle(specialist_id)` / `get(specialist_id)` / `all()`。

FastAPI 单事件循环内读写，无需锁；注册表不持久化，进程重启自动清空（见降级规则）。

### 动作点埋点（`app/core/answer_generator.py`）

`generate()` 与 `generate_stream()` 两条链路各阶段切换时调用注册表：

| 阶段 | phase | phase_text（前端展示） |
|---|---|---|
| 合规预检 | `compliance_precheck` | 正在核查问题合规性 |
| 调百炼生成（内部含知识检索） | `generating` | 正在检索知识库并生成回答 |
| 合规审核 | `compliance_review` | 正在审核回答合规性 |
| 完成 | `done` → 随即 `idle` | 空闲中 |

异常路径（合规拦截 / 百炼异常 / 降级回答）：进入 finally 统一置 idle，保证状态不悬挂。

### 新接口 `GET /api/v1/specialists/live-status`（`app/api/specialists.py`）

鉴权：`get_current_user`（管理员后台，与列表接口一致）。

```json
{
  "code": 0, "message": "success",
  "data": {
    "items": [
      {
        "id": 1, "name": "学术专员-肺癌",
        "lifecycle": "active",
        "state": "working",
        "phase": "generating",
        "phase_text": "正在检索知识库并生成回答",
        "phase_since": "2026-08-06T10:00:00Z",
        "question_snippet": "肺癌用药注意事项…",
        "today_conversations": 12,
        "last_active_at": "2026-08-06T09:58:00Z"
      }
    ],
    "summary": { "working": 3, "idle": 5, "offline": 2 }
  }
}
```

### 状态推导规则

| lifecycle | 注册表 | 推导结果 |
|---|---|---|
| `disabled` / `draft` | — | **offline** |
| `active` | 有记录 | **working**（带 phase） |
| `active` | 无记录 | conversations 表最近 5 分钟有对话 → **working**（phase=generating 粗粒度）；否则 **idle** |

- 服务启动时按 conversations 最近活跃为每个 active 专员重建粗粒度状态，避免重启瞬间全屏变空闲
- `today_conversations`：conversations 表当日计数（与 stats 口径一致）
- `last_active_at`：注册表 phase_since 或最近对话时间

## 前端设计

### 数字专员页 · 办公室视图（`web/src/pages/Specialist/SpecialistOffice.tsx` 新组件）

页面结构（办公室为默认视图）：

- 顶部概览区：汇总数字（工作中 / 空闲 / 离线）+ 轮询开关 + 新增专员按钮 + Segmented 切换「办公室 | 表格」
- 主体：工位卡片网格（响应式，lg 4 列 / sm 2 列），每张卡片：
  - 机器人头像，状态色描边 + 光晕（working 蓝 / idle 琥珀 / offline 灰）
  - 名称 + 生命周期 Tag（正式 / 停用 / 草稿，复用现有 STATUS_MAP）
  - 状态区：working → phase_text + 「正在回答：{question_snippet}」；idle → ☕「空闲中」；offline → 灰显「离线」
  - 底部小字：今日对话数 + 最近活跃时间
  - 悬停操作：编辑 / 启用停用 / 数据看板（复用 SpecialistForm 弹窗与 SpecialistDataDrawer）
  - 卡片点击 → 数据看板 Drawer
- 动画：CSS keyframes（转圈 / 呼吸光晕 / 浮动），按卡片索引错开 delay；不引动画库
- 轮询：3s + 开关；失败静默保留旧数据；接口不可达时卡片只显示生命周期状态
- 空态：无专员时显示「暂无数字专员」+ 新增入口

表格视图：现有 ProTable 原封保留（新增 / 编辑 / 停用 / 数据抽屉全部不变）。

### 仪表盘 · 顶部状态条（`web/src/components/LiveStatusStrip.tsx` 新组件）

- 位置：KPI 卡上方，横向一条
- 内容：迷你工位（头像 + 状态色点 + 动作文案截断），最多 8 个，超出折叠「+N」；右侧汇总「工作中 X · 空闲 Y · 离线 Z」+「查看全部」
- hover Tooltip：名字 + 完整动作 + 问题摘要
- 点击任意工位或「查看全部」→ 跳转 `/specialist/list`
- 轮询 5s（与现有实时动态同节奏），失败静默

### 前端共用改动

- `web/src/services/specialist.ts`：新增 `liveStatus()`（调用 `GET /specialists/live-status`）
- `web/src/types/index.ts`：新增 `LiveStatus` / `LiveStatusItem` / `LiveSummary` 类型
- 数字专员页 `SpecialistList.tsx`：改为「办公室 | 表格」切换壳（原表格逻辑不动）

## 错误处理与降级

- live-status 接口挂：办公室卡片降级为生命周期状态，仪表盘状态条显示「实时状态不可用」；不阻塞页面其他功能
- 进程重启注册表空：按 conversations 最近活跃重建粗粒度状态，不闪「全离线」
- 轮询间隙完成对话：下一轮自动回到空闲，无状态同步问题

## 测试

**后端（pytest，服务目录下运行）：**
- activity_registry 单元测试：set/get/置空闲/重启重建
- answer_generator 阶段切换埋点：mock 百炼 / 合规 / 审计客户端，断言每个阶段注册表状态正确，异常路径置 idle
- live-status 接口：三分支用例（注册表 working / 注册表空 idle / 停用 offline），鉴权 401 用例

**前端：**
- 状态 → 文案 / 颜色的映射测试（沿用项目现有轻量测试思路，不引新框架）

**手工验证：**
- 起 gateway + specialist-service，Web 后台登录，WS 对话进行中打开办公室页面观察动作流转，结束对话观察回到空闲

## 参考

- 现有实时动态模式：Dashboard 5s 轮询（`web/src/pages/Dashboard/index.tsx`）
- 对话链路：`services/specialist-service/app/core/answer_generator.py`
- 现有接口风格：`services/specialist-service/app/api/specialists.py`
