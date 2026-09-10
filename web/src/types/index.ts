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

// ========== 学术触达（二期 G）==========
// 字段与 specialist-service GET /academic-cards/stats 对齐
export interface CardStats {
  days: number;
  total_pushes: number;
  total_reads: number;
  /** 后端返回 0-1 小数（round(total_reads / total_pushes, 4)），展示时需 ×100 转百分数 */
  read_rate: number;
  /** 有效阅读（已读且停留 ≥3s，2026-09-07 A-5）；后端 0-1 小数 */
  effective_reads: number;
  effective_read_rate: number;
  /** 排序=已读数优先（A-5：推送量仅次位） */
  rep_ranking: { representative_id: number; pushes: number; reads: number; read_rate: number }[];
}

// ========== AI 陪练 Skill 模版（二期 H）==========
// 字段与 specialist-service SkillPackage.to_dict 对齐
export interface SkillPackage {
  id: number;
  name: string;
  creator_id: number | null;
  is_public: boolean;
  is_anonymous: boolean;
  audit_status: 'pending' | 'approved' | 'rejected';
  audit_reason: string | null;
  style_tags: string[] | null;
  heat: number;
  approval_rate: number | null;
  description: string | null;
  off_shelf_status: 'active' | 'off_shelved';
  off_shelf_reason: string | null;
  off_shelf_type: 'compliance' | 'author' | null;
  off_shelf_by: number | null;
  off_shelf_at: string | null;
  creator_name?: string | null;
  creator_role?: string | null;
  /** 沟通风格参数：列表/广场接口不返回（隐私边界），仅审核 detail 接口受控返回 */
  skill_weights?: Record<string, any>;
  /** 话术内容：仅审核 detail 接口受控返回（隐私边界），列表/资产接口不返回 */
  content?: string;
  /** 提取来源陪练会话 ID：仅审核 detail 接口受控返回（2026-09-01 审核溯源） */
  source_session_ids?: number[] | null;
  /** 提取来源拜访 ID：仅审核 detail 接口受控返回（2026-09-10 溯源扩拜访） */
  source_visit_ids?: number[] | null;
  created_at: string | null;
}

// ========== Skill 审核留痕与陪练溯源（2026-09-01 审核盲审修复）==========
// 字段与 specialist-service SkillAudit.to_dict(+auditor_name join) 对齐
export interface SkillAuditRecord {
  id: number;
  skill_id: number;
  auditor_id: number;
  auditor_name?: string | null;
  audit_result: 'approve' | 'reject' | string;
  reason: string | null;
  created_at: string | null;
}

// 字段与 specialist-service GET /practices/{id}/review-transcript 对齐
export interface PracticeTranscript {
  id: number;
  representative_id: number;
  rep_name?: string | null;
  scenario: string;
  status: string;
  turn_count: number;
  transcript: { role: string; content: string; turn?: number }[];
  created_at: string | null;
}

// 字段与 specialist-service GET /skill-packages/source-visits/{id} 对齐（2026-09-10 溯源扩拜访）
export interface VisitSourceTranscript {
  id: number;
  representative_id: number;
  rep_name?: string | null;
  hcp_name?: string | null;
  status: string;
  visit_time: string | null;
  rep_lines: number;
  lines: { speaker: string; content: string }[];
  created_at: string | null;
}

// ========== 异议话术库（3.2(5)，web 审核页 2026-09-01）==========
// 字段与 specialist-service ObjectionScript.to_dict 对齐
export interface ObjectionScript {
  id: number;
  scenario_type: string;
  objection_content: string;
  response_guidance: string | null;
  version: string | null;
  review_status: 'pending' | 'approved' | 'rejected';
  review_reason: string | null;
  reviewed_by: number | null;
  created_by: number | null;
  created_at: string | null;
  updated_at: string | null;
}

// ========== 患教模板库（二期 I）==========
// 字段与 specialist-service GET /patient-edu/templates 对齐
export interface PatientEduTemplate {
  id: number;
  title: string;
  disease_area: string;
  content: string;
  version: string;
  review_status: 'pending' | 'approved' | 'rejected';
  review_reason: string | null;
  created_by: number | null;
  created_at: string | null;
}

// ========== 患教内容记录（三期 M，GET /patient-edu/zone|review-queue）==========
export interface EduContentRecord {
  id: number;
  doctor_id: number;
  template_id: number | null;
  content: { title: string; body: string; notes: string; seek_care: string };
  is_ai_generated: boolean;
  visibility: 'private' | 'shared';
  audit_status: 'pending' | 'approved' | 'rejected' | null;
  doctor_name?: string | null;
  created_at: string | null;
}

// ========== 运营统计（二期 I）==========
// 字段与 specialist-service /doctor-stats/activity 对齐
export interface DoctorActivity {
  dau: number;
  wau: number;
  mau: number;
}

// 字段与 specialist-service /doctor-stats/twin-ranking 对齐
export interface TwinRankingItem {
  twin_id: number;
  name: string;
  status: string;
  added_count: number;
  approval_rate: number | null;
}

// ========== 三期 K：MAH 全景 / 数据分类 / 导出审批 ==========
export interface MahOverview {
  total_reps: number;
  filing: { not_filed: number; valid: number; expired: number; pending_review: number; rejected: number };
  training_completed_rate: number;
  commitment_signed_rate: number;
  compliance_pass_rate: number;
}

export interface DataAssetCategory {
  category: string;
  level: string;
  tables: string[];
}

export interface ExportRequest {
  id: number;
  requester_id: number;
  requester_name?: string | null;
  export_type: string;
  reason: string | null;
  status: 'pending' | 'approved' | 'rejected';
  approver_id: number | null;
  approve_reason: string | null;
  file_url: string | null;
  expires_at: string | null;
  responded_at: string | null;
  created_at: string | null;
  sla_overdue?: boolean;
}

export interface PrivacyRequest {
  id: number;
  doctor_id: number;
  doctor_name?: string;
  request_type: 'view' | 'correct' | 'delete' | 'export' | 'account_delete';
  status: 'pending' | 'processing' | 'done' | 'rejected';
  content: {
    detail?: string;
    fields?: { full_name?: string; phone?: string };
    confirm?: boolean;
    response?: string;
  };
  sla_deadline: string | null;
  sla_overdue?: boolean;
  handled_by: number | null;
  handled_at: string | null;
  file_url: string | null;
  created_at: string | null;
}
