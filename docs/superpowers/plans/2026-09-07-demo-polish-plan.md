# 演示前体验与口径收尾计划（2026-09-07）

## 背景

09-02 业务/商业视角全量审查 ~40 项，按「演示阶段功能一个不能少」分档后：演示批第一批 11 项（49a9440）、第二批演示环境 4 项（b64c013）已交付；09-07 修复通知契约错位（ef1214f）并固化 dev_up.py（7bb3c4f）。

本计划 = 剩余 **A 档 6 项**（演示时可能被观众看到的功能缺口/数字失真），全部已代码级定位。B 档（上线前合规/成本）与 C 档（产品完整性长期项）不在本计划范围，维持 CLAUDE.md Known Gaps 挂账口径。

**项目约束（2026-09-07 用户确认）**：项目长期在本机运行和演示，终态服务器上线——本计划修的是演示观感与数字可信度，不引入新依赖、不做大架构改动。

## 任务总览

| 任务 | 一句话 | 域 | 预估 |
|---|---|---|---|
| T1 | 医生端站内通知消费 UI（照代表端移植） | mobile-doctor | 2h |
| T2 | 夜间简报纳入卡片追问 | specialist + seed | 2h |
| T3 | 分身好评率排除卡片 useful 灌水 | specialist + web | 1h |
| T4 | MAH 合规通过率分母收敛为代表对话（联动 seed） | specialist + web + seed | 2h |
| T5 | 触达统计：有效阅读口径 + 排序键改被读数 | specialist + web | 1.5h |
| T6 | 拜访时长 clamp + 僵尸进行中徽标 | visit + web | 1h |

批次：**批1 = T1+T2**（医生反馈闭环一个故事）→ **批2 = T3+T4+T5**（三处统计口径 + seed 联动）→ **批3 = T6**。每批后全量回归。

---

## T1 医生端站内通知消费（A-1）

**现状（代码）**：`mobile-doctor/src/api/inbox.ts` 只有收件箱 API，无 notifications 方法；`AppNavigator.tsx` 无通知屏。后端三端点已就绪且角色已放行：`card_pushes.py:129`（list_notifications，`unread_only` 过滤）、`:147`（unread-count）、`:161`（mark_read，单条/all）——`require_roles("rep", "doctor")` 零后端改动。

**根因**：09-03 演示批只做了代表端消费侧（mobile NotificationsScreen + Profile 红点），医生端 card_new 通知仍只写不读——医生对新卡片无任何提醒，只能主动开收件箱。

**方案**：
1. `inbox.ts` 加三方法，**照 `mobile/src/api/academic.ts`（09-07 修复版）**：含 `mapNotification`（is_read→isRead、created_at→createdAt 映射收口 api 层——刚修过的契约错位不重犯）
2. 新 `screens/Notifications/NotificationsScreen.tsx`（从 mobile 同名屏精简移植）：医生端 TYPE_CONFIG 只需 `card_new` + 兜底；`routeForLink`：`/card-pushes` → `Inbox`（代表端是 BriefingList，此处不同）
3. Profile 加「站内通知」菜单行 + 未读数红点（useFocusEffect 拉 unreadCount）
4. 路由/类型三件套同步（AppNavigator、types）

**测试**：新增 notification-contract（锁 URL/method/body + **映射后响应形状**——含 isRead/createdAt 断言，防 snake/camel 错位复发）；`npx tsc --noEmit` 零错。

**拍板点**：入口放 Profile 菜单行（推荐，与代表端一致、改动小）还是收件箱页内嵌？→ 默认 Profile 菜单行。

---

## T2 夜间简报纳入卡片追问（A-2）

**现状（代码）**：`specialist-service/app/core/briefing_generator.py:104-115` `_doctor_rounds` 只查 `Conversation`（join User，specialist_id + 上海窗口）；医生的卡片追问在 `notifications` 表 type=card_question（`card_pushes.py:118-124` 写入：content=追问原文，link=/briefings，user_id=代表）。两源从不交汇。

**根因**：简报设计于二期 G 之前（一期 C），当时卡片反馈还不存在；二期 G 落地后简报数据源未扩。

**方案**：
1. 新 `_card_questions(db, representative_id, since, until)`：查 `Notification`（type=card_question、user_id=该 rep、created_at ∈ 窗口）join `card_push_records`（拿 card_id）join `academic_cards`（拿卡片标题）→ `[{doctor_name, card_title, question}]`
2. `generate_for_date`（:129）在 doctor_rounds 为空或非空时**均**追加追问段；`_build_prompt`（:85）扩参：追问独立小节「医生对学术卡片的追问」，qwen JSON 契约同步加 `card_questions` 数组（可选键，缺省不阻塞）
3. 幂等：重跑走既有 upsert（:166/:198），content 重算覆盖——追问并段后自动包含
4. `seed_demo_data.py` 补 1 条窗口内 card_question 通知（已有「医生追问」数据吗？09-03 seed 有通知 4 条 rep 未读 2，其中含 card_question——核对在窗口内即可，不在则补）

**测试**：specialist 单测——造 Conversation（窗口内/外）+ Notification（card_question 窗口内）各若干，断言 prompt 与简报 content 含追问段、窗口外不进；既有上海日界判别测试不回归。

**拍板点**：追问放简报新增小节（推荐）vs 并入「需跟进事项」列表。

---

## T3 分身好评率排除卡片 useful 灌水（A-3）

**现状（代码）**：`specialists.py:231-241`（`/specialists/monitor` 聚合）对 `ConversationFeedback` 全量 count——卡片 useful 回流行（`card_pushes.py:107-114`：conversation_id=None、rating=1）全部计入。rating 只有 1 的卡片行**单向抬高**好评率（医生对话本身无负反馈来源时不平衡）。注意 `/{specialist_id}/stats`（:481）是反馈明细列表非聚合，无需改。

**根因**：二期 G 终审把卡片 useful 回流计入 approval_rate 是当时唯一反馈源；三期起对话反馈（rating 1/-1）上线后两口径混在同一指标。

**方案**：`/monitor` 聚合加 `ConversationFeedback.conversation_id.isnot(None)` 过滤——approval_rate 语义收敛为「**对话**好评率」；卡片 useful 留 conversation_feedback 行做留痕与卡片域统计（card_pushes 有自己的 read/favorited），不再进分身好评率。web `MonitorList` 好评率列 tooltip 加口径说明。

**测试**：specialist 单测——造对话好评（conversation_id 有值）+ 卡片 useful（None）两行，断言仅前者计入。

**拍板点（可选不做）**：mobile-doctor TwinChat 加点赞/点踩入口补医生侧数据源——工作量半天、非演示必需；默认不做挂 C 档。

---

## T4 MAH 合规通过率分母收敛（A-4，联动 seed）

**现状（代码）**：`mah_overview.py:57-63`——`total_conv` = 全库 Conversation 行（prep 已排除）。三重失真：
1. **医生行稀释**：medical_qa 对话（医生发起）计入分母，但医生不是被合规管理的 rep——数字被无关行摊薄
2. **medical 拦截不落库**：`medical.py:126-135` 被拦问答只写审计直接 return，不写 Conversation——医生被拦提问对指标不可见（配合①导致该口径既漏分子又混分母）
3. 无对话记 1.0（web MahOverview.tsx:89-91 已有文案披露，保持）

**根因**：MAH 面板语义是「**代表**合规管理全景」，实现时却拿全库对话当分母。

**方案**：
1. 分母/分子均加 `User.role == "rep"`（join）——医生行整体排除，失真①②一次收敛（medical 拦截本就不属代表行为，落库与否不再影响本指标；medical 侧留痕走审计已有）
2. web `MahOverview.tsx:89-91` 口径注释与展示文案同步（「代表分身对话未被拦截占比」）
3. **联动（关键）**：`seed_demo_data.py` 的 8 条医生对话改后全不进分母 → 分母归零、面板显示 1.0（无数据）——seed 必须补 **rep 侧分身对话**（建议 6 条合规 + 1 条 blocked（R001 命中演示拦截闭环）+ 1 条 warn），MAH 面板才有真实感
4. 顺带：`/specialists/review-queue`、`/monitor` 的 compliance_health 已排除 prep，**未排除医生行**——同批一并加 role 过滤（口径一致，T3/T4 同文件顺手）

**测试**：mah 单测（rep/doctor 对话混合，断言医生行不进分母、blocked rep 行进分子）；seed 重跑 + 库内核验 MAH 数字非 1.0。

**拍板点**：分母口径=「rep 的全部分身对话」（推荐，含 visit_prep 已排除）vs「rep+doctor 但医生拦截也落库」。

---

## T5 触达统计：有效阅读 + 排序键（A-5）

**现状（代码）**：
- `card_pushes.py:59-67`（track）：read_status 客户端自报即计 read（秒退也算），tracked_seconds 仅要求 >0 无上限（可传 999999 刷有效时长）
- `academic_cards.py:206-217`（stats）：total_reads = `read_status != 'unread'` 计数（口径=被打开）；`rep_ranking` `order_by(count(id).desc())`——**按推送量排序**，轰炸越多排越前

**方案**：
1. track 服务端 clamp：`tracked_seconds = min(seconds, 3600)`
2. stats 新增 `effective_reads` / `effective_read_rate`：`read_status IN (read, favorited, forwarded) AND tracked_seconds >= 3`（常量 EFFECTIVE_READ_MIN_SECONDS=3）——旧 read_rate 保留（口径=被打开，移动端兼容）
3. `rep_ranking` 排序键改 `reads DESC, pushes DESC`（产出被读优先，推送量仅次位）+ 返回体加 read_rate 供 web 展示
4. web 触达统计页（CardStats）：代表排行按被读数排序展示 + 并列展示「有效阅读率」两指标

**测试**：specialist 单测——秒退（tracked_seconds=1）不计有效、clamp 上限、排序键（A 推 10 读 2 < B 推 3 读 3 时 B 在前）。

**拍板点**：有效阅读阈值 3s；新旧口径并列展示（推荐）vs 直接替换。

---

## T6 拜访时长 clamp + 僵尸进行中徽标（A-6）

**现状（代码）**：
- `visit-service/app/core/visit_manager.py:1013-1015`：`duration = max(1, (now - visit_time) // 60)` 墙钟——忘点结束第二天补 end，时长直接 20h+
- 无超时收尾机制：in_progress 永久挂（列表/工作台持续展示）
- 移动端 `mobile/src/api/visit.ts:128-134` 直接消费 duration_minutes

**方案（演示最小，自动收尾扫描不做挂 B 档）**：
1. end_visit duration clamp：`VISIT_MAX_DURATION_MINUTES = 240`（4h）封顶；触顶时 AI prompt 注入「代表未及时结束拜访，时长按上限记录」→ summary 体现异常（不加列不加迁移）
2. web `VisitList`：status=in_progress 且 visit_time 超 24h → 行灰态 +「未正常结束」徽标（纯前端 ~10 行）

**测试**：visit 单测（visit_time 6h 前 → duration=240；1.5h → 90）；web build。

**拍板点**：上限 4h（推荐，医药代表单次拜访常识上限）vs 8h。

---

## 执行顺序与验证门

```
批1 T1+T2 → 回归：specialist 全量 / mobile-doctor tsc+jest / seed 重跑核验
批2 T3+T4+T5 → 回归：specialist 全量 / web tsc+vitest+build / seed 重跑 + MAH 数字核验
批3 T6 → 回归：visit 全量 / web build
终验：dev_up --check 全绿 + 模拟器走查——
  医生端通知红点点开即读（重进不复活）/ 简报含追问段 /
  monitor 好评率不含卡片行 / MAH 面板数字非 100% 且分母=rep 对话 /
  触达排行按被读排 / 超时 in_progress 徽标
```

基线（2026-09-03 时点）：specialist 349 / visit 118 / web vitest 19 / mobile-doctor jest 32 / mobile jest 105。

## 拍板点汇总

| # | 问题 | 推荐默认 |
|---|---|---|
| 1 | T1 通知入口 | Profile 菜单行 |
| 2 | T2 追问位置 | 简报新增小节 |
| 3 | T3 医生端对话打分入口 | 不做（挂 C 档） |
| 4 | T4 分母口径 | rep 的分身对话（排除医生行） |
| 5 | T5 有效阅读阈值/展示 | 3s；新旧并列 |
| 6 | T6 时长上限 | 240 分钟 |

全部按推荐默认即可直接进 SDD 执行；有异议改本表再开工。
