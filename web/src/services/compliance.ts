import client from './client';
import type {
  ApiResponse, PaginatedResponse, ComplianceRule, ComplianceStats, RuleTestResult,
  ComplianceBlock, BlocksHeatmapStats, DataAssetCategory,
} from '../types';

export const complianceAPI = {
  list: (params?: { page?: number; page_size?: number; rule_type?: string; enabled?: boolean }) =>
    client.get<PaginatedResponse<ComplianceRule>>('/compliance/rules', { params }),

  create: (data: Partial<ComplianceRule>) =>
    client.post<ApiResponse<ComplianceRule>>('/compliance/rules', data),

  update: (id: number, data: Partial<ComplianceRule>) =>
    client.put<ApiResponse<ComplianceRule>>(`/compliance/rules/${id}`, data),

  delete: (id: number) =>
    client.delete<ApiResponse<null>>(`/compliance/rules/${id}`),

  reload: () =>
    client.post<ApiResponse<{ reloaded_rules: number }>>('/compliance/rules/reload'),

  test: (content: string) =>
    client.post<ApiResponse<RuleTestResult>>('/compliance/rules/test', { content }),

  stats: () =>
    client.get<ApiResponse<ComplianceStats>>('/compliance/stats'),

  blocks: (params?: { page?: number; page_size?: number; user_id?: number; rule_code?: string }) =>
    client.get<PaginatedResponse<ComplianceBlock>>('/compliance/blocks', { params }),

  blockDetail: (id: number) =>
    client.get<ApiResponse<ComplianceBlock>>(`/compliance/blocks/${id}`),

  /** 热力图聚合（区域 × 近 N 天拦截量），维度失败时后端自动降级为 service */
  blocksStats: (params?: { days?: number }) =>
    client.get<ApiResponse<BlocksHeatmapStats>>('/compliance/blocks/stats', { params }),

  dataAssets: () =>
    client.get<ApiResponse<DataAssetCategory[]>>('/compliance/data-assets'),

  /** 监管自查报告（3 Sheet xlsx：规则快照/拦截明细/汇总；start/end_time 可选 ISO 8601） */
  exportReport: (body?: { start_time?: string; end_time?: string }) =>
    client.post<Blob>('/compliance/report/export', body ?? {}, { responseType: 'blob' }),
};
