/**
 * 新人引导步骤防漂移断言（对齐 routeAccess.test.ts 的 M17 哲学）：
 * 「去试试」引用不存在/无权限的页面会把用户导航到 403，必须在测试里炸出来。
 */
import { describe, expect, it } from 'vitest';
import { getStepsForRole, tourDoneKey, tourProgressKey, type GuideStep } from './tourSteps';
import { canAccess } from '../../constants/routeAccess';
import { menuConfig } from '../../constants/menu';
import type { MenuDataItem } from '@ant-design/pro-components';

const ROLES = ['admin', 'manager', 'compliance', 'medical'] as const;

/** 展平菜单取全部 path */
function menuPaths(items: MenuDataItem[]): string[] {
  return items.flatMap((i) => [i.path, ...(i.children ? menuPaths(i.children) : [])].filter(Boolean) as string[]);
}

describe('tourSteps（四角色陪玩式引导配置）', () => {
  it('四角色各 ≥5 步：首末为纯讲解步（无 tryPath），中段为体验步（有 tryPath）', () => {
    for (const role of ROLES) {
      const steps = getStepsForRole(role);
      expect(steps.length, role).toBeGreaterThanOrEqual(5);
      expect(steps[0].tryPath, `${role} 首步应是价值叙事纯讲解`).toBeUndefined();
      expect(steps[steps.length - 1].tryPath, `${role} 末步应是收尾纯讲解`).toBeUndefined();
      // 陪玩要求：中段至少 3 步带用户去亲手体验
      expect(steps.filter((s) => s.tryPath).length, `${role} 体验步应 ≥3`).toBeGreaterThanOrEqual(3);
    }
  });

  it('体验步 tryPath 均为该角色可访问且菜单真实存在的页面；tryName/tryHint 必填（召回卡与到页提示依赖）', () => {
    const paths = menuPaths(menuConfig);
    for (const role of ROLES) {
      for (const s of getStepsForRole(role) as GuideStep[]) {
        if (!s.tryPath) continue;
        expect(paths, `${role} 引用 ${s.tryPath} 不在 menuConfig`).toContain(s.tryPath);
        expect(canAccess(s.tryPath, role), `${role} 无权访问引导目标页 ${s.tryPath}`).toBe(true);
        expect(!!s.tryName?.trim(), `${role} ${s.tryPath} 缺 tryName`).toBe(true);
        expect(!!s.tryHint?.trim(), `${role} ${s.tryPath} 缺 tryHint`).toBe(true);
      }
    }
  });

  it('未知角色回落 admin 配置；完成/进度 key 带角色维度', () => {
    expect(getStepsForRole('unknown-role')).toEqual(getStepsForRole('admin'));
    expect(getStepsForRole(undefined)).toEqual(getStepsForRole('admin'));
    expect(tourDoneKey('admin')).toBe('onboarding.web.admin.v2');
    expect(tourDoneKey('compliance')).not.toBe(tourDoneKey('admin'));
    expect(tourProgressKey('admin')).toBe('onboarding.web.admin.progress');
    expect(tourProgressKey('admin')).not.toBe(tourDoneKey('admin'));
  });
});
