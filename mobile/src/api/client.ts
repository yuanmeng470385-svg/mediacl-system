/**
 * API 客户端 - 统一封装
 *
 * TODO: 替换为真实的 API 调用逻辑
 */
import AsyncStorage from '@react-native-async-storage/async-storage';
import { Platform } from 'react-native';

// 开发环境用本地网关，生产环境用正式地址
const API_BASE_URL = Platform.select({
  android: 'http://10.0.2.2:8000',   // Android 模拟器访问宿主机
  ios: 'http://localhost:8000',
  default: 'http://localhost:8000',
});

class APIClient {
  private baseURL: string;
  private token: string | null = null;

  constructor(baseURL: string = API_BASE_URL) {
    this.baseURL = baseURL;
  }

  async setToken(token: string): Promise<void> {
    this.token = token;
    await AsyncStorage.setItem('medagent_token', token);
  }

  async getToken(): Promise<string | null> {
    if (this.token) return this.token;
    this.token = await AsyncStorage.getItem('medagent_token');
    return this.token;
  }

  async request<T>(method: string, path: string, data?: any): Promise<T> {
    const token = await this.getToken();
    const headers: Record<string, string> = {
      'Content-Type': 'application/json',
    };
    if (token) {
      headers['Authorization'] = `Bearer ${token}`;
    }
    // 生成 X-Request-ID
    headers['X-Request-ID'] = this.generateUUID();

    const response = await fetch(`${this.baseURL}${path}`, {
      method,
      headers,
      body: data ? JSON.stringify(data) : undefined,
    });

    const result = await response.json();

    if (result.code !== 0) {
      throw new APIError(result.message, result.code);
    }

    return result.data as T;
  }

  private generateUUID(): string {
    return 'xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx'.replace(/[xy]/g, (c) => {
      const r = (Math.random() * 16) | 0;
      const v = c === 'x' ? r : (r & 0x3) | 0x8;
      return v.toString(16);
    });
  }
}

export class APIError extends Error {
  code: number;
  constructor(message: string, code: number) {
    super(message);
    this.code = code;
    this.name = 'APIError';
  }
}

export const apiClient = new APIClient();
