/**
 * 收藏历史 API（复用既有端点，二期 I 医生端）：
 *   - listFavorites: GET /api/v1/favorites（本人收藏问答分页，items 为问答快照）
 *   - removeFavorite: DELETE /api/v1/favorites/{favoriteId}（取消收藏）
 *   - toggleFavorite: POST /api/v1/conversations/{conversationId}/favorite（会话级收藏开关，
 *     2026-09-11 死页清理批补——此前 TwinChat 无收藏入口，收藏历史页恒空成死页）
 *
 * 后端挂 specialist-service conversations.py 的 favorites_router（toggle 在
 * conversations_router），返回 paginate 形状 {items,total,page,page_size}，本层直接透传。
 */
import { apiClient } from './client';
import type { FavoriteItem, PaginatedResponse } from '../types';

export const favoritesAPI = {
  listFavorites: () =>
    apiClient.request<PaginatedResponse<FavoriteItem>>('GET', '/api/v1/favorites'),

  removeFavorite: (favoriteId: number) =>
    apiClient.request<null>('DELETE', `/api/v1/favorites/${favoriteId}`),

  /** 收藏/取消收藏（后端是 toggle，无 body；与代表端 specialistAPI.toggleFavorite 同款） */
  toggleFavorite: (conversationId: number) =>
    apiClient.request<{ is_favorite: boolean }>(
      'POST',
      `/api/v1/conversations/${conversationId}/favorite`
    ),
};
