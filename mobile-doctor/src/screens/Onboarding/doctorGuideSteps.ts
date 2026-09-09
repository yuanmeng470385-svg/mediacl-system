/**
 * 医生端陪玩式引导步骤（2026-09-09 v2）：价值叙事开场 → 4 个「去试试」体验步 → 操作说明收尾。
 * tryRoute 为编译期锁定的真实路由名（keyof RootStackParamList | keyof MainTabParamList，
 * 路由改名时本文件 tsc 炸出）。
 */
import type { RootStackParamList, MainTabParamList } from '../../navigation/types';

export type GuideRoute = keyof RootStackParamList | keyof MainTabParamList;

/** 引导步（tryRoute 省略 = 纯讲解步） */
export interface GuideStep {
  icon: string;
  title: string;
  bullets: string[];
  /** 「去试试」导航目标（Tab 名或 Stack 屏名） */
  tryRoute?: GuideRoute;
  /** 目标页名（召回卡文案） */
  tryName?: string;
  /** 到页后体验提示（召回卡正文/顶部浮条） */
  tryHint?: string;
}

/** AsyncStorage 完成标记（跳过=完成；v2=陪玩式升级，看过 v1 轮播的用户重弹） */
export const DOCTOR_GUIDE_DONE_KEY = 'onboarding.doctor.v2';
/** 断点续传进度（current 步号） */
export const DOCTOR_GUIDE_PROGRESS_KEY = 'onboarding.doctor.progress';

export const DOCTOR_GUIDE_STEPS: GuideStep[] = [
  {
    icon: '🩺',
    title: '欢迎，医生',
    bullets: [
      '医学问答基于药企知识库，回答带文献引用、可溯源',
      '订阅数字员工后可随时在线咨询，学术内容每日更新',
      '你的每一次反馈都会让推送更贴合你的临床领域',
      '接下来带你亲手逛一遍核心功能——每一步都可以「去试试」',
    ],
  },
  {
    icon: '🪪',
    title: '第一步：医师认证',
    bullets: [
      '上传执业资质照片，平台审核通过即解锁完整功能',
      '审核状态在「我的」页随时可查',
      '未认证也能问、能订阅，认证后学术触达更有针对性',
    ],
    tryRoute: 'CertUpload',
    tryName: '医师认证',
    tryHint: '看看资质上传入口长什么样（不用真的上传）。逛完点顶部蓝色引导条继续。',
  },
  {
    icon: '💬',
    title: '第二步：医学问答',
    bullets: [
      '直接提问，回答附知识库引用，原文可点开核对',
      'AI 生成的回答都带免责声明，仅供学术参考',
      '回答可反馈有用/无用，帮助推送越来越准',
    ],
    tryRoute: 'MedicalQA',
    tryName: '问答',
    tryHint: '随便问一个你关心的问题（如「XX 药的适应症」），看看引用溯源。逛完点顶部蓝色引导条继续。',
  },
  {
    icon: '👥',
    title: '第三步：订阅数字员工',
    bullets: [
      '医药代表的数字分身 7×24 替他值守你的提问',
      '订阅需知情同意，对话数据经你授权使用',
      '不想要的分身随时屏蔽，不影响代表本人',
    ],
    tryRoute: 'MyTwins',
    tryName: '分身',
    tryHint: '看看你已订阅的数字员工列表，点进一个试试对话入口。逛完点顶部蓝色引导条继续。',
  },
  {
    icon: '📬',
    title: '第四步：学术卡片收件箱',
    bullets: [
      '代表推送的学术卡片集中在这，点开即记录阅读',
      '卡片可反馈「有用」或直接追问，代表看得到',
      '新卡片会发站内通知提醒',
    ],
    tryRoute: 'Inbox',
    tryName: '学术卡片收件箱',
    tryHint: '看看收件箱里的学术卡片（没有内容也正常）。逛完点顶部蓝色引导条继续。',
  },
  {
    icon: '🧭',
    title: '最后几件事',
    bullets: [
      '「我的」页还有：患教工具、官方广场、偏好设置、收藏历史、隐私中心',
      '偏好设置：选择关注领域，内容推送更精准',
      '本引导随时可重看：我的 → 功能引导',
    ],
  },
];
