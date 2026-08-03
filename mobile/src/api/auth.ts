/**
 * 认证 API
 */
import { apiClient } from './client';
import type { LoginResponse, User } from '../types';

export const authAPI = {
  /** 发送验证码 */
  async sendCode(phone: string): Promise<{ expire_seconds: number }> {
    return apiClient.request<{ expire_seconds: number }>(
      'POST',
      '/api/v1/auth/send-code',
      { phone }
    );
  },

  /** 手机号+验证码登录 */
  async login(phone: string, code: string): Promise<LoginResponse> {
    const result = await apiClient.request<LoginResponse>(
      'POST',
      '/api/v1/auth/login',
      { phone, code }
    );
    // 登录成功后存储 token
    if (result.token) {
      await apiClient.setToken(result.token);
    }
    return result;
  },

  /** 获取当前用户信息 */
  async getProfile(): Promise<User> {
    return apiClient.request<User>('GET', '/api/v1/auth/profile');
  },

  /** 退出登录 */
  async logout(): Promise<void> {
    await apiClient.clearToken();
  },

  /** 检查是否已登录 */
  async isLoggedIn(): Promise<boolean> {
    const token = await apiClient.getToken();
    return token !== null;
  },
};
