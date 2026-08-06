/**
 * 认证 API
 */
import AsyncStorage from '@react-native-async-storage/async-storage';
import { apiClient } from './client';
import type { LoginResponse, User } from '../types';

/** 缓存用户信息的存储键（启动时网络抖动场景用本地缓存兜底） */
const USER_CACHE_KEY = 'medagent_user';

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
    // 登录成功后存储 token 与用户缓存
    if (result.token) {
      await apiClient.setToken(result.token);
    }
    if (result.user) {
      await authAPI.cacheUser(result.user);
    }
    return result;
  },

  /** 用户名+密码登录（后端 auth.py:138 支持 username+password，返回同一形状） */
  async loginByPassword(username: string, password: string): Promise<LoginResponse> {
    const result = await apiClient.request<LoginResponse>(
      'POST',
      '/api/v1/auth/login',
      { username, password }
    );
    if (result.token) {
      await apiClient.setToken(result.token);
    }
    if (result.user) {
      await authAPI.cacheUser(result.user);
    }
    return result;
  },

  /** 缓存用户信息到本地（登录时写入；checkAuth 网络失败时读取兜底） */
  async cacheUser(user: User): Promise<void> {
    try {
      await AsyncStorage.setItem(USER_CACHE_KEY, JSON.stringify(user));
    } catch {
      // 缓存失败不影响登录主流程
    }
  },

  /** 读取本地缓存的用户信息（可能为 null） */
  async getCachedUser(): Promise<User | null> {
    try {
      const raw = await AsyncStorage.getItem(USER_CACHE_KEY);
      return raw ? (JSON.parse(raw) as User) : null;
    } catch {
      return null;
    }
  },

  /** 获取当前用户信息 */
  async getProfile(): Promise<User> {
    return apiClient.request<User>('GET', '/api/v1/auth/profile');
  },

  /** 读取本地 token（AuthContext 校验登录态用） */
  async getToken(): Promise<string | null> {
    return apiClient.getToken();
  },

  /** 退出登录 */
  async logout(): Promise<void> {
    await apiClient.clearToken();
    try {
      await AsyncStorage.removeItem(USER_CACHE_KEY);
    } catch {
      // 忽略缓存清理失败
    }
  },

  /** 检查是否已登录 */
  async isLoggedIn(): Promise<boolean> {
    const token = await apiClient.getToken();
    return token !== null;
  },
};
