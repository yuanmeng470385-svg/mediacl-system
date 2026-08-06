/**
 * 合规 API
 *
 * 注意：不提供 checkContent —— /api/v1/compliance/check 在网关 INTERNAL_PATHS
 * 中（auth_middleware.py:42），需 X-Internal-Key，客户端调用恒 403。
 * 问题合规预检由服务端 answer_generator.py 在 chat 流程内完成。
 */
import { apiClient } from './client';
import type { ComplianceRule } from '../types';

export const complianceAPI = {
  /** 合规规则列表 */
  async listRules(): Promise<ComplianceRule[]> {
    return apiClient.request<ComplianceRule[]>(
      'GET',
      '/api/v1/compliance/rules'
    );
  },
};
