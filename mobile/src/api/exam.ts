/**
 * 合规培训考试 API —— 契约映射层（二期 F）
 *
 * 后端端点（经网关转发，见 auth-service）：
 *   - GET  /api/v1/training-materials                          培训材料列表（page/page_size）
 *   - POST /api/v1/exams/start                                开考（question_count）
 *   - POST /api/v1/exams/submit                               交卷（answers）
 *   - GET  /api/v1/exams/records/me                           本人考试记录
 *   - POST /api/v1/qualifications/commitment/sign             承诺书签署（短信验证码）
 *   - POST /api/v1/qualifications/commitment/send-code        发送签署验证码（空 body {}）
 *
 * apiClient.request 第三参数对 GET 是 query params、对 POST 是 body（JSON.stringify）。
 * 返回值为后端统一响应里的 data 字段（request 内部已解包，不再套 data 层）。
 */
import { apiClient } from './client';
import type { ExamQuestion, ExamRecord, TrainingMaterial } from '../types';

export interface ExamAnswer { question_id: number; selected: number[]; }

export const examAPI = {
  listMaterials: (params?: { page?: number; page_size?: number }) =>
    apiClient.request<{ items: TrainingMaterial[]; total: number }>(
      'GET',
      '/api/v1/training-materials',
      params
    ),

  startExam: (question_count = 10) =>
    apiClient.request<{ questions: ExamQuestion[] }>('POST', '/api/v1/exams/start', { question_count }),

  submitExam: (answers: ExamAnswer[]) =>
    apiClient.request<ExamRecord>('POST', '/api/v1/exams/submit', { answers }),

  myRecords: () =>
    apiClient.request<any>('GET', '/api/v1/exams/records/me'),

  signCommitment: (code: string) =>
    apiClient.request<{ commitment_signed: boolean }>('POST', '/api/v1/qualifications/commitment/sign', { code }),

  sendCommitmentCode: () =>
    apiClient.request<{ expire_seconds: number }>('POST', '/api/v1/qualifications/commitment/send-code', {}),
};
