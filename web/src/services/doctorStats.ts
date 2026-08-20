import client from './client';
import type { ApiResponse, DoctorActivity, TwinRankingItem } from '../types';

export const doctorStatsAPI = {
  activity: () => client.get<ApiResponse<DoctorActivity>>('/doctor-stats/activity'),
  twinRanking: () => client.get<ApiResponse<{ items: TwinRankingItem[] }>>('/doctor-stats/twin-ranking'),
};
