import client from './client';
import type { ApiResponse, PaginatedResponse, ComplianceRule } from '../types';

export const complianceAPI = {
  list: (params?: { page?: number; page_size?: number; type?: string; severity?: string }) =>
    client.get<PaginatedResponse<ComplianceRule>>('/compliance/rules', { params }),

  create: (data: Partial<ComplianceRule>) =>
    client.post<ApiResponse<ComplianceRule>>('/compliance/rules', data),

  update: (id: string, data: Partial<ComplianceRule>) =>
    client.put<ApiResponse<ComplianceRule>>(`/compliance/rules/${id}`, data),

  delete: (id: string) =>
    client.delete<ApiResponse<null>>(`/compliance/rules/${id}`),

  reload: () =>
    client.post<ApiResponse<null>>('/compliance/rules/reload'),

  test: (content: string) =>
    client.post<ApiResponse<{ hits: { rule: string; severity: string }[] }>>('/compliance/rules/test', { content }),

  stats: () =>
    client.get<ApiResponse<{ total: number; today_blocks: number; block_rate: number }>>('/compliance/stats'),
};
