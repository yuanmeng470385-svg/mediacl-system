import client from './client';
import type { ApiResponse, PaginatedResponse, ExportRequest } from '../types';

export const dataExportAPI = {
  list: (params?: { page?: number; page_size?: number; status?: string }) =>
    client.get<PaginatedResponse<ExportRequest>>('/data-exports/requests', { params }),
  create: (data: { export_type: string; reason: string }) =>
    client.post<ApiResponse<ExportRequest>>('/data-exports/requests', data),
  review: (id: number, data: { verdict: 'approve' | 'reject'; reason?: string }) =>
    client.post<ApiResponse<ExportRequest>>(`/data-exports/requests/${id}/review`, data),
  downloadUrl: (id: number) => `/api/v1/data-exports/requests/${id}/download`,
};
