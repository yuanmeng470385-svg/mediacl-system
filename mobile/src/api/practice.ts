/**
 * AI 陪练 / Skill 广场 / 分身管理 API（二期 H）。
 * 三组 API 共用一个文件（契约测试从 '../practice' 解构三组），
 * 全部走 apiClient.request（GET=query、POST/PUT=body、返回已解包 data）。
 */
import { apiClient } from './client';

/**
 * 同步 AI 生成接口的客户端超时（与 visit.ts 的 AI_SYNC_TIMEOUT_MS 同源语义，2026-08-31）：
 * extract-draft（风格草稿，qwen-turbo 同步生成）与 practices complete（评分输出加长）
 * 后端都同步等 LLM，网关已为这两个路由开 120s carve-out，客户端同步放宽 ——
 * 默认 30s 会先于后端掐断，用户只能白等一次超时（8-28 拜访超时链同款教训）
 */
const AI_SYNC_TIMEOUT_MS = 120000;

export const practiceAPI = {
  create: (payload: { skill_id?: number; scenario: string }) =>
    apiClient.request<any>('POST', '/api/v1/practices', payload),
  turn: (sessionId: number, message: string) =>
    apiClient.request<any>('POST', `/api/v1/practices/${sessionId}/turn`, { message }),
  // complete：评分链同步等 LLM，超时放宽到 120s（决策 11，与网关 carve-out 对齐）
  complete: (sessionId: number) =>
    apiClient.request<any>('POST', `/api/v1/practices/${sessionId}/complete`, {}, AI_SYNC_TIMEOUT_MS),
  list: () => apiClient.request<any>('GET', '/api/v1/practices'),
};

export const plazaAPI = {
  list: (params?: { page?: number; page_size?: number; keyword?: string }) =>
    apiClient.request<any>('GET', '/api/v1/skill-packages/public', params),
  load: (skillId: number) =>
    apiClient.request<any>('POST', `/api/v1/skill-packages/${skillId}/load`, {}),
  releaseSkill: (payload: {
    name: string; description: string; content: string;
    style_tags?: string[]; skill_weights: Record<string, string>; is_anonymous?: boolean;
  }) => apiClient.request<any>('POST', '/api/v1/skill-packages/release', payload),
  mySkills: (params?: { page?: number; page_size?: number }) =>
    apiClient.request<any>('GET', '/api/v1/skill-packages/mine', params),
  /**
   * 三期 P：从本人陪练会话提取风格 Skill 草稿（同步 LLM，120s 超时）。
   * 入参 session_ids 1~10 个（本人 + completed + 单会话 ≥3 轮，门槛在后端校验）；
   * 返回草稿 {name, description, content, style_tags, skill_weights, is_anonymous}，
   * 与 releaseSkill payload 同构（直接预填发布表单）。
   * 失败语义：4002 = 今日 3 次限额已满 / 4003 = LLM 生成失败可重试 / 4xx 中文 message = 会话不合格。
   */
  extractDraft: (sessionIds: number[]) =>
    apiClient.request<any>(
      'POST',
      '/api/v1/skill-packages/extract-draft',
      { session_ids: sessionIds },
      AI_SYNC_TIMEOUT_MS,
    ),
};

export const twinAPI = {
  setStyle: (twinId: number, style: Record<string, string>) =>
    apiClient.request<any>('PUT', `/api/v1/specialists/${twinId}/style`, style),
  pause: (twinId: number) => apiClient.request<any>('POST', `/api/v1/specialists/${twinId}/pause`, {}),
  resume: (twinId: number) => apiClient.request<any>('POST', `/api/v1/specialists/${twinId}/resume`, {}),
  styleTest: (answers: number[]) =>
    apiClient.request<any>('POST', '/api/v1/specialists/style-test', { answers }),
};
