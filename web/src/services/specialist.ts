import client from './client';
import type { ApiResponse, PaginatedResponse, Specialist } from '../types';

export const specialistAPI = {
  list: (params?: { page?: number; page_size?: number; status?: string }) =>
    client.get<PaginatedResponse<Specialist>>('/specialists', { params }),

  detail: (id: string) =>
    client.get<ApiResponse<Specialist>>(`/specialists/${id}`),

  stats: (id: string) =>
    client.get<ApiResponse<{ daily_usage: number; satisfaction: number }>>(`/specialists/${id}/stats`),
};
