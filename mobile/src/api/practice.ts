/**
 * AI 陪练 / Skill 广场 / 分身管理 API（二期 H）。
 * 三组 API 共用一个文件（契约测试从 '../practice' 解构三组），
 * 全部走 apiClient.request（GET=query、POST/PUT=body、返回已解包 data）。
 */
import { apiClient } from './client';

export const practiceAPI = {
  create: (payload: { skill_id?: number; scenario: string }) =>
    apiClient.request<any>('POST', '/api/v1/practices', payload),
  turn: (sessionId: number, message: string) =>
    apiClient.request<any>('POST', `/api/v1/practices/${sessionId}/turn`, { message }),
  complete: (sessionId: number) =>
    apiClient.request<any>('POST', `/api/v1/practices/${sessionId}/complete`, {}),
  list: () => apiClient.request<any>('GET', '/api/v1/practices'),
};

export const plazaAPI = {
  list: (params?: { page?: number; page_size?: number; keyword?: string }) =>
    apiClient.request<any>('GET', '/api/v1/skill-packages/public', params),
  load: (skillId: number) =>
    apiClient.request<any>('POST', `/api/v1/skill-packages/${skillId}/load`, {}),
};

export const twinAPI = {
  setStyle: (twinId: number, style: Record<string, string>) =>
    apiClient.request<any>('PUT', `/api/v1/specialists/${twinId}/style`, style),
  pause: (twinId: number) => apiClient.request<any>('POST', `/api/v1/specialists/${twinId}/pause`, {}),
  resume: (twinId: number) => apiClient.request<any>('POST', `/api/v1/specialists/${twinId}/resume`, {}),
  styleTest: (answers: number[]) =>
    apiClient.request<any>('POST', '/api/v1/specialists/style-test', { answers }),
};
