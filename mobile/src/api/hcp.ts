/**
 * 医生管理 API
 */
import { apiClient } from './client';
import type {
  HCP,
  HCPProfile,
  HCPInteraction,
  PaginatedResponse,
} from '../types';

export const hcpAPI = {
  /** 医生列表（分页 + 多维度筛选） */
  async list(params?: {
    page?: number;
    page_size?: number;
    name?: string;
    hospital?: string;
    department?: string;
    title?: string;
    region?: string;
    status?: string;
    tag?: string;
  }): Promise<PaginatedResponse<HCP>> {
    return apiClient.request<PaginatedResponse<HCP>>(
      'GET',
      '/api/v1/hcps',
      params
    );
  },

  /** 医生详情 */
  async getById(id: number): Promise<HCP> {
    return apiClient.request<HCP>('GET', `/api/v1/hcps/${id}`);
  },

  /** 医生画像 */
  async getProfile(id: number): Promise<HCPProfile> {
    return apiClient.request<HCPProfile>(
      'GET',
      `/api/v1/hcps/${id}/profile`
    );
  },

  /** 互动历史 */
  async getInteractions(id: number): Promise<HCPInteraction[]> {
    return apiClient.request<HCPInteraction[]>(
      'GET',
      `/api/v1/hcps/${id}/interactions`
    );
  },

  /** 新增医生 */
  async create(data: Partial<HCP>): Promise<{ id: number }> {
    return apiClient.request<{ id: number }>(
      'POST',
      '/api/v1/hcps',
      data
    );
  },

  /** 编辑医生 */
  async update(id: number, data: Partial<HCP>): Promise<void> {
    return apiClient.request('PUT', `/api/v1/hcps/${id}`, data);
  },

  /** 添加标签 */
  async addTags(id: number, tags: string[]): Promise<void> {
    return apiClient.request(
      'POST',
      `/api/v1/hcps/${id}/tags`,
      { tags }
    );
  },

  /** 删除标签 */
  async removeTags(id: number, tags: string[]): Promise<void> {
    return apiClient.request(
      'DELETE',
      `/api/v1/hcps/${id}/tags`,
      { tags }
    );
  },
};
