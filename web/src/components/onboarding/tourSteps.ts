/**
 * 三端新人引导 · web 端步骤配置（2026-09-09 A 档）。
 *
 * 设计：价值叙事开场（无 target 居中卡片）→ 菜单动线步（高亮左侧菜单项）→ 操作说明收尾（指向右上角"?"重看入口）。
 * 约束：menuPath 必须是 ROUTE_ACCESS 中该角色可访问、且 menuConfig 里真实存在的菜单项
 * （tourSteps.test.ts 有防漂移断言——角色权限表或菜单变更时测试会炸出来，对齐 M17 单一事实源哲学）。
 */

/** 引导步骤（AppTour 映射为 antd Tour step；menuPath 省略 = 居中叙事卡） */
export interface GuideStep {
  title: string;
  description: string;
  /** 高亮目标：菜单项 path（渲染为 [data-tour-menu=path]）；'help' = 右上角"?"按钮 */
  menuPath?: string;
}

const HELP: GuideStep = {
  title: '随时找回这份引导',
  description:
    '右上角的"?"按钮随时可以重看功能引导；左侧菜单已按你的角色过滤，只显示你有权限的功能。',
  menuPath: '__help__',
};

const ADMIN_STEPS: GuideStep[] = [
  {
    title: '欢迎来到你的数字员工团队',
    description:
      '你管理的不只是一套系统，而是一支 7×24 小时值守的 AI 数字员工：它们替代表回答医学问题、陪访后写总结、给医生推送学术卡片——每一句输出都经过三层合规门禁并留痕。',
  },
  {
    title: '先认识你的"员工"',
    description:
      '数字专员页是团队花名册：查看每个员工今天接了多少对话；3D 办公室里还能看到它们实时的工作状态。',
    menuPath: '/specialist/list',
  },
  {
    title: '给员工装上"大脑"',
    description: '知识库上传文献 → 审核 → 上架，上架即可被数字员工检索引用，回答自带引用溯源。',
    menuPath: '/knowledge/list',
  },
  {
    title: '药企监管台账在这里收口',
    description: '备案管理审核代表资质，合规培训跟踪考试与承诺书签署——面向监管检查的两本账。',
    menuPath: '/filing/list',
  },
  HELP,
];

const MANAGER_STEPS: GuideStep[] = [
  {
    title: '拜访数据不再靠代表手填',
    description:
      '代表 App 里录音自动转写、AI 生成结构化总结并自动建后续任务——你在管理端看到的是实时汇总部，不是几天后的周报。',
  },
  {
    title: '看每一场拜访的全程',
    description: '拜访管理页：转写原文、AI 总结、异议与关键节点、拜访时长，点进任意一场回看全程。',
    menuPath: '/visit/list',
  },
  {
    title: '数字员工也在替你干活',
    description: '分身监控：每个数字员工的对话量、好评率、待复核风险，按分身维度透视工作量与质量。',
    menuPath: '/specialist/monitor',
  },
  {
    title: '投入产出一眼看清',
    description: '运营统计：医生活跃度、分身排行、触达效果——评估数字员工投入产出的看板。',
    menuPath: '/doctor/stats',
  },
  HELP,
];

const COMPLIANCE_STEPS: GuideStep[] = [
  {
    title: '你是最后一道人工闭环',
    description:
      '系统里每一句 AI 输出都先过三层自动门禁（关键词/正则/LLM 语义）——被拦下的高风险内容汇聚到这里，由你做裁决。',
  },
  {
    title: '风险从这里闭环',
    description: '合规风控看板：待复核名单 → 查看对话上下文 → 冻结或放行，裁决全程审计留痕。',
    menuPath: '/compliance/monitor',
  },
  {
    title: '取证溯源的对话检索',
    description: '全文检索任意数字员工对话，多条件定位到具体轮次，取证时不必翻日志。',
    menuPath: '/compliance/conv-search',
  },
  {
    title: '向监管交底的看板',
    description: '药企全景：备案分布、培训覆盖率、合规通过率。监管自查报告可在「合规规则」页一键导出（3 Sheet xlsx）。',
    menuPath: '/compliance/mah-overview',
  },
  HELP,
];

const MEDICAL_STEPS: GuideStep[] = [
  {
    title: '你是医学内容链条的守门人',
    description:
      '从文献上架到患教触达医生，内容全程留痕可溯——每一个进入对话的知识点都能追回原始文档。',
  },
  {
    title: '知识库：员工的大脑',
    description: '文献上传、审核、版本管理（重复上传自动归档旧版），上架即进入检索并带引用溯源。',
    menuPath: '/knowledge/list',
  },
  {
    title: '患教内容：先审后用',
    description: '医生分享的患教材料进入待审队列，approve 后才对患者可见；驳回需填理由并留痕。',
    menuPath: '/patient-edu/review',
  },
  {
    title: '患教模板库',
    description: '按疾病领域维护常用患教模板，医生端一键生成个性化患教内容。',
    menuPath: '/patient-edu/list',
  },
  HELP,
];

const BY_ROLE: Record<string, GuideStep[]> = {
  admin: ADMIN_STEPS,
  manager: MANAGER_STEPS,
  compliance: COMPLIANCE_STEPS,
  medical: MEDICAL_STEPS,
};

export function getStepsForRole(role?: string): GuideStep[] {
  return BY_ROLE[role ?? ''] ?? ADMIN_STEPS;
}

/** localStorage 完成标记（跳过=完成，不再自动弹；重看入口由"?"按钮触发） */
export function tourDoneKey(role?: string): string {
  return `onboarding.web.${role ?? 'admin'}.v1`;
}
