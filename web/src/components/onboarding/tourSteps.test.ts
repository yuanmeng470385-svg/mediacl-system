/**
 * 新人引导步骤防漂移断言（对齐 routeAccess.test.ts 的 M17 哲学）：
 * 引用不存在/无权限的菜单会让引导把用户指向 403 或空 target，必须在测试里炸出来。
 */
import { describe, expect, it } from 'vitest';
import { getStepsForRole, tourDoneKey, type GuideStep } from './tourSteps';
import { canAccess } from '../../constants/routeAccess';
import { menuConfig } from '../../constants/menu';
import type { MenuDataItem } from '@ant-design/pro-components';

const ROLES = ['admin', 'manager', 'compliance', 'medical'] as const;

/** 展平菜单取全部 path */
function menuPaths(items: MenuDataItem[]): string[] {
  return items.flatMap((i) => [i.path, ...(i.children ? menuPaths(i.children) : [])].filter(Boolean) as string[]);
}

describe('tourSteps（四角色引导配置）', () => {
  it('四角色各返回步骤：首步为居中叙事（无 menuPath），末步指向"?"重看入口', () => {
    for (const role of ROLES) {
      const steps = getStepsForRole(role);
      expect(steps.length, role).toBeGreaterThanOrEqual(4);
      expect(steps[0].menuPath, `${role} 首步应是价值叙事居中卡`).toBeUndefined();
      expect(steps[steps.length - 1].menuPath, `${role} 末步应指向 help-btn`).toBe('__help__');
    }
  });

  it('所有 menuPath 均为该角色可访问且菜单真实存在的项（防漂移）', () => {
    const paths = menuPaths(menuConfig);
    for (const role of ROLES) {
      for (const s of getStepsForRole(role) as GuideStep[]) {
        if (!s.menuPath || s.menuPath === '__help__') continue;
        expect(paths, `${role} 引用 ${s.menuPath} 不在 menuConfig`).toContain(s.menuPath);
        expect(canAccess(s.menuPath, role), `${role} 无权访问引导菜单 ${s.menuPath}`).toBe(true);
      }
    }
  });

  it('未知角色回落 admin 配置；存储 key 带角色维度', () => {
    expect(getStepsForRole('unknown-role')).toEqual(getStepsForRole('admin'));
    expect(getStepsForRole(undefined)).toEqual(getStepsForRole('admin'));
    expect(tourDoneKey('admin')).toBe('onboarding.web.admin.v1');
    expect(tourDoneKey('compliance')).not.toBe(tourDoneKey('admin'));
  });
});
