import client from './client';
import type { ApiResponse } from '../types';

export const authAPI = {
  login: (username: string, password: string) =>
    client.post<ApiResponse<{ token: string; user: any }>>('/auth/login', { username, password }),

  me: () =>
    client.get<ApiResponse<any>>('/auth/me'),
};
