import client from './client';
import type { ApiResponse, PaginatedResponse, KnowledgeDoc, KnowledgeStats } from '../types';

export const knowledgeAPI = {
  list: (params?: { page?: number; page_size?: number; doc_type?: string; status?: string; product_id?: number }) =>
    client.get<PaginatedResponse<KnowledgeDoc>>('/knowledge/documents', { params }),

  detail: (id: string) =>
    client.get<ApiResponse<KnowledgeDoc>>(`/knowledge/documents/${id}`),

  /** 上传文档：multipart（file + title/doc_type/product_id/evidence_level/publish_date/source/version） */
  upload: (formData: FormData) =>
    client.post<ApiResponse<KnowledgeDoc>>('/knowledge/upload', formData),

  review: (id: string, action: 'approve' | 'reject', reason?: string) =>
    client.post<ApiResponse<KnowledgeDoc>>(`/knowledge/documents/${id}/review`, { approved: action === 'approve', reason }),

  stats: () =>
    client.get<ApiResponse<KnowledgeStats>>('/knowledge/stats'),

  search: (query: string, top_k?: number) =>
    client.post<ApiResponse<{ results: { content: string; score: number; doc_id: string }[] }>>('/knowledge/search', { query, top_k }),
};
