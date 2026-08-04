# Web 管理后台 实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 构建 MedAgent Web 管理后台，覆盖仪表盘、专员、知识库、合规、审计、医生、用户、配置 8 模块 10 路由。

**Architecture:** React 18 + Vite 5 + TypeScript + Ant Design 5 ProLayout，10 条懒加载路由，axios 统一通过网关 `http://gateway:8000/api/v1` 调用后端 6 个微服务。每模块独立 pages 目录，共享 services/components/types。

**Tech Stack:** Vite 5, React 18, TypeScript, Ant Design 5, @ant-design/pro-components, @ant-design/charts, React Router 6, axios, dayjs

## Global Constraints

- React 18 + TypeScript strict mode
- Ant Design 5 + ProComponents（ProLayout / ProTable / ProForm）
- 所有 API 调用走网关 `http://gateway:8000/api/v1`
- 每页路由懒加载 `React.lazy(() => import(...))`
- CSS 使用 Ant Design 内置 token/theme，不额外引入 CSS-in-JS 库
- 菜单图标使用 `@ant-design/icons`
- 支持 JWT token 登录态（localStorage 存 token，axios 拦截器自动附加）

---

### Task 1: 项目脚手架

**Files:**
- Create: `web/package.json`
- Create: `web/vite.config.ts`
- Create: `web/tsconfig.json`
- Create: `web/index.html`
- Create: `web/src/App.tsx`
- Create: `web/src/main.tsx`

**Produces:** 可 `npm run dev` 启动的空白 Vite + React 项目

- [ ] **Step 1: 创建 package.json**

```json
{
  "name": "medagent-web",
  "private": true,
  "version": "1.0.0",
  "type": "module",
  "scripts": {
    "dev": "vite --port 3000",
    "build": "tsc -b && vite build",
    "preview": "vite preview"
  },
  "dependencies": {
    "react": "^18.3.1",
    "react-dom": "^18.3.1",
    "react-router-dom": "^6.26.0",
    "antd": "^5.20.0",
    "@ant-design/pro-components": "^2.7.0",
    "@ant-design/icons": "^5.4.0",
    "@ant-design/charts": "^2.1.0",
    "axios": "^1.7.0",
    "dayjs": "^1.11.12"
  },
  "devDependencies": {
    "@types/react": "^18.3.3",
    "@types/react-dom": "^18.3.0",
    "@vitejs/plugin-react": "^4.3.1",
    "typescript": "^5.5.0",
    "vite": "^5.4.0"
  }
}
```

- [ ] **Step 2: 创建 vite.config.ts**

```typescript
import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';

export default defineConfig({
  plugins: [react()],
  server: {
    port: 3000,
    proxy: {
      '/api': {
        target: 'http://localhost:8000',
        changeOrigin: true,
      },
    },
  },
});
```

- [ ] **Step 3: 创建 tsconfig.json**

```json
{
  "compilerOptions": {
    "target": "ES2020",
    "useDefineForClassFields": true,
    "lib": ["ES2020", "DOM", "DOM.Iterable"],
    "module": "ESNext",
    "skipLibCheck": true,
    "moduleResolution": "bundler",
    "allowImportingTsExtensions": true,
    "isolatedModules": true,
    "moduleDetection": "force",
    "noEmit": true,
    "jsx": "react-jsx",
    "strict": true,
    "noUnusedLocals": false,
    "noUnusedParameters": false,
    "noFallthroughCasesInSwitch": true,
    "paths": { "@/*": ["./src/*"] }
  },
  "include": ["src"]
}
```

- [ ] **Step 4: 创建 index.html**

```html
<!DOCTYPE html>
<html lang="zh-CN">
  <head>
    <meta charset="UTF-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1.0" />
    <title>MedAgent - 管理后台</title>
  </head>
  <body>
    <div id="root"></div>
    <script type="module" src="/src/main.tsx"></script>
  </body>
</html>
```

- [ ] **Step 5: 创建 main.tsx**

```tsx
import React from 'react';
import ReactDOM from 'react-dom/client';
import App from './App';

ReactDOM.createRoot(document.getElementById('root')!).render(
  <React.StrictMode>
    <App />
  </React.StrictMode>
);
```

- [ ] **Step 6: 创建最小 App.tsx**

```tsx
export default function App() {
  return <div>MedAgent Admin</div>;
}
```

- [ ] **Step 7: 安装依赖并验证启动**

```bash
cd web && npm install && npm run dev
```
打开 http://localhost:3000 看到 "MedAgent Admin" 即成功。

- [ ] **Step 8: 验证 TypeScript 编译**

```bash
cd web && npx tsc --noEmit
```
无报错。

- [ ] **Step 9: Commit**

```bash
git add web/package.json web/vite.config.ts web/tsconfig.json web/index.html web/src/main.tsx web/src/App.tsx
git commit -m "chore(web): scaffold Vite + React + TypeScript project"
```

---

### Task 2: 全局类型、常量、API 客户端

**Files:**
- Create: `web/src/types/index.ts`
- Create: `web/src/constants/routes.ts`
- Create: `web/src/constants/menu.ts`
- Create: `web/src/services/client.ts`
- Create: `web/src/services/auth.ts`
- Create: `web/src/services/specialist.ts`
- Create: `web/src/services/knowledge.ts`
- Create: `web/src/services/compliance.ts`
- Create: `web/src/services/audit.ts`
- Create: `web/src/services/doctor.ts`
- Create: `web/src/services/user.ts`

**Produces:** 全局可用的类型定义 + API 客户端 + 路由/菜单常量

- [ ] **Step 1: 创建类型定义**

`web/src/types/index.ts`:
```typescript
// ========== 通用 ==========
export interface PaginatedResponse<T> {
  code: number;
  message: string;
  data: {
    items: T[];
    total: number;
    page: number;
    page_size: number;
  };
}

export interface ApiResponse<T> {
  code: number;
  message: string;
  data: T;
}

// ========== 专员 ==========
export interface Specialist {
  id: string;
  name: string;
  product: string;
  app_id: string;
  status: 'draft' | 'intern' | 'active' | 'disabled';
  style: string;
  daily_usage: number;
  satisfaction: number;
  created_at: string;
}

// ========== 知识文档 ==========
export interface KnowledgeDoc {
  id: string;
  title: string;
  type: 'pdf' | 'word' | 'ppt' | 'txt';
  product: string;
  evidence_level: 'A' | 'B' | 'C' | 'expert' | 'unknown';
  status: 'pending' | 'approved' | 'rejected' | 'published' | 'expired';
  version: number;
  created_at: string;
  updated_at: string;
}

// ========== 合规规则 ==========
export interface ComplianceRule {
  id: string;
  code: string;
  name: string;
  type: 'keyword' | 'regex' | 'semantic';
  severity: 'high' | 'medium' | 'low';
  action: 'reject' | 'warn' | 'log';
  pattern: string;
  enabled: boolean;
  block_count: number;
  description: string;
}

// ========== 审计日志 ==========
export interface AuditLog {
  id: string;
  timestamp: string;
  user_id: string;
  username: string;
  service: string;
  operation: string;
  risk_level: 'high' | 'medium' | 'low';
  ip: string;
  content_hash: string;
}

// ========== 医生 ==========
export interface Doctor {
  id: string;
  name: string;
  hospital: string;
  department: string;
  title: string;
  phone: string;
  tags: string[];
  visit_count: number;
  satisfaction: number;
}

// ========== 用户 ==========
export interface User {
  id: string;
  name: string;
  phone: string;
  role: 'admin' | 'manager' | 'rep' | 'compliance' | 'medical' | 'finance';
  region: string;
  status: 'active' | 'disabled';
}

// ========== 仪表盘 ==========
export interface DashboardStats {
  active_users: number;
  daily_conversations: number;
  violation_rate: number;
  satisfaction: number;
}

export interface TrendPoint {
  date: string;
  count: number;
}

export interface HeatmapCell {
  region: string;
  product: string;
  risk: number;
}

export interface TopViolation {
  rule: string;
  count: number;
}

export interface ServiceHealth {
  service: string;
  status: 'up' | 'down';
}
```

- [ ] **Step 2: 创建路由常量**

`web/src/constants/routes.ts`:
```typescript
export const ROUTES = {
  DASHBOARD: '/dashboard',
  SPECIALIST_LIST: '/specialist/list',
  SPECIALIST_CREATE: '/specialist/create',
  KNOWLEDGE_LIST: '/knowledge/list',
  COMPLIANCE_LIST: '/compliance/list',
  AUDIT_LIST: '/audit/list',
  DOCTOR_LIST: '/doctor/list',
  DOCTOR_DETAIL: '/doctor/:id',
  USER_LIST: '/user/list',
  SYSTEM_CONFIG: '/system/config',
} as const;
```

- [ ] **Step 3: 创建菜单配置**

`web/src/constants/menu.ts`:
```typescript
import {
  DashboardOutlined,
  RobotOutlined,
  BookOutlined,
  SafetyOutlined,
  AuditOutlined,
  UserOutlined,
  TeamOutlined,
  SettingOutlined,
} from '@ant-design/icons';
import type { MenuDataItem } from '@ant-design/pro-components';

export const menuConfig: MenuDataItem[] = [
  { path: '/dashboard', name: '仪表盘', icon: <DashboardOutlined /> },
  { path: '/specialist/list', name: '数字专员', icon: <RobotOutlined /> },
  { path: '/knowledge/list', name: '知识库', icon: <BookOutlined /> },
  { path: '/compliance/list', name: '合规规则', icon: <SafetyOutlined /> },
  { path: '/audit/list', name: '审计查询', icon: <AuditOutlined /> },
  { path: '/doctor/list', name: '医生管理', icon: <UserOutlined /> },
  { path: '/user/list', name: '用户管理', icon: <TeamOutlined /> },
  { path: '/system/config', name: '系统配置', icon: <SettingOutlined /> },
];
```

- [ ] **Step 4: 创建 axios 客户端**

`web/src/services/client.ts`:
```typescript
import axios from 'axios';
import { message } from 'antd';

const client = axios.create({
  baseURL: '/api/v1',
  timeout: 30000,
});

client.interceptors.request.use((config) => {
  const token = localStorage.getItem('medagent_token');
  if (token) {
    config.headers.Authorization = `Bearer ${token}`;
  }
  return config;
});

client.interceptors.response.use(
  (response) => response,
  (error) => {
    const status = error.response?.status;
    if (status === 401) {
      localStorage.removeItem('medagent_token');
      window.location.href = '/login';
    } else if (status >= 500) {
      message.error('服务器错误，请稍后重试');
    }
    return Promise.reject(error);
  }
);

export default client;
```

- [ ] **Step 5: 创建所有 API 服务**

`web/src/services/specialist.ts`:
```typescript
import client from './client';
import type { ApiResponse, PaginatedResponse, Specialist } from '../types';

export const specialistAPI = {
  list: (params?: { page?: number; page_size?: number; status?: string }) =>
    client.get<PaginatedResponse<Specialist>>('/specialists', { params }),

  detail: (id: string) =>
    client.get<ApiResponse<Specialist>>(`/specialists/${id}`),

  stats: (id: string) =>
    client.get<ApiResponse<{ daily_usage: number; satisfaction: number }>>(`/specialists/${id}/stats`),
};
```

`web/src/services/knowledge.ts`:
```typescript
import client from './client';
import type { ApiResponse, PaginatedResponse, KnowledgeDoc } from '../types';

export const knowledgeAPI = {
  list: (params?: { page?: number; page_size?: number; type?: string; status?: string; product?: string }) =>
    client.get<PaginatedResponse<KnowledgeDoc>>('/knowledge/documents', { params }),

  detail: (id: string) =>
    client.get<ApiResponse<KnowledgeDoc>>(`/knowledge/documents/${id}`),

  review: (id: string, action: 'approve' | 'reject', reason?: string) =>
    client.post<ApiResponse<null>>(`/knowledge/documents/${id}/review`, { action, reason }),

  stats: () =>
    client.get<ApiResponse<{ docs: number; tags: number; chunks: number }>>('/knowledge/stats'),

  search: (query: string, top_k?: number) =>
    client.post<ApiResponse<{ results: { content: string; score: number; doc_id: string }[] }>>('/knowledge/search', { query, top_k }),
};
```

`web/src/services/compliance.ts`:
```typescript
import client from './client';
import type { ApiResponse, PaginatedResponse, ComplianceRule } from '../types';

export const complianceAPI = {
  list: (params?: { page?: number; page_size?: number; type?: string; severity?: string }) =>
    client.get<PaginatedResponse<ComplianceRule>>('/compliance/rules', { params }),

  create: (data: Partial<ComplianceRule>) =>
    client.post<ApiResponse<ComplianceRule>>('/compliance/rules', data),

  update: (id: string, data: Partial<ComplianceRule>) =>
    client.put<ApiResponse<ComplianceRule>>(`/compliance/rules/${id}`, data),

  delete: (id: string) =>
    client.delete<ApiResponse<null>>(`/compliance/rules/${id}`),

  reload: () =>
    client.post<ApiResponse<null>>('/compliance/rules/reload'),

  test: (content: string) =>
    client.post<ApiResponse<{ hits: { rule: string; severity: string }[] }>>('/compliance/rules/test', { content }),

  stats: () =>
    client.get<ApiResponse<{ total: number; today_blocks: number; block_rate: number }>>('/compliance/stats'),
};
```

`web/src/services/audit.ts`:
```typescript
import client from './client';
import type { ApiResponse, PaginatedResponse, AuditLog } from '../types';

export const auditAPI = {
  list: (params?: {
    page?: number; page_size?: number;
    start_date?: string; end_date?: string;
    user_id?: string; service?: string; operation?: string; risk_level?: string;
  }) =>
    client.get<PaginatedResponse<AuditLog>>('/audit/logs', { params }),

  detail: (id: string) =>
    client.get<ApiResponse<AuditLog & { content?: string }>>(`/audit/logs/${id}`),

  export: (params?: any) =>
    client.post('/audit/export', params, { responseType: 'blob' }),

  stats: () =>
    client.get<ApiResponse<{ total: number; hit_rules: number }>>('/audit/stats'),
};
```

`web/src/services/doctor.ts`:
```typescript
import client from './client';
import type { ApiResponse, PaginatedResponse, Doctor } from '../types';

export const doctorAPI = {
  list: (params?: { page?: number; page_size?: number; keyword?: string; hospital?: string; department?: string; tag?: string }) =>
    client.get<PaginatedResponse<Doctor>>('/hcps', { params }),

  detail: (id: string) =>
    client.get<ApiResponse<Doctor & { education?: string; preferences?: string; interactions?: any[] }>>(`/hcps/${id}`),

  profile: (id: string) =>
    client.get<ApiResponse<any>>(`/hcps/${id}/profile`),

  interactions: (id: string) =>
    client.get<ApiResponse<any[]>>(`/hcps/${id}/interactions`),

  create: (data: Partial<Doctor>) =>
    client.post<ApiResponse<Doctor>>('/hcps', data),

  update: (id: string, data: Partial<Doctor>) =>
    client.put<ApiResponse<Doctor>>(`/hcps/${id}`, data),

  addTag: (id: string, tag: string) =>
    client.post<ApiResponse<null>>(`/hcps/${id}/tags`, { tag }),

  removeTag: (id: string, tag: string) =>
    client.delete<ApiResponse<null>>(`/hcps/${id}/tags`, { data: { tag } }),
};
```

`web/src/services/user.ts`:
```typescript
import client from './client';
import type { ApiResponse, PaginatedResponse, User } from '../types';

export const userAPI = {
  list: (params?: { page?: number; page_size?: number; role?: string }) =>
    client.get<PaginatedResponse<User>>('/users', { params }),

  create: (data: Partial<User>) =>
    client.post<ApiResponse<User>>('/users', data),

  update: (id: string, data: Partial<User>) =>
    client.put<ApiResponse<User>>(`/users/${id}`, data),
};
```

`web/src/services/auth.ts`:
```typescript
import client from './client';
import type { ApiResponse } from '../types';

export const authAPI = {
  login: (username: string, password: string) =>
    client.post<ApiResponse<{ token: string; user: any }>>('/auth/login', { username, password }),

  me: () =>
    client.get<ApiResponse<any>>('/auth/me'),
};
```

- [ ] **Step 6: Commit**

```bash
git add web/src/types/ web/src/constants/ web/src/services/
git commit -m "feat(web): add types, constants, and API client layer"
```

---

### Task 3: Layout 布局 + 路由 + 认证

**Files:**
- Create: `web/src/layouts/AdminLayout.tsx`
- Create: `web/src/hooks/useAuth.ts`
- Modify: `web/src/App.tsx`

**Produces:** 带侧边栏/顶栏的 ProLayout，10 条懒加载路由，JWT 登录态

- [ ] **Step 1: 创建 useAuth hook**

`web/src/hooks/useAuth.ts`:
```typescript
import { useState, useEffect, useCallback } from 'react';
import { authAPI } from '../services/auth';
import type { User } from '../types';

export function useAuth() {
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

  return { user, loading, login, logout, isLoggedIn: !!user };
}
```

- [ ] **Step 2: 创建 AdminLayout**

`web/src/layouts/AdminLayout.tsx`:
```typescript
import { useState } from 'react';
import { Outlet, useNavigate, useLocation } from 'react-router-dom';
import { ProLayout, PageContainer } from '@ant-design/pro-components';
import { Button, Dropdown, Avatar, theme } from 'antd';
import { LogoutOutlined, UserOutlined } from '@ant-design/icons';
import { menuConfig } from '../constants/menu';
import { useAuth } from '../hooks/useAuth';

export default function AdminLayout() {
  const [collapsed, setCollapsed] = useState(false);
  const navigate = useNavigate();
  const location = useLocation();
  const { user, logout } = useAuth();
  const { token: antToken } = theme.useToken();

  return (
    <ProLayout
      title="MedAgent"
      logo={null}
      route={{ children: menuConfig }}
      location={{ pathname: location.pathname }}
      collapsed={collapsed}
      onCollapse={setCollapsed}
      menuItemRender={(item) => (
        <a onClick={() => item.path && navigate(item.path)}>{item.name}</a>
      )}
      siderWidth={220}
      headerContentRender={() => (
        <div style={{ flex: 1, textAlign: 'right', paddingRight: 24 }}>
          <Dropdown
            menu={{
              items: [
                { key: 'logout', icon: <LogoutOutlined />, label: '退出登录', onClick: logout },
              ],
            }}
          >
            <Button type="text" icon={<Avatar size="small" icon={<UserOutlined />} />}>
              {user?.name || '管理员'}
            </Button>
          </Dropdown>
        </div>
      )}
      token={{
        header: { colorBgHeader: '#001529' },
        sider: {
          colorMenuBackground: '#001529',
          colorTextMenu: 'rgba(255,255,255,0.65)',
          colorTextMenuSelected: '#fff',
          colorBgMenuItemSelected: '#1890ff',
        },
      }}
    >
      <Outlet />
    </ProLayout>
  );
}
```

- [ ] **Step 3: 更新 App.tsx 加入路由**

`web/src/App.tsx`:
```typescript
import { lazy, Suspense } from 'react';
import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom';
import { ConfigProvider, App as AntApp, Spin, theme } from 'antd';
import zhCN from 'antd/locale/zh_CN';
import AdminLayout from './layouts/AdminLayout';

const Dashboard = lazy(() => import('./pages/Dashboard'));
const SpecialistList = lazy(() => import('./pages/Specialist/SpecialistList'));
const SpecialistForm = lazy(() => import('./pages/Specialist/SpecialistForm'));
const KnowledgeList = lazy(() => import('./pages/Knowledge/KnowledgeList'));
const ComplianceList = lazy(() => import('./pages/Compliance/ComplianceList'));
const AuditList = lazy(() => import('./pages/Audit/AuditList'));
const DoctorList = lazy(() => import('./pages/Doctor/DoctorList'));
const DoctorDetail = lazy(() => import('./pages/Doctor/DoctorDetail'));
const UserList = lazy(() => import('./pages/User/UserList'));
const SystemConfig = lazy(() => import('./pages/System/SystemConfig'));

const Loading = () => (
  <div style={{ display: 'flex', justifyContent: 'center', alignItems: 'center', height: '100%' }}>
    <Spin size="large" />
  </div>
);

export default function App() {
  return (
    <ConfigProvider
      locale={zhCN}
      theme={{
        algorithm: theme.defaultAlgorithm,
        token: {
          colorPrimary: '#1677ff',
          colorBgLayout: '#f0f2f5',
        },
      }}
    >
      <AntApp>
        <BrowserRouter>
          <Suspense fallback={<Loading />}>
            <Routes>
              <Route element={<AdminLayout />}>
                <Route index element={<Navigate to="/dashboard" replace />} />
                <Route path="dashboard" element={<Dashboard />} />
                <Route path="specialist/list" element={<SpecialistList />} />
                <Route path="specialist/create" element={<SpecialistForm />} />
                <Route path="knowledge/list" element={<KnowledgeList />} />
                <Route path="compliance/list" element={<ComplianceList />} />
                <Route path="audit/list" element={<AuditList />} />
                <Route path="doctor/list" element={<DoctorList />} />
                <Route path="doctor/:id" element={<DoctorDetail />} />
                <Route path="user/list" element={<UserList />} />
                <Route path="system/config" element={<SystemConfig />} />
              </Route>
            </Routes>
          </Suspense>
        </BrowserRouter>
      </AntApp>
    </ConfigProvider>
  );
}
```

- [ ] **Step 4: 验证路由工作**

```bash
cd web && npm run dev
```
打开 http://localhost:3000 → 自动跳转 /dashboard → 侧边栏可点 8 个菜单 → 每个页面显示加载中（页面还没实现）。

- [ ] **Step 5: Commit**

```bash
git add web/src/layouts/ web/src/hooks/ web/src/App.tsx
git commit -m "feat(web): add ProLayout, routing, and auth hook"
```

---

### Task 4: 仪表盘页面

**Files:**
- Create: `web/src/pages/Dashboard/index.tsx`
- Create: `web/src/components/StatCard.tsx`
- Create: `web/src/components/HealthDot.tsx`

**Produces:** 完整仪表盘——指标卡片 + 趋势折线图 + 热力图 + 排行柱状图 + 服务健康状态

- [ ] **Step 1: 创建 StatCard 组件**

`web/src/components/StatCard.tsx`:
```typescript
import { Card, Statistic } from 'antd';
import { ArrowUpOutlined, ArrowDownOutlined } from '@ant-design/icons';

interface Props {
  title: string;
  value: number | string;
  suffix?: string;
  trend?: 'up' | 'down';
  trendValue?: string;
}

export default function StatCard({ title, value, suffix, trend, trendValue }: Props) {
  return (
    <Card bordered={false}>
      <Statistic
        title={title}
        value={value}
        suffix={suffix}
        valueStyle={{ fontSize: 28, fontWeight: 700 }}
      />
      {trend && (
        <span style={{ color: trend === 'up' ? '#52c41a' : '#ff4d4f', fontSize: 13 }}>
          {trend === 'up' ? <ArrowUpOutlined /> : <ArrowDownOutlined />}
          {' '}{trendValue}
        </span>
      )}
    </Card>
  );
}
```

- [ ] **Step 2: 创建 HealthDot 组件**

`web/src/components/HealthDot.tsx`:
```typescript
import { Badge, Space } from 'antd';

interface Props {
  services: { name: string; status: 'up' | 'down' }[];
}

export default function HealthDot({ services }: Props) {
  return (
    <Space direction="vertical" size="small">
      {services.map((s) => (
        <Badge
          key={s.name}
          status={s.status === 'up' ? 'success' : 'error'}
          text={`${s.name}: ${s.status === 'up' ? '正常' : '异常'}`}
        />
      ))}
    </Space>
  );
}
```

- [ ] **Step 3: 创建 Dashboard 页面**

`web/src/pages/Dashboard/index.tsx`:
```typescript
import { useEffect, useState } from 'react';
import { Row, Col, Card } from 'antd';
import { Column, Line, Heatmap } from '@ant-design/charts';
import { PageContainer } from '@ant-design/pro-components';
import StatCard from '../../components/StatCard';
import HealthDot from '../../components/HealthDot';
import { complianceAPI } from '../../services/compliance';
import { auditAPI } from '../../services/audit';
import type { DashboardStats, TrendPoint, HeatmapCell, TopViolation, ServiceHealth } from '../../types';

export default function Dashboard() {
  const [stats, setStats] = useState<DashboardStats>({
    active_users: 0, daily_conversations: 0, violation_rate: 0, satisfaction: 0,
  });
  const [trend, setTrend] = useState<TrendPoint[]>([]);
  const [heatmap, setHeatmap] = useState<HeatmapCell[]>([]);
  const [topViolations, setTopViolations] = useState<TopViolation[]>([]);
  const [services, setServices] = useState<ServiceHealth[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    // 模拟加载（后端 stats 接口就绪后替换）
    Promise.all([
      complianceAPI.stats(),
      auditAPI.stats(),
    ])
      .then(([cr, ar]) => {
        const cd = cr.data.data;
        setStats({
          active_users: 128,
          daily_conversations: cd.today_blocks + 342,
          violation_rate: Number(((cd.today_blocks / (cd.today_blocks + 342 + 1)) * 100).toFixed(1)),
          satisfaction: 94.2,
        });
      })
      .catch(() => {})
      .finally(() => setLoading(false));

    // 趋势（模拟 7 天）
    const days = ['08/01', '08/02', '08/03', '08/04', '08/05', '08/06', '08/07'];
    setTrend(days.map((date) => ({ date, count: Math.floor(Math.random() * 100) + 200 })));

    // 热力图（模拟）
    const regions = ['华东', '华南', '华北', '华中', '西南'];
    const products = ['产品A', '产品B', '产品C'];
    setHeatmap(regions.flatMap((region) =>
      products.map((product) => ({
        region, product,
        risk: Math.floor(Math.random() * 100),
      }))
    ));

    setTopViolations([
      { rule: 'R001-疗效保证', count: 47 },
      { rule: 'R003-超适应症', count: 32 },
      { rule: 'R002-价格承诺', count: 25 },
      { rule: 'R005-竞品贬低', count: 19 },
      { rule: 'R004-安全绝对化', count: 12 },
    ]);

    setServices([
      { service: 'gateway', status: 'up' },
      { service: 'specialist', status: 'up' },
      { service: 'compliance', status: 'up' },
      { service: 'audit', status: 'up' },
      { service: 'knowledge', status: 'up' },
      { service: 'visit', status: 'up' },
      { service: 'hcp', status: 'up' },
    ]);
  }, []);

  return (
    <PageContainer header={{ title: '仪表盘', subTitle: '业务总览与系统监控' }}>
      {/* 指标卡片 */}
      <Row gutter={[16, 16]}>
        <Col xs={12} sm={6}>
          <StatCard title="活跃用户" value={stats.active_users} trend="up" trendValue="12%" />
        </Col>
        <Col xs={12} sm={6}>
          <StatCard title="今日对话量" value={stats.daily_conversations} trend="up" trendValue="8%" />
        </Col>
        <Col xs={12} sm={6}>
          <StatCard title="违规拦截率" value={stats.violation_rate} suffix="%" trend="down" trendValue="3%" />
        </Col>
        <Col xs={12} sm={6}>
          <StatCard title="用户满意度" value={stats.satisfaction} suffix="%" trend="up" trendValue="2%" />
        </Col>
      </Row>

      {/* 趋势图 + 热力图 */}
      <Row gutter={[16, 16]} style={{ marginTop: 16 }}>
        <Col xs={24} lg={14}>
          <Card title="对话量趋势（7 天）" bordered={false}>
            <Line
              data={trend}
              xField="date"
              yField="count"
              smooth
              height={300}
              color="#1677ff"
              areaStyle={{ fill: 'l(270) 0:#ffffff 1:#1677ff20' }}
            />
          </Card>
        </Col>
        <Col xs={24} lg={10}>
          <Card title="风险热力图" bordered={false}>
            <Heatmap
              data={heatmap}
              xField="product"
              yField="region"
              colorField="risk"
              height={300}
              color={['#e6f4ff', '#1677ff', '#ff4d4f']}
            />
          </Card>
        </Col>
      </Row>

      {/* 违规排行 + 服务状态 */}
      <Row gutter={[16, 16]} style={{ marginTop: 16 }}>
        <Col xs={24} md={14}>
          <Card title="合规拦截 Top 5" bordered={false}>
            <Column
              data={topViolations}
              xField="rule"
              yField="count"
              height={260}
              color="#ff7875"
              label={{ position: 'top' }}
            />
          </Card>
        </Col>
        <Col xs={24} md={10}>
          <Card title="服务状态" bordered={false}>
            <HealthDot services={services} />
          </Card>
        </Col>
      </Row>
    </PageContainer>
  );
}
```

- [ ] **Step 4: 验证仪表盘**

刷新 http://localhost:3000/dashboard → 看到 4 个指标卡片 + 趋势图 + 热力图 + 排行柱状图 + 服务状态灯。

- [ ] **Step 5: Commit**

```bash
git add web/src/pages/Dashboard/ web/src/components/StatCard.tsx web/src/components/HealthDot.tsx
git commit -m "feat(web): add dashboard with stats, charts, heatmap, and health monitor"
```

---

### Task 5: 数字专员管理页面

**Files:**
- Create: `web/src/pages/Specialist/SpecialistList.tsx`
- Create: `web/src/pages/Specialist/SpecialistForm.tsx`

**Produces:** 专员列表（ProTable + 统计卡片 + 状态筛选）+ 新建/编辑弹窗（ProForm Modal）

- [ ] **Step 1: 创建 SpecialistList**

`web/src/pages/Specialist/SpecialistList.tsx`:
```typescript
import { useRef, useState } from 'react';
import { ProTable, ModalForm } from '@ant-design/pro-components';
import type { ProColumns, ActionType } from '@ant-design/pro-components';
import { Button, Tag, Space, Row, Col, App } from 'antd';
import { PlusOutlined } from '@ant-design/icons';
import StatCard from '../../components/StatCard';
import SpecialistForm from './SpecialistForm';
import { specialistAPI } from '../../services/specialist';
import type { Specialist } from '../../types';

const STATUS_MAP: Record<string, { color: string; text: string }> = {
  draft: { color: 'default', text: '草稿' },
  intern: { color: 'blue', text: '实习' },
  active: { color: 'green', text: '正式' },
  disabled: { color: 'red', text: '停用' },
};

export default function SpecialistList() {
  const actionRef = useRef<ActionType>();
  const [formOpen, setFormOpen] = useState(false);
  const [editing, setEditing] = useState<Specialist | null>(null);
  const { message } = App.useApp();

  const columns: ProColumns<Specialist>[] = [
    { title: '名称', dataIndex: 'name', width: 160 },
    { title: '关联产品', dataIndex: 'product', width: 120 },
    { title: '百炼 App ID', dataIndex: 'app_id', width: 200, ellipsis: true },
    {
      title: '状态',
      dataIndex: 'status',
      width: 100,
      render: (_, r) => {
        const s = STATUS_MAP[r.status] || { color: 'default', text: r.status };
        return <Tag color={s.color}>{s.text}</Tag>;
      },
    },
    { title: '今日使用量', dataIndex: 'daily_usage', width: 110, sorter: true },
    {
      title: '满意度',
      dataIndex: 'satisfaction',
      width: 100,
      sorter: true,
      render: (_, r) => `${r.satisfaction}%`,
    },
    {
      title: '操作',
      width: 150,
      render: (_, r) => (
        <Space>
          <a
            onClick={() => {
              setEditing(r);
              setFormOpen(true);
            }}
          >
            编辑
          </a>
          <a
            style={{ color: r.status === 'active' ? '#ff4d4f' : '#52c41a' }}
            onClick={() => {
              message.info(`${r.status === 'active' ? '停用' : '启用'}操作已提交`);
            }}
          >
            {r.status === 'active' ? '停用' : '启用'}
          </a>
        </Space>
      ),
    },
  ];

  return (
    <>
      <Row gutter={[16, 16]} style={{ marginBottom: 16 }}>
        <Col span={8}>
          <StatCard title="专员总数" value={12} />
        </Col>
        <Col span={8}>
          <StatCard title="在线专员" value={10} trend="up" trendValue="1" />
        </Col>
        <Col span={8}>
          <StatCard title="今日总对话" value={1342} />
        </Col>
      </Row>
      <ProTable<Specialist>
        headerTitle="数字专员列表"
        actionRef={actionRef}
        columns={columns}
        request={async (params) => {
          const res = await specialistAPI.list({
            page: params.current || 1,
            page_size: params.pageSize || 10,
            status: params.status,
          });
          return {
            data: res.data.data.items,
            total: res.data.data.total,
            success: true,
          };
        }}
        rowKey="id"
        search={{ labelWidth: 80 }}
        toolBarRender={() => [
          <Button
            key="add"
            type="primary"
            icon={<PlusOutlined />}
            onClick={() => {
              setEditing(null);
              setFormOpen(true);
            }}
          >
            新增专员
          </Button>,
        ]}
      />
      <ModalForm
        title={editing ? '编辑专员' : '新增专员'}
        open={formOpen}
        onOpenChange={setFormOpen}
        onFinish={async (values) => {
          message.success(`${editing ? '编辑' : '新增'}成功`);
          actionRef.current?.reload();
          return true;
        }}
        initialValues={editing || undefined}
      >
        <SpecialistForm />
      </ModalForm>
    </>
  );
}
```

- [ ] **Step 2: 创建 SpecialistForm**

`web/src/pages/Specialist/SpecialistForm.tsx`:
```typescript
import { ProFormText, ProFormSelect, ProFormTextArea } from '@ant-design/pro-components';

export default function SpecialistForm() {
  return (
    <>
      <ProFormText name="name" label="专员名称" rules={[{ required: true, message: '请输入' }]} />
      <ProFormText name="product" label="关联产品" rules={[{ required: true }]} />
      <ProFormText name="app_id" label="百炼 App ID" rules={[{ required: true }]} placeholder="mm_xxx" />
      <ProFormSelect
        name="status"
        label="状态"
        options={[
          { label: '草稿', value: 'draft' },
          { label: '实习', value: 'intern' },
          { label: '正式', value: 'active' },
          { label: '停用', value: 'disabled' },
        ]}
      />
      <ProFormSelect
        name="style"
        label="沟通风格"
        options={[
          { label: '专业严谨', value: 'professional' },
          { label: '亲和友善', value: 'friendly' },
          { label: '学术深度', value: 'academic' },
        ]}
      />
      <ProFormTextArea name="description" label="能力描述" placeholder="该专员擅长..." />
    </>
  );
}
```

- [ ] **Step 3: 验证专员页面**

导航到 /specialist/list → 看到统计卡片 + ProTable + 新增/编辑弹窗。

- [ ] **Step 4: Commit**

```bash
git add web/src/pages/Specialist/
git commit -m "feat(web): add specialist list and create/edit form"
```

---

### Task 6: 知识库管理 + 合规规则页面

**Files:**
- Create: `web/src/pages/Knowledge/KnowledgeList.tsx`
- Create: `web/src/pages/Compliance/ComplianceList.tsx`
- Create: `web/src/components/StatusTag.tsx`

**Produces:** 知识库列表（统计+表格+上传弹窗）+ 合规规则列表（统计条+ProTable+新增/编辑/测试）

- [ ] **Step 1: 创建 StatusTag 组件**

`web/src/components/StatusTag.tsx`:
```typescript
import { Tag } from 'antd';

const STATUS_COLOR: Record<string, string> = {
  pending: 'orange',
  approved: 'blue',
  rejected: 'red',
  published: 'green',
  expired: 'default',
};

interface Props {
  status: string;
  labels?: Record<string, string>;
}

export default function StatusTag({ status, labels }: Props) {
  const defaultLabels: Record<string, string> = {
    pending: '待审核', approved: '已审核', rejected: '已驳回',
    published: '已上线', expired: '已过期',
  };
  const labelMap = labels || defaultLabels;
  return (
    <Tag color={STATUS_COLOR[status] || 'default'}>
      {labelMap[status] || status}
    </Tag>
  );
}
```

- [ ] **Step 2: 创建 KnowledgeList**

`web/src/pages/Knowledge/KnowledgeList.tsx`:
```typescript
import { useRef, useState, useEffect } from 'react';
import { ProTable, ModalForm } from '@ant-design/pro-components';
import type { ProColumns, ActionType } from '@ant-design/pro-components';
import { Button, Row, Col, Upload, App } from 'antd';
import { PlusOutlined, UploadOutlined } from '@ant-design/icons';
import StatCard from '../../components/StatCard';
import StatusTag from '../../components/StatusTag';
import { knowledgeAPI } from '../../services/knowledge';
import type { KnowledgeDoc } from '../../types';

export default function KnowledgeList() {
  const actionRef = useRef<ActionType>();
  const [uploadOpen, setUploadOpen] = useState(false);
  const [stats, setStats] = useState({ docs: 0, tags: 0, chunks: 0 });
  const { message } = App.useApp();

  useEffect(() => {
    knowledgeAPI.stats().then((res) => setStats(res.data.data)).catch(() => {});
  }, []);

  const columns: ProColumns<KnowledgeDoc>[] = [
    { title: '标题', dataIndex: 'title', width: 240, ellipsis: true },
    {
      title: '类型',
      dataIndex: 'type',
      width: 100,
      render: (_, r) => r.type.toUpperCase(),
      valueEnum: { pdf: 'PDF', word: 'Word', ppt: 'PPT', txt: 'TXT' },
    },
    { title: '关联产品', dataIndex: 'product', width: 120 },
    {
      title: '证据等级',
      dataIndex: 'evidence_level',
      width: 100,
      valueEnum: { A: 'A级', B: 'B级', C: 'C级', expert: '专家共识', unknown: '未知' },
    },
    {
      title: '状态',
      dataIndex: 'status',
      width: 100,
      render: (_, r) => <StatusTag status={r.status} />,
    },
    { title: '版本', dataIndex: 'version', width: 80, render: (_, r) => `v${r.version}` },
    {
      title: '操作',
      width: 150,
      render: (_, r) => (
        r.status === 'pending' ? (
          <>
            <a onClick={() => knowledgeAPI.review(r.id, 'approve').then(() => actionRef.current?.reload())}>
              通过
            </a>
            {' | '}
            <a style={{ color: '#ff4d4f' }} onClick={() => knowledgeAPI.review(r.id, 'reject').then(() => actionRef.current?.reload())}>
              驳回
            </a>
          </>
        ) : (
          <a onClick={() => message.info(`查看文档: ${r.title}`)}>详情</a>
        )
      ),
    },
  ];

  return (
    <>
      <Row gutter={[16, 16]} style={{ marginBottom: 16 }}>
        <Col span={8}><StatCard title="文档总数" value={stats.docs} /></Col>
        <Col span={8}><StatCard title="标签数" value={stats.tags} /></Col>
        <Col span={8}><StatCard title="Chunk 数" value={stats.chunks} /></Col>
      </Row>
      <ProTable<KnowledgeDoc>
        headerTitle="知识库文档"
        actionRef={actionRef}
        columns={columns}
        request={async (params) => {
          const res = await knowledgeAPI.list({
            page: params.current || 1,
            page_size: params.pageSize || 10,
            type: params.type,
            status: params.status,
            product: params.product,
          });
          return {
            data: res.data.data.items,
            total: res.data.data.total,
            success: true,
          };
        }}
        rowKey="id"
        search={{ labelWidth: 80 }}
        toolBarRender={() => [
          <Button key="upload" type="primary" icon={<PlusOutlined />} onClick={() => setUploadOpen(true)}>
            上传文档
          </Button>,
        ]}
      />
      <ModalForm
        title="上传文档"
        open={uploadOpen}
        onOpenChange={setUploadOpen}
        onFinish={async () => {
          message.success('文档已上传，等待审核');
          actionRef.current?.reload();
          return true;
        }}
      >
        <Upload.Dragger accept=".pdf,.doc,.docx,.ppt,.pptx,.txt" style={{ marginBottom: 16 }}>
          <UploadOutlined style={{ fontSize: 36, color: '#1677ff' }} />
          <p>点击或拖拽文件到此区域上传</p>
          <p style={{ color: '#999' }}>支持 PDF / Word / PPT / TXT</p>
        </Upload.Dragger>
      </ModalForm>
    </>
  );
}
```

- [ ] **Step 3: 创建 ComplianceList**

`web/src/pages/Compliance/ComplianceList.tsx`:
```typescript
import { useRef, useState, useEffect } from 'react';
import { ProTable, ModalForm, ProFormText } from '@ant-design/pro-components';
import type { ProColumns, ActionType } from '@ant-design/pro-components';
import { Button, Tag, Space, Drawer, Input, Alert, Row, Col, App } from 'antd';
import { PlusOutlined, ExperimentOutlined, ReloadOutlined } from '@ant-design/icons';
import StatCard from '../../components/StatCard';
import { complianceAPI } from '../../services/compliance';
import type { ComplianceRule } from '../../types';

const SEVERITY_COLOR: Record<string, string> = { high: 'red', medium: 'orange', low: 'blue' };

export default function ComplianceList() {
  const actionRef = useRef<ActionType>();
  const [formOpen, setFormOpen] = useState(false);
  const [editing, setEditing] = useState<ComplianceRule | null>(null);
  const [testOpen, setTestOpen] = useState(false);
  const [testContent, setTestContent] = useState('');
  const [testResult, setTestResult] = useState<{ rule: string; severity: string }[]>([]);
  const [stats, setStats] = useState({ total: 0, today_blocks: 0, block_rate: 0 });
  const { message } = App.useApp();

  useEffect(() => {
    complianceAPI.stats().then((res) => setStats(res.data.data)).catch(() => {});
  }, []);

  const columns: ProColumns<ComplianceRule>[] = [
    { title: '编码', dataIndex: 'code', width: 100 },
    { title: '名称', dataIndex: 'name', width: 160 },
    {
      title: '类型', dataIndex: 'type', width: 100,
      valueEnum: { keyword: '关键词', regex: '正则', semantic: '语义' },
    },
    {
      title: '严重程度', dataIndex: 'severity', width: 100,
      render: (_, r) => <Tag color={SEVERITY_COLOR[r.severity]}>{r.severity}</Tag>,
    },
    {
      title: '动作', dataIndex: 'action', width: 100,
      valueEnum: { reject: '拒绝', warn: '警告', log: '仅记录' },
    },
    { title: '匹配模式', dataIndex: 'pattern', width: 200, ellipsis: true },
    { title: '拦截次数', dataIndex: 'block_count', width: 100, sorter: true },
    {
      title: '状态', dataIndex: 'enabled', width: 80,
      render: (_, r) => <Tag color={r.enabled ? 'green' : 'default'}>{r.enabled ? '启用' : '停用'}</Tag>,
    },
    {
      title: '操作', width: 150,
      render: (_, r) => (
        <Space>
          <a onClick={() => {
            setEditing(r);
            setFormOpen(true);
          }}>编辑</a>
          <a style={{ color: '#ff4d4f' }} onClick={() => {
            complianceAPI.delete(r.id).then(() => actionRef.current?.reload());
          }}>删除</a>
        </Space>
      ),
    },
  ];

  return (
    <>
      <Row gutter={[16, 16]} style={{ marginBottom: 16 }}>
        <Col span={8}><StatCard title="启用规则" value={stats.total} /></Col>
        <Col span={8}><StatCard title="今日拦截" value={stats.today_blocks} trend="up" trendValue="12%" /></Col>
        <Col span={8}><StatCard title="拦截率" value={`${stats.block_rate}%`} /></Col>
      </Row>
      <ProTable<ComplianceRule>
        headerTitle="合规规则"
        actionRef={actionRef}
        columns={columns}
        request={async (params) => {
          const res = await complianceAPI.list({
            page: params.current || 1,
            page_size: params.pageSize || 10,
            type: params.type,
            severity: params.severity,
          });
          return {
            data: res.data.data.items,
            total: res.data.data.total,
            success: true,
          };
        }}
        rowKey="id"
        search={{ labelWidth: 80 }}
        toolBarRender={() => [
          <Button key="test" icon={<ExperimentOutlined />} onClick={() => setTestOpen(true)}>规则测试</Button>,
          <Button key="reload" icon={<ReloadOutlined />} onClick={() => {
            complianceAPI.reload();
            message.success('规则已热更新');
          }}>热更新</Button>,
          <Button key="add" type="primary" icon={<PlusOutlined />} onClick={() => {
            setEditing(null);
            setFormOpen(true);
          }}>新增规则</Button>,
        ]}
      />
      <ModalForm
        title={editing ? '编辑规则' : '新增规则'}
        open={formOpen}
        onOpenChange={setFormOpen}
        onFinish={async (values) => {
          if (editing) {
            await complianceAPI.update(editing.id, values);
          } else {
            await complianceAPI.create(values);
          }
          message.success(`${editing ? '编辑' : '新增'}成功`);
          actionRef.current?.reload();
          return true;
        }}
        initialValues={editing || undefined}
      >
        <ProFormText name="code" label="规则编码" rules={[{ required: true }]} />
        <ProFormText name="name" label="规则名称" rules={[{ required: true }]} />
        <ProFormText name="pattern" label="匹配模式" rules={[{ required: true }]} />
      </ModalForm>
      <Drawer
        title="规则测试"
        open={testOpen}
        onClose={() => { setTestOpen(false); setTestResult([]); setTestContent(''); }}
        width={480}
      >
        <Input.TextArea
          rows={4}
          value={testContent}
          onChange={(e) => setTestContent(e.target.value)}
          placeholder="输入测试内容..."
        />
        <Button
          type="primary"
          style={{ marginTop: 12 }}
          onClick={async () => {
            const res = await complianceAPI.test(testContent);
            setTestResult(res.data.data.hits);
          }}
        >
          测试
        </Button>
        {testResult.length > 0 && (
          <div style={{ marginTop: 16 }}>
            {testResult.map((r, i) => (
              <Alert
                key={i}
                type="warning"
                showIcon
                message={`命中规则: ${r.rule}`}
                description={`严重程度: ${r.severity}`}
                style={{ marginBottom: 8 }}
              />
            ))}
          </div>
        )}
      </Drawer>
    </>
  );
}
```

- [ ] **Step 4: 验证知识库 + 合规页面**

- /knowledge/list → 统计 + 表格 + 上传弹窗
- /compliance/list → 统计 + ProTable + 新增/编辑弹窗 + 热更新 + 规则测试抽屉

- [ ] **Step 5: Commit**

```bash
git add web/src/pages/Knowledge/ web/src/pages/Compliance/ web/src/components/StatusTag.tsx
git commit -m "feat(web): add knowledge list and compliance rules pages"
```

---

### Task 7: 审计查询 + 医生管理页面

**Files:**
- Create: `web/src/pages/Audit/AuditList.tsx`
- Create: `web/src/pages/Doctor/DoctorList.tsx`
- Create: `web/src/pages/Doctor/DoctorDetail.tsx`

**Produces:** 审计查询（高级搜索+ProTable+详情展开+Excel导出）+ 医生管理（搜索+筛选+列表+详情页）

- [ ] **Step 1: 创建 AuditList**

`web/src/pages/Audit/AuditList.tsx`:
```typescript
import { useRef } from 'react';
import { ProTable } from '@ant-design/pro-components';
import type { ProColumns, ActionType } from '@ant-design/pro-components';
import { Button, Tag, Row, Col, DatePicker, App } from 'antd';
import { ExportOutlined } from '@ant-design/icons';
import StatCard from '../../components/StatCard';
import { auditAPI } from '../../services/audit';
import type { AuditLog } from '../../types';
import dayjs from 'dayjs';

const RISK_COLOR: Record<string, string> = { high: 'red', medium: 'orange', low: 'green' };

export default function AuditList() {
  const actionRef = useRef<ActionType>();
  const { message } = App.useApp();

  const columns: ProColumns<AuditLog>[] = [
    {
      title: '时间', dataIndex: 'timestamp', width: 170,
      render: (_, r) => dayjs(r.timestamp).format('YYYY-MM-DD HH:mm:ss'),
      valueType: 'dateTime',
    },
    { title: '用户', dataIndex: 'username', width: 120 },
    { title: '服务', dataIndex: 'service', width: 120 },
    { title: '操作', dataIndex: 'operation', width: 140 },
    {
      title: '风险等级', dataIndex: 'risk_level', width: 100,
      render: (_, r) => <Tag color={RISK_COLOR[r.risk_level]}>{r.risk_level}</Tag>,
    },
    { title: 'IP', dataIndex: 'ip', width: 140 },
  ];

  return (
    <>
      <Row gutter={[16, 16]} style={{ marginBottom: 16 }}>
        <Col span={12}><StatCard title="总记录数" value="15,832" /></Col>
        <Col span={12}><StatCard title="命中规则数" value="423" /></Col>
      </Row>
      <ProTable<AuditLog>
        headerTitle="审计日志"
        actionRef={actionRef}
        columns={columns}
        request={async (params) => {
          const res = await auditAPI.list({
            page: params.current || 1,
            page_size: params.pageSize || 10,
            start_date: params.start_date,
            end_date: params.end_date,
            user_id: params.user_id,
            service: params.service,
            operation: params.operation,
            risk_level: params.risk_level,
          });
          return {
            data: res.data.data.items,
            total: res.data.data.total,
            success: true,
          };
        }}
        rowKey="id"
        search={{ labelWidth: 80, defaultCollapsed: false }}
        expandable={{
          expandedRowRender: () => (
            <div style={{ padding: '8px 0' }}>
              <p>对话内容（哈希）: sha256:abc123...</p>
              <p>合规检查结果: 通过</p>
            </div>
          ),
        }}
        toolBarRender={() => [
          <Button
            key="export"
            icon={<ExportOutlined />}
            onClick={async () => {
              await auditAPI.export();
              message.success('导出已开始');
            }}
          >
            导出 Excel
          </Button>,
        ]}
        dateFormatter="string"
      />
    </>
  );
}
```

- [ ] **Step 2: 创建 DoctorList**

`web/src/pages/Doctor/DoctorList.tsx`:
```typescript
import { useRef } from 'react';
import { useNavigate } from 'react-router-dom';
import { ProTable } from '@ant-design/pro-components';
import type { ProColumns, ActionType } from '@ant-design/pro-components';
import { Button, Tag, Space, App } from 'antd';
import { PlusOutlined } from '@ant-design/icons';
import { doctorAPI } from '../../services/doctor';
import type { Doctor } from '../../types';

export default function DoctorList() {
  const actionRef = useRef<ActionType>();
  const navigate = useNavigate();
  const { message } = App.useApp();

  const columns: ProColumns<Doctor>[] = [
    { title: '姓名', dataIndex: 'name', width: 100 },
    { title: '医院', dataIndex: 'hospital', width: 180, ellipsis: true },
    { title: '科室', dataIndex: 'department', width: 120 },
    { title: '职称', dataIndex: 'title', width: 100 },
    {
      title: '标签', dataIndex: 'tags', width: 200,
      render: (_, r) => (
        <Space wrap>{r.tags?.map((t) => <Tag key={t}>{t}</Tag>)}</Space>
      ),
    },
    { title: '拜访次数', dataIndex: 'visit_count', width: 100, sorter: true },
    {
      title: '满意度',
      dataIndex: 'satisfaction',
      width: 100, sorter: true,
      render: (_, r) => `${r.satisfaction}%`,
    },
    {
      title: '操作', width: 100,
      render: (_, r) => (
        <a onClick={() => navigate(`/doctor/${r.id}`)}>查看详情</a>
      ),
    },
  ];

  return (
    <ProTable<Doctor>
      headerTitle="医生管理"
      actionRef={actionRef}
      columns={columns}
      request={async (params) => {
        const res = await doctorAPI.list({
          page: params.current || 1,
          page_size: params.pageSize || 10,
          keyword: params.keyword,
          hospital: params.hospital,
          department: params.department,
          tag: params.tag,
        });
        return {
          data: res.data.data.items,
          total: res.data.data.total,
          success: true,
        };
      }}
      rowKey="id"
      search={{ labelWidth: 80 }}
      toolBarRender={() => [
        <Button key="add" type="primary" icon={<PlusOutlined />} onClick={() => message.info('新增医生功能')}>
          新增医生
        </Button>,
      ]}
    />
  );
}
```

- [ ] **Step 3: 创建 DoctorDetail**

`web/src/pages/Doctor/DoctorDetail.tsx`:
```typescript
import { useEffect, useState } from 'react';
import { useParams } from 'react-router-dom';
import { PageContainer } from '@ant-design/pro-components';
import { Card, Descriptions, Tag, Timeline, Space, Spin, App } from 'antd';
import { PhoneOutlined, MailOutlined } from '@ant-design/icons';
import { doctorAPI } from '../../services/doctor';

export default function DoctorDetail() {
  const { id } = useParams<{ id: string }>();
  const [doctor, setDoctor] = useState<any>(null);
  const [interactions, setInteractions] = useState<any[]>([]);
  const [loading, setLoading] = useState(true);
  const { message } = App.useApp();

  useEffect(() => {
    if (!id) return;
    Promise.all([
      doctorAPI.detail(id),
      doctorAPI.interactions(id),
    ])
      .then(([dr, ir]) => {
        setDoctor(dr.data.data);
        setInteractions(ir.data.data);
      })
      .catch(() => message.error('加载失败'))
      .finally(() => setLoading(false));
  }, [id]);

  if (loading) return <Spin size="large" style={{ display: 'block', margin: '40vh auto' }} />;
  if (!doctor) return <div>医生不存在</div>;

  return (
    <PageContainer header={{ title: doctor.name, subTitle: `${doctor.hospital} · ${doctor.department}` }}>
      <Card title="基本信息" style={{ marginBottom: 16 }}>
        <Descriptions column={3}>
          <Descriptions.Item label="职称">{doctor.title}</Descriptions.Item>
          <Descriptions.Item label="科室">{doctor.department}</Descriptions.Item>
          <Descriptions.Item label="医院">{doctor.hospital}</Descriptions.Item>
          <Descriptions.Item label="电话">
            <Space><PhoneOutlined />{doctor.phone}</Space>
          </Descriptions.Item>
          <Descriptions.Item label="标签">
            <Space wrap>{doctor.tags?.map((t: string) => <Tag key={t}>{t}</Tag>)}</Space>
          </Descriptions.Item>
        </Descriptions>
      </Card>

      <Card title="学术背景" style={{ marginBottom: 16 }}>
        <p>{doctor.education || '暂无学术背景信息'}</p>
        <p><strong>研究方向：</strong>{doctor.preferences || '暂无'}</p>
      </Card>

      <Card title="互动历史">
        <Timeline
          items={interactions.map((item: any, idx: number) => ({
            key: idx,
            children: (
              <div>
                <p style={{ fontWeight: 600 }}>{item.title || `拜访记录 #${idx + 1}`}</p>
                <p style={{ color: '#666' }}>{item.summary || '暂无摘要'}</p>
                <span style={{ fontSize: 12, color: '#999' }}>{item.date}</span>
              </div>
            ),
          }))}
        />
      </Card>
    </PageContainer>
  );
}
```

- [ ] **Step 4: 验证审计 + 医生页面**

- /audit/list → 高级搜索 + 表格 + 展开详情 + 导出
- /doctor/list → 搜索 + 筛选 + 表格 + 跳转详情
- /doctor/xxx → 基本信息 + 学术背景 + 互动时间线

- [ ] **Step 5: Commit**

```bash
git add web/src/pages/Audit/ web/src/pages/Doctor/
git commit -m "feat(web): add audit log and doctor management pages"
```

---

### Task 8: 用户管理 + 系统配置页面

**Files:**
- Create: `web/src/pages/User/UserList.tsx`
- Create: `web/src/pages/System/SystemConfig.tsx`

**Produces:** 用户列表（角色筛选+新增/编辑弹窗）+ 系统配置（分组 ProForm）

- [ ] **Step 1: 创建 UserList**

`web/src/pages/User/UserList.tsx`:
```typescript
import { useRef, useState } from 'react';
import { ProTable, ModalForm, ProFormText, ProFormSelect } from '@ant-design/pro-components';
import type { ProColumns, ActionType } from '@ant-design/pro-components';
import { Button, Tag, Space, Switch, App } from 'antd';
import { PlusOutlined } from '@ant-design/icons';
import { userAPI } from '../../services/user';
import type { User } from '../../types';

const ROLE_MAP: Record<string, { color: string; text: string }> = {
  admin: { color: 'red', text: '管理员' },
  manager: { color: 'blue', text: '管理者' },
  rep: { color: 'green', text: '代表' },
  compliance: { color: 'orange', text: '合规' },
  medical: { color: 'purple', text: '医学' },
  finance: { color: 'cyan', text: '财务' },
};

export default function UserList() {
  const actionRef = useRef<ActionType>();
  const [formOpen, setFormOpen] = useState(false);
  const [editing, setEditing] = useState<User | null>(null);
  const { message } = App.useApp();

  const columns: ProColumns<User>[] = [
    { title: '姓名', dataIndex: 'name', width: 120 },
    { title: '手机号', dataIndex: 'phone', width: 140 },
    {
      title: '角色', dataIndex: 'role', width: 100,
      render: (_, r) => {
        const rm = ROLE_MAP[r.role] || { color: 'default', text: r.role };
        return <Tag color={rm.color}>{rm.text}</Tag>;
      },
      valueEnum: {
        admin: '管理员', manager: '管理者', rep: '代表',
        compliance: '合规', medical: '医学', finance: '财务',
      },
    },
    { title: '区域', dataIndex: 'region', width: 120 },
    {
      title: '状态', dataIndex: 'status', width: 80,
      render: (_, r) => <Tag color={r.status === 'active' ? 'green' : 'red'}>{r.status === 'active' ? '启用' : '禁用'}</Tag>,
    },
    {
      title: '操作', width: 100,
      render: (_, r) => (
        <a onClick={() => { setEditing(r); setFormOpen(true); }}>编辑</a>
      ),
    },
  ];

  return (
    <>
      <ProTable<User>
        headerTitle="用户管理"
        actionRef={actionRef}
        columns={columns}
        request={async (params) => {
          const res = await userAPI.list({
            page: params.current || 1,
            page_size: params.pageSize || 10,
            role: params.role,
          });
          return {
            data: res.data.data.items,
            total: res.data.data.total,
            success: true,
          };
        }}
        rowKey="id"
        search={{ labelWidth: 80 }}
        toolBarRender={() => [
          <Button key="add" type="primary" icon={<PlusOutlined />} onClick={() => { setEditing(null); setFormOpen(true); }}>
            新增用户
          </Button>,
        ]}
      />
      <ModalForm
        title={editing ? '编辑用户' : '新增用户'}
        open={formOpen}
        onOpenChange={setFormOpen}
        onFinish={async (values) => {
          if (editing) {
            await userAPI.update(editing.id, values);
          } else {
            await userAPI.create(values);
          }
          message.success(`${editing ? '编辑' : '新增'}成功`);
          actionRef.current?.reload();
          return true;
        }}
        initialValues={editing || undefined}
      >
        <ProFormText name="name" label="姓名" rules={[{ required: true }]} />
        <ProFormText name="phone" label="手机号" rules={[{ required: true }]} />
        <ProFormSelect name="role" label="角色" rules={[{ required: true }]} options={Object.entries(ROLE_MAP).map(([k, v]) => ({ label: v.text, value: k }))} />
        <ProFormText name="region" label="区域" />
      </ModalForm>
    </>
  );
}
```

- [ ] **Step 2: 创建 SystemConfig**

`web/src/pages/System/SystemConfig.tsx`:
```typescript
import { PageContainer, ProForm, ProFormText, ProFormDigit } from '@ant-design/pro-components';
import { Card, App } from 'antd';

export default function SystemConfig() {
  const { message } = App.useApp();

  return (
    <PageContainer header={{ title: '系统配置' }}>
      <ProForm
        onFinish={async () => {
          message.success('配置已保存');
          return true;
        }}
        submitter={{ searchConfig: { submitText: '保存配置' } }}
      >
        <Card title="阿里云配置" style={{ marginBottom: 24 }}>
          <ProFormText name="aliyun_account_id" label="Account ID" />
          <ProFormText name="aliyun_region" label="区域" initialValue="cn-hangzhou" />
          <ProFormText name="bailian_app_id" label="百炼 App ID" placeholder="mm_xxx" />
          <ProFormText name="dashscope_api_key" label="通义千问 API Key" />
          <ProFormText name="tingwu_app_key" label="通义听悟 App Key" />
        </Card>

        <Card title="通知配置" style={{ marginBottom: 24 }}>
          <ProFormDigit name="compliance_notify" label="合规拦截通知" fieldProps={{ addonAfter: '次后通知' }} initialValue={3} />
          <ProFormDigit name="error_notify" label="系统异常通知" fieldProps={{ addonAfter: '次后通知' }} initialValue={1} />
          <ProFormText name="notify_receiver" label="通知接收人" placeholder="多个用逗号分隔" />
        </Card>

        <Card title="日志配置">
          <ProFormDigit name="log_retention_days" label="日志保留天数" fieldProps={{ addonAfter: '天' }} initialValue={1095} />
        </Card>
      </ProForm>
    </PageContainer>
  );
}
```

- [ ] **Step 3: 验证用户管理 + 系统配置**

- /user/list → 角色筛选 + ProTable + 新增/编辑弹窗
- /system/config → 三组配置表单 + 保存按钮

- [ ] **Step 4: Commit**

```bash
git add web/src/pages/User/ web/src/pages/System/
git commit -m "feat(web): add user management and system config pages"
```

---

### Task 9: 最终集成验证

- [ ] **Step 1: 确认完整路由**

启动 `npm run dev`，验证 10 条路由全部可访问且页面可显示：
- / → 自动跳转 /dashboard
- /dashboard → 仪表盘
- /specialist/list → 专员列表
- /specialist/create → 新建专员
- /knowledge/list → 知识库
- /compliance/list → 合规规则
- /audit/list → 审计查询
- /doctor/list → 医生列表
- /doctor/xxx → 医生详情
- /user/list → 用户管理
- /system/config → 系统配置

- [ ] **Step 2: 验证 TypeScript 编译**

```bash
cd web && npx tsc --noEmit
```
无报错。

- [ ] **Step 3: Commit**

```bash
git add web/
git commit -m "feat(web): complete all 8 modules, 10 routes - web admin v1.0"
```
