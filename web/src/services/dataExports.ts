import client from './client';
import type { ApiResponse, PaginatedResponse, ExportRequest } from '../types';

export const dataExportAPI = {
  list: (params?: { page?: number; page_size?: number; status?: string }) =>
    client.get<PaginatedResponse<ExportRequest>>('/data-exports/requests', { params }),
  create: (data: { export_type: string; reason: string }) =>
    client.post<ApiResponse<ExportRequest>>('/data-exports/requests', data),
  review: (id: number, data: { verdict: 'approve' | 'reject'; reason?: string }) =>
    client.post<ApiResponse<ExportRequest>>(`/data-exports/requests/${id}/review`, data),
  /** 鉴权下载：走 axios 带 JWT（window.open 直开不带 Authorization 会 401） */
  download: (id: number) =>
    client.get<Blob>(`/data-exports/requests/${id}/download`, { responseType: 'blob' }),
};
