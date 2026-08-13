import client from './client';
import type { ApiResponse, LiveStatus, PaginatedResponse, Specialist, SpecialistStats } from '../types';

/** 创建/更新专员的可提交字段（后端白名单 SPECIALIST_UPDATE_FIELDS） */
export type SpecialistPayload = Partial<Pick<
  Specialist,
  'name' | 'product_id' | 'bailian_app_id' | 'compliance_level' | 'status'
>> & {
  persona?: unknown;
  knowledge_scope?: unknown;
};

export const specialistAPI = {
  list: (params?: { page?: number; page_size?: number; status?: string }) =>
    client.get<PaginatedResponse<Specialist>>('/specialists', { params }),

  detail: (id: number) =>
    client.get<ApiResponse<Specialist>>(`/specialists/${id}`),

  create: (data: SpecialistPayload) =>
    client.post<ApiResponse<Specialist>>('/specialists', data),

  update: (id: number, data: SpecialistPayload) =>
    client.put<ApiResponse<Specialist>>(`/specialists/${id}`, data),

  stats: (id: number) =>
    client.get<ApiResponse<SpecialistStats>>(`/specialists/${id}/stats`),

  feedbackList: (id: number, params?: { page?: number; page_size?: number }) =>
    client.get<PaginatedResponse<SpecialistFeedback>>(
      `/specialists/${id}/feedback`,
      { params },
    ),

  liveStatus: () =>
    client.get<ApiResponse<LiveStatus>>('/specialists/live-status'),
};

/** 专员反馈明细（后端 GET /specialists/{id}/feedback 列表项） */
export interface SpecialistFeedback {
  id: number;
  conversation_id: number;
  rating: 1 | -1;
  comment?: string | null;
  question?: string | null;
  answer?: string | null;
  citations?: unknown[];
  created_at?: string | null;
}
