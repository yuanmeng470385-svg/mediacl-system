# 批次 1：前端接入批 实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** web 加登录页与路由守卫；mobile 五屏接真实后端数据；ContentScreen 删除 MOCK_CONTENT 改接 knowledge 服务。

**Architecture:** web 的 useAuth 升级为 AuthProvider Context（共享登录态供守卫/布局/登录页使用），登录走已有 `POST /api/v1/auth/login` 密码通道；mobile 各屏接已有网关端点（visits/knowledge），NotificationSettings 用 AsyncStorage 持久化（后端无端点，不新增）。契约测试锁定 api 层 URL/method/body 形状。

**Tech Stack:** React 18 + react-router-dom 6 + antd 5（web）；React Native 0.75 + jest（mobile）；网关 8000。

## Global Constraints

- 后端零改动（auth 密码登录、visits、knowledge 端点均已存在）。
- 不新增通知设置/FAQ 后端端点（YAGNI）。
- mobile 新增 api 方法必须同步补契约测试（`mobile/src/api/__tests__/api-contract.test.ts`，mock fetch + lastCall 模式）。
- 所有 commit 走仓库惯例：`fix(scope): 描述` / `feat(scope): 描述`，结尾加 `Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>`。
- web 无测试框架，验证 = `npm run build`（tsc -b && vite build）通过 + 手工冒烟；mobile 验证 = `npx jest` + `npx tsc --noEmit`（mobile/ 目录内）。
- 本批次 10 个提交为本地未 push（沿用仓库"bring-up 完成后统一 push"惯例）。

---

### Task 1: web — useAuth 升级为 AuthProvider（共享登录态）

**Files:**
- Create: `web/src/context/AuthContext.tsx`
- Modify: `web/src/App.tsx`（包 AuthProvider）
- Modify: `web/src/hooks/useAuth.ts`（改为从 context 读）
- Modify: `web/src/layouts/AdminLayout.tsx`（保留 useAuth 用法，不用改逻辑）

**Interfaces:**
- Produces: `AuthProvider`（组件）、`useAuth()` 返回 `{ user, loading, login(username, password), logout, isLoggedIn }`，语义与现有 hooks/useAuth.ts 完全一致（现有调用方 AdminLayout 无需改动）。

问题背景：现有 `useAuth` 是普通 hook，AdminLayout 每次挂载独立 state；登录页与守卫需要共享登录态，必须 Context 化。

- [ ] **Step 1: 写 AuthContext.tsx（把 hooks/useAuth.ts 逻辑搬进 Provider）**

```tsx
// web/src/context/AuthContext.tsx
import { createContext, useContext, useState, useEffect, useCallback, type ReactNode } from 'react';
import { authAPI } from '../services/auth';
import type { User } from '../types';

interface AuthState {
  user: User | null;
  loading: boolean;
  login: (username: string, password: string) => Promise<void>;
  logout: () => void;
  isLoggedIn: boolean;
}

const AuthContext = createContext<AuthState | null>(null);

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<User | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    const token = localStorage.getItem('medagent_token');
    if (token) {
      authAPI.me()
        .then((res) => setUser(res.data.data))
        .catch(() => { localStorage.removeItem('medagent_token'); })
        .finally(() => setLoading(false));
    } else {
      setLoading(false);
    }
  }, []);

  const login = useCallback(async (username: string, password: string) => {
    const res = await authAPI.login(username, password);
    const { token, user } = res.data.data;
    localStorage.setItem('medagent_token', token);
    setUser(user);
  }, []);

  const logout = useCallback(() => {
    localStorage.removeItem('medagent_token');
    setUser(null);
  }, []);

  return (
    <AuthContext.Provider value={{ user, loading, login, logout, isLoggedIn: !!user }}>
      {children}
    </AuthContext.Provider>
  );
}

export function useAuth(): AuthState {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error('useAuth must be used within AuthProvider');
  return ctx;
}
```

- [ ] **Step 2: hooks/useAuth.ts 改为 re-export（保持旧路径 import 可用）**

```ts
// web/src/hooks/useAuth.ts
export { useAuth } from '../context/AuthContext';
```

- [ ] **Step 3: App.tsx 用 AuthProvider 包裹 BrowserRouter**

`web/src/App.tsx`：把 `<BrowserRouter>` 包进 `<AuthProvider>`（AuthProvider 内用到 localStorage，浏览器环境安全；保持 ConfigProvider 在最外层）。

```tsx
<AntApp>
  <AuthProvider>
    <BrowserRouter>
      ...
    </BrowserRouter>
  </AuthProvider>
</AntApp>
```

- [ ] **Step 4: 验证构建**

Run: `cd web && npm run build`
Expected: PASS（tsc -b 无类型错误，vite build 产出 dist/）。

- [ ] **Step 5: Commit**

```bash
cd "/d/gongsi/medical system" && git add web/src && git commit -m "refactor(web): useAuth Context 化，共享登录态
Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

---

### Task 2: web — LoginPage（用户名+密码表单）

**Files:**
- Create: `web/src/pages/Login/index.tsx`

**Interfaces:**
- Consumes: `useAuth().login(username, password)`（Task 1）、`useAuth().isLoggedIn`、`useAuth().loading`
- Produces: `LoginPage` 默认导出组件；登录成功后由路由守卫重定向（Task 3），LoginPage 本身不做 navigate。

- [ ] **Step 1: 写 LoginPage 组件**

```tsx
// web/src/pages/Login/index.tsx
import { useState } from 'react';
import { Card, Form, Input, Button, Typography, Alert } from 'antd';
import { UserOutlined, LockOutlined } from '@ant-design/icons';
import { useAuth } from '../../hooks/useAuth';

const { Title, Text } = Typography;

export default function LoginPage() {
  const { login } = useAuth();
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState('');

  const onFinish = async (values: { username: string; password: string }) => {
    setSubmitting(true);
    setError('');
    try {
      await login(values.username, values.password);
      // 登录成功后路由守卫（Task 3）自动把已登录用户从 /login 重定向到 /dashboard
    } catch (e: any) {
      setError(e?.response?.data?.message || e?.response?.data?.detail?.message || '登录失败，请检查账号密码');
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <div style={{ minHeight: '100vh', display: 'flex', alignItems: 'center', justifyContent: 'center', background: '#f0f2f5' }}>
      <Card style={{ width: 380, boxShadow: '0 4px 12px rgba(0,0,0,0.08)' }}>
        <div style={{ textAlign: 'center', marginBottom: 24 }}>
          <Title level={3} style={{ marginBottom: 4 }}>MedAgent</Title>
          <Text type="secondary">药企 AI 数字员工系统 · 管理后台</Text>
        </div>
        {error && <Alert type="error" message={error} showIcon style={{ marginBottom: 16 }} />}
        <Form onFinish={onFinish} size="large">
          <Form.Item name="username" rules={[{ required: true, message: '请输入用户名' }]}>
            <Input prefix={<UserOutlined />} placeholder="用户名" autoComplete="username" />
          </Form.Item>
          <Form.Item name="password" rules={[{ required: true, message: '请输入密码' }]}>
            <Input.Password prefix={<LockOutlined />} placeholder="密码" autoComplete="current-password" />
          </Form.Item>
          <Form.Item style={{ marginBottom: 0 }}>
            <Button type="primary" htmlType="submit" block loading={submitting}>
              登录
            </Button>
          </Form.Item>
        </Form>
        <Text type="secondary" style={{ display: 'block', textAlign: 'center', marginTop: 16, fontSize: 12 }}>
          管理员账号需先执行 scripts/seed_admin.py 设置密码
        </Text>
      </Card>
    </div>
  );
}
```

- [ ] **Step 2: 验证构建**

Run: `cd web && npm run build`
Expected: PASS。

- [ ] **Step 3: Commit**

```bash
cd "/d/gongsi/medical system" && git add web/src/pages/Login && git commit -m "feat(web): 登录页（用户名+密码，接 auth 服务密码通道）
Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

---

### Task 3: web — 路由守卫 + /login 路由 + 401 跳登录

**Files:**
- Modify: `web/src/App.tsx`（加 /login 路由 + 守卫组件）
- Modify: `web/src/services/client.ts:17-29`（401 拦截器改为跳转登录）
- Create: `web/src/components/RequireAuth.tsx`

**Interfaces:**
- Consumes: `useAuth()` 的 `isLoggedIn`、`loading`（Task 1）
- Produces: `RequireAuth` 组件（未登录重定向 /login）；`/login` 路由（已登录重定向 /dashboard）。

- [ ] **Step 1: 写 RequireAuth 守卫组件**

```tsx
// web/src/components/RequireAuth.tsx
import { Navigate } from 'react-router-dom';
import { Spin } from 'antd';
import { useAuth } from '../hooks/useAuth';
import type { ReactNode } from 'react';

export default function RequireAuth({ children }: { children: ReactNode }) {
  const { isLoggedIn, loading } = useAuth();
  if (loading) {
    return (
      <div style={{ display: 'flex', justifyContent: 'center', alignItems: 'center', height: '100vh' }}>
        <Spin size="large" />
      </div>
    );
  }
  if (!isLoggedIn) return <Navigate to="/login" replace />;
  return <>{children}</>;
}
```

- [ ] **Step 2: App.tsx 加路由**

在现有 `<Route element={<AdminLayout />}>` 之外加：

```tsx
<Route path="/login" element={<LoginPage />} />
<Route element={<RequireAuth><AdminLayout /></RequireAuth>}>
  {/* 现有 10 个子路由不动 */}
</Route>
```

并 import `LoginPage`（非 lazy 或 lazy 均可）与 `RequireAuth`。`/login` 的已登录重定向由 Task 3 Step 3 的 LoginGate 处理。

- [ ] **Step 3: LoginPage 内加已登录重定向**

`web/src/pages/Login/index.tsx`：在组件顶部加：

```tsx
const { login, isLoggedIn, loading } = useAuth();
if (loading) return null;              // 等启动 me() 完成，避免误重定向
if (isLoggedIn) return <Navigate to="/dashboard" replace />;
```

import 加 `Navigate`。

- [ ] **Step 4: client.ts 401 拦截器改为跳登录**

`web/src/services/client.ts` 的 401 分支改为：

```ts
if (status === 401) {
  localStorage.removeItem('medagent_token');
  if (!window.location.pathname.startsWith('/login')) {
    window.location.href = '/login';
  }
}
```

（保留 `>= 500` 分支不动。）

- [ ] **Step 5: 验证构建**

Run: `cd web && npm run build`
Expected: PASS。

- [ ] **Step 6: 手工冒烟（可选，需后端起来）**

1. `cd services/auth-service && python -m uvicorn app.main:app --port 8007`、`cd services/gateway && python -m uvicorn app.main:app --port 8000`
2. `cd web && npm run dev` → 打开 http://localhost:3000 → 应跳 /login（守卫生效）
3. 未登录状态下访问 /dashboard 应重定向 /login
4. 用 seed_admin 设过密码的 admin 账号登录 → 进 /dashboard；header 显示用户名
5. 退出登录（header 下拉）→ 回 /login

- [ ] **Step 7: Commit**

```bash
cd "/d/gongsi/medical system" && git add web/src && git commit -m "feat(web): /login 路由 + 守卫 + 401 跳登录
Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

---

### Task 4: mobile — VisitDetail 接真实拜访详情接口

**Files:**
- Modify: `mobile/src/api/__tests__/api-contract.test.ts`（补 getById 契约用例）
- Modify: `mobile/src/screens/VisitDetail/VisitDetailScreen.tsx`（删假数据 + 假 loading，接 visitAPI.getById）

**Interfaces:**
- Consumes: `visitAPI.getById(visitId)`（已存在，`GET /api/v1/visits/{visit_id}`，返回 `VisitRecord`：`hcp_name/planned_date/status/ai_summary(VisitSummary: summary/key_points/interests/objections/sentiment/next_visit_recommendation)`）
- 无新接口产出。

- [ ] **Step 1: 补契约测试（确认 getById 路径）**

在 `mobile/src/api/__tests__/api-contract.test.ts` 的 `describe('visitAPI')` 内追加：

```ts
it('getById 发 GET /api/v1/visits/{id}（详情页数据源）', async () => {
  await visitAPI.getById(123);
  const c = lastCall();
  expect(c.url).toContain('/api/v1/visits/123');
  expect(c.method).toBe('GET');
});
```

Run: `cd mobile && npx jest api-contract`
Expected: FAIL with "cannot read properties of undefined (reading 'url')" 或 PASS（getById 已存在，用例只做契约锁定——若 PASS 则继续，测试意义在于防回归）。

- [ ] **Step 2: 重写 VisitDetailScreen 数据层**

`mobile/src/screens/VisitDetail/VisitDetailScreen.tsx`：
- 删 `useEffect` 里的 `setTimeout(..., 800)` 假 loading（:20-23），改为：

```tsx
const [record, setRecord] = useState<VisitRecord | null>(null);
const [loading, setLoading] = useState(true);
const [error, setError] = useState('');

useEffect(() => {
  let cancelled = false;
  (async () => {
    try {
      const r = await visitAPI.getById(visitId);
      if (!cancelled) setRecord(r);
    } catch (e: any) {
      if (!cancelled) setError(e.message || '加载失败');
    } finally {
      if (!cancelled) setLoading(false);
    }
  })();
  return () => { cancelled = true; };
}, [visitId]);
```

- import 加 `visitAPI`（`../../api/visit`）与 `VisitRecord` 类型。
- 新增错误态渲染（loading 之后）：

```tsx
if (error) {
  return (
    <View style={styles.centered}>
      <Text style={styles.errorText}>{error}</Text>
      <TouchableOpacity style={styles.retryBtn} onPress={() => { setLoading(true); setError(''); /* 重新触发 effect：visitId 不变，改为用 reload 计数 */ }}>
        <Text style={styles.retryText}>重试</Text>
      </TouchableOpacity>
    </View>
  );
}
```

重试实现：加 `const [reloadKey, setReloadKey] = useState(0);`，effect 依赖 `[visitId, reloadKey]`，重试按钮 `setReloadKey(k => k + 1)`。

- [ ] **Step 3: 硬编码数据替换为 record 字段**

- 基本信息卡片（:47-62）：
  - 医生 → `record?.hcp_name || '未知医生'`
  - 日期 → `record?.planned_date || '--'`
  - 时长：`actual_start_time` 与 `actual_end_time` 都存在时计算分钟数，否则显示 `record?.actual_start_time ? '进行中/已结束' : '--'`；实现 `formatDuration(start, end)` 本地函数，两时间都缺显示 `'--'`
  - 地点：`record?.ai_summary` 无地点字段——改用 `record?.status === 'completed' ? '拜访已完成' : record?.status`（展示状态，不造假地点）
- AI 总结卡片（:66-73）：`record?.ai_summary?.summary`，为空显示 `暂无 AI 总结`
- 关键发现卡片（:76-88）：`record?.ai_summary?.key_points?.map(...)`，为空不渲染该卡片（`{record?.ai_summary?.key_points && record.ai_summary.key_points.length > 0 && (...)}`）
- 追加"兴趣点/异议/下一步"可选卡片：interests/objections 非空时用同款 bulletRow 渲染；`next_visit_recommendation` 非空时显示在总结卡片下方。

- [ ] **Step 4: 契约测试跑绿 + 类型检查**

Run: `cd mobile && npx jest api-contract && npx tsc --noEmit`
Expected: PASS（tsc 无错误）。

- [ ] **Step 5: Commit**

```bash
cd "/d/gongsi/medical system" && git add mobile/src && git commit -m "fix(mobile): VisitDetail 接真实拜访详情接口，删假 loading 与硬编码
Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

---

### Task 5: mobile — Profile 统计数字接真实拜访数

**Files:**
- Modify: `mobile/src/screens/Profile/ProfileScreen.tsx`（统计区）

**Interfaces:**
- Consumes: `visitAPI.list({ page: 1, page_size: 1 })` → `PaginatedResponse<VisitRecord>`，`total` 为总拜访数。
- 无新接口。

- [ ] **Step 1: 统计区接 list total**

`ProfileScreen.tsx`：加状态与 effect：

```tsx
const [visitCount, setVisitCount] = useState<string>('--');

useEffect(() => {
  let cancelled = false;
  visitAPI.list({ page: 1, page_size: 1 })
    .then((res) => { if (!cancelled) setVisitCount(String(res.total)); })
    .catch(() => { /* 保持 '--' */ });
  return () => { cancelled = true; };
}, []);
```

统计数组（:68-72）改为：

```tsx
{[
  { num: '--', label: '本月对话' },
  { num: visitCount, label: '拜访总数' },
  { num: '--', label: '收藏' },
].map(...)}
```

（标签"本月拜访"→"拜访总数"，与 `list` 无月份筛选的语义一致；本月对话/收藏无现成接口，保持 `'--'`——YAGNI。）

- [ ] **Step 2: 类型检查**

Run: `cd mobile && npx tsc --noEmit`
Expected: PASS。

- [ ] **Step 3: Commit**

```bash
cd "/d/gongsi/medical system" && git add mobile/src/screens/Profile && git commit -m "feat(mobile): Profile 拜访总数接真实接口
Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

---

### Task 6: mobile — Settings 显示账号信息 + 真实版本号

**Files:**
- Modify: `mobile/src/screens/Settings/SettingsScreen.tsx`

**Interfaces:**
- Consumes: `useAuth().user`（name/department/region/role）、`useAuth().logout`（AuthContext 已有）
- 无新接口。

- [ ] **Step 1: 顶部账号卡片 + 退出登录**

`SettingsScreen.tsx`：
- import `useAuth`、`Alert`（react-native）
- 在 `ScrollView` 顶部（sections 渲染之前）加账号卡片：

```tsx
const { user, logout } = useAuth();
...
<View style={[styles.card, Shadow.card, { marginBottom: Spacing.md, padding: Spacing.lg }]}>
  <Text style={styles.label}>{user?.name || '未登录'}</Text>
  <Text style={styles.desc}>{(user?.department || '—') + ' · ' + (user?.region || '—') + ' · ' + (user?.role || '—')}</Text>
</View>
<TouchableOpacity style={[styles.card, Shadow.card, { marginBottom: Spacing.lg, alignItems: 'center', padding: Spacing.lg }]} onPress={() => Alert.alert('退出登录', '确定要退出当前账号吗？', [{ text: '取消', style: 'cancel' }, { text: '退出', style: 'destructive', onPress: logout }])}>
  <Text style={{ color: Colors.danger, fontSize: FontSize.md }}>退出登录</Text>
</TouchableOpacity>
```

- [ ] **Step 2: 版本号读 package.json**

- `sections` 的"关于 MedAgent"desc 由 `'v1.0.0'` 改为 `'v' + APP_VERSION`，模块级加：

```ts
const APP_VERSION: string = require('../../package.json').version;
```

（metro 支持 require JSON；@types 若报错，在文件顶部加 `// @ts-ignore` 单行注释于 require 行上方。）

- [ ] **Step 3: 类型检查**

Run: `cd mobile && npx tsc --noEmit`
Expected: PASS。

- [ ] **Step 4: Commit**

```bash
cd "/d/gongsi/medical system" && git add mobile/src/screens/Settings && git commit -m "feat(mobile): Settings 显示账号信息与退出登录，版本号读真实值
Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

---

### Task 7: mobile — NotificationSettings 开关持久化 AsyncStorage

**Files:**
- Modify: `mobile/src/screens/NotificationSettings/NotificationSettingsScreen.tsx`

**Interfaces:**
- Consumes: `@react-native-async-storage/async-storage`（已依赖）
- Produces: 存储键 `notification_settings`（JSON 对象 `Record<string, boolean>`）。

- [ ] **Step 1: 加载 + 保存改造**

`NotificationSettingsScreen.tsx`：

```tsx
import AsyncStorage from '@react-native-async-storage/async-storage';

const STORAGE_KEY = 'notification_settings';
const DEFAULT_TOGGLES = { visit_reminder: true, compliance_alert: true, chat_update: false, system: true };

export default function NotificationSettingsScreen() {
  const [toggles, setToggles] = useState<Record<string, boolean>>(DEFAULT_TOGGLES);

  useEffect(() => {
    let cancelled = false;
    AsyncStorage.getItem(STORAGE_KEY)
      .then((raw) => {
        if (!raw || cancelled) return;
        const saved = JSON.parse(raw);
        if (saved && typeof saved === 'object') {
          setToggles((prev) => ({ ...DEFAULT_TOGGLES, ...saved }));
        }
      })
      .catch(() => { /* 读失败用默认值 */ });
    return () => { cancelled = true; };
  }, []);

  const toggle = (key: string, value: boolean) => {
    setToggles((prev) => {
      const next = { ...prev, [key]: value };
      AsyncStorage.setItem(STORAGE_KEY, JSON.stringify(next)).catch(() => {});
      return next;
    });
  };
```

`Switch onValueChange` 改为 `(v) => toggle(item.key, v)`。导入 `useEffect`。

- [ ] **Step 2: 类型检查**

Run: `cd mobile && npx tsc --noEmit`
Expected: PASS。

- [ ] **Step 3: Commit**

```bash
cd "/d/gongsi/medical system" && git add mobile/src/screens/NotificationSettings && git commit -m "feat(mobile): 通知设置持久化到 AsyncStorage
Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

---

### Task 8: mobile — content.ts API 模块 + 契约测试

**Files:**
- Create: `mobile/src/api/content.ts`
- Modify: `mobile/src/api/__tests__/api-contract.test.ts`（加 contentAPI 用例）
- Modify: `mobile/src/types/index.ts`（ContentItem 字段容错化）

**Interfaces:**
- Produces:
  - `contentAPI.getDocuments(params: { page?: number; page_size?: number; doc_type?: string }): Promise<PaginatedResponse<ContentItem>>` → `GET /api/v1/knowledge/documents`
  - `contentAPI.getDocument(id: number): Promise<ContentDetail>` → `GET /api/v1/knowledge/documents/{id}`
  - 类型 `ContentDetail = ContentItem & { content?: string }`（正文，后端缺时容错）

- [ ] **Step 1: 写 content.ts**

```ts
/**
 * 学术内容 API（知识库）
 */
import { apiClient } from './client';
import type { PaginatedResponse, ContentItem } from '../types';

export interface ContentDetail extends ContentItem {
  content?: string;
}

export const contentAPI = {
  /** 文档列表（分页 + 类型筛选） */
  async getDocuments(params?: {
    page?: number;
    page_size?: number;
    doc_type?: string;
  }): Promise<PaginatedResponse<ContentItem>> {
    return apiClient.request<PaginatedResponse<ContentItem>>(
      'GET',
      '/api/v1/knowledge/documents',
      params
    );
  },

  /** 文档详情（含正文） */
  async getDocument(id: number): Promise<ContentDetail> {
    return apiClient.request<ContentDetail>(
      'GET',
      `/api/v1/knowledge/documents/${id}`
    );
  },
};
```

- [ ] **Step 2: ContentItem 容错化**

`mobile/src/types/index.ts` ContentItem（:204-214）改为可选字段（后端 knowledge 文档字段与前端不完全一致，缺字段前端容错）：

```ts
export interface ContentItem {
  id: number;
  title: string;
  type: 'literature' | 'guideline' | 'manual' | 'news';
  summary?: string;
  source?: string;
  publish_date?: string;
  evidence_level?: string;
  file_url?: string;
  tags?: string[];
}
```

（summary/source/publish_date/evidence_level/tags 全部可选；渲染处用 `item.summary ?? ''` 等容错。）

- [ ] **Step 3: 契约测试**

`mobile/src/api/__tests__/api-contract.test.ts` 追加：

```ts
import { contentAPI } from '../content';

describe('contentAPI', () => {
  it('getDocuments 发 GET /api/v1/knowledge/documents 且透传 doc_type', async () => {
    await contentAPI.getDocuments({ page: 1, page_size: 50, doc_type: 'guideline' });
    const c = lastCall();
    expect(c.url).toContain('/api/v1/knowledge/documents');
    expect(c.url).toContain('doc_type=guideline');
    expect(c.method).toBe('GET');
  });

  it('getDocument 发 GET /api/v1/knowledge/documents/{id}', async () => {
    await contentAPI.getDocument(7);
    const c = lastCall();
    expect(c.url).toContain('/api/v1/knowledge/documents/7');
    expect(c.method).toBe('GET');
  });
});
```

- [ ] **Step 4: 跑测试 + 类型检查**

Run: `cd mobile && npx jest api-contract && npx tsc --noEmit`
Expected: PASS（新用例断言 URL/参数）。

- [ ] **Step 5: Commit**

```bash
cd "/d/gongsi/medical system" && git add mobile/src && git commit -m "feat(mobile): content API 模块 + 契约测试
Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

---

### Task 9: mobile — ContentScreen 接 API（删 MOCK_CONTENT + 详情页导航）

**Files:**
- Modify: `mobile/src/screens/Content/ContentScreen.tsx`（删 MOCK_CONTENT，数据源改 contentAPI）
- Create: `mobile/src/screens/Content/ContentDetailScreen.tsx`
- Modify: `mobile/src/navigation/AppNavigator.tsx:160-164`（ContentDetail 路由改指向新详情页）
- Modify: `mobile/src/navigation/types.ts`（ContentDetail 参数已是 `{ contentId: number }`，无需改）

**Interfaces:**
- Consumes: `contentAPI.getDocuments` / `contentAPI.getDocument`（Task 8）
- Produces: `ContentDetailScreen`（参数 `{ contentId: number }`，标题栏"文档详情"）。

- [ ] **Step 1: ContentScreen 数据源改造**

- 删 `MOCK_CONTENT`（:19-50）
- 状态加 `items/loading/error`，加载 effect：

```tsx
const [items, setItems] = useState<ContentItem[]>([]);
const [loading, setLoading] = useState(true);
const [error, setError] = useState('');
const [refreshing, setRefreshing] = useState(false);

const load = useCallback(async () => {
  try {
    const res = await contentAPI.getDocuments({ page: 1, page_size: 50 });
    setItems(res.items);
    setError('');
  } catch (e: any) {
    setError(e.message || '加载失败');
  } finally {
    setLoading(false);
    setRefreshing(false);
  }
}, []);

useEffect(() => { load(); }, [load]);
```

- `filteredContent` 改为基于 `items` 过滤（逻辑不变，:65-73 的 `MOCK_CONTENT` → `items`）；搜索字段 `item.tags.some(...)` 需容错：`(item.tags ?? []).some(...)`，`item.title.includes` → `(item.title || '').includes`
- FlatList 加 `refreshControl={<RefreshControl refreshing={refreshing} onRefresh={() => { setRefreshing(true); load(); }} />}`（import RefreshControl）
- ListEmptyComponent 保持 EmptyState（文案已有）；`loading` 时显示 ActivityIndicator 居中（复用 styles.centered 样式，参照 VisitDetail 的错误态结构新增）
- 卡片 `TouchableOpacity`（:79）加 `onPress={() => navigation.navigate('ContentDetail', { contentId: item.id })}`；import `useNavigation` + `NativeStackNavigationProp`（参照 ProfileScreen 的写法）
- 渲染处容错：`item.summary` → `item.summary ?? ''`、`item.source` → `item.source ?? ''`、`item.publish_date` → `item.publish_date ?? ''`、`item.evidence_level` → `item.evidence_level ?? ''`（`{item.evidence_level}级证据` 改为 `{item.evidence_level ? item.evidence_level + '级证据' : ''}` 或整个标签条件渲染）、`item.tags.map` → `(item.tags ?? []).map`

- [ ] **Step 2: 写 ContentDetailScreen**

```tsx
/**
 * 学术内容详情页 - 文档正文
 */
import React, { useEffect, useState } from 'react';
import { View, Text, ScrollView, StyleSheet, TouchableOpacity, ActivityIndicator } from 'react-native';
import { useRoute, useNavigation } from '@react-navigation/native';
import type { RouteProp } from '@react-navigation/native';
import Icon from '../../components/Icon';
import { contentAPI, type ContentDetail } from '../../api/content';
import { Colors, FontSize, Spacing, BorderRadius, Shadow } from '../../constants/theme';
import type { RootStackParamList } from '../../navigation/types';

type RouteType = RouteProp<RootStackParamList, 'ContentDetail'>;

export default function ContentDetailScreen() {
  const route = useRoute<RouteType>();
  const navigation = useNavigation();
  const { contentId } = route.params;
  const [doc, setDoc] = useState<ContentDetail | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');

  useEffect(() => {
    let cancelled = false;
    contentAPI.getDocument(contentId)
      .then((d) => { if (!cancelled) setDoc(d); })
      .catch((e: any) => { if (!cancelled) setError(e.message || '加载失败'); })
      .finally(() => { if (!cancelled) setLoading(false); });
    return () => { cancelled = true; };
  }, [contentId]);

  if (loading) {
    return (
      <View style={styles.centered}>
        <ActivityIndicator size="large" color={Colors.primary} />
      </View>
    );
  }
  if (error || !doc) {
    return (
      <View style={styles.centered}>
        <Text style={{ color: Colors.textSecondary }}>{error || '文档不存在'}</Text>
      </View>
    );
  }

  return (
    <View style={styles.container}>
      <View style={styles.header}>
        <TouchableOpacity onPress={() => navigation.goBack()}>
          <Icon name="chevron-left" size={22} color={Colors.textWhite} />
        </TouchableOpacity>
        <Text style={styles.headerTitle}>文档详情</Text>
        <View style={{ width: 24 }} />
      </View>
      <ScrollView contentContainerStyle={styles.content}>
        <Text style={styles.title}>{doc.title}</Text>
        <View style={styles.metaRow}>
          <Text style={styles.metaText}>{doc.source ?? ''} {doc.publish_date ? '· ' + doc.publish_date : ''}</Text>
        </View>
        <View style={[styles.card, Shadow.card]}>
          <Text style={styles.body}>{doc.content || '暂无正文内容'}</Text>
        </View>
        <View style={{ height: 40 }} />
      </ScrollView>
    </View>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1, backgroundColor: Colors.background },
  centered: { flex: 1, justifyContent: 'center', alignItems: 'center', backgroundColor: Colors.background },
  header: {
    backgroundColor: Colors.primary, paddingTop: 50, paddingBottom: 14,
    paddingHorizontal: Spacing.lg, flexDirection: 'row',
    alignItems: 'center', justifyContent: 'space-between', ...Shadow.header,
  },
  headerTitle: { color: Colors.textWhite, fontSize: FontSize.lg, fontWeight: '600' },
  content: { padding: Spacing.lg },
  title: { fontSize: FontSize.xl, fontWeight: '700', color: Colors.textPrimary, lineHeight: 30 },
  metaRow: { marginTop: Spacing.xs, marginBottom: Spacing.lg },
  metaText: { fontSize: FontSize.xs, color: Colors.textHint },
  card: { backgroundColor: Colors.white, borderRadius: BorderRadius.xl, padding: Spacing.lg },
  body: { fontSize: FontSize.md, color: Colors.textPrimary, lineHeight: 24 },
});
```

- [ ] **Step 3: AppNavigator 路由指向修正**

`mobile/src/navigation/AppNavigator.tsx:160-164`：`ContentDetail` 的 component 由 `ContentScreen` 改为新 `ContentDetailScreen`（import 相应改）。

- [ ] **Step 4: 类型检查**

Run: `cd mobile && npx tsc --noEmit`
Expected: PASS。

- [ ] **Step 5: 模拟器冒烟（可选）**

服务端起来 + `python scripts/seed_demo_docs.py` 灌 3 篇文档后：内容页显示列表（无假数据）、tab/搜索过滤生效、点卡片进详情页看到正文、空库时显示空态文案。

- [ ] **Step 6: Commit**

```bash
cd "/d/gongsi/medical system" && git add mobile/src && git commit -m "feat(mobile): ContentScreen 接知识库 API，新增文档详情页
Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

---

### Task 10: 批次 1 收尾 — 全量验证

- [ ] **Step 1: mobile 全量测试 + 类型**

Run: `cd mobile && npx jest && npx tsc --noEmit`
Expected: 全部 PASS。

- [ ] **Step 2: web 构建**

Run: `cd web && npm run build`
Expected: PASS。

- [ ] **Step 3: 后端 pytest 回归（确认前端改动未影响后端测试基线的判定，实为只读确认）**

Run: `cd "/d/gongsi/medical system" && for s in auth-service visit-service specialist-service knowledge-service gateway; do (cd services/$s && python -m pytest -q 2>&1 | tail -1); done`
Expected: 各服务 ok / N passed。

- [ ] **Step 4: 汇报**

汇总：web 登录链路（路由/守卫/401）、五屏改造逐项、ContentScreen 接 API 与详情页、测试与构建结果。
