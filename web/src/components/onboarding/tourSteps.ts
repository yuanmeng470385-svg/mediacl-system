/**
 * 三端新人引导 · web 端步骤配置（2026-09-10 v4：全页面覆盖 + 每卡四按钮）。
 *
 * v4 变化（用户要求「每个卡片都是 跳过引导/上一个/去试试/下一个 四个按钮」）：
 * 撤销 v3 的 TRY_PAGES 核心页区分——**每一步**（含开场/收尾）都带 tryPath 可「去试试」，
 * 讲解卡按钮组由 GuideTour 统一渲染四键；PAGE_GUIDES 全量补 tryHint。
 *
 * v3 变化（「每一个页面都引导一下，介绍其功能」）：
 * 开场价值叙事 → 按左侧菜单顺序对**该角色可见的全部页面**各走一步 → 收尾。
 * 步骤由 menuConfig+canAccess 自动派生：新增菜单页会自动获得一步（文案缺省兜底），
 * tourSteps.test.ts 断言覆盖与菜单叶序完全一致——菜单/权限变更时炸出（M17 哲学）。
 */
import { menuConfig } from '../../constants/menu';
import { canAccess } from '../../constants/routeAccess';

/** 引导步（v4 起全部步骤都有 tryPath——四按钮要求；page = 本步介绍的菜单页，覆盖断言用） */
export interface GuideStep {
  title: string;
  description: string;
  /** 本步介绍的页面（菜单 path；try 步等于 tryPath） */
  page?: string;
  /** 「去试试」导航目标路由 */
  tryPath?: string;
  /** 目标页名（召回卡文案用） */
  tryName?: string;
  /** 到达目标页后的一次性提示 */
  tryHint?: string;
}

/** 每页讲解卡文案库：path → { 这是什么/有什么用, 到页体验提示 tryHint } */
const PAGE_GUIDES: Record<string, { description: string; tryHint?: string }> = {
  '/dashboard': {
    description:
      '登录后的落地总览页：今日对话量、最新拜访动态、合规拦截热力与网关健康一屏打尽——每天开工先看这一页。',
    tryHint: '看一眼今日对话量与实时动态。逛完回来，点右下角"?"悬浮球继续引导。',
  },
  '/specialist/list': {
    description:
      '数字专员花名册：每个专员对应一个挂在公司名下的 AI 员工（对话量/好评率/风险一排看清），新建、编辑、启停与数据统计都在这里；切到「办公室」视图还能看它们 3D 实时值守。',
    tryHint: '看看每个员工今天的对话量与好评率。逛完回来，点右下角"?"悬浮球继续引导。',
  },
  '/specialist/monitor': {
    description:
      '「分身」是代表创建、医生端可见的数字员工：这里按分身透视今日服务量、好评率、合规健康度与被添加数——哪个「员工」需要人工介入一眼可见；官方公共分身也在此创建。',
    tryHint: '看看分身的对话量与合规健康度列。逛完点"?"继续。',
  },
  '/visit/list': {
    description:
      '每一场线下拜访的数字档案：App 录音自动转写全文、AI 结构化总结、异议与关键节点、自动建好的后续任务——代表不用回来补填，你看到的就是实时汇总部。',
    tryHint: '点开一场已完成拜访，看 AI 总结与转写全文。逛完回来点"?"继续。',
  },
  '/doctor/stats': {
    description:
      '医生侧运营看板：医生活跃度（日/周/月活）、数字分身使用排行（被添加数+好评率）、学术卡片触达效果——评估数字员工投入产出的地方。',
    tryHint: '看看分身排行榜和医生活跃趋势。逛完点"?"继续。',
  },
  '/knowledge/list': {
    description:
      '给数字员工装「大脑」的地方：文献上传→审核→上架后即被检索引用，AI 回答自带引用可溯源；重复上传自动归档旧版。',
    tryHint: '试试左上角「上传文档」按钮的位置，或点开一篇文档看版本与审核状态。逛完点"?"继续。',
  },
  '/skill/list': {
    description:
      'Skill 是代表可复用的话术风格模版（AI 陪练按它打分，个人 Skill 可发布到 App 广场共用）：这里审核官方模版与代表发布、受控查看权重与素材原文、执行合规/作者两类下架，全程审计。',
    tryHint: '看看待审队列与已上架模版（空队列正常）。逛完点"?"继续。',
  },
  '/patient-edu/list': {
    description:
      '患教=患者教育。按疾病领域维护患教模板库，医生在 App 端选模板一键 AI 生成患教材料发给患者——默认仅医生本人可见，不采集任何患者数据。',
    tryHint: '按疾病领域筛筛模板。逛完点"?"继续。',
  },
  '/patient-edu/review': {
    description:
      '医生分享到患教专区的材料待审队列：approve 后才对全体医生可见，驳回需填理由并留痕——专区内容的最后一道人工关。',
    tryHint: '看看待审队列长什么样（没有待审也是正常态）。逛完点"?"继续。',
  },
  '/practice/objections': {
    description:
      'AI 陪练的「题库」：代表在 App 里与 AI 扮演的医生对话练话术，这里维护医生常见疑虑（如「有真实世界数据吗」）与标准回应素材——陪练据此出题，评分据此对照。',
    tryHint: '看看有哪些场景类型的异议素材。逛完点"?"继续。',
  },
  '/compliance/list': {
    description:
      '三层门禁（关键词/正则/LLM 语义）的规则源：R001-R011 映射 2026《医药代表管理办法》的禁止行为——每一句 AI 输出先过这里再出门；监管自查报告在此一键导出。',
    tryHint: '点开一条规则看命中样例与启停开关。逛完点"?"继续。',
  },
  '/compliance/blocks': {
    description:
      '每一次被门禁拦下的 AI 输出台账：命中规则、处理动作、原始内容与上下文——风控取证、复盘误伤都从这里查。',
    tryHint: '按规则筛筛拦截记录，点开看命中的原文片段。逛完点"?"继续。',
  },
  '/compliance/monitor': {
    description:
      '风险闭环工作台：拦截日报/趋势、近 24h 被拦截≥5 次的分身待复核名单→查看对话上下文→冻结或放行——人工裁决，全程审计留痕。',
    tryHint: '找到「待复核」入口，看一条风险对话的完整上下文。逛完回来点"?"继续。',
  },
  '/compliance/mah-overview': {
    description:
      'MAH（药品上市许可持有人）合规全景看板：全量代表的备案状态分布、培训/承诺书完成率、合规通过率（口径=代表分身对话未被拦截占比）——监管自查与内部交底的总账。',
    tryHint: '看备案分布与合规通过率的口径说明。逛完点"?"继续。',
  },
  '/compliance/conv-search': {
    description:
      '全文检索任意数字员工的对话记录，多条件定位到具体轮次并带完整上下文——取证、排查不用翻日志。',
    tryHint: '随便输个关键词（如「疗效」）试试检索。逛完点"?"继续。',
  },
  '/compliance/card-stats': {
    description:
      '学术卡片的触达效果看板：推送量、有效阅读（停留≥3 秒）、医生「有用」反馈与追问回流，代表按被读数排名——防「推得多读得少」。',
    tryHint: '看看有效阅读率与代表排行。逛完点"?"继续。',
  },
  '/data/assets': {
    description:
      '敏感数据资产清单与分级（个人信息/业务数据/合规留存）：哪些表存敏感数据、出域要走什么流程一目了然——对话明细等敏感导出必须走「导出审批」。',
    tryHint: '看看三类数据的分级与对应表。逛完点"?"继续。',
  },
  '/data/exports': {
    description:
      '数据导出审批队列：admin/manager 申请、合规部裁决；approve 生成 7 天有效的 xlsx 明细，下载全程留痕，超 3 天 SLA 标红。',
    tryHint: '看看审批队列与 SLA 标红（空队列正常）。逛完点"?"继续。',
  },
  '/privacy/requests': {
    description:
      '医生在 App 提出的隐私请求（查看/更正/导出/注销）：30 天 SLA 追踪，处理动作全部审计——个保法合规的响应台账。',
    tryHint: '看看请求类型分布与 SLA 状态。逛完点"?"继续。',
  },
  '/audit/list': {
    description:
      '全系统操作底账：谁在何时看了 Skill 内容、审了什么、冻结了谁、导出了哪批数据——监管追问时从这里取证（可导出 Excel）。',
    tryHint: '按动作类型筛筛操作流水。逛完点"?"继续。',
  },
  '/doctor/list': {
    description:
      '医生（HCP）档案库：基本信息、标签、历次拜访与对话的互动历史，AI 画像自动汇总学术偏好与异议——Excel 批量导入也在这里。',
    tryHint: '点开一位医生看 AI 画像卡。逛完点"?"继续。',
  },
  '/doctor-cert/list': {
    description:
      '医师资质审核：医生在 App 上传执业证明，你审核通过后其账号解锁完整功能——医生端准入的人工关。',
    tryHint: '看看待审资质长什么样（空队列正常）。逛完点"?"继续。',
  },
  '/user/list': {
    description:
      '后台与一线账号管理：五种角色（rep/manager/compliance/medical/admin）的建号、启停与角色调整；菜单按角色自动过滤，越权访问会撞 403。',
    tryHint: '按角色筛筛账号列表。逛完点"?"继续。',
  },
  '/filing/list': {
    description:
      '药企监管台账：代表备案资质的提交与审核；到期未续自动冻结账号（防带病上岗）——MAH 看板的备案分布就统计自这里。',
    tryHint: '看一眼代表备案状态分布，点开任意一行看资质明细。逛完点"?"继续。',
  },
  '/training/list': {
    description:
      '代表合规培训三件套：培训材料库（法规/RDPAC/内部）、题库与考试成绩、承诺书签署记录——MAH 看板的「培训完成率」分母在这里。',
    tryHint: '看看材料类型与考试记录。逛完点"?"继续。',
  },
  '/system/config': {
    description:
      '网关与各服务运行参数的在线只读视图（密钥类只显示「已配置/未配置」，不显值）——生产配置统一走部署环境变量，不在这里改。',
    tryHint: '看看各配置项的开关状态。逛完点"?"继续。',
  },
};

/** 各角色开场价值叙事（n=该角色可见页面数，组进文案） */
const OPENINGS: Record<string, (n: number) => string> = {
  admin: (n) =>
    `你管理的不只是一套系统，而是一支 7×24 小时值守的 AI 数字员工：它们替代表回答医学问题、陪访后写总结、给医生推送学术卡片——每一句输出都经过三层合规门禁并留痕。接下来按左侧菜单顺序，带你过一遍你能看到的全部 ${n} 个页面（每张卡都能「去试试」，随时可跳过，右下角"?"悬浮球可重看）。`,
  manager: (n) =>
    `拜访数据不再靠代表手填：App 里录音自动转写、AI 生成结构化总结并自动建后续任务，你在管理端看到的是实时汇总部。接下来按左侧菜单顺序，带你过一遍你能看到的全部 ${n} 个页面（每张卡都能「去试试」，随时可跳过，右下角"?"悬浮球可重看）。`,
  compliance: (n) =>
    `系统里每一句 AI 输出都先过三层自动门禁（关键词/正则/LLM 语义）——被拦下的高风险内容汇聚到这里，由你裁决。接下来按左侧菜单顺序，带你过一遍你能看到的全部 ${n} 个页面（每张卡都能「去试试」，随时可跳过，右下角"?"悬浮球可重看）。`,
  medical: (n) =>
    `从文献上架到患教触达医生，内容全程留痕可溯——每一个进入对话的知识点都能追回原始文档。接下来按左侧菜单顺序，带你过一遍你能看到的全部 ${n} 个页面（每张卡都能「去试试」，随时可跳过，右下角"?"悬浮球可重看）。`,
};

const CLOSING: GuideStep = {
  title: '逛完了，最后两件事',
  description:
    '① 右下角的"?"悬浮球随时重看本引导；② 左侧菜单已按你的角色过滤，只显示你有权限的功能——哪个页面忘了干什么，回来再逛一遍就熟了。',
  tryPath: '/dashboard',
  tryName: '仪表盘',
  tryHint: '去仪表盘随手逛逛。想重看本引导，随时点右下角"?"悬浮球。',
};

/** 展平菜单取叶子项（path+name），按 menuConfig 顺序、按角色过滤 */
function menuLeaves(role: string): { path: string; name: string }[] {
  const walk = (items: typeof menuConfig): { path: string; name: string }[] =>
    items.flatMap((i) =>
      i.children?.length ? walk(i.children) : i.path && canAccess(i.path, role)
        ? [{ path: i.path, name: i.name ?? i.path }]
        : [],
    );
  return walk(menuConfig);
}

/** 由菜单自动派生该角色步骤：开场 → 每页一步（v4 起都带「去试试」）→ 收尾 */
function buildSteps(role: string): GuideStep[] {
  const leaves = menuLeaves(role);
  const first = leaves[0] ?? { path: '/dashboard', name: '仪表盘' };
  const steps: GuideStep[] = [
    {
      title: {
        admin: '欢迎来到你的数字员工团队',
        manager: '拜访数据不再靠代表手填',
        compliance: '你是最后一道人工闭环',
        medical: '你是医学内容链条的守门人',
      }[role] ?? '欢迎来到你的数字员工团队',
      description: (OPENINGS[role] ?? OPENINGS.admin)(leaves.length),
      // 开场也可「去试试」：先落到第一个菜单页（四按钮要求）
      tryPath: first.path,
      tryName: first.name,
      tryHint: `先去「${first.name}」看一眼，逛完点右下角"?"悬浮球回来继续。`,
    },
  ];
  for (const leaf of leaves) {
    const guide = PAGE_GUIDES[leaf.path];
    // 新增菜单页未配文案时的兜底（测试会炸出来提醒补文案，运行时不白屏）
    const description = guide?.description ?? '这个页面的介绍还在路上——点「我知道了」继续，或从左侧菜单直接进去逛逛。';
    steps.push({
      title: leaf.name,
      description,
      page: leaf.path,
      tryPath: leaf.path,
      tryName: leaf.name,
      tryHint: guide?.tryHint ?? '逛完回来，点右下角"?"悬浮球继续引导。',
    });
  }
  steps.push(CLOSING);
  return steps;
}

const KNOWN_ROLES = ['admin', 'manager', 'compliance', 'medical'];
const STEPS_CACHE: Record<string, GuideStep[]> = {};

export function getStepsForRole(role?: string): GuideStep[] {
  const r = role && KNOWN_ROLES.includes(role) ? role : 'admin';
  return (STEPS_CACHE[r] ??= buildSteps(r));
}

/** localStorage 完成/进度 key（跳过=完成；progress 支持断点续传）。v4=每卡四按钮+全步可试，看过 v3 的用户重弹 */
export function tourDoneKey(role?: string): string {
  return `onboarding.web.${role ?? 'admin'}.v4`;
}
export function tourProgressKey(role?: string): string {
  return `onboarding.web.${role ?? 'admin'}.progress`;
}
