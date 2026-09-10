import client from './client';
import type {
  ApiResponse, ObjectionScript, PaginatedResponse, PracticeTranscript, VisitSourceTranscript,
} from '../types';

/** 陪练域管理端接口（异议话术库 3.2(5) + 审核溯源 2026-09-01/09-10） */
export const practiceAPI = {
  // 异议话术库：列表/审核（后端 OBJECTION_ADMIN_ROLES 四角色）
  objectionList: (params?: { page?: number; page_size?: number; review_status?: string; scenario_type?: string }) =>
    client.get<PaginatedResponse<ObjectionScript>>('/practices/objection-scripts', { params }),
  objectionReview: (id: number, data: { verdict: 'approve' | 'reject'; reason?: string }) =>
    client.post<ApiResponse<ObjectionScript>>('/practices/objection-scripts/' + id + '/review', data),
  // 审核溯源：受控查看陪练会话原始 transcript（后端记 practice_source_view 审计）
  reviewTranscript: (sessionId: number) =>
    client.get<ApiResponse<PracticeTranscript>>('/practices/' + sessionId + '/review-transcript'),
  // 审核溯源：受控查看拜访转写原文（后端记 visit_source_view 审计，2026-09-10 扩拜访）
  visitTranscript: (visitId: number) =>
    client.get<ApiResponse<VisitSourceTranscript>>('/skill-packages/source-visits/' + visitId),
};
