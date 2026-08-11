/**
 * MedAgent 移动端 - 全局类型定义
 */

// ========== 通用 ==========
export interface PaginatedResponse<T> {
  items: T[];
  total: number;
  page: number;
  page_size: number;
}

export interface ApiResponse<T> {
  code: number;
  message: string;
  data: T;
}

// ========== 用户 & 认证 ==========
export interface User {
  id: number;
  name: string;
  phone: string;
  role: string;
  department: string;
  region: string;
  avatar?: string;
}

export interface LoginResponse {
  token: string;
  user: User;
}

// ========== 数字专员 ==========
export interface DigitalSpecialist {
  id: number;
  name: string;
  product_id: number;
  product_name?: string;
  persona: string;
  knowledge_scope: string;
  compliance_level: string;
  bailian_app_id?: string;
  prompt_version: string;
  /** 后端枚举（specialists.py VALID_STATUSES）：draft=草稿 / active=正常 / disabled=已停用 */
  status: 'draft' | 'active' | 'disabled';
  avatar_color?: string;
}

export interface ChatRequest {
  question: string;
  session_id?: string;
}

export interface Citation {
  title: string;
  url?: string;
  content?: string;
}

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

export interface ConversationMessage {
  id: string;
  role: 'user' | 'assistant';
  content: string;
  citations?: Citation[];
  evidence_level?: string;
  timestamp: string;
}

// ========== 拜访 ==========
export type VisitStatus = 'pending' | 'in_progress' | 'completed' | 'cancelled';

/**
 * 拜访记录 —— api 层映射后的屏幕消费形状（屏幕只读这里的字段）。
 * 后端 to_dict 原生字段（visit_time / duration_minutes / ai_summary(字符串) /
 * key_points / hcp_interests / hcp_objections / sentiment / next_visit_plan / status 派生）
 * 统一由 src/api/visit.ts 映射为以下形状，hcp_name 缺省回退 "医生 #id"。
 */
export interface VisitRecord {
  id: number;
  hcp_id: number;
  /** 医生名（映射层已做回退，恒为字符串） */
  hcp_name: string;
  product_id: number;
  /** 拜访日期 YYYY-MM-DD（取自 visit_time） */
  planned_date: string;
  /** 完整开始时间（取自 visit_time，ISO 字符串） */
  visit_time?: string;
  actual_start_time?: string;
  /** 由 visit_time + duration_minutes 推算 */
  actual_end_time?: string;
  duration_minutes?: number;
  status: VisitStatus;
  transcript?: string;
  ai_summary?: VisitSummary;
  compliance_issues?: ComplianceIssue[];
  follow_up_plan?: string;
}

export interface VisitSummary {
  summary: string;
  key_points: string[];
  interests: string[];
  objections: string[];
  sentiment: 'positive' | 'neutral' | 'negative';
  next_visit_recommendation: string;
}

/** 合规告警 —— 映射自后端 compliance.violations（{rule_code, rule_name, severity, action, matched_text, reason}） */
export interface ComplianceAlert {
  rule_code: string;
  /** 优先取 matched_text，其次 reason */
  description: string;
  severity?: 'low' | 'medium' | 'high';
  /** action=reject 的规则即合规红线（触发红线弹窗） */
  critical?: boolean;
}

/** LLM 实时推荐：关键节点标记（服务端 visit_records.key_nodes 元素） */
export interface KeyNode {
  type: 'decision_point' | 'interest_point';
  label: string;
  quote: string;
}

/** LLM 实时推荐：话术建议 */
export interface AiSuggestion {
  topic: string;
  advice: string;
}

/** sendTranscript 的映射结果 —— 屏幕消费形状（后端 objection/compliance 键位错位在此抹平） */
export interface TranscriptResult {
  transcript: string;
  objections: ObjectionAlert[];
  compliance_alerts: ComplianceAlert[];
  key_nodes: KeyNode[];
  ai_suggestion: AiSuggestion | null;
}

export interface FollowUpResult {
  follow_up_plan: string;
  suggested_date: string;
}

export interface ComplianceIssue {
  rule_code: string;
  description: string;
  severity: 'low' | 'medium' | 'high';
  snippet: string;
}

export interface VisitPrepareData {
  hcp_profile: HCPProfile;
  recommendations: {
    suggested_topics: string[];
    red_lines: string[];
    opening_remarks: string;
    materials: { title: string; url: string }[];
    last_follow_up: string;
  };
}

/** 异议提醒 —— 映射自后端 objections.objections（[{type, text}]）+ suggestions.objection_responses */
export interface ObjectionAlert {
  id: string;
  type: string;
  text: string;
  description: string;
  suggested_response?: string;
}

// ========== 医生 ==========
export interface HCP {
  id: number;
  name: string;
  hospital: string;
  department: string;
  title: string;
  region: string;
  status: 'active' | 'inactive';
  phone?: string;
  email?: string;
  academic_background?: string;
  research_interests?: string;
  prescription_preference?: string;
  influence_level?: 'high' | 'medium' | 'low';
  tags: string[];
  avatar?: string;
}

export interface HCPProfile {
  /** 基础档案（后端 profile 响应顶层 hcp 平铺字段映射而来） */
  basic_info?: {
    name: string;
    hospital: string;
    department: string;
    title: string;
    region: string;
  };
  /** 学术背景（ai_profile.academic_profile 字符串 → {background, research_interests}） */
  academic_profile?: {
    background: string;
    research_interests: string[];
  } | null;
  /** 处方偏好（ai_profile.prescription_preference 字符串 → {preference, decision_factors}） */
  prescription_analysis?: {
    preference: string;
    decision_factors: string[];
  } | null;
  communication_advice?: {
    /** LLM 返回纯文本时原样展示 */
    raw_text?: string;
    best_time?: string;
    preferred_channels?: string[];
    topics_to_avoid?: string[];
  } | null;
  /** 合规风险（ai_profile.risk_alert 派生 [{level, description}]） */
  compliance_risk?: { level: string; description: string }[] | null;
  /** 下一步跟进建议 */
  next_step_suggestion?: string;
  /** AI 画像是否可用（ai_profile 为 null / 降级形状时为 false） */
  ai_available?: boolean;
  /** 画像不可用时的说明（降级原因/提示） */
  ai_unavailable_reason?: string;
  /** 画像来源 */
  source?: string;
}

export interface HCPInteraction {
  id: number;
  /** 拜访时间（后端 visit_time ISO 字符串映射而来） */
  visit_date: string;
  duration_minutes?: number;
  /** 拜访摘要（后端 ai_summary 映射而来） */
  summary: string;
  /** 关键点（后端 key_points） */
  key_points?: string[];
  interests?: string[];
  objections?: string[];
  follow_up_suggestions?: string;
  next_visit_plan?: string;
  sentiment?: string;
}

// ========== 合规 ==========
export interface ComplianceRule {
  id: number;
  rule_code: string;
  rule_name: string;
  rule_type: 'keyword' | 'regex' | 'semantic';
  severity: 'low' | 'medium' | 'high';
  action: string;
  description: string;
  enabled: boolean;
  version: number;
}

// ========== 学术内容 ==========
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
