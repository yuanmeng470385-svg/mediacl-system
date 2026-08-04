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
  name: string;
  status: 'up' | 'down';
}
