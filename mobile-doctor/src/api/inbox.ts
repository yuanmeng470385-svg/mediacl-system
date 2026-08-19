/**
 * 学术卡片收件箱 API（二期 G 端点契约）：
 *   - listInbox: GET /api/v1/card-pushes（医生端收件箱，分页返回 items 且每条带 card 对象）
 *   - trackRead: POST /api/v1/card-pushes/{pushId}/track（阅读上报 read_status + 停留秒数）
 *   - submitFeedback: POST /api/v1/card-pushes/{pushId}/feedback（useful/useless/追问文本）
 */
import { apiClient } from './client';
import type { CardPushRecord, PaginatedResponse } from '../types';

export const inboxAPI = {
  /** 收件箱分页列表（后端 paginate 形状 {items,total,page,page_size}） */
  listInbox: () =>
    apiClient.request<PaginatedResponse<CardPushRecord>>(
      'GET',
      '/api/v1/card-pushes'
    ),

  trackRead: (pushId: number, readStatus: string, seconds: number) =>
    apiClient.request<CardPushRecord>(
      'POST',
      `/api/v1/card-pushes/${pushId}/track`,
      { read_status: readStatus, seconds }
    ),

  submitFeedback: (pushId: number, feedback: string) =>
    apiClient.request<CardPushRecord>(
      'POST',
      `/api/v1/card-pushes/${pushId}/feedback`,
      { feedback }
    ),
};
