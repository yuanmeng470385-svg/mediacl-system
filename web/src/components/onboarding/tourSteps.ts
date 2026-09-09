/**
 * 三端新人引导 · web 端步骤配置（2026-09-09 v3：全页面覆盖）。
 *
 * v3 变化（用户要求「每一个页面都引导一下，介绍其功能」）：
 * 开场价值叙事 → 按左侧菜单顺序对**该角色可见的全部页面**各走一步（核心页带
 * 「去试试」自动导航体验，其余纯讲解翻卡）→ 收尾。
 * 步骤由 menuConfig+canAccess 自动派生：新增菜单页会自动获得一步（文案缺省兜底），
 * tourSteps.test.ts 断言覆盖与菜单叶序完全一致——菜单/权限变更时炸出（M17 哲学）。
 */
import { menuConfig } from '../../constants/menu';
import { canAccess } from '../../constants/routeAccess';

/** 引导步（tryPath 省略 = 纯讲解步；page = 本步介绍的菜单页，覆盖断言用） */
export interface GuideStep {
  title: string;
  description: string;
  /** 本步介绍的页面（菜单 path；try 步等于 tryPath） */
  page?: string;
  /** 「去试试」导航目标路由 */
  tryPath?: string;
  /** 目标页名（召回卡文案用，有 tryPath 必填） */
  tryName?: string;
  /** 到达目标页后的一次性提示（有 tryPath 必填） */
  tryHint?: string;
}

/** 每页讲解卡文案库：path → 功能介绍（核心页附体验提示 tryHint） */
const PAGE_GUIDES: Record<string, { description: string; tryHint?: string }> = {
  '/dashboard': {
    description:
      '登录落地页：今日对话量、拜访动态、系统健康一屏总览——数字员工团队的「晨报」。',
  },
  '/specialist/list': {
    description:
      '数字员工花名册：每个专员的对话量、好评率、待复核风险；3D 办公室还能看它们实时值守。',
    tryHint: '看看每个员工今天的对话量与好评率。逛完回来，点右下角"?"悬浮球继续引导。',
  },
  '/specialist/monitor': {
    description:
      '按分身维度透视工作量与质量：对话量、好评率、待复核——哪个「员工」需要人工介入一眼可见。',
  },
  '/visit/list': {
    description:
      '每一场拜访的全程回放：录音转写原文、AI 结构化总结、异议与关键节点、自动建好的后续任务。',
    tryHint: '点开一场已完成拜访，看 AI 总结与转写全文。逛完回来点"?"继续。',
  },
  '/doctor/stats': {
    description: '医生活跃度、分身排行、触达效果——评估数字员工投入产出的运营看板。',
    tryHint: '看看分身排行榜和医生活跃趋势。逛完点"?"继续。',
  },
  '/knowledge/list': {
    description:
      '给员工装「大脑」：文献上传→审核→上架即被检索引用，回答自带引用溯源；重复上传自动归档旧版。',
    tryHint: '试试左上角「上传文档」按钮的位置，或点开一篇文档看版本与审核状态。逛完点"?"继续。',
  },
  '/skill/list': {
    description:
      'Skill 资产台账：模版审核与上架、权重受控查看、两类下架（合规/作者）——发布链路全程审计。',
  },
  '/patient-edu/list': {
    description:
      '按疾病领域维护患教模板，医生端一键生成个性化患教材料——隐私版，不采集患者数据。',
    tryHint: '按疾病领域筛选模板试试。逛完点"?"继续。',
  },
  '/patient-edu/review': {
    description: '医生分享的患教材料待审队列：approve 后才进专区对患者可见，驳回需填理由并留痕。',
    tryHint: '看看待审队列长什么样（没有待审也是正常态）。逛完点"?"继续。',
  },
  '/practice/objections': {
    description:
      'AI 陪练的「题库」：医生常见疑虑的标准回应素材，陪练对话据此出题，代表练完看逐句反馈。',
  },
  '/compliance/list': {
    description:
      '三层门禁（关键词/正则/LLM 语义）的规则源：R001-R011 映射 2026《医药代表管理办法》22 项禁止行为；监管自查报告在此一键导出。',
  },
  '/compliance/blocks': {
    description: '每一次被拦下的 AI 输出：命中规则、处理动作、原始内容——风控的证据台账。',
  },
  '/compliance/monitor': {
    description: '风险闭环工作台：待复核名单→查看对话上下文→冻结或放行，人工裁决全程审计留痕。',
    tryHint: '找到「待复核」入口，看一条风险对话的完整上下文。逛完回来点"?"继续。',
  },
  '/compliance/mah-overview': {
    description: '向监管交底的 MAH 看板：备案分布、培训覆盖率、合规通过率（口径=代表的合规对话）。',
    tryHint: '看备案分布与合规通过率的口径说明。逛完点"?"继续。',
  },
  '/compliance/conv-search': {
    description: '全文检索任意数字员工对话，多条件定位到具体轮次——取证不必翻日志。',
    tryHint: '随便输个关键词（如「疗效」）试试检索。逛完点"?"继续。',
  },
  '/compliance/card-stats': {
    description: '学术卡片触达效果：推送量、有效阅读（≥3 秒）、医生反馈与追问回流——按被读数排名。',
  },
  '/data/assets': {
    description: '敏感数据资产清单与导出规范：对话明细出域必须走审批，防止数据裸奔。',
  },
  '/data/exports': {
    description: '数据导出审批队列：approve 生成 7 天有效的 xlsx 明细，下载全程留痕；超 SLA 会标红。',
  },
  '/privacy/requests': {
    description: '医生提出的隐私请求（导出/更正/注销）：30 天 SLA 追踪，处理动作全部审计。',
  },
  '/audit/list': {
    description: '全系统操作底账：谁看了 Skill 内容、审了什么、冻结了谁——监管追问时从这里取证。',
  },
  '/doctor/list': {
    description: '医生（HCP）档案库：基本信息、互动历史，AI 画像自动汇总历次拜访洞察。',
    tryHint: '点开一位医生看 AI 画像卡。逛完点"?"继续。',
  },
  '/doctor-cert/list': {
    description: '医师资质审核：医生端上传执业证明，你审核通过后其账号解锁完整功能。',
  },
  '/user/list': {
    description: '后台账号与角色管理：五种角色（rep/manager/compliance/medical/admin），菜单按角色自动过滤。',
  },
  '/filing/list': {
    description: '药企监管台账：代表资质备案审核；到期未续自动冻结账号（防带病上岗）。',
    tryHint: '看一眼代表备案状态分布，点开任意一行看资质明细。逛完点"?"继续。',
  },
  '/training/list': {
    description: '培训三件套：材料库、考试成绩、承诺书签署——培训完成度的统计分母在这里。',
  },
  '/system/config': {
    description: '网关运行参数在线查看（只读）——生产配置统一走部署环境变量。仅管理员可见。',
  },
};

/** 各角色的核心体验页（带「去试试」；均取自 PAGE_GUIDES 带 tryHint 的页面） */
const TRY_PAGES: Record<string, string[]> = {
  admin: ['/specialist/list', '/knowledge/list', '/visit/list', '/compliance/monitor', '/filing/list', '/doctor/stats'],
  manager: ['/visit/list', '/specialist/monitor', '/doctor/stats', '/knowledge/list', '/doctor/list'],
  compliance: ['/compliance/monitor', '/compliance/conv-search', '/compliance/mah-overview', '/compliance/blocks'],
  medical: ['/knowledge/list', '/patient-edu/review', '/patient-edu/list'],
};

/** 各角色开场价值叙事（n=该角色可见页面数，组进文案） */
const OPENINGS: Record<string, (n: number) => string> = {
  admin: (n) =>
    `你管理的不只是一套系统，而是一支 7×24 小时值守的 AI 数字员工：它们替代表回答医学问题、陪访后写总结、给医生推送学术卡片——每一句输出都经过三层合规门禁并留痕。接下来按左侧菜单顺序，带你过一遍你能看到的全部 ${n} 个页面（随时可「跳过引导」，右下角"?"悬浮球可重看）。`,
  manager: (n) =>
    `拜访数据不再靠代表手填：App 里录音自动转写、AI 生成结构化总结并自动建后续任务，你在管理端看到的是实时汇总部。接下来按左侧菜单顺序，带你过一遍你能看到的全部 ${n} 个页面（随时可「跳过引导」，右下角"?"悬浮球可重看）。`,
  compliance: (n) =>
    `系统里每一句 AI 输出都先过三层自动门禁（关键词/正则/LLM 语义）——被拦下的高风险内容汇聚到这里，由你裁决。接下来按左侧菜单顺序，带你过一遍你能看到的全部 ${n} 个页面（随时可「跳过引导」，右下角"?"悬浮球可重看）。`,
  medical: (n) =>
    `从文献上架到患教触达医生，内容全程留痕可溯——每一个进入对话的知识点都能追回原始文档。接下来按左侧菜单顺序，带你过一遍你能看到的全部 ${n} 个页面（随时可「跳过引导」，右下角"?"悬浮球可重看）。`,
};

const CLOSING: GuideStep = {
  title: '逛完了，最后两件事',
  description:
    '① 右下角的"?"悬浮球随时重看本引导；② 左侧菜单已按你的角色过滤，只显示你有权限的功能——哪个页面忘了干什么，回来再逛一遍就熟了。',
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

/** 由菜单自动派生该角色步骤：开场 → 每页一步 → 收尾 */
function buildSteps(role: string): GuideStep[] {
  const leaves = menuLeaves(role);
  const tryPages = new Set(TRY_PAGES[role] ?? []);
  const steps: GuideStep[] = [
    {
      title: {
        admin: '欢迎来到你的数字员工团队',
        manager: '拜访数据不再靠代表手填',
        compliance: '你是最后一道人工闭环',
        medical: '你是医学内容链条的守门人',
      }[role] ?? '欢迎来到你的数字员工团队',
      description: (OPENINGS[role] ?? OPENINGS.admin)(leaves.length),
    },
  ];
  for (const leaf of leaves) {
    const guide = PAGE_GUIDES[leaf.path];
    // 新增菜单页未配文案时的兜底（测试会炸出来提醒补文案，运行时不白屏）
    const description = guide?.description ?? '这个页面的介绍还在路上——点「我知道了」继续，或从左侧菜单直接进去逛逛。';
    const isTry = tryPages.has(leaf.path);
    steps.push({
      title: leaf.name,
      description,
      page: leaf.path,
      ...(isTry
        ? { tryPath: leaf.path, tryName: leaf.name, tryHint: guide?.tryHint ?? '逛完回来，点右下角"?"悬浮球继续引导。' }
        : {}),
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

/** localStorage 完成/进度 key（跳过=完成；progress 支持断点续传）。v3=全页面覆盖，看过 v2 的用户重弹 */
export function tourDoneKey(role?: string): string {
  return `onboarding.web.${role ?? 'admin'}.v3`;
}
export function tourProgressKey(role?: string): string {
  return `onboarding.web.${role ?? 'admin'}.progress`;
}
