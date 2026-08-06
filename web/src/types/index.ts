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
