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

/** complete 响应中的考点话术（2026-09-10 异议话术批） */
export interface ObjectionUsedItem {
  content: string;
  guidance: string | null;
}

/** complete 响应映射（收口 api 层）：后端 objections_used → objectionsUsed（原键不外漏） */
const mapComplete = (raw: any): any => {
  const { objections_used: _rawUsed, ...rest } = raw ?? {};
  return {
    ...rest,
    objectionsUsed: (Array.isArray(raw?.objections_used) ? raw.objections_used : []).map(
      (o: any): ObjectionUsedItem => ({
        content: String(o?.content ?? ''),
        guidance: typeof o?.guidance === 'string' ? o.guidance : null,
      }),
    ),
  };
};

export const practiceAPI = {
  create: (payload: { skill_id?: number; scenario: string }) =>
    apiClient.request<any>('POST', '/api/v1/practices', payload),
  turn: (sessionId: number, message: string) =>
    apiClient.request<any>('POST', `/api/v1/practices/${sessionId}/turn`, { message }),
  // complete：评分链同步等 LLM，超时放宽到 120s（决策 11，与网关 carve-out 对齐）
  complete: (sessionId: number) =>
    apiClient
      .request<any>('POST', `/api/v1/practices/${sessionId}/complete`, {}, AI_SYNC_TIMEOUT_MS)
      .then(mapComplete),
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
    /** 提取来源陪练会话 ID（2026-09-01 审核溯源）：extract 链路带入，后端校验归属并留档 */
    source_session_ids?: number[];
    /** 提取来源拜访 ID（2026-09-10 溯源扩拜访）：extract 链路带入，后端校验归属并留档 */
    source_visit_ids?: number[];
  }) => apiClient.request<any>('POST', '/api/v1/skill-packages/release', payload),
  mySkills: (params?: { page?: number; page_size?: number }) =>
    apiClient.request<any>('GET', '/api/v1/skill-packages/mine', params),
  /**
   * 三期 P：从本人对话记录提取风格 Skill 草稿（同步 LLM，120s 超时）。
   * sessionIds（陪练会话：本人 + completed + 单会话 ≥3 轮）与 visitIds（拜访记录：
   * 本人 + 非取消 + 单条 ≥3 条代表发言）两类可选、合计 1~10 条（2026-09-10 扩拜访，
   * 门槛在后端校验）；返回草稿 {name, description, content, style_tags, skill_weights,
   * is_anonymous}，与 releaseSkill payload 同构（直接预填发布表单）。
   * 失败语义：4002 = 今日 3 次限额已满 / 4003 = LLM 生成失败可重试 / 4xx 中文 message = 会话不合格。
   */
  extractDraft: (sessionIds: number[], visitIds?: number[]) =>
    apiClient.request<any>(
      'POST',
      '/api/v1/skill-packages/extract-draft',
      visitIds?.length
        ? { session_ids: sessionIds, visit_ids: visitIds }
        : { session_ids: sessionIds },
      AI_SYNC_TIMEOUT_MS,
    ),
};

export const twinAPI = {
  setStyle: (twinId: number, style: Record<string, string>) =>
    apiClient.request<any>('PUT', `/api/v1/specialists/${twinId}/style`, style),
  pause: (twinId: number) => apiClient.request<any>('POST', `/api/v1/specialists/${twinId}/pause`, {}),
  resume: (twinId: number) => apiClient.request<any>('POST', `/api/v1/specialists/${twinId}/resume`, {}),
  /**
   * 删除本人分身（2026-09-15）：后端软删 status=disabled，对话/审计历史留存（合规口径），
   * rep 列表过滤 disabled 即"消失"；官方/他人分身 403。
   */
  delete: (twinId: number) =>
    apiClient.request<any>('DELETE', `/api/v1/specialists/${twinId}`),
  /**
   * 2026-09-10 从历史记录生成分身：可选素材列表（本人三类对话记录，各最近 20 条）。
   * chats 项 id 为 session_id 字符串；visits 项 visit_id / practices 项 session_id 为整数。
   */
  styleSources: () =>
    apiClient.request<any>('GET', '/api/v1/specialists/style-sources'),
  /**
   * 创建分身统一入口（2026-09-15 向导合并，原 styleTest 收编）：
   * answers = 5 题问卷（0-2 索引，映射风格三枚举）；sources = 1~10 条 {type, id}
   * （素材合计 ≥10 条代表发言，门槛在后端校验，同步 LLM 120s 超时）；name 可选。
   * 三者组合：answers+sources=向导全量 / 仅 sources=记录提取 / 仅 answers=纯问卷（不调 LLM）。
   * 失败语义：4002 = 今日 3 次限额已满（仅素材路径）/ 4003 = LLM 生成失败可重试。
   */
  styleFromRecords: (
    sources: Array<{ type: 'chat' | 'visit' | 'practice'; id: string | number }>,
    name?: string,
    answers?: number[],
  ) => {
    const payload: Record<string, unknown> = { sources };
    if (name) payload.name = name;
    if (answers) payload.answers = answers;
    return apiClient.request<any>(
      'POST',
      '/api/v1/specialists/style-from-records',
      payload,
      AI_SYNC_TIMEOUT_MS,
    );
  },
};
