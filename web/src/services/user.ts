import client from './client';
import type { ApiResponse, PaginatedResponse, User } from '../types';

export const userAPI = {
  list: (params?: { page?: number; page_size?: number; role?: string }) =>
    client.get<PaginatedResponse<User>>('/users', { params }),

  create: (data: Partial<User>) =>
    client.post<ApiResponse<User>>('/users', data),

  update: (id: string, data: Partial<User>) =>
    client.put<ApiResponse<User>>(`/users/${id}`, data),
};
