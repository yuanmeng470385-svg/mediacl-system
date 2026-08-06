import client from './client';
import type { ApiResponse } from '../types';

export interface SystemConfigItem {
  key: string;
  label: string;
  configured: boolean;
}

export interface SystemConfigData {
  items: SystemConfigItem[];
  info: {
    rate_limit_per_minute: number;
    log_level: string;
  };
}

export const systemAPI = {
  /** 系统配置状态（只读，admin；网关 GET /api/v1/system/config） */
  config: () => client.get<ApiResponse<SystemConfigData>>('/system/config'),
};
