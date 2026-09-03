/**
 * 学术卡片 API —— 契约映射层（后端 /api/v1/academic-cards、/api/v1/card-pushes，二期 G）
 *
 * 代表端：createCard（AI 生成 + 三层合规预检后落库）、listMyCards（本人卡片分页）、
 *         pushCard（推送给订阅了本人分身的医生，后端校验订阅关系并 skipped 未订阅者）。
 * 医生端收件箱/阅读追踪在 mobile-doctor（本层只映射代表端用到的端点）。
 */
import { apiClient } from './client';
import type { AcademicCard } from '../types';

export interface AcademicCardCreatePayload {
  title: string;
  topic: string;
}

export interface PushResult {
  pushed: number;
  skipped: number;
}

export interface PushTarget {
  doctorId: number;
  doctorName: string;
  twinNames: string[];
  subscribedAt: string | null;
}

export interface AppNotification {
  id: number;
  type: 'briefing_ready' | 'card_feedback' | 'card_question' | 'card_new' | string;
  title: string;
  content: string | null;
  /** 后端跳转目标：/briefings（简报/反馈）/ /card-pushes（医生端新卡片，代表端不产生） */
  link: string | null;
  isRead: boolean;
  createdAt: string | null;
}

export const academicAPI = {
  /** 生成学术卡片（AI 生成 + 三层合规预检 fail-closed） */
  createCard: (payload: AcademicCardCreatePayload) =>
    apiClient.request<AcademicCard>('POST', '/api/v1/academic-cards', payload),

  /** 本人学术卡片列表（后端默认 page=1/page_size=20） */
  listMyCards: () =>
    apiClient.request<{ items: AcademicCard[]; total: number }>(
      'GET',
      '/api/v1/academic-cards'
    ),

  /** 推送卡片给订阅了本人分身且 status='subscribed' 的医生 */
  pushCard: (cardId: number, doctorIds: number[]) =>
    apiClient.request<PushResult>('POST', `/api/v1/academic-cards/${cardId}/push`, {
      doctor_ids: doctorIds,
    }),

  /** 推送目标清单（订阅了本人分身的医生，多选 UI 供数；与 /push 校验同口径） */
  pushTargets: () =>
    apiClient.request<{ items: PushTarget[]; total: number }>(
      'GET',
      '/api/v1/academic-cards/push-targets'
    ),

  /** 站内通知（代表端简报就绪/医生反馈回流）分页 */
  notifications: (page = 1, pageSize = 20, unreadOnly = false) =>
    apiClient.request<{ items: AppNotification[]; total: number }>(
      'GET',
      `/api/v1/card-pushes/notifications?page=${page}&page_size=${pageSize}${unreadOnly ? '&unread_only=true' : ''}`
    ),

  /** 未读通知数（红点） */
  unreadCount: () =>
    apiClient.request<{ unread: number }>(
      'GET',
      '/api/v1/card-pushes/notifications/unread-count'
    ),

  /** 标记已读：单条或全部 */
  markRead: (notificationId?: number, all = false) =>
    apiClient.request<{ marked?: number } | AppNotification>(
      'POST',
      '/api/v1/card-pushes/notifications/read',
      all ? { all: true } : { notification_id: notificationId }
    ),
};
