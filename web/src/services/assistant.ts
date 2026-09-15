/** 产品使用 AI 助手（2026-09-15 三端）：功能地图问答，后端按角色注入对应端功能地图 */
import client from './client';
import type { ApiResponse } from '../types';

export interface AssistantAnswer {
  answer: string;
  disclaimer?: string | null;
}

export const assistantAPI = {
  ask: (question: string) =>
    client.post<ApiResponse<AssistantAnswer>>('/assistant/qa', { question }),
};
