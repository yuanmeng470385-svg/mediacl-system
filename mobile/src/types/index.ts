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
  status: 'active' | 'inactive' | 'configuring';
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

export interface VisitRecord {
  id: number;
  user_id: number;
  hcp_id: number;
  hcp_name?: string;
  product_id: number;
  planned_date: string;
  actual_start_time?: string;
  actual_end_time?: string;
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

export interface ObjectionAlert {
  type: string;
  description: string;
  suggested_response: string;
  severity: 'info' | 'warning' | 'critical';
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
  basic_info: {
    name: string;
    hospital: string;
    department: string;
    title: string;
    region: string;
  };
  academic_profile?: {
    background: string;
    research_interests: string;
    publications?: string[];
  };
  prescription_analysis?: {
    preference: string;
    decision_factors: string[];
  };
  communication_advice?: {
    best_time: string;
    preferred_channels: string[];
    topics_to_avoid: string[];
  };
  compliance_risk?: string[];
}

export interface HCPInteraction {
  id: number;
  visit_date: string;
  product_name: string;
  summary: string;
  outcome: string;
  sentiment: 'positive' | 'neutral' | 'negative';
}

// ========== 合规 ==========
export interface ComplianceRule {
  code: string;
  description: string;
  severity: 'low' | 'medium' | 'high';
  type: 'keyword' | 'regex' | 'llm';
}

// ========== 学术内容 ==========
export interface ContentItem {
  id: number;
  title: string;
  type: 'literature' | 'guideline' | 'manual' | 'news';
  summary: string;
  source: string;
  publish_date: string;
  evidence_level: string;
  file_url?: string;
  tags: string[];
}
