/**
 * 产品使用 AI 助手 API（2026-09-15 三端）：
 * 后端按登录角色注入对应端功能地图，qwen-turbo 直答"功能是什么/在哪/怎么用"。
 * 无状态：会话仅存组件本地 state，不落库。
 */
import { apiClient } from './client';

export interface AssistantAnswer {
  answer: string;
  disclaimer?: string | null;
}

export const assistantAPI = {
  ask: (question: string) =>
    apiClient.request<AssistantAnswer>('POST', '/api/v1/assistant/qa', { question }),
};
