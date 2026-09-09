/**
 * 代表端陪玩式引导步骤（2026-09-09 v2）：价值叙事开场 → 4 个「去试试」体验步 → 操作说明收尾。
 * tryRoute 为编译期锁定的真实路由名（keyof RootStackParamList | keyof MainTabParamList，
 * 路由改名时本文件 tsc 炸出——比 web 端 menuConfig 防漂移断言更前移）。
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
export const REP_GUIDE_DONE_KEY = 'onboarding.rep.v2';
/** 断点续传进度（current 步号） */
export const REP_GUIDE_PROGRESS_KEY = 'onboarding.rep.progress';

export const REP_GUIDE_STEPS: GuideStep[] = [
  {
    icon: '🤖',
    title: '你的 AI 数字员工已就位',
    bullets: [
      '7×24 小时替你值守医生的医学问答，回答带文献引用',
      '拜访结束自动生成结构化总结，并创建后续跟进任务',
      '每一句话都经过三层合规门禁，安全可溯源',
      '接下来带你亲手逛一遍核心功能——每一步都可以「去试试」',
    ],
  },
  {
    icon: '🏠',
    title: '工作台：一场拜访的起点',
    bullets: [
      '点「开始拜访」→ AI 自动生成拜访前准备要点',
      '拜访中：录音实时转写 + AI 话术推荐',
      '结束：AI 总结、异议沉淀、医生画像自动更新',
    ],
    tryRoute: 'Home',
    tryName: '工作台',
    tryHint: '看看「开始拜访」按钮在哪（不用真的开始）。「今日拜访」与任务也都在这页。逛完点顶部蓝色引导条继续。',
  },
  {
    icon: '💬',
    title: '对话：数字专员随时待命',
    bullets: [
      '选一个专员直接提问，回答附知识库引用',
      '遇到合规红线会被实时拦截保护你',
      '对话可收藏、可反馈好坏',
    ],
    tryRoute: 'Specialists',
    tryName: '对话',
    tryHint: '点开一个专员，随便问一个医学问题（如「适应症是什么」）看看引用溯源。逛完点顶部蓝色引导条继续。',
  },
  {
    icon: '👨‍⚕️',
    title: '医生：档案与互动历史',
    bullets: [
      '搜索医生档案，查看基本信息与标签',
      '每次拜访、每轮对话都沉淀成互动历史',
      'AI 画像帮你记住每位医生的学术偏好',
    ],
    tryRoute: 'HCPs',
    tryName: '医生',
    tryHint: '搜索或点开一位医生，看看互动历史与 AI 画像。逛完点顶部蓝色引导条继续。',
  },
  {
    icon: '🛡️',
    title: '合规中心：备案与培训',
    bullets: [
      '备案资质上传与状态查询（有效期临近会提醒）',
      '合规培训材料、在线考试、承诺书签署都在这里',
      '这是藏得最深、也最重要的页面',
    ],
    tryRoute: 'ComplianceCenter',
    tryName: '合规中心',
    tryHint: '看看你的备案状态和培训考试入口（在「我的」里也能进来）。逛完点顶部蓝色引导条继续。',
  },
  {
    icon: '🧭',
    title: '最后几件事',
    bullets: [
      '「我的」页还有：分身分享、夜间简报、AI 陪练、Skill 广场',
      '本引导随时可重看：我的 → 设置 → 功能引导',
      '有问题先去「帮助中心」翻一翻（含合规红线清单）',
    ],
  },
];
