/**
 * 合规 API
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

  /** 合规文本检查 */
  async checkContent(content: string, context?: Record<string, any>): Promise<{
    blocked: boolean;
    violations: { rule_code: string; description: string; severity: string }[];
    risk_level: 'none' | 'low' | 'medium' | 'high';
  }> {
    return apiClient.request(
      'POST',
      '/api/v1/compliance/check',
      { content, context }
    );
  },
};
