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
  PerformanceStats: undefined;
  HelpCenter: undefined;
  ComplianceCenter: undefined;
  // 分身分享 & 夜间简报
  Share: undefined;
  BriefingList: undefined;
  BriefingDetail: { briefingId: number };
  // 站内通知中心（2026-09-03 业务审查批：通知三端零消费补齐）
  Notifications: undefined;
  // 学术卡片（二期 G）
  AcademicCardCreate: undefined;
  AcademicCardList: undefined;
  // AI 陪练 / Skill 广场 / 分身管理（二期 H）
  PracticeList: { skillId?: number } | undefined;
  PracticeChat: { sessionId: number };
  Plaza: undefined;
  TwinManage: undefined;
  // 从历史记录生成分身（2026-09-10）：选三类对话记录 → LLM 提取本人风格
  StyleSource: undefined;
  // Skill 生态（三期 J）
  SkillRelease: { draft?: SkillDraft } | undefined;
  MySkillList: undefined;
  // 从陪练对话提取风格草稿（三期 P）
  SkillExtract: undefined;
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

/**
 * 从陪练对话提取的风格 Skill 草稿（三期 P）：
 * specialist-service extract-draft 返回，与 releaseSkill payload 同构，
 * 由 SkillExtractScreen replace 到 SkillRelease 做表单预填。
 */
export type SkillDraft = {
  name: string;
  description: string;
  content: string;
  style_tags?: string[] | null;
  /** 沟通风格权重（枚举白名单与后端 skill_packages.py / specialists.py 对齐） */
  skill_weights?: {
    formal_level?: string;
    reply_length?: string;
    opening_mode?: string;
  };
  is_anonymous?: boolean;
  /** 提取来源会话 ID（2026-09-01 审核溯源）：extract 屏带入，release 提交时原样回传 */
  source_session_ids?: number[] | null;
  /** 提取来源拜访 ID（2026-09-10 溯源扩拜访）：extract 屏带入，release 提交时原样回传 */
  source_visit_ids?: number[] | null;
};
