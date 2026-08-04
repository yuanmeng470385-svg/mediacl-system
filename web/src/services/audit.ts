import client from './client';
import type { ApiResponse, PaginatedResponse, AuditLog } from '../types';

export const auditAPI = {
  list: (params?: {
    page?: number; page_size?: number;
    start_date?: string; end_date?: string;
    user_id?: string; service?: string; operation?: string; risk_level?: string;
  }) =>
    client.get<PaginatedResponse<AuditLog>>('/audit/logs', { params }),

  detail: (id: string) =>
    client.get<ApiResponse<AuditLog & { content?: string }>>(`/audit/logs/${id}`),

  export: (params?: any) =>
    client.post('/audit/export', params, { responseType: 'blob' }),

  stats: () =>
    client.get<ApiResponse<{ total: number; hit_rules: number }>>('/audit/stats'),
};
