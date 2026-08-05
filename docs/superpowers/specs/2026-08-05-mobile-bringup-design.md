# MedAgent 移动端 Bring-up 设计文档（2026-08-05）

> 目标：让 `mobile/` 从「5540 行从未编译过的源码」变成「能在 Pixel_7 模拟器上真实登录并跑通主流程的 App」。
> 基线：2026-08-05 全项目审计。后端 108 项测试全绿、web `tsc` 通过、git 工作区干净；问题集中在移动端。

## 0. 审计结论（本设计的出发点）

`mobile/src` 已按方案 11.1 写齐 16 个屏幕（方案只列了 12 个），UI 层不缺。缺的是三样东西：

1. **原生工程不存在** —— 无 `index.js`/`metro.config.js`/`babel.config.js`/`app.json`/`android/`，`ios/` 是 0 文件空目录。`npm start` 与 `run-android` 都无法执行，那 5540 行代码从未被编译过一次。
2. **3 个 TypeScript 错误** —— CI 的 `cd mobile && npx tsc --noEmit` 步骤必挂，CI 当前是红的。
3. **7 处前后端契约错位** —— 即使编译通过，运行时也会 404 / ParamError / 静默无效。

## 1. 已确认的决策

| 决策点 | 结论 |
|---|---|
| 录音方案 | **NLS 实时流式转写**（对接后端已实现的 `WS /ws/visits/{id}/asr`）。**本轮不做**，留下一轮 |
| 本轮范围 | 原生工程 + 修契约，让现有 16 屏真实跑通 |
| 验收标准 | **全链路实测**：docker-compose 起后端 → 真登录 → 逐屏验证修过的契约。已授权对话页真实调用百炼（产生费用） |
| 原生工程生成方式 | 方案 A：官方 CLI init 到临时目录，搬运原生产物，用完删临时目录 |
| 契约修复方向 | **除一处外全部改前端**。唯一改后端的是 chat 补返 `conversation_id` |
| web 空目录残留 | 一并删除 |

**为什么改前端而不是改后端**：后端有 108 项测试护着，且路由语义本来就更合理 —— feedback 挂 `conversation_id` 比挂 `specialist_id` 正确。唯一必须动后端的是 `conversation_id` 缺环，前端无从构造该主键。

**关键佐证**：`.gitignore` 第 27-31 行已写有 `mobile/ios/Pods/`、`mobile/android/build/`、`mobile/android/app/build/`、`mobile/android/.gradle/` —— 只忽略构建产物、不忽略目录本身，`git check-ignore` 亦确认未忽略。说明**项目本来就设计成要提交原生工程，只是那一步从未执行**。本轮是补齐原定设计，不是新增架构决定。

## 2. 环境事实（已实测确认，非假设）

| 项 | 状态 |
|---|---|
| Node / npm | v25.9.0 / 11.12.1 |
| JDK | Temurin 17.0.19（RN 0.75 要求的版本） |
| ANDROID_HOME | `D:\AndroidSDK`，platforms 有 android-34/35/36，build-tools 有 34.0.0/35.0.0，NDK 27，platform-tools/adb 齐全 |
| 模拟器 | AVD `Pixel_7` 已存在 |
| Gradle 发行版 | `~/.gradle/wrapper/dists/gradle-8.8-all` 已完整解压（`.ok` 标记在）—— **正是 RN 0.75 wrapper 指定版本** |
| Gradle 依赖缓存 | `com.facebook.react:react-android:0.75.0`、`hermes-android:0.75.0`、`fbjni`、`soloader`、`yoga`、`fresco` + AGP + 137 组依赖已缓存（时间戳 2026-08-04 11:10） |
| npm registry | 可达（`npm view react-native@0.75.0` 成功） |
| Postgres / Redis | 容器在跑；users 2 行（admin 13800138000、rep_test 13900000002/role=rep）、products 1 行（id=1）、hcps 4 行、digital_specialists 1 行（bailian_app_id 已配）、conversations 12 行 |

**推论**：Gradle 重活儿已在本地，首次构建无需重新下载 react-android AAR 与 Gradle 发行版。`product_id=1` 真实存在，代码里 `productId || 1` 的兜底与库数据一致。conversations 已有 12 行，feedback/favorite 可拿现存行实测，不必依赖新对话。

## 3. 第一节：原生工程落地

### 3.1 生成

```bash
# <TEMP> = 系统临时目录（Windows 下即 %TEMP%，本机为 C:\Users\yuanmenglong\AppData\Local\Temp）
# 该目录仅用于承接 CLI 产物，搬运完毕后整个删除，不留在仓库内
npx @react-native-community/cli@14 init MedAgentMobile \
  --version 0.75.0 \
  --directory <TEMP>/MedAgentMobile \
  --package-name com.medagent.mobile \
  --pm npm --skip-install --skip-git-init
```

`--package-name` 同时设定 Android 包名与 iOS bundle ID，**因此不需要事后手改 Kotlin 包目录、`namespace`/`applicationId`、debug manifest** —— 这是本方案里原本最容易出错的一块，靠 CLI 参数直接绕开。

### 3.2 搬入 `mobile/`

`android/`、`ios/`（覆盖现有空目录）、`index.js`、`metro.config.js`、`babel.config.js`、`app.json`、`jest.config.js`、`.watchmanconfig`、`Gemfile`（iOS CocoaPods 用，留待将来上 Mac）。

### 3.3 三处改动（全部内容）

1. `index.js`：入口 `'./App'` → `'./src/App'`（现有 `src/App.tsx` 已有标准 default export）
2. `app.json`：`name` / `displayName` → `MedAgent`（`index.js` 依赖 `app.json` 的 name 注册组件，两者必须一致）
3. `android/app/build.gradle`：追加
   `apply from: file("../../node_modules/react-native-vector-icons/fonts.gradle")`
   —— 不加这行全 App 图标显示为方框

### 3.4 不搬入

模板根 `App.tsx`、`__tests__/App.test.tsx`（它 import 根 App.tsx）、模板的 `package.json` / `tsconfig.json` / `.eslintrc.js` / `.prettierrc.js` / `README.md` / `.gitignore`。这些是「不复制」，不会进仓库。

### 3.5 新架构

保持 RN 0.75 模板默认 `newArchEnabled=false`。vector-icons 等库对新架构支持不齐，本轮目标是跑起来，不引入该变量。

### 3.6 风险

**Node v25.9.0 对 RN 0.75 偏新**（官方要求 `>=18`，实际验证基线为 18/20），metro 可能报错。这是全流程唯一可能真正卡住的点，且与 Gradle 缓存无关。若触发：先尝试 metro 兼容配置；仍不行则**停下来询问用户**是否切换 Node 版本，不擅自改动全局 Node 环境。

## 4. 第二节：TS 错误与契约修复

### 4.1 三个 TypeScript 错误

| 位置 | 处置 |
|---|---|
| `src/store/AuthContext.tsx:44` | 在 `src/api/auth.ts` 的 `authAPI` 补 `getToken()`，代理到 `apiClient.getToken()`。保持 AuthContext 只依赖 authAPI，不反向 import apiClient |
| `src/api/visit.ts:94` | **删除 `visitAPI.update`**。零调用方；声明的 `status`/`notes` 与后端白名单 `{hcp_id, product_id, specialist_id, visit_time, duration_minutes, attachments}` 完全不重合，说明当初系凭想象所写。下轮真需编辑功能时照后端白名单重写 |
| `src/components/Icon.tsx:8` | 安装 `@types/react-native-vector-icons` |

> `AuthContext.tsx:44` 不只是类型错误：冷启动时 `checkAuth()` 调用不存在的方法抛异常，被 catch 吞掉后走 `authAPI.logout()` 清 token，导致**每次重开 App 都静默登出，永远无法保持登录**。

### 4.2 契约修复（7 处错位 + 1 处信息丢失）

第 6 条严格说不是契约错位，而是前端丢弃了后端已返回的信息；因与第 5 条同在 ChatScreen 的 blocked 分支，一并修复。

| # | 现状 | 修法 |
|---|---|---|
| 1 | `prepareVisit` 送 `{hcpId, productId}`，后端读 `hcp_id`（`visits.py:65`）→ 100% ParamError | api 层映射成 `{hcp_id, product_id}`，调用处签名不变 |
| 2 | `POST /specialists/{id}/feedback` 不存在 → 404 | 改 `POST /api/v1/conversations/{conversation_id}/feedback`，body `{rating: 1\|-1, comment?}`，签名改为 `(conversationId, rating, comment?)` |
| 3 | `POST /specialists/{id}/favorite` 不存在 → 404 | 改 `POST /api/v1/conversations/{conversation_id}/favorite`，**无 body**（后端为 toggle 语义），返回 `{is_favorite}` |
| 4 | `GET /conversations/{sessionId}` → conversations 路由只有 POST → 404 | 改 `GET /api/v1/specialists/conversations/{session_id}` |
| 5 | `complianceAPI.checkContent` 调 `/compliance/check`，该路径在网关 `INTERNAL_PATHS`（`auth_middleware.py:42`）需 `X-Internal-Key` → 恒 403 | **删除**该方法及 ChatScreen 发送前预检块。服务端 `answer_generator.py:69` 已做问题预检并返回同样的 `violations` |
| 6 | ChatScreen blocked 时写死「该问题建议直接咨询医学顾问」，丢弃后端真实原因 | 改为渲染后端返回的 `answer` + `violations` |
| 7 | `visitAPI.list` 送 `start_date`/`end_date`，后端收 `date_from`/`date_to` → 日期筛选静默失效 | 改为 `date_from`/`date_to` |
| 8 | **后端缺环**：chat 只返 `session_id`/`request_id`，不返 `conversation_id`，而 feedback/favorite 主键正是 `conversation_id` | `specialists.py` 在 `db.commit()` 后注入 `result["conversation_id"] = conv_ai.id`（assistant 行）。入库在 try/except 内，失败时该字段为 `null` |

**为何取 assistant 行**：chat 一次写两条 Conversation（`conv` role=user、`conv_ai` role=assistant），只有 assistant 行带 `citations`/`compliance_result`/`latency_ms`。对答案点赞/收藏才有语义。`favorite` 端点内部按 `session_id` 反查同会话的问答两条做快照，传 assistant 行 id 与其实现一致。

**配套**：ChatScreen 的 `Message` 结构由存 `requestId` 改存 `conversationId`；`conversationId` 为 `null` 时禁用点赞/收藏按钮。

`src/api/compliance.ts` 保留（`listRules` 仍被 ComplianceScreen 使用）。

## 5. 第三节：测试与验收

### 5.1 jest 契约测试

新增 `mobile/__tests__/api-contract.test.ts`：mock `global.fetch`，对每个 api 方法断言实际发出的 **URL + method + body 形状**。

这一层测试针对性极强 —— 路径漂移与 camelCase/snake_case 错配正是编译器和类型系统抓不到、而本次审计发现了 8 处的那一类 bug。mobile 现有 jest 依赖但零配置零测试；`jest.config.js` 由模板带入，AsyncStorage 官方自带 jest mock。

### 5.2 后端测试

specialist-service 新增一条测试，断言 chat 返回体含 `conversation_id`。现有 11 项测试须保持全绿。

### 5.3 全链路实测

1. `docker-compose up -d` 起 8 服务（Postgres/Redis 已在跑）
2. `GET localhost:8000/health` 确认后端在线
3. 从 auth-service 日志捞 `rep_test`(13900000002) 的验证码（短信通道仍是 ConsoleSender，只写日志）
4. 启动 Pixel_7 模拟器，`npm run android`
5. 逐屏走查，**每条修过的契约都必须有一个对应的实测动作**：

   | 屏幕 | 验证的契约 |
   |---|---|
   | 登录 | `send-code` / `login`；重启 App 验证登录态保持（验 4.1 的 getToken 修复） |
   | 工作台 | `visits.list`（验 #7 date_from/date_to） |
   | 医生列表 / 详情 | `hcps.list` / `profile` / `interactions` |
   | 拜访准备 | `pre-visit`（验 #1 snake_case 修复） |
   | 专员列表 | `specialists.list` |
   | 对话 | `chat` 真实调用百炼一次（验 #8 返回 conversation_id） |
   | 点赞 / 收藏 | `conversations/{id}/feedback` / `favorite`（验 #2 #3 全链路） |
   | 合规规则 | `compliance/rules` |

6. 截图留证

**不能只靠单测推导**：jest 契约测试保证请求形状正确，实测保证后端真的接受该形状。两者缺一不可。

## 6. 第四节：删除清单

| 对象 | 理由 |
|---|---|
| 临时目录 `<TEMP>/MedAgentMobile` | init 产物，搬运完毕即删 |
| `visitAPI.update`（`src/api/visit.ts`） | 零调用方 + 类型错误 + 字段与后端白名单完全不重合 |
| `complianceAPI.checkContent`（`src/api/compliance.ts`） | 恒 403，且服务端已做同样的检查 |
| ChatScreen 发送前预检块 | 同上 |
| `web/src/pages/Doctors/`、`web/src/pages/Specialists/` | 空目录，与已有 `Doctor/`、`Specialist/` 重名残留 |

**保留**：`src/api/compliance.ts` 文件本身（`listRules` 在用）、`knowledge-base/` 空目录（方案要求的文献目录，非残留）。

## 7. 本轮明确不做

- 录音与 NLS 实时转写 —— 下一轮，且需先由用户在阿里云智能语音交互控制台开通项目取得 `NLS_APPKEY`（当前 `.env` 未配置，`asr_ws.py:50` 为 fail-closed 直接 RuntimeError）
- mobile WebSocket 客户端
- 网关 WebSocket 代理（gateway 当前只有 HTTP `api_route`，WS 请求走不通，下轮需加代理或让 App 直连 visit-service:8002）
- ContentScreen 接真实 knowledge API（当前为 `MOCK_CONTENT` 假数据，验收时明确标注「仍是假数据」）
- web 登录页与路由守卫
- VisitDetail / Profile / Settings / NotificationSettings / HelpCenter 五屏的后端对接
- 短信真实通道（ConsoleSender 仍只写日志）

## 8. 完成定义

1. `cd mobile && npx tsc --noEmit` 零错误（CI 的 frontend-check 转绿）
2. `cd mobile && npm test` 契约测试全过
3. 各服务 pytest 全绿（含 specialist 新增的 conversation_id 测试）
4. Pixel_7 模拟器上 App 真实启动，5.3 表格中每一项均实测通过并留有截图
5. 删除清单执行完毕
6. `mobile/android`、`mobile/ios`、`index.js` 等原生工程文件进入 git（构建产物按 `.gitignore` 既有规则排除）
