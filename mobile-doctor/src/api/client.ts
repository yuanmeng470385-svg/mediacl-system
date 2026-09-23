/**
 * API 客户端 - 统一封装
 *
 * 所有后端请求通过网关 (gateway:8000) 访问
 */
import AsyncStorage from '@react-native-async-storage/async-storage';
import { API_HOST, API_SCHEME } from '../config';
import { API_PORT } from '../config';

// 开发环境用本地网关，生产环境用正式地址；host 集中定义在 src/config.ts（真机联调改一处）
const API_BASE_URL = `${API_SCHEME}://${API_HOST}:${API_PORT}`;

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
  /** 401 通知回调（AuthContext 注册：token 失效 → 全局登出）。多个并发 401 会触发多次，回调需幂等 */
  private onUnauthorized: (() => void) | null = null;

  constructor(baseURL: string = API_BASE_URL) {
    this.baseURL = baseURL;
  }

  /** 注册 token 失效回调（任意请求 401 时触发；client 层已清 token，回调只负责 UI 状态） */
  setOnUnauthorized(cb: (() => void) | null): void {
    this.onUnauthorized = cb;
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
      if (error instanceof APIError) {
        // token 失效（HTTP 401 或 JWT 错误码 2000-2003）：清除本地凭证 + 通知上层登出。
        // 网络错误（status 为空）不触发 —— 一次网络抖动不能把已登录用户踢出
        const tokenInvalid =
          error.status === 401 || [2000, 2001, 2002, 2003].includes(error.code);
        if (tokenInvalid) {
          await this.clearToken();
          this.onUnauthorized?.();
        }
        throw error;
      }
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

  /**
   * multipart 上传通道（资质证书文件）：request 是 JSON 专用，上传走这里。
   * 不设 Content-Type —— fetch 自动生成 multipart boundary；超时放宽到 60s。
   */
  async upload<T>(path: string, formData: FormData): Promise<T> {
    const token = await this.getToken();
    const headers: Record<string, string> = {
      'X-Request-ID': this.generateUUID(),
    };
    if (token) {
      headers['Authorization'] = `Bearer ${token}`;
    }

    const controller = new AbortController();
    const timeoutId = setTimeout(() => controller.abort(), 60000);

    try {
      const response = await fetch(`${this.baseURL}${path}`, {
        method: 'POST',
        headers,
        body: formData,
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
      if (error instanceof APIError) {
        const tokenInvalid =
          error.status === 401 || [2000, 2001, 2002, 2003].includes(error.code);
        if (tokenInvalid) {
          await this.clearToken();
          this.onUnauthorized?.();
        }
        throw error;
      }
      if (error.name === 'AbortError') {
        throw new APIError('上传超时，请检查网络连接', -1);
      }
      throw new APIError(error.message || '网络异常，请检查网络连接', -1);
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
