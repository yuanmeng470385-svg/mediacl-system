/**
 * 学术卡片收件箱 API（二期 G 端点契约）：
 *   - listInbox: GET /api/v1/card-pushes（医生端收件箱，分页返回 items 且每条带 card 对象）
 *   - trackRead: POST /api/v1/card-pushes/{pushId}/track（阅读上报 read_status + 停留秒数）
 *   - submitFeedback: POST /api/v1/card-pushes/{pushId}/feedback（useful/useless/追问文本）
 *   - notifications/unreadCount/markRead: 站内通知消费（2026-09-07 A-1，端点本就
 *     require_roles("rep","doctor")——此前医生端只写不读，代表新卡片无提醒入口）
 */
import { apiClient } from './client';
import type { CardPushRecord, PaginatedResponse } from '../types';

export interface AppNotification {
  id: number;
  type: 'card_new' | 'briefing_ready' | 'card_feedback' | 'card_question' | string;
  title: string;
  content: string | null;
  /** 后端跳转目标：/card-pushes（收件箱）；代表端路径医生端不跳 */
  link: string | null;
  isRead: boolean;
  createdAt: string | null;
}

/** 后端 Notification.to_dict（snake_case）→ AppNotification（契约映射在 api 层做，不污染屏幕组件——
 *  2026-09-07 代表端同款错位的教训：is_read/created_at 直接透传会让红点与时间列全空） */
function mapNotification(raw: any): AppNotification {
  return {
    id: raw?.id,
    type: raw?.type,
    title: raw?.title ?? '',
    content: raw?.content ?? null,
    link: raw?.link ?? null,
    isRead: !!raw?.is_read,
    createdAt: raw?.created_at ?? null,
  };
}

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

  /** 站内通知（医生端主要收 card_new 新卡片）分页（后端 is_read/created_at 在此映射） */
  notifications: (page = 1, pageSize = 20, unreadOnly = false) =>
    apiClient
      .request<{ items: any[]; total: number }>(
        'GET',
        `/api/v1/card-pushes/notifications?page=${page}&page_size=${pageSize}${unreadOnly ? '&unread_only=true' : ''}`
      )
      .then((res) => ({
        total: res?.total ?? 0,
        items: (Array.isArray(res?.items) ? res.items : []).map(mapNotification),
      })),

  /** 未读通知数（红点） */
  unreadCount: () =>
    apiClient.request<{ unread: number }>(
      'GET',
      '/api/v1/card-pushes/notifications/unread-count'
    ),

  /** 标记已读：单条或全部（单条返回后端 to_dict snake_case 行、全部返回 {marked}，调用方不消费具体形状） */
  markRead: (notificationId?: number, all = false) =>
    apiClient.request<Record<string, unknown>>(
      'POST',
      '/api/v1/card-pushes/notifications/read',
      all ? { all: true } : { notification_id: notificationId }
    ),
};
