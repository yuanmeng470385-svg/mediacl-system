import client from './client';
import type { ApiResponse, PaginatedResponse, KnowledgeDoc } from '../types';

export const knowledgeAPI = {
  list: (params?: { page?: number; page_size?: number; type?: string; status?: string; product?: string }) =>
    client.get<PaginatedResponse<KnowledgeDoc>>('/knowledge/documents', { params }),

  detail: (id: string) =>
    client.get<ApiResponse<KnowledgeDoc>>(`/knowledge/documents/${id}`),

  review: (id: string, action: 'approve' | 'reject', reason?: string) =>
    client.post<ApiResponse<null>>(`/knowledge/documents/${id}/review`, { approved: action === 'approve', reason }),

  stats: () =>
    client.get<ApiResponse<{ docs: number; tags: number; chunks: number }>>('/knowledge/stats'),

  search: (query: string, top_k?: number) =>
    client.post<ApiResponse<{ results: { content: string; score: number; doc_id: string }[] }>>('/knowledge/search', { query, top_k }),
};
