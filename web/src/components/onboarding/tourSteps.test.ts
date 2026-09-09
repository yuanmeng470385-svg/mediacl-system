/**
 * 新人引导步骤防漂移断言（对齐 routeAccess.test.ts 的 M17 哲学）：
 * v3 全页面覆盖——每个角色必须按菜单顺序覆盖其可见的全部页面，一步不缺；
 * 「去试试」引用不存在/无权限的页面会把用户导航到 403，也必须炸出来。
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
  it('步数=可见页数+2（开场/收尾）；首末为纯讲解步', () => {
    for (const role of ROLES) {
      const steps = getStepsForRole(role);
      const pages = visibleMenuPaths(role);
      expect(steps.length, `${role} 应=页数+2`).toBe(pages.length + 2);
      expect(steps[0].tryPath, `${role} 首步应是价值叙事纯讲解`).toBeUndefined();
      expect(steps[steps.length - 1].tryPath, `${role} 末步应是收尾纯讲解`).toBeUndefined();
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
        expect(!!s.description.trim() && !s.description.includes('还在路上'), `${role} ${s.page} 缺功能介绍文案`).toBe(true);
      }
    }
  });

  it('体验步 tryPath 均为该角色可访问且菜单真实存在的页面；tryName/tryHint 必填；每角色 ≥3 步', () => {
    const allPaths = menuConfig.flatMap((i) =>
      [i.path, ...(i.children ?? []).map((c) => c.path)].filter(Boolean) as string[],
    );
    for (const role of ROLES) {
      const trySteps = (getStepsForRole(role) as GuideStep[]).filter(
        (s): s is GuideStep & { tryPath: string } => !!s.tryPath,
      );
      expect(trySteps.length, `${role} 体验步应 ≥3`).toBeGreaterThanOrEqual(3);
      for (const s of trySteps) {
        expect(allPaths, `${role} 引用 ${s.tryPath} 不在 menuConfig`).toContain(s.tryPath);
        expect(canAccess(s.tryPath, role), `${role} 无权访问引导目标页 ${s.tryPath}`).toBe(true);
        expect(!!s.tryName?.trim(), `${role} ${s.tryPath} 缺 tryName`).toBe(true);
        expect(!!s.tryHint?.trim(), `${role} ${s.tryPath} 缺 tryHint`).toBe(true);
      }
    }
  });

  it('未知角色回落 admin 配置；完成/进度 key 带角色维度', () => {
    expect(getStepsForRole('unknown-role')).toEqual(getStepsForRole('admin'));
    expect(getStepsForRole(undefined)).toEqual(getStepsForRole('admin'));
    expect(tourDoneKey('admin')).toBe('onboarding.web.admin.v3');
    expect(tourDoneKey('compliance')).not.toBe(tourDoneKey('admin'));
    expect(tourProgressKey('admin')).toBe('onboarding.web.admin.progress');
    expect(tourProgressKey('admin')).not.toBe(tourDoneKey('admin'));
  });
});
