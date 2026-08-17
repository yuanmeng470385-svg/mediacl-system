import client from './client';
import type { ApiResponse, PaginatedResponse, DoctorCert } from '../types';

export interface DoctorCertReviewPayload {
  verdict: 'approve' | 'reject';
  reason?: string;
}

export const doctorCertAPI = {
  list: (params?: {
    page?: number;
    page_size?: number;
    cert_status?: string;
    keyword?: string;
  }) => client.get<PaginatedResponse<DoctorCert>>('/doctors/certs', { params }),

  review: (id: number, data: DoctorCertReviewPayload) =>
    client.put<ApiResponse<DoctorCert>>(`/doctors/certs/${id}/review`, data),
};
