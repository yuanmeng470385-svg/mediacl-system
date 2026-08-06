# MedAgent 三批缺口修复设计（2026-08-06）

## 背景与现状

上次 bring-up（be5a9e0..640ec73）完成后遗留 6 项缺口，本设计按依赖关系分 3 批依次修复，每批独立 spec→plan→实现→测试闭环。

现状核查结论（2026-08-06 全部经子代理核实）：

| 缺口 | 现状 |
|---|---|
| web 登录页 | 无 /login 路由直接进 AdminLayout；但 auth service + useAuth hook 已完整实现（login/me、token 存 localStorage），只是 UI 未接线 |
| 五屏零后端调用 | VisitDetail 硬编码+假 loading（visitId 拿了不用）；Profile 已接 profile 接口；Settings/NotificationSettings/HelpCenter 纯本地 |
| ContentScreen 假数据 | ContentScreen.tsx:19-50 仅 3 条 MOCK_CONTENT，零 API 调用 |
| 短信通道 | ConsoleSender 只写日志；AliyunSmsSender 抛错占位，无 SDK、无签名/模板配置 |
| 录音/NLS | 无录音库、无双端权限、无 NLS_APPKEY；ChatScreen 麦克风是死按钮；**后端 NLS 链路已完整就绪**（realtime_asr.py token 换取/流式协议/mock 兜底，ASR WS 协议已定义） |
| WS 流式 | specialist→百炼已走 WS 但服务端攒包一次性返回；specialist 无对外 WS 端点；gateway httpx 仅 HTTP；mobile 纯 fetch 一次性请求 |

后端 API 可用性（网关 ROUTE_MAP 已配置，路径统一 `/api/v1` 前缀）：
- `POST /api/v1/auth/login`：支持手机号+验证码 **或** 用户名+密码（`_login_by_password`，需 users.password_hash 非 NULL，admin 默认 NULL 需先跑 seed_admin）
- `GET /api/v1/visits/{visit_id}`：含 ai_summary/key_points/hcp_interests/hcp_objections/follow_up_suggestions/sentiment/compliance_flags/next_visit_plan/conversation_transcript
- `GET /api/v1/visits`：分页 `{items,total,page,page_size}` + 筛选
- `GET /api/v1/knowledge/documents`（分页+doc_type 筛选）、`GET /api/v1/knowledge/documents/{doc_id}`、`POST /api/v1/knowledge/search`
- 通知设置/FAQ/个人资料自助更新端点：**不存在**（相应屏保持本地/静态，不新增后端）

外部凭证决策（用户已确认）：短信签名+模板 CODE **无** → 代码就绪+配置位；NLS_APPKEY **无** → 录音全做、识别走现成链路+配置位。

---

## 批次 1：前端接入批（web 登录页 + 五屏 + ContentScreen）

### 1.1 web 登录页（web/）

- 新建 `web/src/pages/Login/index.tsx`：用户名+密码表单（复用现有 `useAuth().login(username, password)`，签名已匹配），登录成功跳 /dashboard，失败显示后端错误信息
- `web/src/App.tsx`：加 `/login` 路由；路由守卫——无 token（localStorage `medagent_token`）访问受保护路由重定向 /login，/login 已登录则跳 /dashboard
- `web/src/services/client.ts`：401 拦截器从"静默处理"改为清除 token + 跳 /login
- `web/src/layouts/AdminLayout.tsx`：已显示 user 信息 + logout，保持
- **部署前置**：admin 需先跑 `scripts/seed_admin.py` 设密码（否则 password_hash NULL 无法密码登录），写进 CLAUDE.md 登录说明
- 后端零改动

### 1.2 五屏接后端（mobile/）

| 屏 | 改动 |
|---|---|
| VisitDetail（VisitDetailScreen.tsx） | 用路由 visitId 调 `GET /api/v1/visits/{visit_id}`；字段映射 ai_summary/key_points/hcp_interests/hcp_objections/follow_up_suggestions/sentiment/compliance_flags；**删除 800ms 假 loading**（:20-23），换真 loading + 错误态（加载失败显示重试）；api 模块已有 visit.ts，补 `getVisitDetail` + 契约测试 |
| Profile（ProfileScreen.tsx） | 统计数字从硬编码 `'--'` 改为调 `GET /api/v1/visits`（page=1,page_size=1）取 total 显示拜访总数；其余保持 |
| Settings（SettingsScreen.tsx） | 顶部显示登录账号/角色/区域（AuthContext 已有 user），加"退出登录"按钮（AuthContext 若无 logout 则补，并清 token 回登录流程）；菜单保持本地 |
| NotificationSettings | 开关状态从 useState 改为 **AsyncStorage 持久化**（键 `notification_settings`），启动读、切换写；后端无端点，不新增 |
| HelpCenter（HelpCenterScreen.tsx） | FAQ 保持静态（内容本就静态）；版本号改读 package.json 真实版本（require/import 或注入） |

### 1.3 ContentScreen 接 content API（mobile/）

- 新建 `mobile/src/api/content.ts`：`getDocuments({page,page_size,doc_type})` → `GET /api/v1/knowledge/documents`（doc_type 映射 guideline/literature/manual，status 过滤由服务端/查询参数处理）；`getDocument(docId)` → `GET /api/v1/knowledge/documents/{doc_id}`
- 契约测试：加入 `mobile/src/api/__tests__/api-contract.test.ts` 或新建 content 契约用例（沿用现有 mock fetch 模式）
- ContentScreen.tsx：删 MOCK_CONTENT（:19-50），数据源改 api；tab 过滤改前端按 type 过滤或服务端 doc_type 参数（前端过滤更简单，保留现有 `filteredContent` 结构）；loading/错误/空态（EmptyState 复用）；下拉刷新（RefreshControl）
- 字段映射：ContentItem(id/title/type/summary/source/publish_date/evidence_level/tags) ↔ knowledge_documents 实际字段；**缺字段前端容错**（undefined 不渲染/显示占位），映射函数 `mapDocToContentItem` 单测覆盖缺字段情形
- 卡片 onPress → 新建 `mobile/src/screens/Content/ContentDetailScreen.tsx`：展示文档详情（title/正文/source/日期），正文为空显示空态
- 导航：ContentScreen 的 stack 注册新详情页（app 导航结构内）
- 数据现状：knowledge-base/ 为空目录 → 页面初始显示空态（文案提示"内容库建设中"）；联调用 `scripts/seed_demo_docs.py` 灌 3 篇演示文档
- `src/types/index.ts` ContentItem 若无 evidence_level/tags 映射则保留可选字段

---

## 批次 2：外部服务接入批（短信 + 录音/NLS）

### 2.1 短信真实现（services/auth-service）

- requirements.txt 新增 `alibabacloud_dysmsapi20170525`
- `app/services/sms.py` AliyunSmsSender 真实现（替换抛错占位，保留 fail-fast 精神）：
  - 构造时读 `AUTH_SMS_SIGN_NAME` + `AUTH_SMS_TEMPLATE_CODE`，缺失抛 `SmsSendError`（明确列出缺哪个）
  - 复用 `ALIYUN_ACCESS_KEY_ID` / `ALIYUN_ACCESS_KEY_SECRET`（.env 现有命名需与 config.py 读取一致）建 dysmsapi 客户端；REGION 用现有 `ALIYUN_REGION` 或缺省 `cn-shanghai`
  - `send_code(phone, code)`：调 SendSms，模板变量 `{"code": code}`；返回 Code != "OK" 或异常 → 抛 `SmsSendError`（上层 auth.py:105 已转业务错误 6001）
  - 对手机号做与 auth.py:82 一致的格式校验（或沿用上层校验，不重复）
- `app/config.py`：加 `SMS_SIGN_NAME` / `SMS_TEMPLATE_CODE` 两个配置项（getenv，无默认值即 None）
- `.env.example`：加 `AUTH_SMS_SIGN_NAME=` / `AUTH_SMS_TEMPLATE_CODE=` 注释"阿里云短信签名/模板 CODE，配置后 AUTH_SMS_PROVIDER=aliyun 生效"
- 测试（tests/test_sms.py 或并入 test_auth.py）：
  - mock dysmsapi 客户端（monkeypatch 构造器或 dependency 注入），三分支：成功（Code=OK）、业务失败（Code!=OK 抛错）、签名缺失（构造抛错）
  - 现有 RecordingSender/ConsoleSender 测试保持
- **不真发短信**（无凭证）；凭证到位后改 `AUTH_SMS_PROVIDER=aliyun` 即启用

### 2.2 录音/NLS（mobile + 复用现成 ASR 链路）

后端 NLS 链路已就绪：`visit-service/app/services/realtime_asr.py`（token 换取+流式协议+MockRealtimeAsrClient）、`app/api/asr_ws.py`（`/ws/visits/{visit_id}/asr?token=JWT`，binary=PCM 16k/16bit/mono，text=`{"type":"stop"}`，回 `ready/sentence/compliance/error/completed` 帧，fail-closed：无 NLS_APPKEY 且无 NLS_MOCK → error 4500）。**后端零改动**。

mobile 侧：
- package.json 新增 `react-native-audio-record`（WAV 16k/16bit/mono 录制；不用 react-native-live-audio-stream——过老，RN 0.75 兼容风险高）
- Android：`android/app/src/main/AndroidManifest.xml` 加 `<uses-permission android:name="android.permission.RECORD_AUDIO"/>`
- iOS：`ios/medagentmobile/Info.plist` 加 `NSMicrophoneUsageDescription`（用途文案如"用于语音提问与拜访录音转写"）
- 新建 `mobile/src/services/asr.ts`：ASR WS 客户端封装——连接 `/ws/visits/{visit_id}/asr?token=JWT`（**直连 visit-service:8002**，与 CLAUDE.md「WS 不走网关」定论一致；批次 3 网关代理只覆盖 chat 路径，ASR 不代理）、发送 PCM 帧（跳过 WAV 44 字节头）、帧解析（ready/sentence/compliance/error/completed）、事件回调（onSentence/onReady/onError/onCompleted）、连接清理；单元测试 mock WebSocket 覆盖帧解析与错误路径
- ChatScreen.tsx 麦克风按钮（:207-209）接线：按下→请求录音权限→AudioRecord 开始录 WAV→连 ASR WS 边录边推帧→sentence 增量上屏→停录发 stop→completed 后转写文本填入输入框；录音/转写中按钮状态机（idle/recording/transcribing）；无 NLS_APPKEY 时收到 error 帧 → Toast 提示"NLS 未配置"，不产生假文本
- 录音文件录制位置：缓存目录，用完清理
- 联调路径：`NLS_MOCK=1` 服务端 Mock 会话吐假断句（不落库）全链路联调；Android 模拟器无麦克风 → 录音真机受限，以协议单测 + mock 联调为主
- VisitInProgressScreen 的 simulateInput 不动（拜访记录模拟功能，非语音转写）

---

## 批次 3：WS 流式完整链路（specialist + gateway + mobile）

### 3.1 specialist 对外 WS 端点（services/specialist-service）

- 新增 `app/api/chat_ws.py`（或并入 specialists.py）：`/ws/specialists/{specialist_id}/chat?token=<JWT>`
  - 鉴权：query token，`verify_token` 失败关 4401（复用 visit ASR 模式；若 specialist 无 verify_token 工具则从 shared 引入）
  - 客户端→服务端：Text JSON
    - `{"type":"question","text":"...","session_id":"..."}` 首帧必发（问题由此传递；URL 只带 specialist_id）
    - `{"type":"stop"}`（可选，中止当前流式生成）
  - 服务端→客户端（send 加锁防 websockets>=12 ConcurrencyError，沿用 asr_ws.py send_lock 模式）：
    - `{"type":"start","request_id":...}` 收到 question 后开始生成（conversation_id 无法在生成前给出——落库需完整答案，由 done 帧携带）
    - `{"type":"delta","text":"..."}` 百炼 RespondingContent 增量文本（bailian_client 需新增 `chat_stream()` 方法，REST `chat()` 保留复用流式内部实现）
    - `{"type":"done","text":"<全文>","session_id":...,"conversation_id":...,"citations":[...]}` 结束（conversation_id 由 `_persist_conversation` 在生成完成后落库返回）
    - `{"type":"error","message":...}` 后关 4500
  - 落库：沿用 `_persist_conversation`；feedback/favorite 仍走 REST（不动）
- 单测：`tests/test_chat_ws.py`，mock 百炼（扩展现有 `_FakeWs` 模式）覆盖 delta 顺序、done 落库、error 路径
- REST `POST /chat` 保留（mobile fallback 与既有测试不破坏）

### 3.2 gateway WS 代理（services/gateway）

- `app/main.py` 新增 WS 路由：`/api/v1/specialists/{specialist_id}/chat/ws` → 双向透传 specialist-service:8001 `/ws/specialists/{specialist_id}/chat`，token query param 原样透传（认证由 specialist 做，与 ASR 直连模式一致；网关不重复鉴权）
- 实现：starlette WebSocket，receive→forward send（binary/text 均透传），异常/断开关闭两侧连接；uvicorn 原生支持 WS，无新依赖
- 透传路径与 ROUTE_MAP 的 HTTP 规则共存（WS 路由单独注册，不冲突）
- 测试：TestClient websocket_connect 到网关代理 → 断言转发/回传（对 specialist 用 Fake 上游或仅验证握手路由存在 + 单测转发逻辑）

### 3.3 mobile 流式客户端（mobile/）

- 新建 `mobile/src/services/wsChat.ts`：RN 内置 WebSocket（**零新依赖**）——连接 `/api/v1/specialists/{id}/chat/ws?token=...`（走网关 8000）、发送 question 帧、帧处理（start/delta/done/error）、断线自动降级 REST（调用现有 specialist.chat POST）、事件回调；单测 mock WebSocket
- ChatScreen.tsx：发送消息改优先 WS 流式（连接后发 question 帧，delta 逐字追加显示，替换现有整条 POST 返回的渲染路径）；WS 连不上、error 或 8s 内未收到 start → 自动降级现有 REST 路径；流式状态机（sending/streaming/done/error）
- REST chat 路径保留作 fallback，现有契约测试不破坏
- 会话创建逻辑：现有 chat 接口负责 conversation_id 返回；WS 的 conversation_id 由 done 帧携带（反馈/收藏以 done 帧为准）

---

## 测试策略汇总

- 批次 1：web 无独立测试框架的现状下做手工冒烟（vite dev + 浏览器）；mobile 契约测试补 visit-detail/content 用例；跑 `yarn test`（或现有测试命令）全绿
- 批次 2：auth-service pytest（sms 三分支 + 既有全量）；mobile asr.ts 单测；后端全量 pytest 回归
- 批次 3：specialist pytest（chat_ws + 既有 11 用例回归）；gateway pytest（WS 代理 + 既有 health）；mobile wsChat 单测 + 既有契约测试
- 每批完成后 git commit（沿用仓库 message 惯例：`fix(scope): 描述` / `feat(scope): 描述`）

## 顺序与依赖

批次 1 → 批次 2 → 批次 3，严格串行。批次 1 与 2 无依赖可并行实现但按用户要求依次执行；批次 3 依赖批次 2 的录音（ASR WS 复用经验）但代码上独立。

## 明确不做（YAGNI）

- 后端新增通知设置/FAQ 端点（无需求依据）
- NLS 真机转写实测（无 appkey、模拟器无麦克风）
- 短信真发（无签名/模板凭证）
- web 端聊天功能（无需求依据，批次 3 只做 mobile）
- SSE 替代 WS（用户已选完整 WS 链路）
