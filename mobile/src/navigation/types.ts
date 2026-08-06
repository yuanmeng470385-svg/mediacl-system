/**
 * MedAgent 移动端 - 导航类型定义
 */

import type { DigitalSpecialist, HCP, VisitRecord } from '../types';

// ========== 主导航 ==========
export type MainTabParamList = {
  Home: undefined;
  Specialists: undefined;
  HCPs: undefined;
  Profile: undefined;
};

// ========== Stack 导航 ==========
export type RootStackParamList = {
  // 认证
  Login: undefined;
  // 主 Tab
  MainTabs: undefined;
  // 数字专员
  Chat: { specialistId: number; specialistName: string };
  // 拜访流程
  VisitPrepare: { hcpId: number; hcpName: string; productId?: number };
  VisitInProgress: { visitId: number; hcpName: string };
  VisitEnd: { visitId: number };
  VisitDetail: { visitId: number };
  // 医生
  HCPDetail: { hcpId: number };
  HCPProfile: { hcpId: number };
  // 学术
  Content: undefined;
  ContentDetail: { contentId: number };
  // 合规
  ComplianceManual: undefined;
  ComplianceRuleDetail: { ruleCode: string };
  // 设置
  Settings: undefined;
  NotificationSettings: undefined;
  HelpCenter: undefined;
};

// ========== 路由参数类型导出 ==========
export type ChatScreenParams = {
  specialistId: number;
  specialistName: string;
};

export type VisitPrepareParams = {
  hcpId: number;
  hcpName: string;
  productId?: number;
};

export type VisitInProgressParams = {
  visitId: number;
  hcpName: string;
};

export type VisitEndParams = {
  visitId: number;
};

export type HCPDetailParams = {
  hcpId: number;
};
