/**
 * MedAgent 移动端 - 导航类型定义
 */

import type { DigitalSpecialist, HCP, VisitRecord, VisitSummary } from '../types';

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
  VisitEnd: { visitId: number; summary?: VisitSummary };
  VisitDetail: { visitId: number };
  // 医生
  HCPDetail: { hcpId: number };
  // 学术
  Content: undefined;
  ContentDetail: { contentId: number };
  // 合规
  ComplianceManual: undefined;
  // 合规培训考试（二期 F）
  TrainingMaterial: undefined;
  Exam: undefined;
  Commitment: undefined;
  // 任务 & 收藏
  TaskList: undefined;
  Favorites: undefined;
  // 设置
  Settings: undefined;
  NotificationSettings: undefined;
  HelpCenter: undefined;
  ComplianceCenter: undefined;
  // 分身分享 & 夜间简报
  Share: undefined;
  BriefingList: undefined;
  BriefingDetail: { briefingId: number };
  // 学术卡片（二期 G）
  AcademicCardCreate: undefined;
  AcademicCardList: undefined;
  // AI 陪练 / Skill 广场 / 分身管理（二期 H）
  PracticeList: { skillId?: number } | undefined;
  PracticeChat: { sessionId: number };
  Plaza: undefined;
  TwinManage: undefined;
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
  /**
   * VisitInProgress 已在导航前调过 endVisit 时传入结果；缺省时 VisitEndScreen 自己调一次。
   * retryable=true 表示后端写入 AI 失败占位串（拜访尚未结束，可重试 end_visit）。
   */
  summary?: VisitSummary & { retryable?: boolean };
};

export type HCPDetailParams = {
  hcpId: number;
};
