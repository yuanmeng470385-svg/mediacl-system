import client from './client';
import type { ApiResponse, PaginatedResponse, SkillAuditRecord, SkillPackage } from '../types';

export const skillAPI = {
  list: (params?: { page?: number; page_size?: number; audit_status?: string }) =>
    client.get<PaginatedResponse<SkillPackage>>('/skill-packages', { params }),
  assetList: (params?: { page?: number; page_size?: number; audit_status?: string; off_shelf_status?: string; keyword?: string }) =>
    client.get<PaginatedResponse<SkillPackage>>('/skill-packages/asset-list', { params }),
  // 审核详情：受控查看 skill_weights（列表接口不返回，隐私边界）
  detail: (id: number) =>
    client.get<ApiResponse<SkillPackage>>(`/skill-packages/${id}/detail`),
  create: (data: { name: string; style_tags?: string[]; skill_weights: Record<string, any>; is_public?: boolean }) =>
    client.post<ApiResponse<SkillPackage>>('/skill-packages', data),
  review: (id: number, data: { verdict: 'approve' | 'reject'; reason?: string }) =>
    client.post<ApiResponse<SkillPackage>>(`/skill-packages/${id}/review`, data),
  offShelf: (id: number, data: { type: 'compliance' | 'author'; reason: string }) =>
    client.post<ApiResponse<SkillPackage>>(`/skill-packages/${id}/off-shelf`, data),
  // 审核历史（2026-09-01 审核盲审修复）：skill_audits 全量 + 审核人姓名
  audits: (id: number) =>
    client.get<ApiResponse<SkillAuditRecord[]>>(`/skill-packages/${id}/audits`),
};
