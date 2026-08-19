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

  /** 站内通知（代表端简报就绪/医生反馈回流） */
  notifications: () =>
    apiClient.request<{ items: unknown[]; total: number }>(
      'GET',
      '/api/v1/card-pushes/notifications'
    ),
};
