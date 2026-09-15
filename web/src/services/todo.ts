/** 管理端待办中心（2026-09-15 C 批）：auth + specialist 两端待办计数，并行拉取聚合 */
import client from './client';
import type { ApiResponse } from '../types';

export interface TodoItem {
  key: string;
  count: number;
}

export interface TodoSummary {
  items: TodoItem[];
}

export const todoAPI = {
  authSummary: () => client.get<ApiResponse<TodoSummary>>('/auth/todo-summary'),
  specialistSummary: () => client.get<ApiResponse<TodoSummary>>('/specialists/todo-summary'),
};

/** 拉全量待办（两端并行，任一失败不影响另一端），返回 key → count */
export async function fetchTodoCounts(): Promise<Record<string, number>> {
  const [authRes, specRes] = await Promise.allSettled([todoAPI.authSummary(), todoAPI.specialistSummary()]);
  const counts: Record<string, number> = {};
  for (const r of [authRes, specRes]) {
    if (r.status === 'fulfilled') {
      for (const it of r.value.data?.data?.items ?? []) counts[it.key] = it.count;
    }
  }
  return counts;
}

/** 合计（徽标数字）；0 = 无待办（Badge 自动隐藏用 0） */
export function sumTodoCounts(counts: Record<string, number>): number {
  return Object.values(counts).reduce((a, b) => a + b, 0);
}
