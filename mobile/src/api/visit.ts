/**
 * 陪访助手 API —— 契约映射层
 *
 * 铁律：后端响应形状（snake_case / 键位错位 / 嵌套分页）统一在此映射为屏幕消费形状，
 * 屏幕组件只消费这里的映射结果，不直接碰后端原生字段。
 *
 * 后端契约（visit-service，2026-08-06 收敛后）：
 *  - start_visit            → {id, visit_id, status, start_time}
 *  - process_transcript     → {visit_id, transcript, compliance:{blocked, violations:[{rule_code,rule_name,severity,action,matched_text,reason}]}, objections:{objections:[{type,text}],interests,sentiment,method}, suggestions:{objection_responses:[{objection,response}],compliance_warnings}}
 *  - end_visit / get/list   → record.to_dict()：{id, hcp_id, hcp_name, visit_time, duration_minutes, status(派生),
 *                              conversation_transcript, ai_summary(字符串), key_points, hcp_interests,
 *                              hcp_objections, follow_up_suggestions, sentiment, next_visit_plan, ...}
 *  - follow_up              → {visit_id, follow_up: <AI JSON>, degraded}
 *  - pre-visit              → {hcp_profile: 平铺 hcp 行, recommendations: <AI JSON，键名不稳定/含中文键>}
 */
import { apiClient, APIError } from './client';
import type {
  VisitRecord,
  VisitPrepareData,
  VisitSummary,
  ObjectionAlert,
  ComplianceAlert,
  TranscriptResult,
  FollowUpResult,
  PaginatedResponse,
} from '../types';

// ==================== 内部映射工具 ====================

/** 尝试解析 AI JSON（兼容 ```json 代码块包裹），失败返回 null */
function tryParseJson(text: unknown): any | null {
  if (typeof text !== 'string') return null;
  let trimmed = text.trim();
  if (trimmed.startsWith('```')) {
    trimmed = trimmed.replace(/^```[a-zA-Z]*\s*/, '').replace(/```\s*$/, '').trim();
  }
  try {
    const parsed = JSON.parse(trimmed);
    return parsed && typeof parsed === 'object' ? parsed : null;
  } catch {
    return null;
  }
}

const VALID_SENTIMENTS = ['positive', 'neutral', 'negative'];

/**
 * 把后端 to_dict 的 ai_summary（字符串）解析为 VisitSummary。
 * 结构化字段（key_points/hcp_interests/hcp_objections/next_visit_plan）优先读记录顶层
 * （后端 to_dict 独立列），其次读 ai_summary JSON 内部（兼容 JSON 字符串形态）。
 * ai_summary 解析失败则包成 {summary: str} —— 绝不崩，绝不伪造。
 */
function parseVisitSummary(raw: any): VisitSummary | undefined {
  const aiSummary = raw?.ai_summary;
  if (aiSummary === undefined || aiSummary === null || aiSummary === '') return undefined;

  const parsed = typeof aiSummary === 'object' && aiSummary !== null
    ? aiSummary
    : tryParseJson(aiSummary);

  const topArr = (k: string) => (Array.isArray(raw?.[k]) ? raw[k] : undefined);
  const jsonArr = (k: string) =>
    parsed && typeof parsed === 'object' && Array.isArray(parsed[k]) ? parsed[k] : undefined;
  const keyPoints = topArr('key_points') ?? jsonArr('key_points') ?? [];
  const interests = topArr('hcp_interests') ?? jsonArr('hcp_interests') ?? jsonArr('interests') ?? [];
  const objections = topArr('hcp_objections') ?? jsonArr('hcp_objections') ?? jsonArr('objections') ?? [];

  const nextPlan =
    raw?.next_visit_plan ??
    (parsed && typeof parsed === 'object' ? parsed.next_visit_plan : undefined);
  let nextVisitRecommendation = '';
  if (typeof nextPlan === 'string') {
    nextVisitRecommendation = nextPlan;
  } else if (nextPlan && typeof nextPlan === 'object') {
    const parts: string[] = [];
    if (nextPlan.recommended_time) parts.push(`建议时间：${nextPlan.recommended_time}`);
    if (Array.isArray(nextPlan.recommended_topics) && nextPlan.recommended_topics.length) {
      parts.push(`建议话题：${nextPlan.recommended_topics.join('、')}`);
    }
    if (Array.isArray(nextPlan.materials_to_send) && nextPlan.materials_to_send.length) {
      parts.push(`建议发送：${nextPlan.materials_to_send.join('、')}`);
    }
    nextVisitRecommendation = parts.join('；');
  }

  const sentiment = VALID_SENTIMENTS.includes(raw?.sentiment) ? raw.sentiment : 'neutral';

  return {
    // 纯字符串摘要 → 包成 {summary: str}；JSON 形态取 parsed.summary
    summary: parsed && typeof parsed === 'object'
      ? String(parsed.summary ?? aiSummary)
      : String(aiSummary),
    key_points: keyPoints,
    interests,
    objections,
    sentiment,
    next_visit_recommendation: nextVisitRecommendation,
  };
}

/** 把后端 to_dict 映射为屏幕消费的 VisitRecord（日期/医生名/时长/状态/AI 总结全部在此对齐） */
function mapVisitRecord(raw: any): VisitRecord {
  const id = raw?.id ?? 0;
  const visitTime = raw?.visit_time || raw?.start_time || undefined;
  const duration = raw?.duration_minutes ?? undefined;

  let actualEndTime: string | undefined;
  if (visitTime && typeof duration === 'number' && duration > 0) {
    const d = new Date(visitTime);
    if (!Number.isNaN(d.getTime())) {
      d.setMinutes(d.getMinutes() + duration);
      actualEndTime = d.toISOString();
    }
  }

  const status =
    raw?.status === 'pending' || raw?.status === 'cancelled'
      ? raw.status
      : raw?.status === 'completed' || raw?.ai_summary
        ? 'completed'
        : 'in_progress';

  const followUpPlan = Array.isArray(raw?.follow_up_suggestions)
    ? raw.follow_up_suggestions.filter((x: any) => typeof x === 'string').join('；')
    : typeof raw?.follow_up_suggestions === 'string'
      ? raw.follow_up_suggestions
      : undefined;

  return {
    id,
    hcp_id: raw?.hcp_id ?? 0,
    // hcp_name 暂缺时回退 "医生 #id"，恒为字符串
    hcp_name: String(raw?.hcp_name || `医生 #${raw?.hcp_id ?? id}`),
    product_id: raw?.product_id ?? 0,
    planned_date: visitTime ? String(visitTime).slice(0, 10) : '',
    visit_time: visitTime,
    actual_start_time: visitTime,
    actual_end_time: actualEndTime,
    duration_minutes: duration,
    status,
    transcript: raw?.conversation_transcript || undefined,
    ai_summary: parseVisitSummary(raw),
    follow_up_plan: followUpPlan,
  };
}

/** 后端 to_dict → 拜访总结（endVisit / getById 共用） */
function mapEndResult(raw: any): VisitSummary {
  return (
    parseVisitSummary(raw) ?? {
      summary: '',
      key_points: [],
      interests: [],
      objections: [],
      sentiment: 'neutral',
      next_visit_recommendation: '',
    }
  );
}

/**
 * compliance violations → 合规告警（description 取 matched_text 或 reason）。
 * REST transcript 与 ASR WS compliance 帧共用同一映射，保证同一套告警展示。
 */
export function mapComplianceViolations(violations: unknown): ComplianceAlert[] {
  const list = Array.isArray(violations) ? violations : [];
  return list
    .filter((v): v is Record<string, unknown> => !!v && typeof v === 'object')
    .map((v) => ({
      rule_code: String(v.rule_code ?? ''),
      description: String(
        (v.matched_text as string) || (v.reason as string) || (v.rule_name as string) || '检测到潜在合规风险',
      ),
      severity: v.severity as ComplianceAlert['severity'],
      critical: v.action === 'reject',
    }));
}

/** process_transcript 响应 → 屏幕消费形状（后端 objections 是 {objections:[...]} 对象，compliance 是嵌套对象） */
function mapTranscriptResult(raw: any): TranscriptResult {
  const rawObjections = raw?.objections;
  const objectionList = Array.isArray(rawObjections)
    ? rawObjections
    : Array.isArray(rawObjections?.objections)
      ? rawObjections.objections
      : [];

  // suggestions.objection_responses: [{objection, response}] → 按原文/类型回挂建议话术
  const responseByText = new Map<string, string>();
  const responseByType = new Map<string, string>();
  (raw?.suggestions?.objection_responses ?? []).forEach((s: any) => {
    if (s && typeof s === 'object') {
      if (typeof s.objection === 'string' && s.response) responseByText.set(s.objection, String(s.response));
      if (typeof s.type === 'string' && s.response) responseByType.set(s.type, String(s.response));
    }
  });

  const objections: ObjectionAlert[] = objectionList
    .map((o: any, i: number) => {
      const type = typeof o === 'object' && o ? String(o.type ?? 'other') : 'other';
      const text = typeof o === 'object' && o ? String(o.text ?? '') : String(o ?? '');
      return {
        id: `${type}_${i}`,
        type,
        text,
        description: text,
        suggested_response: responseByText.get(text) ?? responseByType.get(type) ?? undefined,
      };
    })
    .filter((o: ObjectionAlert) => o.text);

  return {
    transcript: String(raw?.transcript ?? ''),
    objections,
    compliance_alerts: mapComplianceViolations(raw?.compliance?.violations),
  };
}

/** follow_up 响应 → {follow_up_plan, suggested_date}（AI JSON 解析失败给空结构，不崩） */
function mapFollowUpResult(raw: any): FollowUpResult {
  try {
    // 后端已把 AI 输出解析为 dict（失败时是 {content: "..."}）；若直接收到字符串则尝试解析，
    // 解析失败按约定给空结构，不崩
    const followUp = typeof raw?.follow_up === 'string'
      ? tryParseJson(raw.follow_up)
      : raw?.follow_up;
    if (!followUp || typeof followUp !== 'object') return { follow_up_plan: '', suggested_date: '' };

    const items = Array.isArray(followUp.follow_up_items) ? followUp.follow_up_items : [];
    const parts: string[] = [];
    let suggestedDate = '';
    items.forEach((item: any) => {
      if (!item || typeof item !== 'object') return;
      if (typeof item.action === 'string' && item.action.trim()) {
        parts.push(item.due ? `${item.action}（${item.due}）` : item.action);
        if (!suggestedDate && typeof item.due === 'string' && /^\d{4}-\d{2}-\d{2}$/.test(item.due)) {
          suggestedDate = item.due;
        }
      }
    });
    if (Array.isArray(followUp.reminders)) {
      followUp.reminders.filter((r: unknown) => typeof r === 'string' && r.trim())
        .forEach((r: string) => parts.push(r));
    }
    if (!parts.length && typeof followUp.content === 'string' && followUp.content.trim()) {
      parts.push(followUp.content);
    }
    return { follow_up_plan: parts.join('；'), suggested_date: suggestedDate };
  } catch {
    return { follow_up_plan: '', suggested_date: '' };
  }
}

/** pre-visit 响应 → VisitPrepareData（平铺 hcp 行包成 basic_info；recommendations 兼容英文键与中文键） */
function mapPrepareResult(raw: any): VisitPrepareData {
  const hcp: any = raw?.hcp_profile ?? {};
  const recs: any = raw?.recommendations ?? {};

  const pick = (...keys: string[]): any => {
    for (const k of keys) {
      const v = recs[k];
      if (v !== undefined && v !== null && v !== '') return v;
    }
    return undefined;
  };
  const toStrings = (v: any): string[] => {
    if (Array.isArray(v)) return v.filter((x) => typeof x === 'string' || typeof x === 'number').map(String);
    if (typeof v === 'string') return v.split(/[、,，;；\n]/).map((s) => s.trim()).filter(Boolean);
    return [];
  };

  const basicInfo =
    hcp?.basic_info && typeof hcp.basic_info === 'object'
      ? hcp.basic_info
      : {
          name: String(hcp?.name ?? ''),
          hospital: String(hcp?.hospital ?? ''),
          department: String(hcp?.department ?? ''),
          title: String(hcp?.title ?? ''),
          region: String(hcp?.region ?? ''),
        };

  // materials 兼容：{title,url}[] / 字符串数组 / 字符串清单（; 或换行分隔）
  let materials: { title: string; url: string }[] = [];
  const rawMaterials = pick('materials', '材料清单', '材料', '资料');
  if (Array.isArray(rawMaterials)) {
    materials = rawMaterials
      .map((m) => {
        if (m && typeof m === 'object') {
          return { title: String(m.title ?? m.name ?? ''), url: String(m.url ?? '') };
        }
        if (typeof m === 'string' && m.trim()) return { title: m.trim(), url: '' };
        return null;
      })
      .filter((m): m is { title: string; url: string } => !!m && m.title.length > 0);
  } else if (typeof rawMaterials === 'string') {
    materials = rawMaterials.split(/[;；\n]/).map((s) => s.trim()).filter(Boolean)
      .map((t) => ({ title: t, url: '' }));
  }

  return {
    hcp_profile: {
      basic_info: basicInfo,
    },
    recommendations: {
      suggested_topics: toStrings(pick('suggested_topics', '推荐话题', 'topics')),
      red_lines: toStrings(pick('red_lines', '红线提醒', 'red_line', '红线', '合规红线')),
      opening_remarks: String(pick('opening_remarks', '开场白建议', '开场白', 'opening_remark') ?? ''),
      materials,
      last_follow_up: String(pick('last_follow_up', '上次未完成的跟进项', '上次跟进', 'last_followup') ?? ''),
    },
  };
}

// ==================== API ====================

export const visitAPI = {
  /** 拜访前准备——获取准备包（后端回平铺 hcp 行 + 不稳定 AI 键，映射为屏幕形状） */
  async prepareVisit(params: {
    hcpId: number;
    productId?: number;
  }): Promise<VisitPrepareData> {
    const raw = await apiClient.request<any>(
      'POST',
      '/api/v1/visits/pre-visit',
      { hcp_id: params.hcpId, product_id: params.productId },
    );
    return mapPrepareResult(raw);
  },

  /**
   * 开始拜访——创建拜访记录。
   * 后端返回 {id, visit_id, status, start_time}：取 visit_id，无则回退 id，
   * 保证 VisitInProgress 的 navigation 参数 visitId 不再是 undefined。
   */
  async startVisit(data: {
    hcp_id: number;
    product_id: number;
    planned_date: string;
    notes?: string;
  }): Promise<{ visit_id: number; status?: string; start_time?: string }> {
    const raw = await apiClient.request<any>(
      'POST',
      '/api/v1/visits/start',
      data
    );
    const visitId = raw?.visit_id ?? raw?.id;
    if (typeof visitId !== 'number' || Number.isNaN(visitId)) {
      throw new APIError('开始拜访失败：服务未返回拜访 ID', 5000);
    }
    return {
      visit_id: visitId,
      status: raw?.status,
      start_time: raw?.start_time ?? raw?.visit_time,
    };
  },

  /** 上传转写文本（实时转写）——把后端的 compliance/objections 键位映射为屏幕消费形状 */
  async sendTranscript(
    visitId: number,
    data: {
      text?: string;
      audio_url?: string;
    }
  ): Promise<TranscriptResult> {
    const raw = await apiClient.request<any>(
      'POST',
      `/api/v1/visits/${visitId}/transcript`,
      data
    );
    return mapTranscriptResult(raw);
  },

  /** 结束拜访——生成总结（后端返回 record.to_dict()，映射为 VisitSummary） */
  async endVisit(visitId: number): Promise<VisitSummary> {
    const raw = await apiClient.request<any>(
      'POST',
      `/api/v1/visits/${visitId}/end`
    );
    return mapEndResult(raw);
  },

  /** 获取拜访详情 */
  async getById(visitId: number): Promise<VisitRecord> {
    const raw = await apiClient.request<any>(
      'GET',
      `/api/v1/visits/${visitId}`
    );
    return mapVisitRecord(raw);
  },

  /** 拜访列表（解包后端 pagination 嵌套，映射 items） */
  async list(params?: {
    page?: number;
    page_size?: number;
    status?: string;
    hcp_id?: number;
    date_from?: string;
    date_to?: string;
  }): Promise<PaginatedResponse<VisitRecord>> {
    const raw = await apiClient.request<any>(
      'GET',
      '/api/v1/visits',
      params
    );
    const items = Array.isArray(raw?.items) ? raw.items : [];
    const pagination = raw?.pagination ?? {};
    return {
      items: items.map(mapVisitRecord),
      total: raw?.total ?? pagination?.total ?? items.length,
      page: raw?.page ?? pagination?.page ?? 1,
      page_size: raw?.page_size ?? pagination?.page_size ?? items.length,
    };
  },

  /** 生成跟进建议（后端 {visit_id, follow_up: AI JSON, degraded} → 解析为 {follow_up_plan, suggested_date}） */
  async followUp(visitId: number): Promise<FollowUpResult> {
    const raw = await apiClient.request<any>(
      'POST',
      `/api/v1/visits/${visitId}/follow-up`
    );
    return mapFollowUpResult(raw);
  },
};
