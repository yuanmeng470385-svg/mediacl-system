import client from './client';
import type { ApiResponse, CardStats } from '../types';

export const cardStatsAPI = {
  stats: (days = 30) =>
    client.get<ApiResponse<CardStats>>('/academic-cards/stats', { params: { days } }),
};
