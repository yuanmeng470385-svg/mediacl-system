# Web 医生管理补全 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 医生管理页「新增医生」从占位提示改为真实 ModalForm 表单，医生详情页展示 AI 画像（含降级兼容）。

**Architecture:** 后端 `POST /hcps` 与 `GET /hcps/{id}/profile` 已完整就绪，本计划全部是 web 前端改动：契约映射层（doctor.ts）补画像类型与映射（移植 mobile/src/api/hcp.ts 的既有逻辑），DoctorList 加 ModalForm（参照 UserList.tsx 模式），DoctorDetail 加载画像并渲染。

**Tech Stack:** React + Ant Design Pro（ProTable / ModalForm / ProFormText / ProFormSelect）+ TypeScript + axios（web/src/services/client.ts，baseURL `/api/v1`，自动带 JWT，400-499 自动弹后端 message）

## Global Constraints

- 后端响应形状（snake_case）统一在 `web/src/services/doctor.ts` 映射为页面消费形状，页面组件不直接碰后端原生字段
- 提交字段必须对齐后端白名单 `HCP_WRITABLE_FIELDS`（hcp_repo.py:13-17）：`name, hospital, department, title, specialty, phone, email, region, academic_background, prescription_preference, influence_level, tags, status`——白名单外字段后端 400
- 医生写操作（POST）后端要求 admin/manager 角色，非 admin/manager 用户隐藏「新增医生」按钮
- web 无单测框架，每个任务的验证 = `cd web && npm run build`（tsc + vite）通过 + 手工确认
- 每次任务结束提交一个 commit

---

### Task 1: doctor.ts 补 AI 画像类型与映射（移植 mobile 既有逻辑）

**Files:**
- Modify: `web/src/services/doctor.ts`（在 `mapInteractions` 之后追加；`profile` 方法改返回类型）
- Modify: `web/src/types/index.ts`（`Doctor` 接口扩展可选字段）

**Interfaces:**
- Produces: `HcpProfile`（后端原始形状）、`DoctorProfile`（页面消费形状）、`mapProfile(raw: unknown): DoctorProfile`、`doctorAPI.profile(id): Promise<ApiResponse<{data: HcpProfile}>>`
- 下游 Task 2/3 用 `mapProfile` 与 `doctorAPI.profile`

- [ ] **Step 1: 扩展 `Doctor` 类型**

`web/src/types/index.ts` 中 `Doctor` 接口（现约 189-199 行）追加可选字段（保持现有必填不变）：

```ts
export interface Doctor {
  id: string;
  name: string;
  hospital?: string;
  department?: string;
  title?: string;
  phone?: string;
  tags?: string[];
  visit_count?: number;
  satisfaction?: number;
  specialty?: string;
  email?: string;
  region?: string;
  status?: string;
  influence_level?: 'high' | 'medium' | 'low' | string;
}
```

- [ ] **Step 2: 在 `web/src/services/doctor.ts` 追加画像类型与映射**

在 `mapInteractions` 函数之后（约 99 行处）追加：

```ts
/** AI 画像原始响应（后端 GET /hcps/{id}/profile，hcps.py:116-119） */
export interface HcpProfile {
  ai_profile:
    | {
        academic_profile?: string;
        prescription_preference?: string;
        communication_advice?: string | { best_time?: string; preferred_channels?: string[]; topics_to_avoid?: string[] };
        next_step_suggestion?: string;
        risk_alert?: string | Array<{ level?: string; description?: string }>;
      }
    | { summary: string; base_info?: Record<string, string> }
    | null;
  interactions?: unknown;
  degraded?: boolean;
  reason?: string;
  hcp?: unknown;
}

/** 页面消费形状（映射自 HcpProfile，含降级兼容） */
export interface DoctorProfile {
  ai_available: boolean;
  ai_unavailable_reason: string;
  academic_profile: string;
  prescription_preference: string;
  communication_advice: string;
  next_step_suggestion: string;
  /** 空数组 = 无风险提示 */
  risk_alerts: { level: string; description: string }[];
}

/** risk_alert：字符串（"无"/"无风险"→空数组）或对象数组；逻辑移植自 mobile/src/api/hcp.ts mapRiskAlert */
function mapRiskAlert(risk: unknown): DoctorProfile['risk_alerts'] {
  if (typeof risk === 'string') {
    const t = risk.trim();
    if (!t || t === '无' || t === '无风险') return [];
    return [{ level: 'warning', description: t }];
  }
  if (Array.isArray(risk)) {
    return risk
      .filter((v): v is Record<string, unknown> => !!v && typeof v === 'object')
      .map((v) => ({
        level: typeof v.level === 'string' && v.level ? v.level : 'warning',
        description: typeof v.description === 'string' ? v.description : String(v),
      }))
      .filter((x) => x.description && x.description.trim());
  }
  return [];
}

/** communication_advice：字符串原样；对象抽 best_time/preferred_channels/topics_to_avoid（移植 mobile mapCommunication） */
function mapCommunicationAdvice(v: unknown): string {
  if (typeof v === 'string') return v.trim();
  if (v && typeof v === 'object') {
    const o = v as { best_time?: unknown; preferred_channels?: unknown; topics_to_avoid?: unknown };
    const parts: string[] = [];
    if (typeof o.best_time === 'string' && o.best_time.trim()) parts.push(`最佳时间：${o.best_time}`);
    if (Array.isArray(o.preferred_channels) && o.preferred_channels.length) parts.push(`偏好渠道：${o.preferred_channels.join('、')}`);
    if (Array.isArray(o.topics_to_avoid) && o.topics_to_avoid.length) parts.push(`注意规避：${o.topics_to_avoid.join('、')}`);
    return parts.join('\n');
  }
  return '';
}

/** 画像映射（含降级：degraded 或 ai_profile 为 null / 含 base_info·summary 时置 ai_available=false） */
export function mapProfile(raw: unknown): DoctorProfile {
  const r = (raw ?? {}) as HcpProfile;
  const ap = r.ai_profile;
  const degraded = !!r.degraded || !ap || typeof ap !== 'object' || 'base_info' in ap || 'summary' in ap;
  const reason =
    typeof r.reason === 'string' && r.reason
      ? r.reason
      : ap && typeof ap === 'object' && 'summary' in ap && typeof ap.summary === 'string'
        ? ap.summary
        : 'AI 画像暂不可用';
  if (degraded) {
    return {
      ai_available: false,
      ai_unavailable_reason: reason || 'AI 画像暂不可用',
      academic_profile: '',
      prescription_preference: '',
      communication_advice: '',
      next_step_suggestion: '',
      risk_alerts: [],
    };
  }
  return {
    ai_available: true,
    ai_unavailable_reason: '',
    academic_profile: typeof ap.academic_profile === 'string' ? ap.academic_profile : '',
    prescription_preference: typeof ap.prescription_preference === 'string' ? ap.prescription_preference : '',
    communication_advice: mapCommunicationAdvice(ap.communication_advice),
    next_step_suggestion: typeof ap.next_step_suggestion === 'string' ? ap.next_step_suggestion : '',
    risk_alerts: mapRiskAlert(ap.risk_alert),
  };
}
```

- [ ] **Step 3: `profile` 方法改类型化返回**

`doctor.ts:133-134` 的 `profile` 方法改为：

```ts
  profile: (id: string) =>
    client.get<ApiResponse<HcpProfile>>(`/hcps/${id}/profile`),
```

（页面侧 `mapProfile(res.data?.data)` 消费；`doctorAPI.profile` 本身不再做映射，与 `list` 一致保持原始返回）

- [ ] **Step 4: 验证 build**

Run: `cd web && npm run build`
Expected: PASS（tsc 无类型错误）

- [ ] **Step 5: 提交**

```bash
git add web/src/types/index.ts web/src/services/doctor.ts
git commit -m "feat(web): doctor.ts 补 AI 画像类型与映射（移植 mobile hcp.ts 降级逻辑）"
```

---

### Task 2: DoctorList 新增医生 ModalForm

**Files:**
- Modify: `web/src/pages/Doctor/DoctorList.tsx`（整体改造，现有 51 行）

**Interfaces:**
- Consumes: `doctorAPI.create(data: Partial<Doctor>)`（doctor.ts:142-143）、`useAuth()`（`web/src/hooks/useAuth`，返回 `{ user }`，`user.role` 为 'admin'|'manager'|'rep'|'compliance'|'medical'|'finance'）
- Produces: 无（UI 完成）

- [ ] **Step 1: 改造 `DoctorList.tsx`**

完整重写（ModalForm 模式照抄 `web/src/pages/User/UserList.tsx`）：

```tsx
import { useRef, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { ProTable, ModalForm, ProFormText, ProFormSelect } from '@ant-design/pro-components';
import type { ProColumns, ActionType } from '@ant-design/pro-components';
import { Button, Tag, Space, App } from 'antd';
import { PlusOutlined } from '@ant-design/icons';
import { doctorAPI } from '../../services/doctor';
import { useAuth } from '../../hooks/useAuth';
import type { Doctor } from '../../types';

export default function DoctorList() {
  const actionRef = useRef<ActionType>();
  const navigate = useNavigate();
  const { message } = App.useApp();
  const [formOpen, setFormOpen] = useState(false);
  const { user: me } = useAuth();
  // 后端 POST /hcps 仅 admin/manager（require_roles），其余角色隐藏新增按钮
  const canWrite = me?.role === 'admin' || me?.role === 'manager';

  const columns: ProColumns<Doctor>[] = [
    { title: '姓名', dataIndex: 'name', width: 100 },
    { title: '医院', dataIndex: 'hospital', width: 180, ellipsis: true },
    { title: '科室', dataIndex: 'department', width: 120 },
    { title: '职称', dataIndex: 'title', width: 100 },
    { title: '标签', dataIndex: 'tags', width: 200,
      render: (_, r) => <Space wrap>{(r.tags ?? []).map((t) => <Tag key={t}>{t}</Tag>)}</Space> },
    { title: '拜访次数', dataIndex: 'visit_count', width: 100,
      render: (_, r) => (r.visit_count != null ? r.visit_count : '--') },
    { title: '满意度', dataIndex: 'satisfaction', width: 100,
      render: (_, r) => (r.satisfaction != null ? `${r.satisfaction}%` : '--') },
    { title: '操作', width: 100,
      render: (_, r) => <a onClick={() => navigate(`/doctor/${r.id}`)}>查看详情</a> },
  ];

  return (
    <>
      <ProTable<Doctor>
        headerTitle="医生管理"
        actionRef={actionRef}
        columns={columns}
        request={async (params) => {
          const res = await doctorAPI.list({
            page: params.current || 1, page_size: params.pageSize || 10,
            keyword: params.keyword, hospital: params.hospital,
            department: params.department, tag: params.tag,
          });
          return { data: res.data.data.items, total: res.data.data.total, success: true };
        }}
        rowKey="id"
        search={{ labelWidth: 80 }}
        toolBarRender={() => canWrite
          ? [<Button key="add" type="primary" icon={<PlusOutlined />} onClick={() => setFormOpen(true)}>新增医生</Button>]
          : []}
      />
      <ModalForm
        key="create"
        title="新增医生"
        open={formOpen}
        onOpenChange={setFormOpen}
        modalProps={{ destroyOnHidden: true }}
        onFinish={async (values) => {
          try {
            // 字段对齐后端白名单 HCP_WRITABLE_FIELDS；空值不提交（后端白名单校验）
            const payload: Partial<Doctor> = {
              name: values.name,
              hospital: values.hospital,
              department: values.department,
              title: values.title,
              specialty: values.specialty,
              phone: values.phone,
              email: values.email,
              region: values.region,
              influence_level: values.influence_level,
            };
            if (Array.isArray(values.tags) && values.tags.length) payload.tags = values.tags;
            await doctorAPI.create(payload);
            message.success('新增成功');
            actionRef.current?.reload();
            return true;
          } catch {
            return false; // 400-499 已由 client.ts 拦截器弹后端 message，保留表单
          }
        }}>
        <ProFormText name="name" label="姓名" rules={[{ required: true }]} placeholder="医生姓名（必填）" />
        <ProFormText name="hospital" label="医院" />
        <ProFormText name="department" label="科室" />
        <ProFormText name="title" label="职称" />
        <ProFormText name="specialty" label="专业方向" />
        <ProFormText name="phone" label="电话" />
        <ProFormText name="email" label="邮箱" />
        <ProFormText name="region" label="区域" />
        <ProFormSelect name="influence_level" label="影响力"
          options={[{ label: '高', value: 'high' }, { label: '中', value: 'medium' }, { label: '低', value: 'low' }]} />
        <ProFormSelect name="tags" label="标签" mode="tags" placeholder="输入后回车添加" />
      </ModalForm>
    </>
  );
}
```

注意：`pro-table` 现有 `Space` import 保留；`useAuth` hook 路径与 UserList.tsx 一致（`../../hooks/useAuth`）。

- [ ] **Step 2: 验证 build**

Run: `cd web && npm run build`
Expected: PASS

- [ ] **Step 3: 手工验证（admin 账号）**

启动后端 8 服务 + web dev，admin 登录 → 医生管理 → 「新增医生」→ 填 name + 部分字段 → 提交 → 列表出现新行。非 admin 账号（rep）登录确认按钮隐藏。
（若环境未起服务，此项记录为待办并在提交信息中注明"手工验证待做"）

- [ ] **Step 4: 提交**

```bash
git add web/src/pages/Doctor/DoctorList.tsx
git commit -m "feat(web): DoctorList 新增医生 ModalForm 真实接线（admin/manager 可见）"
```

---

### Task 3: DoctorDetail AI 画像卡片

**Files:**
- Modify: `web/src/pages/Doctor/DoctorDetail.tsx`（现有 82 行）

**Interfaces:**
- Consumes: `doctorAPI.profile(id)`、`mapProfile(raw)`、`formatProfileField(v: unknown): string`（doctor.ts:55-67，JSONB/字符串 → 展示文本）
- Produces: 无（UI 完成）

- [ ] **Step 1: 改造 `DoctorDetail.tsx`**

现有结构：`PageContainer` + 三个 Card（基本信息 / 学术背景 / 互动历史），数据来自 `Promise.all([doctorAPI.detail(id), doctorAPI.interactions(id)])`。改造：

- 状态：`const [profile, setProfile] = useState<DoctorProfile | null>(null);`、`const [profileLoading, setProfileLoading] = useState(false);`、`const [profileFailed, setProfileFailed] = useState(false);`
- 加载：detail/interactions 的 `Promise.all` 之后追加画像加载（独立 catch，画像失败不拖垮页面）：

```tsx
  useEffect(() => {
    if (!id) return;
    let cancelled = false;
    setProfileLoading(true);
    doctorAPI.profile(id)
      .then((res) => { if (!cancelled) setProfile(mapProfile(res.data?.data)); })
      .catch(() => { if (!cancelled) setProfileFailed(true); })
      .finally(() => { if (!cancelled) setProfileLoading(false); });
    return () => { cancelled = true; };
  }, [id]);
```

- 在「基本信息」Card 之后插入「AI 画像」Card（渲染逻辑）：

```tsx
      <Card title="AI 画像" loading={profileLoading}>
        {profileFailed ? (
          <Empty description="画像生成失败，请稍后重试" />
        ) : profile && !profile.ai_available ? (
          <Alert type="info" showIcon message="AI 画像暂不可用" description={profile.ai_unavailable_reason} />
        ) : profile ? (
          <Descriptions column={1} size="small" labelStyle={{ width: 120 }}>
            <Descriptions.Item label="学术画像">{profile.academic_profile || '—'}</Descriptions.Item>
            <Descriptions.Item label="处方偏好">{profile.prescription_preference || '—'}</Descriptions.Item>
            <Descriptions.Item label="沟通建议">
              <Typography.Paragraph style={{ whiteSpace: 'pre-line', marginBottom: 0 }}>
                {profile.communication_advice || '—'}
              </Typography.Paragraph>
            </Descriptions.Item>
            <Descriptions.Item label="下一步建议">{profile.next_step_suggestion || '—'}</Descriptions.Item>
            <Descriptions.Item label="合规风险">
              {profile.risk_alerts.length
                ? <Space wrap>{profile.risk_alerts.map((r, i) => <Tag key={i} color={r.level === 'high' ? 'red' : r.level === 'medium' ? 'orange' : 'warning'}>{r.description}</Tag>)}</Space>
                : <span style={{ color: '#52c41a' }}>无风险提示</span>}
            </Descriptions.Item>
          </Descriptions>
        ) : null}
      </Card>
```

- 需要的新 import：`useState`/`useEffect`（按现有写法，若文件已 import 则追加）、`Alert`、`Empty`、`Typography`（antd）、`DoctorProfile`、`mapProfile`（`../../services/doctor`）
- 画像接口触发 qwen-max（付费），详情页自动加载合理；页面加载画像失败仅展示占位，不阻塞其余信息

- [ ] **Step 2: 验证 build**

Run: `cd web && npm run build`
Expected: PASS

- [ ] **Step 3: 手工验证**

admin 登录 → 医生管理 → 查看详情 → 「AI 画像」卡片出现（成功态展示 5 字段；LLM 未配置/失败时展示降级提示）。
（若环境未起服务，此项记录为待办）

- [ ] **Step 4: 提交**

```bash
git add web/src/pages/Doctor/DoctorDetail.tsx
git commit -m "feat(web): DoctorDetail 展示 AI 画像（含降级兼容）"
```
