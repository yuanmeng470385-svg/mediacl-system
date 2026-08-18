/**
 * 夜间简报 API —— 契约映射层（后端 /api/v1/briefings）
 *
 * 列表返回 {items, total}；详情返回 NightlyBriefing（content.summary + content.doctors）。
 */
import { apiClient } from './client';
import type { NightlyBriefing } from '../types';

export const briefingAPI = {
  /** 简报分页列表 */
  list: (page = 1, pageSize = 20) =>
    apiClient.request<{ items: NightlyBriefing[]; total: number }>(
      'GET',
      '/api/v1/briefings',
      { page, page_size: pageSize }
    ),

  /** 简报详情 */
  getDetail: (id: number) =>
    apiClient.request<NightlyBriefing>('GET', `/api/v1/briefings/${id}`),
};
