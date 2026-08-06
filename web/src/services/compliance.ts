import client from './client';
import type { ApiResponse, PaginatedResponse, ComplianceRule, ComplianceStats, RuleTestResult } from '../types';

export const complianceAPI = {
  list: (params?: { page?: number; page_size?: number; rule_type?: string; enabled?: boolean }) =>
    client.get<PaginatedResponse<ComplianceRule>>('/compliance/rules', { params }),

  create: (data: Partial<ComplianceRule>) =>
    client.post<ApiResponse<ComplianceRule>>('/compliance/rules', data),

  update: (id: number, data: Partial<ComplianceRule>) =>
    client.put<ApiResponse<ComplianceRule>>(`/compliance/rules/${id}`, data),

  delete: (id: number) =>
    client.delete<ApiResponse<null>>(`/compliance/rules/${id}`),

  reload: () =>
    client.post<ApiResponse<{ reloaded_rules: number }>>('/compliance/rules/reload'),

  test: (content: string) =>
    client.post<ApiResponse<RuleTestResult>>('/compliance/rules/test', { content }),

  stats: () =>
    client.get<ApiResponse<ComplianceStats>>('/compliance/stats'),

  blocks: (params?: { page?: number; page_size?: number; rule_code?: string }) =>
    client.get<PaginatedResponse<{
      id: number; user_id: number | null; service_name: string; content: string;
      rule_code: string; rule_name: string; severity: string;
      action: string; blocked_at: string;
    }>>('/compliance/blocks', { params }),
};
