/**
 * 数字员工分身 API（Task 6 端点契约 + 对话）：
 *   - activate: 分享链接激活（返回 {twin, subscribed, subscription_status}）
 *   - subscribe: 订阅（consent_agreed: true 硬编码——能走到这一步说明用户
 *     已在知情同意 Modal 点过"同意并添加"）
 *   - list: 本人订阅列表
 *   - toggle: 订阅/屏蔽切换
 *   - chat: 分身对话（REST，无流式）POST /api/v1/specialists/{id}/chat
 *
 * 契约偏差说明（相对 plan Step 1 片段）：list 后端返回 success(items) 裸数组
 * （twin_subscriptions.py:152，test 断言 data 为 list），不是 {items} 包装 ——
 * 本层直接返回 TwinSubscriptionItem[]。
 */
import { apiClient } from './client';
import type {
  ChatResponse,
  TwinActivateResult,
  TwinSubscription,
  TwinSubscriptionItem,
} from '../types';

export const twinAPI = {
  activate: (token: string) =>
    apiClient.request<TwinActivateResult>(
      'POST',
      `/api/v1/share-links/${token}/activate`,
      {}
    ),

  subscribe: (twinId: number) =>
    apiClient.request<TwinSubscription>('POST', '/api/v1/twin-subscriptions', {
      twin_id: twinId,
      consent_agreed: true,
    }),

  list: () =>
    apiClient.request<TwinSubscriptionItem[]>(
      'GET',
      '/api/v1/twin-subscriptions',
      undefined
    ),

  toggle: (twinId: number, status: 'subscribed' | 'blocked') =>
    apiClient.request<TwinSubscription>(
      'POST',
      `/api/v1/twin-subscriptions/${twinId}/toggle`,
      { status }
    ),

  /** 分身对话（REST 兜底；v1.1 支持 session_id 续会话——WS 路径同款语义） */
  chat: (twinId: number, question: string, sessionId?: string) =>
    apiClient.request<ChatResponse>(
      'POST',
      `/api/v1/specialists/${twinId}/chat`,
      sessionId ? { question, session_id: sessionId } : { question }
    ),
};
