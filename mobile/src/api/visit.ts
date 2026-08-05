/**
 * 陪访助手 API
 */
import { apiClient } from './client';
import type {
  VisitRecord,
  VisitPrepareData,
  VisitSummary,
  ObjectionAlert,
  PaginatedResponse,
} from '../types';

export const visitAPI = {
  /** 拜访前准备——获取准备包 */
  async prepareVisit(params: {
    hcpId: number;
    productId?: number;
  }): Promise<VisitPrepareData> {
    return apiClient.request<VisitPrepareData>(
      'POST',
      '/api/v1/visits/pre-visit',
      params
    );
  },

  /** 开始拜访——创建拜访记录 */
  async startVisit(data: {
    hcp_id: number;
    product_id: number;
    planned_date: string;
    notes?: string;
  }): Promise<{ visit_id: number }> {
    return apiClient.request<{ visit_id: number }>(
      'POST',
      '/api/v1/visits/start',
      data
    );
  },

  /** 上传转写文本（实时转写） */
  async sendTranscript(
    visitId: number,
    data: {
      text?: string;
      audio_url?: string;
    }
  ): Promise<{
    transcript: string;
    objections: ObjectionAlert[];
    compliance_alerts: { rule_code: string; description: string }[];
  }> {
    return apiClient.request(
      'POST',
      `/api/v1/visits/${visitId}/transcript`,
      data
    );
  },

  /** 结束拜访——生成总结 */
  async endVisit(visitId: number): Promise<VisitSummary> {
    return apiClient.request<VisitSummary>(
      'POST',
      `/api/v1/visits/${visitId}/end`
    );
  },

  /** 获取拜访详情 */
  async getById(visitId: number): Promise<VisitRecord> {
    return apiClient.request<VisitRecord>(
      'GET',
      `/api/v1/visits/${visitId}`
    );
  },

  /** 拜访列表 */
  async list(params?: {
    page?: number;
    page_size?: number;
    status?: string;
    hcp_id?: number;
    start_date?: string;
    end_date?: string;
  }): Promise<PaginatedResponse<VisitRecord>> {
    return apiClient.request<PaginatedResponse<VisitRecord>>(
      'GET',
      '/api/v1/visits',
      params
    );
  },

  /** 生成跟进建议 */
  async followUp(visitId: number): Promise<{
    follow_up_plan: string;
    suggested_date: string;
  }> {
    return apiClient.request(
      'POST',
      `/api/v1/visits/${visitId}/follow-up`
    );
  },
};
