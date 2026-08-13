import client from './client';
import type { ApiResponse, PaginatedResponse } from '../types';

/** 拜访记录（visit-service VisitRecord.to_dict() + hcp_name 附注） */
export interface VisitRecord {
  id: number;
  hcp_id?: number | null;
  hcp_name?: string | null;
  user_id?: number | null;
  product_id?: number | null;
  visit_time?: string | null;
  duration_minutes?: number | null;
  status: 'in_progress' | 'completed' | 'cancelled';
  conversation_transcript?: string | null;
  ai_summary?: string | null;
  key_points?: unknown[] | null;
  hcp_interests?: unknown[] | null;
  hcp_objections?: unknown[] | null;
  follow_up_suggestions?: unknown[] | null;
  sentiment?: string | null;
  compliance_flags?: Record<string, unknown> | null;
  next_visit_plan?: unknown | null;
  created_at?: string | null;
  updated_at?: string | null;
}

/** 拜访任务（visit-service Task.to_dict()） */
export interface VisitTask {
  id: number;
  visit_id?: number | null;
  title: string;
  description?: string | null;
  task_type?: string | null;
  due_date?: string | null;
  channel?: string | null;
  status: 'open' | 'done' | 'cancelled';
  created_at?: string | null;
}

export const visitAPI = {
  list: (params?: {
    page?: number;
    page_size?: number;
    status?: string;
    user_id?: number;
    hcp_id?: number;
    date_from?: string;
    date_to?: string;
  }) =>
    client.get<PaginatedResponse<VisitRecord>>('/visits', { params }),

  detail: (id: number) =>
    client.get<ApiResponse<VisitRecord>>(`/visits/${id}`),

  tasks: (id: number) =>
    client.get<ApiResponse<VisitTask[]>>(`/visits/${id}/tasks`),
};
