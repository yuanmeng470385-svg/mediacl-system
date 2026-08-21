/** 隐私请求处理（三期 L）：管理端列表 + 处理留痕 */
import client from './client';
import type { ApiResponse, PaginatedResponse, PrivacyRequest } from '../types';

export interface PrivacyRequestQuery {
  page?: number;
  page_size?: number;
  status?: string;
  request_type?: string;
}

export interface HandlePayload {
  action: 'processing' | 'done' | 'rejected';
  response?: string;
}

export const privacyAPI = {
  list: (params: PrivacyRequestQuery) =>
    client.get<PaginatedResponse<PrivacyRequest>>('/privacy-requests', { params }),
  handle: (id: number, data: HandlePayload) =>
    client.post<ApiResponse<PrivacyRequest>>(`/privacy-requests/${id}/handle`, data),
};
