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
// 与后端 specialists.py to_dict() 对齐（product_id 而非 product；无 style/daily_usage/satisfaction）
export interface Specialist {
  id: number;
  name: string;
  product_id: number | null;
  persona?: unknown;
  knowledge_scope?: unknown;
  compliance_level?: string;
  bailian_app_id?: string | null;
  status: 'draft' | 'active' | 'disabled';
  created_at: string;
}

/** 专员使用统计（GET /specialists/{id}/stats 对齐后字段；satisfaction_rate 为 0-100 百分数） */
export interface SpecialistStats {
  total_conversations: number;
  total_feedback: number;
  satisfaction_rate: number | null;
}

// ========== 数字员工办公室（live-status）==========
export type SpecialistLiveState = 'working' | 'idle' | 'offline';
export type SpecialistPhase = 'compliance_precheck' | 'generating' | 'compliance_review';

/** 与后端 GET /specialists/live-status 对齐 */
export interface LiveStatusItem {
  id: number;
  name: string;
  lifecycle: 'draft' | 'active' | 'disabled';
  state: SpecialistLiveState;
  phase: SpecialistPhase | null;
  phase_text: string | null;
  phase_since: string | null;
  question_snippet: string | null;
  today_conversations: number;
  last_active_at: string | null;
}

export interface LiveSummary {
  working: number;
  idle: number;
  offline: number;
}

export interface LiveStatus {
  items: LiveStatusItem[];
  summary: LiveSummary;
}

// ========== 知识文档 ==========
export type KnowledgeDocType = 'product' | 'guideline' | 'literature' | 'regulation' | 'competitor' | 'other';
export type KnowledgeDocStatus = 'draft' | 'processing' | 'ready' | 'rejected' | 'archived';

export interface KnowledgeDoc {
  id: string;
  title: string;
  doc_type: KnowledgeDocType;
  source: string | null;
  content: string | null;
  file_url: string | null;
  product_id: number | null;
  evidence_level: string | null;
  publish_date: string | null;
  version: string | null;
  status: KnowledgeDocStatus;
  reviewer_id: number | null;
  review_date: string | null;
  tags: string[] | null;
  revision: number;
  parent_doc_id: number | null;
  created_at: string | null;
  updated_at: string | null;
}

export interface KnowledgeStats {
  total: number;
  by_status: Record<string, number>;
  workspace_id?: string | null;
  knowledge_base_id?: string | null;
  app_id?: string | null;
}

// ========== 合规规则 ==========
export interface ComplianceRule {
  id: number;
  rule_code: string;
  rule_name: string;
  rule_type: 'keyword' | 'regex' | 'semantic';
  content: { patterns: string[] };
  severity: 'high' | 'medium' | 'low';
  action: 'reject' | 'warn' | 'log';
  description: string;
  enabled: boolean;
  version: number;
}

export interface ComplianceStats {
  total_rules: number;
  enabled_rules: number;
  loaded_memory_rules: number;
}

export interface RuleTestHit {
  rule_code: string;
  rule_name: string;
  rule_type: 'keyword' | 'regex' | 'semantic';
  severity: 'high' | 'medium' | 'low';
  action: 'reject' | 'warn' | 'log';
  hit: boolean;
  matched_text: string | null;
}

export interface RuleTestResult {
  content: string;
  hits: RuleTestHit[];
  total_rules_tested: number;
}

// ========== 合规拦截记录 ==========
// 字段与 compliance-service list_blocks / block_detail 对齐
export interface ComplianceBlock {
  id: number;
  user_id: number | null;
  service_name: string;
  content: string;
  rule_code: string;
  rule_name: string;
  severity: string;
  action: string;
  blocked_at: string | null;
  /** 详情接口独有：完整上下文（列表接口不含） */
  context?: Record<string, unknown> | null;
}

/** 热力图聚合点：区域（或降级维度 service）× 日期 */
export interface BlocksHeatmapPoint {
  region: string;
  date: string;
  count: number;
}

export interface BlocksHeatmapStats {
  /** region = join users 表取区域；service = users 不可达时按 service_name 兜底 */
  dimension: 'region' | 'service';
  days: number;
  items: BlocksHeatmapPoint[];
}

// ========== 审计日志 ==========
// 字段与 audit-service `_log_to_dict` 对齐
export interface AuditLog {
  id: string;
  timestamp: string;
  service_name: string;
  user_id: string;
  action: string;
  resource_type?: string;
  resource_id?: string;
  ai_involved?: boolean;
  ai_model?: string;
  ai_prompt_hash?: string;
  ai_response_hash?: string;
  compliance_result?: Record<string, unknown> | null;
  risk_level?: 'high' | 'medium' | 'low' | null;
  client_ip?: string;
  request_id?: string;
}

// ========== 医生 ==========
// 注：visit_count/satisfaction 后端 hcps 表无此字段（2026-08-12 已从列表页删除幻影列），
// 互动/画像数据在 DoctorDetail 展示
export interface Doctor {
  id: string;
  name: string;
  hospital: string;
  department: string;
  title: string;
  phone: string;
  tags: string[];
  specialty?: string;
  email?: string;
  region?: string;
  status?: string;
  influence_level?: 'high' | 'medium' | 'low' | string;
}

// ========== 用户 ==========
// 字段与 auth-service `User.to_dict` 对齐（full_name 后端白名单字段）
export interface User {
  id: string;
  username: string;
  full_name: string;
  /** 后端 to_dict 兼容字段（= full_name），AdminLayout 等处仍在使用 */
  name?: string;
  phone: string;
  email?: string;
  role: 'admin' | 'manager' | 'rep' | 'compliance' | 'medical' | 'finance';
  region: string;
  status: 'active' | 'disabled';
}

// ========== 备案与资质 ==========
// 字段与 auth-service RepresentativeQualification.to_dict 对齐（列表项另含 rep_name/rep_phone）
export interface Qualification {
  id: string;
  representative_id: string;
  education_cert: string;
  training_cert?: string;
  audit_status: 'pending' | 'approved' | 'rejected';
  filing_number?: string;
  filing_status: 'not_filed' | 'valid' | 'expired';
  filing_expire_date?: string;
  days_until_expiry?: number | null;
  reject_reason?: string;
  reviewed_by?: number;
  reviewed_at?: string;
  rep_name?: string;
  rep_phone?: string;
  compliance_training_completed: boolean;
  commitment_signed: boolean;
}

// ========== 医生资质审核 ==========
// 字段与 auth-service DoctorCertification.to_dict 对齐（列表项另含 doctor_name/doctor_phone）
export interface DoctorCert {
  id: number;
  doctor_id: number;
  doctor_name?: string;
  doctor_phone?: string;
  cert_type: 'physician' | 'practice';
  cert_image_url: string;
  cert_status: 'pending' | 'approved' | 'rejected';
  reject_reason?: string | null;
  reviewed_by?: number | null;
  reviewed_at?: string | null;
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
  name: string;
  status: 'up' | 'down';
}

// ========== 合规培训考试 ==========
// 字段与 auth-service TrainingMaterial.to_dict 对齐
export interface TrainingMaterial {
  id: number;
  title: string;
  material_type: 'regulation' | 'rdpac' | 'internal';
  content: string;
  version: string;
  status: string;
  created_at: string | null;
  updated_at: string | null;
}

// 字段与 auth-service ExamQuestion.to_dict 对齐（列表默认不返回 answer，仅 AI 草稿预览用）
export interface ExamQuestion {
  id: number;
  material_id: number | null;
  question_type: 'single' | 'multiple' | 'judge';
  content: string;
  options: string[];
  answer?: number[];
  review_status: 'pending' | 'approved' | 'rejected';
  review_reason: string | null;
  created_at: string | null;
}

// 字段与 auth-service ExamRecord.to_dict 对齐
export interface ExamRecord {
  id: number;
  representative_id: number;
  question_count: number;
  correct_count: number;
  score: number;
  passed: boolean;
  submitted_at: string | null;
}

// ========== 合规风控看板（二期 E）==========
// 字段与 compliance-service daily-summary / trends / review-queue 对齐
export interface ComplianceDailySummary {
  total: number;
  by_rule: { rule_code: string; count: number }[];
  by_action: { action: string; count: number }[];
  by_day: { date: string; count: number }[];
  days: number;
}

export interface ComplianceTrends {
  time_series: { date: string; count: number }[];
  rep_ranking: { user_id: number; rep_name: string; count: number }[];
  rule_frequency: { rule_code: string; rule_name: string; count: number }[];
}

export interface ReviewQueueItem {
  specialist_id: number;
  name: string;
  rep_name: string | null;
  block_count: number;
  window_hours: number;
  threshold: number;
}

// 字段与 conversations-service search 对齐
export interface ConvSearchItem {
  id: number;
  user_id: number;
  specialist_id: number;
  session_id: string;
  role: string;
  content: string;
  blocked: boolean;
  created_at: string | null;
  context: { role: string; content: string; blocked: boolean }[];
}

// 字段与 specialist-service /specialists/monitor 对齐（avg_latency_ms 后端可能为 null）
export interface SpecialistMonitor {
  id: number;
  name: string;
  status: string;
  is_official: boolean;
  representative_id: number | null;
  today_services: number;
  avg_latency_ms: number | null;
  service_doctors: number;
  compliance_health: 'green' | 'yellow' | 'red';
  added_count: number;
  approval_rate: number | null;
}
