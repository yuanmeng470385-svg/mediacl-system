import client from './client';
import type { ApiResponse, PaginatedResponse, AuditLog } from '../types';

/** /audit/logs 查询参数，与 audit-service search_logs 对齐 */
export interface AuditListParams {
  page?: number;
  page_size?: number;
  start_time?: string;
  end_time?: string;
  user_id?: string;
  service_name?: string;
  action?: string;
  risk_level?: string;
  keyword?: string;
}

/** /audit/export 请求体（后端仅支持这 4 个筛选字段） */
export interface AuditExportParams {
  start_time?: string;
  end_time?: string;
  service_name?: string;
  risk_level?: string;
}

export const auditAPI = {
  list: (params?: AuditListParams) =>
    client.get<PaginatedResponse<AuditLog>>('/audit/logs', { params }),

  detail: (id: string) =>
    client.get<ApiResponse<AuditLog>>(`/audit/logs/${id}`),

  export: (params?: AuditExportParams) =>
    client.post<Blob>('/audit/export', params ?? {}, { responseType: 'blob' }),

  stats: () =>
    client.get<ApiResponse<{
      total_records: number;
      recent_records: number;
      recent_days: number;
      risk_distribution: Record<string, number>;
      service_distribution: Record<string, number>;
      trend_daily: { date: string; count: number }[];
    }>>('/audit/stats'),
};
