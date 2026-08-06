/**
 * API 客户端 - 统一封装
 *
 * 所有后端请求通过网关 (gateway:8000) 访问
 */
import AsyncStorage from '@react-native-async-storage/async-storage';
import { Platform } from 'react-native';

// 开发环境用本地网关，生产环境用正式地址
const API_BASE_URL = Platform.select({
  android: 'http://10.0.2.2:8000',   // Android 模拟器访问宿主机
  ios: 'http://localhost:8000',
  default: 'http://localhost:8000',
});

interface RequestOptions {
  method: string;
  path: string;
  data?: any;
  params?: Record<string, any>;  // GET 查询参数
  timeout?: number;
}

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

  async clearToken(): Promise<void> {
    this.token = null;
    await AsyncStorage.removeItem('medagent_token');
  }

  async request<T>(
    method: string,
    path: string,
    dataOrParams?: any
  ): Promise<T> {
    const token = await this.getToken();
    const headers: Record<string, string> = {
      'Content-Type': 'application/json',
    };
    if (token) {
      headers['Authorization'] = `Bearer ${token}`;
    }
    headers['X-Request-ID'] = this.generateUUID();

    // 构建 URL（GET 请求拼查询参数）
    let url = `${this.baseURL}${path}`;
    let body: string | undefined;

    if (method === 'GET' && dataOrParams) {
      const params = new URLSearchParams();
      Object.entries(dataOrParams).forEach(([key, value]) => {
        if (value !== undefined && value !== null && value !== '') {
          params.append(key, String(value));
        }
      });
      const qs = params.toString();
      if (qs) url += `?${qs}`;
    } else if (dataOrParams) {
      body = JSON.stringify(dataOrParams);
    }

    // 超时控制
    const controller = new AbortController();
    const timeoutId = setTimeout(() => controller.abort(), 30000);

    try {
      const response = await fetch(url, {
        method,
        headers,
        body,
        signal: controller.signal,
      });

      clearTimeout(timeoutId);

      const result = await response.json();

      if (result.code !== 0) {
        throw new APIError(
          result.message || '请求失败',
          result.code || -1,
          response.status
        );
      }

      return result.data as T;
    } catch (error: any) {
      clearTimeout(timeoutId);
      if (error instanceof APIError) throw error;
      if (error.name === 'AbortError') {
        throw new APIError('请求超时，请检查网络连接', -1);
      }
      // 网络错误
      throw new APIError(
        error.message || '网络异常，请检查网络连接',
        -1
      );
    }
  }

  private generateUUID(): string {
    return 'xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx'.replace(
      /[xy]/g,
      (c) => {
        const r = (Math.random() * 16) | 0;
        const v = c === 'x' ? r : (r & 0x3) | 0x8;
        return v.toString(16);
      }
    );
  }
}

export class APIError extends Error {
  code: number;
  /** HTTP 状态码（网关 401 = token 过期/无效；网络错误时为 undefined） */
  status?: number;
  constructor(message: string, code: number, status?: number) {
    super(message);
    this.code = code;
    this.status = status;
    this.name = 'APIError';
  }
}

export const apiClient = new APIClient();
