# MedAgent 移动端 Bring-up 实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 让 `mobile/` 从「5540 行从未编译过的源码」变成「能在 Pixel_7 模拟器上真实登录并跑通主流程的 App」。

**Architecture:** 用官方 RN CLI 在临时目录生成 0.75.0 原生工程，搬运原生产物入 `mobile/`（三处改动：入口指向 `src/App.tsx`、app 名 MedAgent、vector-icons fonts.gradle）。契约修复除一处外全在前端 api 层完成，调用处签名尽量不变；唯一后端改动是 chat 补返 `conversation_id`。新增 jest 契约测试锁住「URL + method + body 形状」这一类编译器抓不到的 bug。

**Tech Stack:** React Native 0.75.0 / TypeScript 5.5 / React Navigation 6 / jest 29 / FastAPI / pytest

## Global Constraints

- RN 版本锁定 **0.75.0**；Android 包名与 iOS bundle ID 均为 **`com.medagent.mobile`**；App 显示名 **`MedAgent`**
- 新架构保持模板默认 **`newArchEnabled=false`**
- 后端测试**必须在各服务目录下运行**（`sys.path` 依赖 cwd），从仓库根跑必然 `ModuleNotFoundError`
- Commit 格式：conventional commits，末尾 `Co-Authored-By: Claude <noreply@anthropic.com>`；**本地提交，不 push**
- 前端请求体一律 **snake_case**，映射在 `src/api/*.ts` 内完成，不污染屏幕组件
- 统一响应 `{code, message, data}`；`apiClient.request` 已负责拆 `data` 与抛 `APIError`
- **不擅自改动全局 Node 版本**。若 metro 因 Node v25.9.0 报错，停下来询问用户
- 环境已就绪，勿重复安装：JDK 17、`ANDROID_HOME=D:\AndroidSDK`(android-34/35/36, build-tools 34/35, NDK 27, adb)、AVD `Pixel_7`、`gradle-8.8-all` 已解压、`react-android:0.75.0` 等 Gradle 依赖已缓存

---

## Task 1: 生成并搬运 RN 原生工程

**Files:**
- Create: `mobile/index.js`, `mobile/metro.config.js`, `mobile/babel.config.js`, `mobile/app.json`, `mobile/jest.config.js`, `mobile/.watchmanconfig`, `mobile/Gemfile`
- Create: `mobile/android/**`（整目录）
- Create: `mobile/ios/**`（整目录，覆盖现有 0 文件空目录）
- Modify: `mobile/android/app/build.gradle`（加 fonts.gradle）

**Interfaces:**
- Consumes: 现有 `mobile/src/App.tsx`（已有标准 default export，不改动）
- Produces: 可执行的 `npm start` / `npm run android`；后续所有任务依赖此工程能构建

- [ ] **Step 1: 生成模板到临时目录**

```bash
cd "$TEMP" && npx --yes @react-native-community/cli@14 init MedAgentMobile \
  --version 0.75.0 --directory "$TEMP/MedAgentMobile" \
  --package-name com.medagent.mobile \
  --pm npm --skip-install --skip-git-init
```

`--package-name` 同时设定 Android 包名与 iOS bundle ID，因此**不需要手改 Kotlin 包目录、`namespace`、`applicationId`、debug manifest**。

- [ ] **Step 2: 确认模板产物齐全**

```bash
ls "$TEMP/MedAgentMobile"
ls "$TEMP/MedAgentMobile/android/gradle/wrapper/"
grep -r "com.medagent.mobile" "$TEMP/MedAgentMobile/android/app/build.gradle"
```

Expected: 根目录含 `android ios index.js metro.config.js babel.config.js app.json jest.config.js`；wrapper 目录含 `gradle-wrapper.jar` 与 `gradle-wrapper.properties`；build.gradle 含 `com.medagent.mobile`。
若 `gradle-wrapper.jar` 缺失，**停止**并报告 —— 该二进制无法手写。

- [ ] **Step 3: 确认 wrapper 指向 gradle-8.8（本机已缓存）**

```bash
grep distributionUrl "$TEMP/MedAgentMobile/android/gradle/wrapper/gradle-wrapper.properties"
```

Expected: 含 `gradle-8.8-all.zip`。若为其他版本，构建会触发一次新下载（可接受，但需在报告中说明）。

- [ ] **Step 4: 搬运原生产物入 mobile/**

```bash
cd "D:/gongsi/medical system/mobile"
rmdir ios 2>/dev/null || true          # 现有 ios 是 0 文件空目录
cp -r "$TEMP/MedAgentMobile/android" ./android
cp -r "$TEMP/MedAgentMobile/ios" ./ios
cp "$TEMP/MedAgentMobile/index.js" \
   "$TEMP/MedAgentMobile/metro.config.js" \
   "$TEMP/MedAgentMobile/babel.config.js" \
   "$TEMP/MedAgentMobile/app.json" \
   "$TEMP/MedAgentMobile/jest.config.js" \
   "$TEMP/MedAgentMobile/.watchmanconfig" \
   "$TEMP/MedAgentMobile/Gemfile" ./
```

**不复制**：模板根 `App.tsx`、`__tests__/App.test.tsx`、模板 `package.json`、`tsconfig.json`、`.eslintrc.js`、`.prettierrc.js`、`README.md`、`.gitignore` —— 我们已有自己的版本。

- [ ] **Step 5: 改 index.js 入口指向 src/App**

`mobile/index.js` 全文替换为：

```javascript
/**
 * MedAgent 移动端入口
 * 注意：App 组件在 src/App.tsx（非模板默认的根 App.tsx）
 */
import {AppRegistry} from 'react-native';
import App from './src/App';
import {name as appName} from './app.json';

AppRegistry.registerComponent(appName, () => App);
```

- [ ] **Step 6: 改 app.json 应用名**

`mobile/app.json` 全文替换为：

```json
{
  "name": "MedAgent",
  "displayName": "MedAgent"
}
```

`index.js` 依赖 `app.json` 的 `name` 注册组件，两者必须一致。

- [ ] **Step 7: 加 vector-icons 字体打包**

在 `mobile/android/app/build.gradle` 末尾追加（不加则全 App 图标显示为方框）：

```gradle
apply from: file("../../node_modules/react-native-vector-icons/fonts.gradle")
```

- [ ] **Step 8: 验证 metro 能启动**

```bash
cd "D:/gongsi/medical system/mobile" && npx react-native start --reset-cache
```

Expected: 打印 "Welcome to Metro" 与 dev server 地址，无栈错误。确认后 Ctrl-C 停止。

**若此步因 Node v25.9.0 报错**（如 `ERR_UNSUPPORTED_*`、metro 内部 API 不兼容）：先尝试 `npx react-native start --reset-cache` 清缓存重试；仍失败则**停止执行，向用户报告**，建议用 nvm 切换到 Node 20，不擅自改动全局环境。

- [ ] **Step 9: 验证 Android 构建**

```bash
cd "D:/gongsi/medical system/mobile/android" && ./gradlew assembleDebug
```

Expected: `BUILD SUCCESSFUL`。本机已缓存 gradle-8.8 与 `react-android:0.75.0`，预期无大量下载。

- [ ] **Step 10: 删除临时目录**

```bash
rm -rf "$TEMP/MedAgentMobile"
```

- [ ] **Step 11: 提交**

```bash
cd "D:/gongsi/medical system"
git add mobile/android mobile/ios mobile/index.js mobile/metro.config.js \
        mobile/babel.config.js mobile/app.json mobile/jest.config.js \
        mobile/.watchmanconfig mobile/Gemfile
git commit -m "$(cat <<'EOF'
feat(mobile): 生成 RN 0.75.0 原生工程（android/ios/metro/babel）

包名与 bundle ID 统一 com.medagent.mobile，入口指向 src/App.tsx，
补 vector-icons fonts.gradle 避免图标显示为方框。
.gitignore 既有规则已排除构建产物。

Co-Authored-By: Claude <noreply@anthropic.com>
EOF
)"
```

---

## Task 2: 修复 3 个 TypeScript 错误

**Files:**
- Modify: `mobile/src/api/auth.ts`（补 `getToken`）
- Modify: `mobile/src/api/visit.ts:88-98`（删 `update`）
- Modify: `mobile/package.json`（加 `@types/react-native-vector-icons`）

**Interfaces:**
- Produces: `authAPI.getToken(): Promise<string | null>` —— Task 3 的契约测试会覆盖它
- Produces: `visitAPI` 不再有 `update` 方法

- [ ] **Step 1: 确认三个错误当前存在**

```bash
cd "D:/gongsi/medical system/mobile" && npx tsc --noEmit
```

Expected: 恰好 3 个错误，分别在 `src/api/visit.ts(94,37)`、`src/components/Icon.tsx(8,36)`、`src/store/AuthContext.tsx(44,32)`。

- [ ] **Step 2: 给 authAPI 补 getToken**

在 `mobile/src/api/auth.ts` 的 `authAPI` 对象内，`logout` 之前插入：

```typescript
  /** 读取本地 token（AuthContext 校验登录态用） */
  async getToken(): Promise<string | null> {
    return apiClient.getToken();
  },
```

> 这不只是类型修复：`AuthContext.checkAuth()` 调用不存在的方法会抛异常 → 被 catch 吞掉 → 走 `logout()` 清 token，导致**每次重开 App 都静默登出**。

- [ ] **Step 3: 删除死代码 visitAPI.update**

从 `mobile/src/api/visit.ts` 中整段删除：

```typescript
  /** 编辑拜访记录 */
  async update(
    visitId: number,
    data: Partial<Pick<VisitRecord, 'status' | 'notes'>>
  ): Promise<void> {
    return apiClient.request(
      'PUT',
      `/api/v1/visits/${visitId}`,
      data
    );
  },
```

理由：零调用方（已 grep 确认）；`VisitRecord` 无 `notes` 字段；声明的 `status`/`notes` 与后端白名单 `{hcp_id, product_id, specialist_id, visit_time, duration_minutes, attachments}`（`visits.py:46`）完全不重合，系凭想象所写。下轮真需编辑功能时照后端白名单重写。

- [ ] **Step 4: 安装 vector-icons 类型**

```bash
cd "D:/gongsi/medical system/mobile" && npm install --save-dev @types/react-native-vector-icons
```

- [ ] **Step 5: 验证零错误**

```bash
cd "D:/gongsi/medical system/mobile" && npx tsc --noEmit
```

Expected: 无输出（退出码 0）。

- [ ] **Step 6: 提交**

```bash
cd "D:/gongsi/medical system"
git add mobile/src/api/auth.ts mobile/src/api/visit.ts mobile/package.json mobile/package-lock.json
git commit -m "$(cat <<'EOF'
fix(mobile): 修复 3 个 TS 错误，CI frontend-check 转绿

- authAPI 补 getToken：原先 AuthContext 调不存在的方法被 catch 吞掉后清 token，
  导致每次重开 App 静默登出
- 删除 visitAPI.update：零调用方，字段与后端白名单完全不重合
- 安装 @types/react-native-vector-icons

Co-Authored-By: Claude <noreply@anthropic.com>
EOF
)"
```

---

## Task 3: 修复 api 层契约（TDD）

**Files:**
- Create: `mobile/jest.setup.js`
- Create: `mobile/src/api/__tests__/api-contract.test.ts`
- Modify: `mobile/jest.config.js`（挂 setupFiles）
- Modify: `mobile/package.json`（加 `@types/jest`）
- Modify: `mobile/src/api/visit.ts`（prepareVisit 映射、list 日期参数名）
- Modify: `mobile/src/api/specialist.ts`（feedback / favorite / 会话历史路径）
- Modify: `mobile/src/api/compliance.ts`（删 checkContent）
- Modify: `mobile/src/types/index.ts`（ChatResponse 加 `conversation_id`、`violations`）

**Interfaces:**
- Consumes: `apiClient.request<T>(method, path, dataOrParams?)`（现有，不改）
- Produces（Task 4 的 ChatScreen 依赖这些精确签名）：
  - `specialistAPI.sendFeedback(conversationId: number, rating: 1 | -1, comment?: string): Promise<{feedback_id: number}>`
  - `specialistAPI.toggleFavorite(conversationId: number): Promise<{is_favorite: boolean}>`
  - `ChatResponse` 新增 `conversation_id?: number | null`、`violations?: {rule_code: string; description: string}[]`
  - `complianceAPI` 仅剩 `listRules`

- [ ] **Step 1: 装 @types/jest 并配置 AsyncStorage mock**

契约测试放在 `src/api/__tests__/` 下，会被 `tsconfig.json` 的 `include: ["src/**/*"]` 覆盖，因此 `describe`/`it`/`expect`/`jest.Mock` 这些全局需要类型声明。当前 `@types/jest` **既未声明也未安装**，不装则 `tsc --noEmit` 报 `Cannot find name 'describe'`。

```bash
cd "D:/gongsi/medical system/mobile" && npm install --save-dev @types/jest
```

（tsconfig 未显式设置 `types` 数组，装进 `node_modules/@types` 即被 TypeScript 自动纳入。）

`apiClient.request` 内部会 `await this.getToken()` → `AsyncStorage.getItem`。RN 的 jest preset **不会**自动 mock AsyncStorage，不配则测试直接失败于 `NativeModule: AsyncStorage is null`。

创建 `mobile/jest.setup.js`：

```javascript
/**
 * jest 环境准备。
 * AsyncStorage 是原生模块，jest 环境下必须用官方 mock 替换，
 * 否则 apiClient.getToken() 会抛 "NativeModule: AsyncStorage is null"。
 */
jest.mock('@react-native-async-storage/async-storage', () =>
  require('@react-native-async-storage/async-storage/jest/async-storage-mock'),
);
```

把 `mobile/jest.config.js`（Task 1 从模板搬入，内容为 `preset: 'react-native'`）替换为：

```javascript
module.exports = {
  preset: 'react-native',
  setupFiles: ['<rootDir>/jest.setup.js'],
};
```

- [ ] **Step 2: 写失败的契约测试**

创建 `mobile/src/api/__tests__/api-contract.test.ts`：

```typescript
/**
 * API 契约测试：锁定每个方法实际发出的 URL / method / body 形状。
 * 这一类 bug（路径漂移、camelCase 与 snake_case 错配）编译器抓不到，
 * 2026-08-05 审计一次性发现了 7 处。
 */
import { visitAPI } from '../visit';
import { specialistAPI } from '../specialist';
import { complianceAPI } from '../compliance';
import { hcpAPI } from '../hcp';

const okResponse = (data: any = {}) => ({
  json: async () => ({ code: 0, message: 'success', data }),
});

let fetchMock: jest.Mock;

beforeEach(() => {
  fetchMock = jest.fn().mockResolvedValue(okResponse());
  (global as any).fetch = fetchMock;
});

/** 取出最近一次 fetch 的 url / method / body(已解析) */
function lastCall() {
  const [url, init] = fetchMock.mock.calls[fetchMock.mock.calls.length - 1];
  return {
    url: url as string,
    method: init.method as string,
    body: init.body ? JSON.parse(init.body as string) : undefined,
  };
}

describe('visitAPI', () => {
  it('prepareVisit 必须发 snake_case（后端 visits.py:65 读 hcp_id）', async () => {
    await visitAPI.prepareVisit({ hcpId: 7, productId: 1 });
    const c = lastCall();
    expect(c.url).toContain('/api/v1/visits/pre-visit');
    expect(c.method).toBe('POST');
    expect(c.body).toEqual({ hcp_id: 7, product_id: 1 });
    expect(c.body).not.toHaveProperty('hcpId');
  });

  it('list 日期参数必须是 date_from / date_to', async () => {
    await visitAPI.list({ page: 1, date_from: '2026-08-05', date_to: '2026-08-05' });
    const c = lastCall();
    expect(c.url).toContain('date_from=2026-08-05');
    expect(c.url).toContain('date_to=2026-08-05');
    expect(c.url).not.toContain('start_date');
  });
});

describe('specialistAPI', () => {
  it('sendFeedback 挂 conversation_id，rating 是 1/-1', async () => {
    await specialistAPI.sendFeedback(42, 1, '很有用');
    const c = lastCall();
    expect(c.url).toContain('/api/v1/conversations/42/feedback');
    expect(c.method).toBe('POST');
    expect(c.body).toEqual({ rating: 1, comment: '很有用' });
  });

  it('sendFeedback 不传 comment 时不带该字段', async () => {
    await specialistAPI.sendFeedback(42, -1);
    expect(lastCall().body).toEqual({ rating: -1 });
  });

  it('toggleFavorite 是无 body 的 toggle', async () => {
    await specialistAPI.toggleFavorite(42);
    const c = lastCall();
    expect(c.url).toContain('/api/v1/conversations/42/favorite');
    expect(c.method).toBe('POST');
    expect(c.body).toBeUndefined();
  });

  it('会话历史走 specialists 前缀', async () => {
    await specialistAPI.getConversationHistory('sess-1');
    const c = lastCall();
    expect(c.url).toContain('/api/v1/specialists/conversations/sess-1');
    expect(c.method).toBe('GET');
  });

  it('chat 路径与 body 不变', async () => {
    await specialistAPI.sendMessage(1, { question: '你好' });
    const c = lastCall();
    expect(c.url).toContain('/api/v1/specialists/1/chat');
    expect(c.body).toEqual({ question: '你好' });
  });
});

describe('complianceAPI', () => {
  it('只保留 listRules（checkContent 已删：网关 INTERNAL_PATHS 恒 403）', async () => {
    await complianceAPI.listRules();
    expect(lastCall().url).toContain('/api/v1/compliance/rules');
    expect((complianceAPI as any).checkContent).toBeUndefined();
  });
});

describe('hcpAPI', () => {
  it('list 透传筛选参数', async () => {
    await hcpAPI.list({ page: 1, name: '张' });
    const c = lastCall();
    expect(c.url).toContain('/api/v1/hcps');
    expect(c.url).toContain('name=');
  });
});
```

- [ ] **Step 3: 运行测试确认失败**

```bash
cd "D:/gongsi/medical system/mobile" && npx jest src/api/__tests__/api-contract.test.ts
```

Expected: FAIL。`prepareVisit` 断言收到 `{hcpId, productId}`、`sendFeedback` 因签名不符报类型/调用错误、`checkContent` 仍存在。

- [ ] **Step 4: 修 visit.ts 的两处**

`prepareVisit` 方法体改为（**调用处签名保持 camelCase 不变**，映射在 api 层内完成）：

```typescript
  /** 拜访前准备——获取准备包（后端收 snake_case） */
  async prepareVisit(params: {
    hcpId: number;
    productId?: number;
  }): Promise<VisitPrepareData> {
    return apiClient.request<VisitPrepareData>(
      'POST',
      '/api/v1/visits/pre-visit',
      { hcp_id: params.hcpId, product_id: params.productId },
    );
  },
```

`list` 的参数类型中，`start_date`/`end_date` 改名为 `date_from`/`date_to`：

```typescript
  /** 拜访列表 */
  async list(params?: {
    page?: number;
    page_size?: number;
    status?: string;
    hcp_id?: number;
    date_from?: string;
    date_to?: string;
  }): Promise<PaginatedResponse<VisitRecord>> {
    return apiClient.request<PaginatedResponse<VisitRecord>>(
      'GET',
      '/api/v1/visits',
      params
    );
  },
```

- [ ] **Step 5: 修 specialist.ts 的三处**

`getConversationHistory` 路径加 `specialists` 前缀：

```typescript
  /** 获取会话历史（后端挂在 specialists 路由下） */
  async getConversationHistory(
    sessionId: string
  ): Promise<ConversationMessage[]> {
    return apiClient.request<ConversationMessage[]>(
      'GET',
      `/api/v1/specialists/conversations/${sessionId}`
    );
  },
```

`sendFeedback` 与 `toggleFavorite` 整体替换为：

```typescript
  /** 对话反馈（点赞/点踩）—— 挂 conversation_id，非 specialist_id */
  async sendFeedback(
    conversationId: number,
    rating: 1 | -1,
    comment?: string
  ): Promise<{ feedback_id: number }> {
    const body: { rating: 1 | -1; comment?: string } = { rating };
    if (comment) body.comment = comment;
    return apiClient.request(
      'POST',
      `/api/v1/conversations/${conversationId}/feedback`,
      body
    );
  },

  /** 收藏/取消收藏（后端是 toggle，无 body） */
  async toggleFavorite(
    conversationId: number
  ): Promise<{ is_favorite: boolean }> {
    return apiClient.request(
      'POST',
      `/api/v1/conversations/${conversationId}/favorite`
    );
  },
```

- [ ] **Step 6: 删 compliance.ts 的 checkContent**

`mobile/src/api/compliance.ts` 全文替换为：

```typescript
/**
 * 合规 API
 *
 * 注意：不提供 checkContent —— /api/v1/compliance/check 在网关 INTERNAL_PATHS
 * 中（auth_middleware.py:42），需 X-Internal-Key，客户端调用恒 403。
 * 问题合规预检由服务端 answer_generator.py 在 chat 流程内完成。
 */
import { apiClient } from './client';
import type { ComplianceRule } from '../types';

export const complianceAPI = {
  /** 合规规则列表 */
  async listRules(): Promise<ComplianceRule[]> {
    return apiClient.request<ComplianceRule[]>(
      'GET',
      '/api/v1/compliance/rules'
    );
  },
};
```

- [ ] **Step 7: 扩展 ChatResponse 类型**

`mobile/src/types/index.ts` 中 `ChatResponse` 替换为：

```typescript
export interface ChatResponse {
  answer: string;
  citations: Citation[];
  evidence_level: 'A' | 'B' | 'C' | 'D';
  session_id: string;
  request_id: string;
  latency_ms: number;
  blocked: boolean;
  /** 反馈/收藏的主键（assistant 行 id）。入库失败时为 null */
  conversation_id?: number | null;
  /** blocked 为 true 时的违规明细 */
  violations?: { rule_code: string; description: string }[];
}
```

- [ ] **Step 8: 运行测试确认通过**

```bash
cd "D:/gongsi/medical system/mobile" && npx jest src/api/__tests__/api-contract.test.ts
```

Expected: 全部 PASS。

- [ ] **Step 9: 类型检查**

```bash
cd "D:/gongsi/medical system/mobile" && npx tsc --noEmit
```

Expected: 报错仅剩 `src/screens/Chat/ChatScreen.tsx`（仍在用旧签名与已删的 `complianceAPI.checkContent`）—— Task 4 修复。若其他文件报错，说明有未发现的调用方，需一并处理。

- [ ] **Step 10: 提交**

```bash
cd "D:/gongsi/medical system"
git add mobile/src/api mobile/src/types/index.ts mobile/jest.config.js mobile/jest.setup.js \
        mobile/package.json mobile/package-lock.json
git commit -m "$(cat <<'EOF'
fix(mobile): 修复 api 层契约错位 + 新增契约测试

- prepareVisit 映射 snake_case（原先 100% ParamError）
- feedback/favorite 改挂 conversation_id（原先 404 被 catch 吞成假动作）
- 会话历史补 specialists 前缀
- list 日期参数改 date_from/date_to
- 删 complianceAPI.checkContent（网关 INTERNAL_PATHS 恒 403，服务端已做预检）

契约测试锁定 URL/method/body 形状，防这类编译器抓不到的漂移。

Co-Authored-By: Claude <noreply@anthropic.com>
EOF
)"
```

---

## Task 4: ChatScreen 接入新契约

**Files:**
- Modify: `mobile/src/screens/Chat/ChatScreen.tsx:24`（删 complianceAPI import）
- Modify: `mobile/src/screens/Chat/ChatScreen.tsx:30-38`（Message 类型）
- Modify: `mobile/src/screens/Chat/ChatScreen.tsx:57-121`（handleSend/handleFeedback/handleFavorite）
- Modify: `mobile/src/screens/Chat/ChatScreen.tsx:164`（按钮显示条件）

**Interfaces:**
- Consumes: Task 3 的 `specialistAPI.sendFeedback(conversationId, rating, comment?)`、`specialistAPI.toggleFavorite(conversationId)`、`ChatResponse.conversation_id`、`ChatResponse.violations`

- [ ] **Step 1: 删除 complianceAPI import**

删除 `mobile/src/screens/Chat/ChatScreen.tsx` 第 24 行：

```typescript
import { complianceAPI } from '../../api/compliance';
```

- [ ] **Step 2: Message 类型改存 conversationId**

第 30-38 行的 `interface Message` 替换为：

```typescript
interface Message {
  id: string;
  role: 'user' | 'assistant' | 'system';
  content: string;
  citations?: { title: string; url?: string }[];
  evidenceLevel?: string;
  blocked?: boolean;
  /** 反馈/收藏主键（assistant 行 id）。为空则禁用这两个动作 */
  conversationId?: number | null;
}
```

- [ ] **Step 3: 重写 handleSend（删预检 + 保留后端 blocked 原因）**

第 57-107 行的 `handleSend` 整体替换为：

```typescript
  const handleSend = useCallback(async () => {
    const text = input.trim();
    if (!text || loading) return;

    // 不做客户端合规预检：/compliance/check 需 X-Internal-Key（恒 403），
    // 且服务端 answer_generator 已在 chat 流程内完成问题预检。
    const userMsg: Message = { id: `u_${Date.now()}`, role: 'user', content: text };
    setMessages((prev) => [...prev, userMsg]);
    setInput('');
    setLoading(true);

    try {
      const response = await specialistAPI.sendMessage(specialistId, {
        question: text,
        session_id: sessionId || undefined,
      });

      if (!sessionId && response.session_id) setSessionId(response.session_id);

      // blocked 时展示后端给出的真实原因与违规明细，不再写死话术
      const violationText = (response.violations ?? [])
        .map((v) => v.description)
        .filter(Boolean)
        .join('；');
      const content = response.blocked
        ? [response.answer, violationText && `（${violationText}）`]
            .filter(Boolean)
            .join('')
        : response.answer;

      const aiMsg: Message = {
        id: response.request_id || `a_${Date.now()}`,
        role: 'assistant',
        content,
        citations: response.citations,
        evidenceLevel: response.evidence_level,
        blocked: response.blocked,
        conversationId: response.conversation_id ?? null,
      };
      setMessages((prev) => [...prev, aiMsg]);
    } catch (e: any) {
      setMessages((prev) => [...prev, {
        id: `err_${Date.now()}`, role: 'assistant',
        content: `抱歉，出错了：${e.message || '请稍后重试'}`,
      }]);
    } finally {
      setLoading(false);
    }
  }, [input, loading, specialistId, sessionId]);
```

- [ ] **Step 4: 重写 handleFeedback / handleFavorite**

第 109-121 行整体替换为：

```typescript
  const handleFeedback = (msg: Message, rating: 1 | -1) => {
    if (!msg.conversationId) return;
    specialistAPI.sendFeedback(msg.conversationId, rating)
      .then(() => Alert.alert('提示', rating === 1 ? '感谢反馈！' : '我们会持续改进'))
      .catch((e) => Alert.alert('提示', e.message || '操作失败'));
  };

  const handleFavorite = (msg: Message) => {
    if (!msg.conversationId) return;
    specialistAPI.toggleFavorite(msg.conversationId)
      .then((r) => Alert.alert('提示', r.is_favorite ? '已收藏' : '已取消收藏'))
      .catch((e) => Alert.alert('提示', e.message || '操作失败'));
  };
```

> 失败不再静默 `.catch(() => {})` —— 那正是这次 404 假动作藏了这么久的原因。

- [ ] **Step 5: 改按钮 onPress 与显示条件**

第 164 行的显示条件 `item.requestId` 改为 `item.conversationId`：

```typescript
        {!isUser && !item.blocked && item.conversationId && (
```

同块内两个 feedback 按钮的 onPress 改为传数字：

```typescript
            <TouchableOpacity style={styles.actionBtn} onPress={() => handleFeedback(item, 1)}>
```

```typescript
            <TouchableOpacity style={styles.actionBtn} onPress={() => handleFeedback(item, -1)}>
```

（`handleFavorite(item)` 那个按钮不变。）

- [ ] **Step 6: 类型检查 + 全量测试**

```bash
cd "D:/gongsi/medical system/mobile" && npx tsc --noEmit && npx jest
```

Expected: `tsc` 零错误；jest 全过。

- [ ] **Step 7: 提交**

```bash
cd "D:/gongsi/medical system"
git add mobile/src/screens/Chat/ChatScreen.tsx
git commit -m "$(cat <<'EOF'
fix(mobile): ChatScreen 接入 conversation_id 契约

- 删客户端合规预检（恒 403，服务端已做）
- blocked 时展示后端真实原因与 violations，不再写死"建议咨询医学顾问"
- 反馈/收藏改用 conversation_id，失败不再静默吞掉

Co-Authored-By: Claude <noreply@anthropic.com>
EOF
)"
```

---

## Task 5: 后端 chat 补返 conversation_id

**Files:**
- Modify: `services/specialist-service/app/api/specialists.py:97-123`
- Create: `services/specialist-service/tests/test_chat_conversation_id.py`

**Interfaces:**
- Produces: `_persist_conversation(db, user_id, specialist_id, question, result) -> int | None` —— 返回 assistant 行 id，入库失败返回 `None`
- Produces: chat 响应 `data` 中新增 `conversation_id` 字段（Task 4 已消费）

**为何取 assistant 行**：chat 一次写两条 Conversation（user + assistant），只有 assistant 行带 `citations`/`compliance_result`/`latency_ms`；对答案点赞/收藏才有语义。`favorite` 端点内部按 `session_id` 反查同会话问答两条做快照，传 assistant 行 id 与其实现一致。

- [ ] **Step 1: 写失败的测试**

创建 `services/specialist-service/tests/test_chat_conversation_id.py`：

```python
"""chat 必须返回 conversation_id（assistant 行 id），前端反馈/收藏依赖它。

沿用本服务既有风格：不起真实 DB，用假 session 验证落库逻辑与返回值。
"""
import pytest

from app.api.specialists import _persist_conversation


class FakeSession:
    """最小 Session 替身：add 时给对象补 id，模拟 commit 后主键回填"""

    def __init__(self, fail_on_commit=False):
        self.added = []
        self.fail_on_commit = fail_on_commit
        self.committed = False

    def add(self, obj):
        self.added.append(obj)

    def commit(self):
        if self.fail_on_commit:
            raise RuntimeError("db down")
        self.committed = True
        for i, obj in enumerate(self.added, start=1):
            obj.id = i

    def rollback(self):
        pass


RESULT = {
    "answer": "答案内容",
    "citations": [{"title": "文献A"}],
    "session_id": "sess-1",
    "latency_ms": 120,
    "blocked": False,
}


def test_persist_returns_assistant_row_id():
    db = FakeSession()
    conv_id = _persist_conversation(db, user_id=3, specialist_id=1,
                                    question="你好", result=RESULT)
    # 两条：user 行 id=1，assistant 行 id=2 —— 必须返回 assistant 行
    assert len(db.added) == 2
    assert db.added[0].role == "user"
    assert db.added[1].role == "assistant"
    assert conv_id == 2


def test_persist_assistant_row_carries_answer_and_citations():
    db = FakeSession()
    _persist_conversation(db, user_id=3, specialist_id=1,
                          question="你好", result=RESULT)
    ai_row = db.added[1]
    assert ai_row.content == "答案内容"
    assert ai_row.citations == [{"title": "文献A"}]
    assert ai_row.latency_ms == 120


def test_persist_returns_none_on_db_failure():
    """入库失败不能让整个 chat 挂掉 —— 返回 None，前端据此禁用反馈按钮"""
    db = FakeSession(fail_on_commit=True)
    conv_id = _persist_conversation(db, user_id=3, specialist_id=1,
                                    question="你好", result=RESULT)
    assert conv_id is None
```

- [ ] **Step 2: 运行确认失败**

```bash
cd "D:/gongsi/medical system/services/specialist-service" && python -m pytest tests/test_chat_conversation_id.py -v
```

Expected: FAIL —— `ImportError: cannot import name '_persist_conversation'`。

- [ ] **Step 3: 抽出 _persist_conversation 函数**

在 `services/specialist-service/app/api/specialists.py` 中，`chat_with_specialist` **之前**插入：

```python
def _persist_conversation(db, user_id: int, specialist_id: int,
                          question: str, result: dict):
    """落库问答两行，返回 assistant 行 id（反馈/收藏的主键）。

    入库失败不影响 chat 主流程 —— 返回 None，前端据此禁用反馈/收藏。
    """
    from app.models.conversation import Conversation
    try:
        conv = Conversation(
            user_id=user_id,
            specialist_id=specialist_id,
            session_id=result.get("session_id"),
            role="user",
            content=question,
        )
        db.add(conv)
        conv_ai = Conversation(
            user_id=user_id,
            specialist_id=specialist_id,
            session_id=result.get("session_id"),
            role="assistant",
            content=result.get("answer", ""),
            citations=result.get("citations"),
            compliance_result={"blocked": result.get("blocked")},
            latency_ms=result.get("latency_ms"),
        )
        db.add(conv_ai)
        db.commit()
        return conv_ai.id
    except Exception as e:
        logger.error(f"对话记录入库失败: {e}")
        db.rollback()
        return None
```

- [ ] **Step 4: 改 chat 端点调用它并注入返回值**

`specialists.py` 第 97-123 行（`# 对话记录入库` 到 `return success(result)`）替换为：

```python
    # 对话记录入库 —— conversation_id 是前端反馈/收藏的主键
    result["conversation_id"] = _persist_conversation(
        db, current_user["id"], specialist_id, question, result
    )

    return success(result)
```

同时更新该端点 docstring 的 Response 示例，在 `"blocked": false,` 之后加一行：

```python
            "conversation_id": 42,
```

- [ ] **Step 5: 运行新测试**

```bash
cd "D:/gongsi/medical system/services/specialist-service" && python -m pytest tests/test_chat_conversation_id.py -v
```

Expected: 3 passed。

- [ ] **Step 6: 全服务回归**

```bash
cd "D:/gongsi/medical system/services/specialist-service" && python -m pytest tests/ -q
```

Expected: 14 passed（原 11 + 新 3）。

- [ ] **Step 7: 提交**

```bash
cd "D:/gongsi/medical system"
git add services/specialist-service/app/api/specialists.py \
        services/specialist-service/tests/test_chat_conversation_id.py
git commit -m "$(cat <<'EOF'
feat(specialist): chat 返回 conversation_id 供反馈/收藏使用

抽出 _persist_conversation 返回 assistant 行 id。此前前端拿不到该主键，
feedback/favorite 无法调用（这是唯一必须改后端的契约缺环）。
入库失败返回 None，前端据此禁用按钮。

Co-Authored-By: Claude <noreply@anthropic.com>
EOF
)"
```

---

## Task 6: 清理残留 + 全链路实测验收

**Files:**
- Delete: `web/src/pages/Doctors/`, `web/src/pages/Specialists/`（空目录残留）

**Interfaces:**
- Consumes: Task 1-5 的全部产出

- [ ] **Step 1: 删除 web 空目录残留**

```bash
cd "D:/gongsi/medical system/web/src/pages"
ls -A Doctors Specialists   # 先确认确实为空
rmdir Doctors Specialists
```

与已有的 `Doctor/`、`Specialist/` 重名残留。若非空，**停止**并报告内容。

- [ ] **Step 2: 起后端并确认健康**

```bash
cd "D:/gongsi/medical system" && docker-compose up -d && sleep 20
curl -s http://localhost:8000/health
```

Expected: `{"status":"ok",...}` 且 backends 列出 7 个服务地址。

- [ ] **Step 3: 起模拟器并装 App**

```bash
"D:/AndroidSDK/emulator/emulator.exe" -avd Pixel_7 &
sleep 45 && "D:/AndroidSDK/platform-tools/adb.exe" devices
cd "D:/gongsi/medical system/mobile" && npx react-native run-android
```

Expected: `adb devices` 列出 emulator；App 安装并启动，登录页渲染出来（不是红屏）。

- [ ] **Step 4: 捞验证码登录**

```bash
docker-compose logs --tail=50 auth-service | grep -i "验证码\|code"
```

用 `rep_test` 的手机号 **13900000002**（role=rep，库中已存在）在 App 内登录。短信通道仍是 ConsoleSender，验证码只写日志。

- [ ] **Step 5: 逐屏验证（每条修过的契约都要有对应动作）**

| 屏幕 | 动作 | 验证的契约 |
|---|---|---|
| 登录 | 输手机号取码登录 | `send-code` / `login` |
| **杀掉 App 重开** | 应直接进工作台、不回登录页 | Task 2 的 `getToken` 修复 |
| 工作台 | 查看今日拜访列表 | `visits.list`（`date_from`/`date_to`） |
| 医生 Tab | 列表 → 点进详情 | `hcps.list` / `profile` / `interactions` |
| 医生详情 | 点「准备包」 | **`pre-visit`（snake_case 修复，此前 100% ParamError）** |
| 对话 Tab | 专员列表 → 进入对话 | `specialists.list` |
| 对话页 | 发一条真实问题 | `chat` 真调百炼，返回含 `conversation_id` |
| 对话页 | 点赞 + 收藏 | **`conversations/{id}/feedback` / `favorite` 全链路** |
| 我的 → 合规 | 打开合规规则页 | `compliance/rules` |

每屏截图留证。

- [ ] **Step 6: 数据库侧确认反馈/收藏真落库**

```bash
docker exec medagent-postgres psql -U medagent -d medagent \
  -c "SELECT id, conversation_id, user_id, rating FROM conversation_feedback ORDER BY id DESC LIMIT 3;" \
  -c "SELECT id, conversation_id, user_id FROM conversation_favorites ORDER BY id DESC LIMIT 3;"
```

Expected: 有刚才操作产生的新行。**这是「不再是假动作」的最终证据。**

- [ ] **Step 7: 全量回归**

```bash
cd "D:/gongsi/medical system/mobile" && npx tsc --noEmit && npx jest
cd "D:/gongsi/medical system/web" && npx tsc --noEmit
cd "D:/gongsi/medical system/services"
for s in auth-service specialist-service hcp-service visit-service compliance-service knowledge-service audit-service gateway; do
  (cd "$s" && echo "[$s] $(python -m pytest tests/ -q 2>&1 | tail -1)")
done
```

Expected: 前端零错误 + jest 全过；后端 111 项全过（原 108 + 新 3）。

- [ ] **Step 8: 提交**

```bash
cd "D:/gongsi/medical system"
git add -A
git commit -m "$(cat <<'EOF'
chore: 删除 web 空目录残留，移动端 bring-up 验收通过

Doctors/ 与 Specialists/ 是与 Doctor/ Specialist/ 重名的空目录残留。

Co-Authored-By: Claude <noreply@anthropic.com>
EOF
)"
```

- [ ] **Step 9: 如实报告**

报告须包含：
- 每屏实测结果与截图
- **明确标注仍是假数据的部分**：ContentScreen 用 `MOCK_CONTENT`；VisitDetail / Profile / Settings / NotificationSettings / HelpCenter 五屏零后端调用
- 拜访中页面仍无录音（"点击底部按钮模拟语音输入"），NLS 实时转写留下一轮
- 任何未通过的项必须列出，不得省略

---

## 本轮不做（范围边界）

录音与 NLS 实时转写（需用户先在阿里云智能语音交互控制台取得 `NLS_APPKEY`）、mobile WebSocket 客户端、网关 WebSocket 代理、ContentScreen 接真实 knowledge API、web 登录页与路由守卫、五个零后端调用屏幕的对接、短信真实通道。

## 完成定义

1. `cd mobile && npx tsc --noEmit` 零错误（CI frontend-check 转绿）
2. `cd mobile && npx jest` 契约测试全过
3. 各服务 pytest 全绿（111 项）
4. Pixel_7 上 App 真实启动，Task 6 Step 5 表格每项实测通过并留截图
5. `conversation_feedback` / `conversation_favorites` 表有实测产生的新行
6. 删除清单执行完毕（临时目录、`visitAPI.update`、`complianceAPI.checkContent`、web 两个空目录）
7. `mobile/android`、`mobile/ios`、`index.js` 等进入 git
