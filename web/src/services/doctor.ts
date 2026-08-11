/**
 * 医生管理 API —— 契约映射层
 *
 * 铁律：后端响应形状（snake_case / 键位错位 / 嵌套包装）统一在此映射为页面消费形状，
 * 页面组件只消费这里的映射结果，不直接碰后端原生字段。
 *
 * 后端契约（hcp-service，2026-08-06 收敛后）：
 *  - GET /hcps/{id}           → Hcp.to_dict()：academic_background / prescription_preference（JSONB，字符串或对象）
 *  - GET /hcps/{id}/interactions → 裸数组，元素含 visit_time / ai_summary / key_points 等
 */
import client from './client';
import type { ApiResponse, PaginatedResponse, Doctor } from '../types';

/** 医生详情（映射自后端 /hcps/{id} to_dict） */
export interface DoctorDetail {
  id: string;
  name: string;
  hospital: string;
  department: string;
  title: string;
  specialty?: string;
  phone?: string;
  email?: string;
  region?: string;
  status?: string;
  influence_level?: string;
  /** JSONB：字符串或 {background/summary/...} 对象 */
  academic_background?: unknown;
  /** JSONB：字符串或 {preference/summary/...} 对象 */
  prescription_preference?: unknown;
  tags?: string[];
  created_at?: string;
  updated_at?: string;
  /** 后端无此字段（列表页保留展示位，空值显示 "--"） */
  visit_count?: number;
  /** 后端无此字段（列表页保留展示位，空值显示 "--"） */
  satisfaction?: number;
}

/** 互动历史记录（visit_records 只读视图字段） */
export interface DoctorInteraction {
  id: number;
  visit_time?: string;
  duration_minutes?: number | null;
  sentiment?: string | null;
  ai_summary?: string | null;
  key_points?: string[] | null;
  interests?: string[] | null;
  objections?: string[] | null;
  follow_up_suggestions?: string | null;
  next_visit_plan?: string | null;
}

/** JSONB/文本 字段（academic_background / prescription_preference）→ 展示文本，空值返回 '' */
export function formatProfileField(v: unknown): string {
  if (v === null || v === undefined) return '';
  if (typeof v === 'string') return v.trim();
  if (Array.isArray(v)) return v.filter((x): x is string => typeof x === 'string').join('、');
  if (typeof v === 'object') {
    const o = v as Record<string, unknown>;
    for (const k of ['background', 'summary', 'content', 'description', 'text', 'preference']) {
      if (typeof o[k] === 'string' && (o[k] as string).trim()) return (o[k] as string).trim();
    }
    return JSON.stringify(o);
  }
  return String(v);
}

/** ISO/带空格时间 → "YYYY-MM-DD HH:mm"（空值回退 ''） */
export function formatVisitTime(v?: string | null): string {
  if (!v) return '';
  const s = String(v).replace('T', ' ');
  return s.length > 16 ? s.slice(0, 16) : s;
}

function mapInteraction(raw: any): DoctorInteraction {
  return {
    id: typeof raw?.id === 'number' ? raw.id : 0,
    visit_time: typeof raw?.visit_time === 'string' ? raw.visit_time : undefined,
    duration_minutes: raw?.duration_minutes ?? null,
    sentiment: typeof raw?.sentiment === 'string' ? raw.sentiment : null,
    ai_summary: typeof raw?.ai_summary === 'string' ? raw.ai_summary : null,
    key_points: Array.isArray(raw?.key_points) ? raw.key_points : null,
    interests: Array.isArray(raw?.interests) ? raw.interests : null,
    objections: Array.isArray(raw?.objections) ? raw.objections : null,
    follow_up_suggestions:
      typeof raw?.follow_up_suggestions === 'string' ? raw.follow_up_suggestions : null,
    next_visit_plan: typeof raw?.next_visit_plan === 'string' ? raw.next_visit_plan : null,
  };
}

/** 互动历史：后端裸数组；防御旧 {items:[...]} 形状（兼容解包） */
export function mapInteractions(raw: unknown): DoctorInteraction[] {
  if (Array.isArray(raw)) return raw.map(mapInteraction);
  if (raw && typeof raw === 'object' && Array.isArray((raw as { items?: unknown[] }).items)) {
    return ((raw as { items: unknown[] }).items).map(mapInteraction);
  }
  return [];
}

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

function mapDoctorDetail(raw: any): DoctorDetail {
  if (!raw || typeof raw !== 'object') return {} as DoctorDetail;
  return {
    id: String(raw.id ?? ''),
    name: String(raw.name ?? ''),
    hospital: String(raw.hospital ?? ''),
    department: String(raw.department ?? ''),
    title: String(raw.title ?? ''),
    specialty: raw.specialty ? String(raw.specialty) : undefined,
    phone: raw.phone ? String(raw.phone) : undefined,
    email: raw.email ? String(raw.email) : undefined,
    region: raw.region ? String(raw.region) : undefined,
    status: raw.status ? String(raw.status) : undefined,
    influence_level: raw.influence_level ? String(raw.influence_level) : undefined,
    academic_background: raw.academic_background ?? undefined,
    prescription_preference: raw.prescription_preference ?? undefined,
    tags: Array.isArray(raw.tags) ? raw.tags.map(String) : undefined,
    created_at: raw.created_at ? String(raw.created_at) : undefined,
    updated_at: raw.updated_at ? String(raw.updated_at) : undefined,
  };
}

export const doctorAPI = {
  list: (params?: { page?: number; page_size?: number; keyword?: string; hospital?: string; department?: string; tag?: string }) =>
    client.get<PaginatedResponse<Doctor>>('/hcps', { params }),

  detail: (id: string) =>
    client.get<ApiResponse<DoctorDetail>>(`/hcps/${id}`).then((res) => ({
      ...res,
      data: { ...res.data, data: mapDoctorDetail(res.data?.data) },
    })),

  profile: (id: string) =>
    client.get<ApiResponse<{ data: HcpProfile }>>(`/hcps/${id}/profile`),

  interactions: (id: string) =>
    client.get<ApiResponse<unknown>>(`/hcps/${id}/interactions`).then((res) => ({
      ...res,
      data: { ...res.data, data: mapInteractions(res.data?.data) },
    })),

  create: (data: Partial<Doctor>) =>
    client.post<ApiResponse<Doctor>>('/hcps', data),

  update: (id: string, data: Partial<Doctor>) =>
    client.put<ApiResponse<Doctor>>(`/hcps/${id}`, data),

  addTag: (id: string, tag: string) =>
    client.post<ApiResponse<null>>(`/hcps/${id}/tags`, { tag }),

  removeTag: (id: string, tag: string) =>
    client.delete<ApiResponse<null>>(`/hcps/${id}/tags`, { data: { tag } }),
};
