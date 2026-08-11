/**
 * 学术内容 API（知识库）
 */
import { apiClient } from './client';
import type { PaginatedResponse, ContentItem } from '../types';

export interface ContentDetail extends ContentItem {
  content?: string;
}

/**
 * 后端返回 doc_type（product/guideline/literature/regulation/competitor/other），
 * 前端契约用 type（literature/guideline/manual/news）—— 缺映射时 Tab 过滤恒空。
 * 未知值兜底 'news'，避免 type 为 undefined 使筛选全部落空。
 */
export function mapDocType(docType?: string | null): ContentItem['type'] {
  switch (docType) {
    case 'literature': return 'literature';
    case 'guideline': return 'guideline';
    case 'regulation': return 'guideline'; // 法规 → 归"指南"（制度性文档）
    case 'product': return 'manual';       // 产品说明书
    case 'competitor': return 'news';      // 竞品动态 → 资讯
    case 'other': return 'news';
    default: return 'news';
  }
}

export function mapContentItem(raw: Record<string, any>): ContentItem {
  const type = mapDocType(raw?.doc_type ?? raw?.type);
  return {
    id: raw?.id,
    title: raw?.title ?? '',
    type,
    summary: raw?.summary,
    source: raw?.source,
    publish_date: raw?.publish_date,
    evidence_level: raw?.evidence_level,
    file_url: raw?.file_url,
    tags: raw?.tags,
  };
}

export const contentAPI = {
  /** 文档列表（分页 + 类型筛选） */
  async getDocuments(params?: {
    page?: number;
    page_size?: number;
    doc_type?: string;
  }): Promise<PaginatedResponse<ContentItem>> {
    const data = await apiClient.request<PaginatedResponse<any>>(
      'GET',
      '/api/v1/knowledge/documents',
      params
    );
    return { ...data, items: (data.items || []).map(mapContentItem) };
  },

  /** 文档详情（含正文） */
  async getDocument(id: number): Promise<ContentDetail> {
    const raw = await apiClient.request<any>(
      'GET',
      `/api/v1/knowledge/documents/${id}`
    );
    return { ...mapContentItem(raw), content: raw?.content };
  },
};
