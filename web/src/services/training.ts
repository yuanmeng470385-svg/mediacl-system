import client from './client';
import type { ApiResponse, PaginatedResponse, ExamQuestion, ExamRecord, TrainingMaterial } from '../types';

export const trainingAPI = {
  listMaterials: (params?: { page?: number; page_size?: number; material_type?: string; keyword?: string }) =>
    client.get<PaginatedResponse<TrainingMaterial>>('/training-materials', { params }),
  createMaterial: (data: { title: string; material_type: string; content: string }) =>
    client.post<ApiResponse<TrainingMaterial>>('/training-materials', data),
  updateMaterial: (id: number, data: { title: string; material_type: string; content: string }) =>
    client.put<ApiResponse<TrainingMaterial>>(`/training-materials/${id}`, data),
  archiveMaterial: (id: number) => client.delete<ApiResponse<TrainingMaterial>>(`/training-materials/${id}`),

  listQuestions: (params?: { page?: number; page_size?: number; review_status?: string; keyword?: string }) =>
    client.get<PaginatedResponse<ExamQuestion>>('/exams/questions', { params }),
  createQuestion: (data: { question_type: string; content: string; options: string[]; answer: number[]; material_id?: number | null }) =>
    client.post<ApiResponse<ExamQuestion>>('/exams/questions', data),
  reviewQuestion: (id: number, data: { verdict: 'approve' | 'reject'; reason?: string }) =>
    client.post<ApiResponse<ExamQuestion>>(`/exams/questions/${id}/review`, data),
  aiGenerate: (data: { material_id: number; count?: number; question_type?: string }) =>
    client.post<ApiResponse<any[]>>('/exams/questions/ai-generate', data),

  listRecords: (params?: { page?: number; page_size?: number }) =>
    client.get<PaginatedResponse<ExamRecord>>('/exams/records', { params }),
};
