/**
 * 新人引导步骤防漂移断言（对齐 routeAccess.test.ts 的 M17 哲学）：
 * v5 方向键自动跳页——**每一步**（含开场/收尾）都必须有可访问的 navPath 与非空 navHint；
 * 每个角色必须按菜单顺序覆盖其可见的全部页面，一步不缺；
 * 「上一个/下一个」引用不存在/无权限的页面会把用户导航到 403，也必须炸出来。
 */
import { describe, expect, it } from 'vitest';
import { getStepsForRole, tourDoneKey, tourProgressKey, type GuideStep } from './tourSteps';
import { canAccess } from '../../constants/routeAccess';
import { menuConfig } from '../../constants/menu';
import type { MenuDataItem } from '@ant-design/pro-components';

const ROLES = ['admin', 'manager', 'compliance', 'medical'] as const;

/** 该角色可见的菜单叶子 path（按 menuConfig 顺序） */
function visibleMenuPaths(role: string): string[] {
  const walk = (items: MenuDataItem[]): string[] =>
    items.flatMap((i) =>
      i.children?.length
        ? walk(i.children)
        : i.path && canAccess(i.path, role) ? [i.path] : [],
    );
  return walk(menuConfig);
}

describe('tourSteps（四角色全页面覆盖引导配置）', () => {
  it('步数=可见页数+2（开场/收尾）；首末步的跳页目标都落在仪表盘（全角色可达）', () => {
    for (const role of ROLES) {
      const steps = getStepsForRole(role);
      const pages = visibleMenuPaths(role);
      expect(steps.length, `${role} 应=页数+2`).toBe(pages.length + 2);
      expect(steps[0].navPath, `${role} 首步（价值叙事）应落到仪表盘`).toBe('/dashboard');
      expect(steps[steps.length - 1].navPath, `${role} 末步（收尾）应落到仪表盘`).toBe('/dashboard');
    }
  });

  it('中段页面步按菜单顺序完整覆盖该角色可见页面（缺页/多页/乱序都炸）；文案不得为兜底占位', () => {
    for (const role of ROLES) {
      const steps = getStepsForRole(role);
      const mid = steps.slice(1, -1);
      expect(
        mid.map((s) => s.page),
        `${role} 页面覆盖应与菜单叶序完全一致`,
      ).toEqual(visibleMenuPaths(role));
      for (const s of mid) {
        expect(
          !!s.description.trim() && !s.description.includes('介绍还没写好'),
          `${role} ${s.page} 缺功能介绍文案`,
        ).toBe(true);
        // v5.1：面向普通人的详解——每页至少说清楚一段话，别退化成一句话口号
        expect(s.description.length, `${role} ${s.page} 讲解过短（<80 字）`).toBeGreaterThanOrEqual(80);
      }
    }
  });

  it('v5 每一步都带自动跳页目标：navPath 均为菜单真实存在且该角色可访问的页面；navHint 必填', () => {
    const allPaths = menuConfig.flatMap((i) =>
      [i.path, ...(i.children ?? []).map((c) => c.path)].filter(Boolean) as string[],
    );
    for (const role of ROLES) {
      const steps = getStepsForRole(role) as GuideStep[];
      // v5 方向键要求：任何一步点「上一个/下一个」都不能落空（导航到 403 也算落空）
      const navSteps = steps.filter((s): s is GuideStep & { navPath: string } => !!s.navPath);
      expect(navSteps.length, `${role} 每一步都应有 navPath`).toBe(steps.length);
      for (const s of navSteps) {
        expect(allPaths, `${role} 引用 ${s.navPath} 不在 menuConfig`).toContain(s.navPath);
        expect(canAccess(s.navPath, role), `${role} 无权访问引导目标页 ${s.navPath}`).toBe(true);
        expect(!!s.navHint?.trim(), `${role} ${s.navPath} 缺 navHint`).toBe(true);
      }
    }
  });

  it('未知角色回落 admin 配置；完成/进度 key 带角色维度', () => {
    expect(getStepsForRole('unknown-role')).toEqual(getStepsForRole('admin'));
    expect(getStepsForRole(undefined)).toEqual(getStepsForRole('admin'));
    expect(tourDoneKey('admin')).toBe('onboarding.web.admin.v5');
    expect(tourDoneKey('compliance')).not.toBe(tourDoneKey('admin'));
    expect(tourProgressKey('admin')).toBe('onboarding.web.admin.progress');
    expect(tourProgressKey('admin')).not.toBe(tourDoneKey('admin'));
  });
});
