/**
 * 医生端新人引导文案（价值叙事开场 → 操作说明收尾）。
 */

export interface OnboardingSlide {
  icon: string;
  title: string;
  bullets: string[];
}

/** AsyncStorage 完成标记（跳过=完成；「我的 → 功能引导」清除后可重看） */
export const DOCTOR_ONBOARDING_KEY = 'onboarding.doctor.v1';

export const DOCTOR_ONBOARDING_SLIDES: OnboardingSlide[] = [
  {
    icon: '🩺',
    title: '欢迎，医生',
    bullets: [
      '医学问答基于药企知识库，回答带文献引用、可溯源',
      '订阅数字员工后可随时在线咨询，学术内容每日更新',
      '你的每一次反馈都会让推送更贴合你的临床领域',
    ],
  },
  {
    icon: '🪪',
    title: '先完成医师认证',
    bullets: [
      '上传执业资质（我的 → 医师认证）',
      '通过审核后解锁完整功能，学术触达更有针对性',
    ],
  },
  {
    icon: '🗺️',
    title: '三个 Tab 各管一摊',
    bullets: [
      '问答：医学问题随问，引用原文可点开',
      '分身：订阅/管理数字员工，对话历史与收藏',
      '我的：收件箱（学术卡片）、患教工具、偏好设置',
    ],
  },
  {
    icon: '🌅',
    title: '最后：偏好与简报',
    bullets: [
      '偏好设置：选择关注的疾病领域，夜间简报每天早晨推送',
      '患教工具：选模板一键生成患者教育材料，可直接分享',
      '本引导随时可重看：我的 → 功能引导',
    ],
  },
];
