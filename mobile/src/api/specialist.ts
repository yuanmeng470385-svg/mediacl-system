/**
 * 数字专员 API
 */
import { apiClient } from './client';
import type {
  DigitalSpecialist,
  ChatRequest,
  ChatResponse,
  ConversationMessage,
  PaginatedResponse,
} from '../types';

export const specialistAPI = {
  /** 获取专员列表 */
  async list(params?: {
    page?: number;
    page_size?: number;
    status?: string;
  }): Promise<PaginatedResponse<DigitalSpecialist>> {
    return apiClient.request<PaginatedResponse<DigitalSpecialist>>(
      'GET',
      '/api/v1/specialists',
      params
    );
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

  /** 获取会话历史 */
  async getConversationHistory(
    sessionId: string
  ): Promise<ConversationMessage[]> {
    return apiClient.request<ConversationMessage[]>(
      'GET',
      `/api/v1/conversations/${sessionId}`
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

  /** 对话反馈（点赞/点踩） */
  async sendFeedback(
    specialistId: number,
    data: {
      request_id: string;
      rating: 'like' | 'dislike';
      comment?: string;
    }
  ): Promise<void> {
    return apiClient.request(
      'POST',
      `/api/v1/specialists/${specialistId}/feedback`,
      data
    );
  },

  /** 收藏/取消收藏 */
  async toggleFavorite(
    specialistId: number,
    requestId: string,
    favorite: boolean
  ): Promise<void> {
    return apiClient.request(
      'POST',
      `/api/v1/specialists/${specialistId}/favorite`,
      { request_id: requestId, favorite }
    );
  },
};
