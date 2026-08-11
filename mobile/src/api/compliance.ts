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
  /**
   * 红线速览列表（rep 面向用户）。
   * 走 /redlines 净化端点（rules.py）—— /rules 含 patterns/content 已收紧为
   * admin/manager/compliance 专属，移动端仅需展示字段，不暴露匹配细节。
   */
  async listRules(): Promise<ComplianceRule[]> {
    const data = await apiClient.request<{ items: ComplianceRule[] }>(
      'GET',
      '/api/v1/compliance/redlines'
    );
    return data.items || [];
  },
};
