/**
 * 学术内容 API（知识库）
 */
import { apiClient } from './client';
import type { PaginatedResponse, ContentItem } from '../types';

export interface ContentDetail extends ContentItem {
  content?: string;
}

export const contentAPI = {
  /** 文档列表（分页 + 类型筛选） */
  async getDocuments(params?: {
    page?: number;
    page_size?: number;
    doc_type?: string;
  }): Promise<PaginatedResponse<ContentItem>> {
    return apiClient.request<PaginatedResponse<ContentItem>>(
      'GET',
      '/api/v1/knowledge/documents',
      params
    );
  },

  /** 文档详情（含正文） */
  async getDocument(id: number): Promise<ContentDetail> {
    return apiClient.request<ContentDetail>(
      'GET',
      `/api/v1/knowledge/documents/${id}`
    );
  },
};
