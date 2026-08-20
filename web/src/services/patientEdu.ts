import client from './client';
import type { ApiResponse, PaginatedResponse, PatientEduTemplate, EduContentRecord } from '../types';

export const patientEduAPI = {
  list: (params?: { page?: number; page_size?: number; disease_area?: string }) =>
    client.get<PaginatedResponse<PatientEduTemplate>>('/patient-edu/templates', { params }),
  create: (data: { title: string; disease_area: string; content: string }) =>
    client.post<ApiResponse<PatientEduTemplate>>('/patient-edu/templates', data),
  review: (id: number, data: { verdict: 'approve' | 'reject'; reason?: string }) =>
    client.post<ApiResponse<PatientEduTemplate>>(`/patient-edu/templates/${id}/review`, data),
  reviewQueue: (params?: { page?: number; page_size?: number }) =>
    client.get<PaginatedResponse<EduContentRecord>>('/patient-edu/review-queue', { params }),
  reviewRecord: (id: number, data: { verdict: 'approve' | 'reject'; reason?: string }) =>
    client.post<ApiResponse<EduContentRecord>>(`/patient-edu/${id}/review`, data),
};
