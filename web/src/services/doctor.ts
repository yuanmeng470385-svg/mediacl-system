import client from './client';
import type { ApiResponse, PaginatedResponse, Doctor } from '../types';

export const doctorAPI = {
  list: (params?: { page?: number; page_size?: number; keyword?: string; hospital?: string; department?: string; tag?: string }) =>
    client.get<PaginatedResponse<Doctor>>('/hcps', { params }),

  detail: (id: string) =>
    client.get<ApiResponse<Doctor & { education?: string; preferences?: string; interactions?: any[] }>>(`/hcps/${id}`),

  profile: (id: string) =>
    client.get<ApiResponse<any>>(`/hcps/${id}/profile`),

  interactions: (id: string) =>
    client.get<ApiResponse<any[]>>(`/hcps/${id}/interactions`),

  create: (data: Partial<Doctor>) =>
    client.post<ApiResponse<Doctor>>('/hcps', data),

  update: (id: string, data: Partial<Doctor>) =>
    client.put<ApiResponse<Doctor>>(`/hcps/${id}`, data),

  addTag: (id: string, tag: string) =>
    client.post<ApiResponse<null>>(`/hcps/${id}/tags`, { tag }),

  removeTag: (id: string, tag: string) =>
    client.delete<ApiResponse<null>>(`/hcps/${id}/tags`, { data: { tag } }),
};
