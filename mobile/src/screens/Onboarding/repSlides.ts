/**
 * 代表端新人引导文案（价值叙事开场 → 操作说明收尾）。
 * 末屏是操作说明（合规培训深藏入口的重看路径），tourSteps.test 同款防漂移思路见 __tests__。
 */

export interface OnboardingSlide {
  icon: string;
  title: string;
  bullets: string[];
}

/** AsyncStorage 完成标记（跳过=完成；设置→通用→功能引导 清除后可重看） */
export const REP_ONBOARDING_KEY = 'onboarding.rep.v1';

export const REP_ONBOARDING_SLIDES: OnboardingSlide[] = [
  {
    icon: '🤖',
    title: '你的 AI 数字员工已就位',
    bullets: [
      '7×24 小时替你值守医生的医学问答，回答带文献引用',
      '拜访结束自动生成结构化总结，并创建后续跟进任务',
      '每一句话都经过三层合规门禁，安全可溯源',
    ],
  },
  {
    icon: '🎙️',
    title: '一场拜访的完整动线',
    bullets: [
      '工作台点「开始拜访」→ 自动生成拜访前准备要点',
      '拜访中：录音实时转写 + AI 关键节点话术推荐',
      '结束：AI 总结、异议沉淀、医生画像自动更新',
    ],
  },
  {
    icon: '🗺️',
    title: '四个 Tab 各管一摊',
    bullets: [
      '工作台：今日拜访、任务与进度',
      '对话：与数字专员随时问答，可收藏历史',
      '医生：搜索档案、查看互动历史',
      '我的：分身分享、夜间简报、AI 陪练、Skill 广场',
    ],
  },
  {
    icon: '🧭',
    title: '最后一件重要的事',
    bullets: [
      '备案资质、合规培训与考试、承诺书签署入口：\n我的 → 顶部用户卡 → 设置 → 备案与资质（页面最底部）',
      '本引导随时可重看：设置 → 通用 → 功能引导',
      '有任何问题先去「帮助中心」翻一翻',
    ],
  },
];
