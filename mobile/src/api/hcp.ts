/**
 * 医生管理 API —— 契约映射层
 *
 * 铁律：后端响应形状（snake_case / 键位错位 / 嵌套包装）统一在此映射为屏幕消费形状，
 * 屏幕组件只消费这里的映射结果，不直接碰后端原生字段。
 *
 * 后端契约（hcp-service，2026-08-06 收敛后）：
 *  - GET /hcps/{id}/interactions → 裸数组，元素含 visit_time / ai_summary / key_points 等
 *  - GET /hcps/{id}/profile      → {hcp, ai_profile: {academic_profile(字符串), prescription_preference(字符串),
 *                                    communication_advice, next_step_suggestion, risk_alert}, source}
 *    ai_profile 为 null 或降级形状 {summary, base_info} 时表示画像未生成/不可用。
 */
import { apiClient } from './client';
import type {
  HCP,
  HCPProfile,
  HCPInteraction,
  PaginatedResponse,
} from '../types';

// ==================== 后端原生形状（勿直接给屏幕用） ====================

/** 互动记录原始形状（visit_records 只读视图） */
interface RawInteraction {
  id?: number;
  visit_time?: string | null;
  duration_minutes?: number | null;
  sentiment?: string | null;
  ai_summary?: string | null;
  key_points?: string[] | null;
  interests?: string[] | null;
  objections?: string[] | null;
  follow_up_suggestions?: string | null;
  next_visit_plan?: string | null;
}

/** 画像原始形状：{hcp, ai_profile, source}（降级时 ai_profile 为 null 或 {summary, base_info}） */
interface RawHCPProfile {
  hcp?: HCP | null;
  ai_profile?: {
    academic_profile?: unknown;
    prescription_preference?: unknown;
    communication_advice?: unknown;
    next_step_suggestion?: unknown;
    risk_alert?: unknown;
    /** 降级形状标记 */
    base_info?: unknown;
    summary?: unknown;
  } | null;
  source?: string;
  degraded?: boolean;
  reason?: string;
}

// ==================== 内部映射工具 ====================

function toStringList(v: unknown): string[] {
  if (Array.isArray(v)) return v.filter((x): x is string => typeof x === 'string');
  if (typeof v === 'string' && v.trim()) return [v.trim()];
  return [];
}

/** 后端互动记录 → 屏幕消费形状（visit_time → visit_date，ai_summary → summary） */
function mapInteraction(raw: RawInteraction): HCPInteraction {
  return {
    id: raw?.id ?? 0,
    visit_date: raw?.visit_time ?? '',
    duration_minutes: raw?.duration_minutes ?? undefined,
    summary: raw?.ai_summary ?? '',
    key_points: Array.isArray(raw?.key_points) ? raw.key_points : undefined,
    interests: Array.isArray(raw?.interests) ? raw.interests : undefined,
    objections: Array.isArray(raw?.objections) ? raw.objections : undefined,
    follow_up_suggestions:
      typeof raw?.follow_up_suggestions === 'string' ? raw.follow_up_suggestions : undefined,
    next_visit_plan: typeof raw?.next_visit_plan === 'string' ? raw.next_visit_plan : undefined,
    sentiment: raw?.sentiment ?? undefined,
  };
}

/** 沟通建议：对象原样归一，纯文本原样透出 */
function mapCommunication(advice: unknown): HCPProfile['communication_advice'] {
  if (typeof advice === 'string' && advice.trim()) {
    return { raw_text: advice.trim() };
  }
  if (!advice || typeof advice !== 'object') return null;
  const o = advice as Record<string, unknown>;
  const bestTime = typeof o.best_time === 'string' ? o.best_time : undefined;
  const channels = toStringList(o.preferred_channels);
  const avoid = toStringList(o.topics_to_avoid);
  return bestTime || channels.length || avoid.length
    ? { best_time: bestTime, preferred_channels: channels, topics_to_avoid: avoid }
    : null;
}

/** 合规风险：risk_alert（字符串/数组）→ [{level, description}]，"无"视为无风险 */
function mapRiskAlert(alert: unknown): HCPProfile['compliance_risk'] {
  if (typeof alert === 'string') {
    const t = alert.trim();
    if (t && t !== '无' && t !== '无风险') return [{ level: 'high', description: t }];
    return null;
  }
  if (Array.isArray(alert)) {
    const items = alert.filter(
      (x): x is string => typeof x === 'string' && x.trim() !== '' && x.trim() !== '无'
    );
    return items.length ? items.map((x) => ({ level: 'high', description: x })) : null;
  }
  return null;
}

/** 后端画像响应 → 屏幕消费形状（academic/prescription 字符串展开，risk_alert 派生合规风险） */
function mapProfile(raw: RawHCPProfile): HCPProfile {
  const ap = raw?.ai_profile ?? null;
  // 画像未生成/降级：ai_profile 为 null，或降级形状 {summary, base_info}
  const degraded = !ap || typeof ap !== 'object' || 'base_info' in ap;

  const basicInfo = raw?.hcp
    ? {
        name: raw.hcp.name ?? '',
        hospital: raw.hcp.hospital ?? '',
        department: raw.hcp.department ?? '',
        title: raw.hcp.title ?? '',
        region: raw.hcp.region ?? '',
      }
    : undefined;

  if (degraded) {
    return {
      basic_info: basicInfo,
      academic_profile: null,
      prescription_analysis: null,
      communication_advice: null,
      compliance_risk: null,
      ai_available: false,
      ai_unavailable_reason:
        typeof ap?.summary === 'string' && ap.summary
          ? ap.summary
          : raw?.reason || 'AI 画像暂不可用',
      source: raw?.source,
    };
  }

  const academic = typeof ap.academic_profile === 'string' ? ap.academic_profile.trim() : '';
  const prescription =
    typeof ap.prescription_preference === 'string' ? ap.prescription_preference.trim() : '';

  return {
    basic_info: basicInfo,
    academic_profile: academic ? { background: academic, research_interests: [] } : null,
    prescription_analysis: prescription ? { preference: prescription, decision_factors: [] } : null,
    communication_advice: mapCommunication(ap.communication_advice),
    compliance_risk: mapRiskAlert(ap.risk_alert),
    next_step_suggestion:
      typeof ap.next_step_suggestion === 'string' ? ap.next_step_suggestion : undefined,
    ai_available: true,
    source: raw?.source,
  };
}

// ==================== API ====================

export const hcpAPI = {
  /** 医生列表（分页 + 多维度筛选） */
  async list(params?: {
    page?: number;
    page_size?: number;
    name?: string;
    hospital?: string;
    department?: string;
    title?: string;
    region?: string;
    status?: string;
    tag?: string;
  }): Promise<PaginatedResponse<HCP>> {
    return apiClient.request<PaginatedResponse<HCP>>(
      'GET',
      '/api/v1/hcps',
      params
    );
  },

  /** 医生详情 */
  async getById(id: number): Promise<HCP> {
    return apiClient.request<HCP>('GET', `/api/v1/hcps/${id}`);
  },

  /** 医生画像（映射 ai_profile 为屏幕消费形状；null/降级 → ai_available=false） */
  async getProfile(id: number): Promise<HCPProfile> {
    const raw = await apiClient.request<RawHCPProfile>(
      'GET',
      `/api/v1/hcps/${id}/profile`
    );
    return mapProfile(raw ?? {});
  },

  /**
   * 互动历史（映射 visit_time/ai_summary 等字段）。
   * 后端返回裸数组；防御旧 {items:[...]} 形状（兼容解包）。
   */
  async getInteractions(id: number): Promise<HCPInteraction[]> {
    const raw = await apiClient.request<HCPInteraction[] | { items?: HCPInteraction[] }>(
      'GET',
      `/api/v1/hcps/${id}/interactions`
    );
    const list = Array.isArray(raw) ? raw : Array.isArray(raw?.items) ? raw.items : [];
    return (list as RawInteraction[]).map(mapInteraction);
  },

  // create/update 已删除（2026-08-13 低危批 G3）：无调用方，且传 Partial<HCP>
  // 会带 id/ai_profile 等后端白名单之外的键，直接撞 hcp-service 400。
  // TODO：后续需要医生录入功能时，按后端白名单字段单独定义请求形状。

  /** 添加标签 */
  async addTags(id: number, tags: string[]): Promise<void> {
    return apiClient.request(
      'POST',
      `/api/v1/hcps/${id}/tags`,
      { tags }
    );
  },

  /** 删除标签 */
  async removeTags(id: number, tags: string[]): Promise<void> {
    return apiClient.request(
      'DELETE',
      `/api/v1/hcps/${id}/tags`,
      { tags }
    );
  },
};
