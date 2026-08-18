/**
 * 医学 AI 问答 API（Task 5 端点契约）：
 *   - qa: POST /api/v1/medical/qa（检索+生成+引用+合规双检+审计都在服务端完成）
 *
 * 响应 {answer, citations, disclaimer, blocked, violations, knowledge_empty}；
 * disclaimer 为强制展示文案（屏幕必须在每条回答下渲染），blocked 时 answer
 * 已是服务端安全话术。
 */
import { apiClient } from './client';
import type { MedicalAnswer } from '../types';

export const medicalAPI = {
  qa: (question: string) =>
    apiClient.request<MedicalAnswer>('POST', '/api/v1/medical/qa', { question }),
};
