/**
 * 医生端隐私中心 API（三期 L 端点契约）：
 *   - getPrivacyPolicy: 隐私政策全文（静态文案，公开）
 *   - getPersonalData: 个人信息查看（user + doctor_profile）
 *   - createPrivacyRequest: 发起 更正/导出/删除/注销 申请
 *   - getMyPrivacyRequests: 本人请求分页 + 状态过滤
 *
 * 契约铁律：请求体/响应形状以本文件为唯一映射点（snake_case、分页解包在此做）。
 */
import { apiClient } from './client';
import type { PaginatedResponse } from '../types';

export interface PrivacyPolicy {
  title: string;
  version: string;
  updated_at: string;
  content: string;
}

export interface PersonalData {
  user: {
    id: number;
    username: string;
    full_name: string;
    name: string;
    phone: string | null;
    email: string | null;
    role: string;
    region: string | null;
    status: string;
  };
  doctor_profile: {
    interest_areas: string[] | null;
    preferred_doc_type: string | null;
    preferred_style: string | null;
    closed: boolean;
  } | null;
}

export type PrivacyRequestType = 'view' | 'correct' | 'delete' | 'export' | 'account_delete';
export type PrivacyRequestStatus = 'pending' | 'processing' | 'done' | 'rejected';

export interface PrivacyRequestItem {
  id: number;
  request_type: PrivacyRequestType;
  status: PrivacyRequestStatus;
  content: {
    detail?: string;
    fields?: { full_name?: string; phone?: string };
    response?: string;
  };
  sla_deadline: string | null;
  file_url: string | null;
  created_at: string | null;
}

export interface CreatePrivacyRequestPayload {
  request_type: Exclude<PrivacyRequestType, 'view'>;
  detail?: string;
  fields?: { full_name?: string; phone?: string };
  confirm?: boolean;
}

export const privacyAPI = {
  getPrivacyPolicy: () =>
    apiClient.request<PrivacyPolicy>('GET', '/api/v1/doctors/privacy-policy'),

  getPersonalData: () =>
    apiClient.request<PersonalData>('GET', '/api/v1/doctors/personal-data'),

  createPrivacyRequest: (payload: CreatePrivacyRequestPayload) =>
    apiClient.request<PrivacyRequestItem>('POST', '/api/v1/privacy-requests', payload),

  getMyPrivacyRequests: (status?: PrivacyRequestStatus) =>
    apiClient.request<PaginatedResponse<PrivacyRequestItem>>(
      'GET',
      `/api/v1/privacy-requests/me${status ? `?status=${status}` : ''}`,
    ),
};
