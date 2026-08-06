import client from './client';
import type { ApiResponse, PaginatedResponse, Specialist, SpecialistStats } from '../types';

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
};
