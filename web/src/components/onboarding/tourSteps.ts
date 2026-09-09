/**
 * 三端新人引导 · web 端步骤配置（2026-09-09 A 档 v2：陪玩式）。
 *
 * 每步可带 tryPath：「去试试」自动导航到目标页，用户亲手体验后点「我知道了」回来继续下一步
 * （GuideTour 状态机 card→trying→next；进度持久化可断点续传）。
 * 约束：tryPath 必须 ∈ ROUTE_ACCESS 该角色可访问集合且 menuConfig 真实存在
 * （tourSteps.test.ts 防漂移断言——权限/菜单变更时炸出，M17 单一事实源哲学）。
 */

/** 引导步（tryPath 省略 = 纯讲解步） */
export interface GuideStep {
  title: string;
  description: string;
  /** 「去试试」导航目标路由 */
  tryPath?: string;
  /** 目标页名（召回卡文案用，有 tryPath 必填） */
  tryName?: string;
  /** 到达目标页后的一次性提示（有 tryPath 必填） */
  tryHint?: string;
}

const CLOSING: GuideStep = {
  title: '逛完了，最后两件事',
  description:
    '① 右下角的"?"悬浮球随时重看本引导；② 左侧菜单已按你的角色过滤，只显示你有权限的功能——其余页面逛逛就熟了。',
};

const ADMIN_STEPS: GuideStep[] = [
  {
    title: '欢迎来到你的数字员工团队',
    description:
      '你管理的不只是一套系统，而是一支 7×24 小时值守的 AI 数字员工：它们替代表回答医学问题、陪访后写总结、给医生推送学术卡片——每一句输出都经过三层合规门禁并留痕。接下来带你亲手逛一圈核心页面。',
  },
  {
    title: '第一步：认识你的"员工"',
    description: '专员列表是团队花名册：每个数字员工的对话量、好评率、待复核风险都在这里。',
    tryPath: '/specialist/list',
    tryName: '专员列表',
    tryHint: '这里能看到每个数字员工今天接了多少对话。逛完回来，点右下角"?"悬浮球继续引导。',
  },
  {
    title: '第二步：给员工装上"大脑"',
    description: '文献上传 → 审核 → 上架即被检索引用，数字员工的回答自带引用溯源。',
    tryPath: '/knowledge/list',
    tryName: '知识库',
    tryHint: '试试左上角「上传文档」按钮的位置，或随便点开一篇文档看版本与审核状态。逛完点"?"继续。',
  },
  {
    title: '第三步：药企监管台账',
    description: '备案管理审核代表资质、合规培训跟踪考试与承诺书——向监管交底的两本账。',
    tryPath: '/filing/list',
    tryName: '备案管理',
    tryHint: '看一眼代表备案状态分布，点开任意一行看资质明细。逛完点"?"继续。',
  },
  CLOSING,
];

const MANAGER_STEPS: GuideStep[] = [
  {
    title: '拜访数据不再靠代表手填',
    description:
      '代表 App 里录音自动转写、AI 生成结构化总结并自动建后续任务——你在管理端看到的是实时汇总部。接下来带你逛三个核心看板。',
  },
  {
    title: '第一步：看每一场拜访的全程',
    description: '转写原文、AI 总结、异议与关键节点、拜访时长，点进任意一场回看全程。',
    tryPath: '/visit/list',
    tryName: '拜访管理',
    tryHint: '点开一场已完成拜访，看 AI 总结与转写全文。逛完回来点"?"悬浮球继续。',
  },
  {
    title: '第二步：数字员工也在替你干活',
    description: '每个数字员工的对话量、好评率、待复核风险，按分身维度透视工作量与质量。',
    tryPath: '/specialist/monitor',
    tryName: '分身监控',
    tryHint: '留意「待复核」列——那是需要人工裁决的风险对话。逛完点"?"继续。',
  },
  {
    title: '第三步：投入产出一眼看清',
    description: '医生活跃度、分身排行、触达效果——评估数字员工投入产出的看板。',
    tryPath: '/doctor/stats',
    tryName: '运营统计',
    tryHint: '看看分身排行榜和医生活跃趋势。逛完点"?"继续。',
  },
  CLOSING,
];

const COMPLIANCE_STEPS: GuideStep[] = [
  {
    title: '你是最后一道人工闭环',
    description:
      '系统里每一句 AI 输出都先过三层自动门禁（关键词/正则/LLM 语义）——被拦下的高风险内容汇聚到这里，由你裁决。接下来带你走一遍风控闭环动线。',
  },
  {
    title: '第一步：风险从这里闭环',
    description: '待复核名单 → 查看对话上下文 → 冻结或放行，裁决全程审计留痕。',
    tryPath: '/compliance/monitor',
    tryName: '合规风控',
    tryHint: '找到「待复核」入口，看一条风险对话的完整上下文。逛完回来点"?"悬浮球继续。',
  },
  {
    title: '第二步：取证溯源的对话检索',
    description: '全文检索任意数字员工对话，多条件定位到具体轮次，取证不必翻日志。',
    tryPath: '/compliance/conv-search',
    tryName: '对话检索',
    tryHint: '随便输个关键词（如「疗效」）试试检索。逛完点"?"继续。',
  },
  {
    title: '第三步：向监管交底的看板',
    description: '备案分布、培训覆盖率、合规通过率；监管自查报告可在「合规规则」页一键导出（3 Sheet xlsx）。',
    tryPath: '/compliance/mah-overview',
    tryName: '药企全景',
    tryHint: '看备案分布与合规通过率的口径说明。逛完点"?"继续。',
  },
  CLOSING,
];

const MEDICAL_STEPS: GuideStep[] = [
  {
    title: '你是医学内容链条的守门人',
    description:
      '从文献上架到患教触达医生，内容全程留痕可溯——每一个进入对话的知识点都能追回原始文档。接下来带你走内容链的三个关键页。',
  },
  {
    title: '第一步：知识库，员工的大脑',
    description: '文献上传、审核、版本管理（重复上传自动归档旧版），上架即带引用溯源。',
    tryPath: '/knowledge/list',
    tryName: '知识库',
    tryHint: '点开一篇文档看版本与审核状态。逛完回来点"?"悬浮球继续。',
  },
  {
    title: '第二步：患教内容，先审后用',
    description: '医生分享的患教材料进入待审队列，approve 后才对患者可见；驳回需填理由并留痕。',
    tryPath: '/patient-edu/review',
    tryName: '患教内容',
    tryHint: '看看待审队列长什么样（没有待审也是正常态）。逛完点"?"继续。',
  },
  {
    title: '第三步：患教模板库',
    description: '按疾病领域维护常用患教模板，医生端一键生成个性化患教内容。',
    tryPath: '/patient-edu/list',
    tryName: '患教模板',
    tryHint: '按疾病领域筛选模板试试。逛完点"?"继续。',
  },
  CLOSING,
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

/** localStorage 完成/进度 key（跳过=完成；progress 支持断点续传）。v2=陪玩式升级，看过 v1 的用户重弹 */
export function tourDoneKey(role?: string): string {
  return `onboarding.web.${role ?? 'admin'}.v2`;
}
export function tourProgressKey(role?: string): string {
  return `onboarding.web.${role ?? 'admin'}.progress`;
}
