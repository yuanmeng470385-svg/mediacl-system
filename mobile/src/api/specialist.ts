/**
 * 数字专员 API
 */
import { apiClient } from './client';
import type {
  DigitalSpecialist,
  ChatRequest,
  ChatResponse,
  ConversationMessage,
} from '../types';

export const specialistAPI = {
  /** 获取专员列表（后端返回 paginate 分页对象，解出 items 数组） */
  async list(params?: {
    page?: number;
    page_size?: number;
    status?: string;
  }): Promise<DigitalSpecialist[]> {
    const res = await apiClient.request<{
      items: DigitalSpecialist[];
      total: number;
      page: number;
      page_size: number;
    }>(
      'GET',
      '/api/v1/specialists',
      params
    );
    return res.items ?? [];
  },

  /** 获取专员详情 */
  async getById(id: number): Promise<DigitalSpecialist> {
    return apiClient.request<DigitalSpecialist>(
      'GET',
      `/api/v1/specialists/${id}`
    );
  },

  /** 发送对话消息（核心接口） */
  async sendMessage(
    specialistId: number,
    data: ChatRequest
  ): Promise<ChatResponse> {
    return apiClient.request<ChatResponse>(
      'POST',
      `/api/v1/specialists/${specialistId}/chat`,
      data
    );
  },

  /** 获取会话历史（后端挂在 specialists 路由下） */
  async getConversationHistory(
    sessionId: string
  ): Promise<ConversationMessage[]> {
    return apiClient.request<ConversationMessage[]>(
      'GET',
      `/api/v1/specialists/conversations/${sessionId}`
    );
  },

  /** 获取专员使用统计 */
  async getStats(
    id: number
  ): Promise<{
    total_questions: number;
    avg_latency_ms: number;
    favorite_count: number;
  }> {
    return apiClient.request('GET', `/api/v1/specialists/${id}/stats`);
  },

  /** 对话反馈（点赞/点踩）—— 挂 conversation_id，非 specialist_id */
  async sendFeedback(
    conversationId: number,
    rating: 1 | -1,
    comment?: string
  ): Promise<{ feedback_id: number }> {
    const body: { rating: 1 | -1; comment?: string } = { rating };
    if (comment) body.comment = comment;
    return apiClient.request(
      'POST',
      `/api/v1/conversations/${conversationId}/feedback`,
      body
    );
  },

  /** 收藏/取消收藏（后端是 toggle，无 body） */
  async toggleFavorite(
    conversationId: number
  ): Promise<{ is_favorite: boolean }> {
    return apiClient.request(
      'POST',
      `/api/v1/conversations/${conversationId}/favorite`
    );
  },
};
