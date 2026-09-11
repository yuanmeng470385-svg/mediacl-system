import client from './client';
import type {
  ApiResponse, ObjectionScript, PaginatedResponse, PracticeTranscript, VisitSourceTranscript,
} from '../types';

/** 陪练域管理端接口（异议话术库 3.2(5) + 审核溯源 2026-09-01/09-10） */
export const practiceAPI = {
  // 异议话术库：列表/审核（后端 OBJECTION_ADMIN_ROLES 四角色）
  objectionList: (params?: { page?: number; page_size?: number; review_status?: string; scenario_type?: string }) =>
    client.get<PaginatedResponse<ObjectionScript>>('/practices/objection-scripts', { params }),
  // 异议话术批（2026-09-10）：创建/编辑走送审流——创建即 pending；编辑仅 pending/rejected 可改，
  // 保存后重置 pending 重新送审（approved 不可改，后端 4001）
  objectionCreate: (data: { scenario_type: string; objection_content: string; response_guidance?: string; version?: string }) =>
    client.post<ApiResponse<ObjectionScript>>('/practices/objection-scripts', data),
  objectionUpdate: (id: number, data: { scenario_type: string; objection_content: string; response_guidance?: string; version?: string }) =>
    client.put<ApiResponse<ObjectionScript>>('/practices/objection-scripts/' + id, data),
  // AI 起草（同步 LLM，网关 120s carve-out）：按场景生成 3~5 条草稿，不落库——确认后逐条 objectionCreate 入库送审
  objectionAiGenerate: (scenario: string) =>
    client.post<ApiResponse<{ scenario: string; items: Array<{ scenario_type: string; objection_content: string; response_guidance: string | null }> }>>(
      '/practices/objection-scripts/ai-generate', { scenario }, { timeout: 120000 },
    ),
  // 真实数据提取（数据飞轮）：从最近陪练 AI 医生发言 + 拜访医生异议/转写提取草稿，同样不落库
  objectionExtractDraft: () =>
    client.post<ApiResponse<{ items: Array<{ scenario_type: string; objection_content: string; response_guidance: string | null }>; sources: { practice_sessions: number; visits: number } }>>(
      '/practices/objection-scripts/extract-draft', {}, { timeout: 120000 },
    ),
  objectionReview: (id: number, data: { verdict: 'approve' | 'reject'; reason?: string }) =>
    client.post<ApiResponse<ObjectionScript>>('/practices/objection-scripts/' + id + '/review', data),
  // 审核溯源：受控查看陪练会话原始 transcript（后端记 practice_source_view 审计）
  reviewTranscript: (sessionId: number) =>
    client.get<ApiResponse<PracticeTranscript>>('/practices/' + sessionId + '/review-transcript'),
  // 审核溯源：受控查看拜访转写原文（后端记 visit_source_view 审计，2026-09-10 扩拜访）
  visitTranscript: (visitId: number) =>
    client.get<ApiResponse<VisitSourceTranscript>>('/skill-packages/source-visits/' + visitId),
};
