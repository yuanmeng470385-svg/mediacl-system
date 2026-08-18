/**
 * 分身分享链接 API —— 契约映射层（后端 specialist-service /api/v1/share-links）
 *
 * 后端 share_links 模型（share_link.to_dict）：{id, twin_id, twin_name, url_token,
 * share_url, add_count, expire_at, created_at}。生成/追踪为 C 计划，B 只建表 + 激活接收侧；
 * 本文件是代表端生成/列表的唯一映射点。
 */
import { apiClient } from './client';
import type { ShareLinkItem } from '../types';

export const shareAPI = {
  /** 生成分享链接（expire_days 可省，后端据此计算 expire_at） */
  create: (twinId: number, expireDays?: number) =>
    apiClient.request<ShareLinkItem>(
      'POST',
      '/api/v1/share-links',
      { twin_id: twinId, ...(expireDays !== undefined ? { expire_days: expireDays } : {}) }
    ),

  /** 我的分享链接列表 */
  list: () => apiClient.request<ShareLinkItem[]>('GET', '/api/v1/share-links'),
};
