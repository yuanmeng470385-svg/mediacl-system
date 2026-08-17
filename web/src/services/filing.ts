import client from './client';
import type { ApiResponse, PaginatedResponse, Qualification } from '../types';

export interface QualificationReviewPayload {
  verdict: 'approve' | 'reject';
  reason?: string;
  filing_expire_date?: string;
}

export const filingAPI = {
  list: (params?: {
    page?: number;
    page_size?: number;
    audit_status?: string;
    filing_status?: string;
    keyword?: string;
  }) => client.get<PaginatedResponse<Qualification>>('/qualifications', { params }),

  review: (id: string, data: QualificationReviewPayload) =>
    client.put<ApiResponse<Qualification>>(`/qualifications/${id}/review`, data),
};
