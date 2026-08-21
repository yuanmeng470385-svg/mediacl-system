/**
 * M17（2026-08-21 审计）：web 前端角色访问控制 —— 路由角色表 + 菜单过滤。
 *
 * 单一事实源是后端各端点的 require_roles：前端放严只是少看菜单，放宽则会
 * 把用户引到 403 页面。新增页面时须同步三处——App.tsx 路由、本表条目、
 * routeAccess.test.ts 的数量断言——缺一会在测试里炸出来。
 */

/** web 会登录的全部角色（rep/doctor 走移动端） */
export const ALL_WEB_ROLES = ['admin', 'manager', 'compliance', 'medical'] as const;

const FOUR = ALL_WEB_ROLES;
const THREE: readonly string[] = ['admin', 'manager', 'compliance'];
const TWO: readonly string[] = ['admin', 'manager'];

/** 路径模板（支持 :param 动态段）→ 允许角色 */
export const ROUTE_ACCESS: Record<string, readonly string[]> = {
  // 任意登录角色：登录落地页 / 拜访列表（后端 get_current_user，不限角色）
  '/dashboard': FOUR,
  '/visit/list': FOUR,
  // 专员列表（specialists.py require_roles 四角色）/ 分身监控 MONITOR_ADMIN_ROLES
  '/specialist/list': FOUR,
  '/specialist/monitor': THREE,
  // 知识库 KB_ADMIN_ROLES
  '/knowledge/list': ['admin', 'manager', 'medical'],
  // 合规风控域：RULE_ADMIN_ROLES / EXPORT_ROLES / PRIVACY_ADMIN / AUDIT_VIEW_ROLES
  '/compliance/list': THREE,
  '/compliance/blocks': THREE,
  '/compliance/monitor': THREE,
  '/compliance/conv-search': THREE,
  '/compliance/mah-overview': THREE,
  '/compliance/card-stats': FOUR, // academic-cards/stats 四角色
  '/data/assets': THREE,
  '/data/exports': THREE,
  '/privacy/requests': THREE,
  '/audit/list': THREE,
  // 医生域：HCP_ADMIN_ROLES（档案）/ STATS_ADMIN_ROLES（运营统计）
  '/doctor/list': TWO,
  '/doctor/:id': TWO,
  '/doctor/stats': FOUR,
  // 用户管理 users.py / 备案·认证·培训·Skill·患教（QUAL/EXAM/MATERIAL/SKILL/EDU_ADMIN_ROLES）
  '/user/list': TWO,
  '/filing/list': FOUR,
  '/doctor-cert/list': FOUR,
  '/training/list': FOUR,
  '/skill/list': FOUR,
  '/patient-edu/list': FOUR,
  '/patient-edu/review': FOUR,
  // 网关 system_config 硬编码 role == admin
  '/system/config': ['admin'],
};

function match(pattern: string, path: string): boolean {
  const ps = pattern.split('/');
  const xs = path.split('/');
  if (ps.length !== xs.length) return false;
  return ps.every((seg, i) => seg.startsWith(':') || seg === xs[i]);
}

/** 路径是否已登记角色（未登记路径交给 Router 404，守卫不拦） */
export function isKnownRoute(path: string): boolean {
  return Object.keys(ROUTE_ACCESS).some((p) => match(p, path));
}

export function canAccess(path: string, role?: string | null): boolean {
  if (!role) return false;
  return Object.entries(ROUTE_ACCESS).some(
    ([p, roles]) => match(p, path) && roles.includes(role),
  );
}

/** 菜单按角色过滤（泛型兼容 MenuDataItem；扁平配置无 children 分支） */
export function filterMenu<T extends { path?: string }>(items: T[], role?: string | null): T[] {
  return items.filter((it) => it.path && canAccess(it.path, role));
}
