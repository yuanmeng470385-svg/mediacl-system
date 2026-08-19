import client from './client';
import type {
  ApiResponse, ComplianceDailySummary, ComplianceTrends, ConvSearchItem,
  PaginatedResponse, ReviewQueueItem, Specialist, SpecialistMonitor,
} from '../types';

export const monitorAPI = {
  dailySummary: (days = 7) =>
    client.get<ApiResponse<ComplianceDailySummary>>('/compliance/daily-summary', { params: { days } }),
  trends: (days = 30) =>
    client.get<ApiResponse<ComplianceTrends>>('/compliance/trends', { params: { days } }),
  reviewQueue: () =>
    client.get<ApiResponse<{ items: ReviewQueueItem[]; threshold: number; window_hours: number }>>('/specialists/review-queue'),

  convSearch: (params?: { page?: number; page_size?: number; keyword?: string; user_id?: number; specialist_id?: number; date_from?: string; date_to?: string }) =>
    client.get<PaginatedResponse<ConvSearchItem>>('/conversations/search', { params }),

  specialistMonitor: (params?: { page?: number; page_size?: number; status?: string; official?: boolean }) =>
    client.get<PaginatedResponse<SpecialistMonitor>>('/specialists/monitor', { params }),
  freeze: (id: number, reason: string) =>
    client.post<ApiResponse<SpecialistMonitor>>(`/specialists/${id}/freeze`, { reason }),
  unfreeze: (id: number) =>
    client.post<ApiResponse<SpecialistMonitor>>(`/specialists/${id}/unfreeze`, {}),

  // 创建官方公共数字员工（is_official 固定 true，医学部/合规部维护）
  createOfficial: (data: { name: string; product_id: number }) =>
    client.post<ApiResponse<Specialist>>('/specialists', { ...data, is_official: true }),
};
