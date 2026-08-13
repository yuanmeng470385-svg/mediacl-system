/**
 * 拜访任务 API —— 契约映射层（后端 visit-service /api/v1/tasks）
 *
 * 后端任务模型（task.to_dict）：{id, visit_id, title, description, task_type,
 * due_date, channel, status(open/done/cancelled), created_at}
 */
import { apiClient } from './client';
import type { PaginatedResponse } from '../types';

export type TaskStatus = 'open' | 'done' | 'cancelled';

export interface TaskItem {
  id: number;
  visit_id?: number | null;
  title: string;
  description?: string | null;
  task_type: string;
  due_date?: string | null;
  channel?: string | null;
  status: TaskStatus;
  created_at?: string;
}

/** 任务类型 → 中文标签（未知类型显示原值） */
export const TASK_TYPE_LABELS: Record<string, string> = {
  follow_up: '跟进',
  call: '电话',
  send_material: '发送资料',
  book_appointment: '预约拜访',
  email: '邮件',
};

export const taskAPI = {
  /** 我的任务列表（解包 pagination 嵌套） */
  async list(params?: {
    status?: string;
    page?: number;
    page_size?: number;
  }): Promise<PaginatedResponse<TaskItem>> {
    const raw = await apiClient.request<any>(
      'GET',
      '/api/v1/tasks',
      params
    );
    const items = Array.isArray(raw?.items) ? raw.items : [];
    const pagination = raw?.pagination ?? {};
    return {
      items: items.map(mapTaskItem),
      total: raw?.total ?? pagination?.total ?? items.length,
      page: raw?.page ?? pagination?.page ?? 1,
      page_size: raw?.page_size ?? pagination?.page_size ?? items.length,
    };
  },

  /** 更新任务状态（完成/取消/重开）：{"status": "done"|"cancelled"|"open"} */
  async updateStatus(taskId: number, status: TaskStatus): Promise<TaskItem> {
    const raw = await apiClient.request<any>(
      'PUT',
      `/api/v1/tasks/${taskId}`,
      { status }
    );
    return mapTaskItem(raw);
  },
};

function mapTaskItem(raw: any): TaskItem {
  return {
    id: raw?.id ?? 0,
    visit_id: raw?.visit_id ?? null,
    title: String(raw?.title ?? ''),
    description: raw?.description ? String(raw.description) : null,
    task_type: String(raw?.task_type ?? ''),
    due_date: raw?.due_date ?? null,
    channel: raw?.channel ? String(raw.channel) : null,
    status: (raw?.status === 'done' || raw?.status === 'cancelled' ? raw.status : 'open') as TaskStatus,
    created_at: raw?.created_at ?? undefined,
  };
}
