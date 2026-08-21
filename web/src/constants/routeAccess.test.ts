/**
 * M17（2026-08-21 审计）：web 前端角色访问控制。
 *
 * 路由角色表以后端各端点 require_roles 为单一事实源（前端收紧只是少看菜单，
 * 放宽则会把用户引到 403 页面）；守卫 + 菜单过滤都消费本模块，禁止各写一份。
 */
import { describe, expect, it } from 'vitest';
import { canAccess, isKnownRoute, filterMenu, ROUTE_ACCESS } from './routeAccess';

const FOUR = ['admin', 'manager', 'compliance', 'medical'];
const THREE = ['admin', 'manager', 'compliance'];
const TWO = ['admin', 'manager'];

describe('canAccess（路由→角色表）', () => {
  it('medical 看不到合规风控三角色域（审计/合规/隐私/数据治理）', () => {
    for (const p of ['/audit/list', '/compliance/list', '/compliance/monitor',
                     '/privacy/requests', '/data/exports', '/data/assets']) {
      expect(canAccess(p, 'medical'), p).toBe(false);
    }
  });

  it('compliance 看不到管理域（医生管理/用户管理/系统配置）', () => {
    for (const p of ['/doctor/list', '/user/list', '/system/config']) {
      expect(canAccess(p, 'compliance'), p).toBe(false);
    }
  });

  it('system/config 仅 admin（网关端点硬编码 role==admin）', () => {
    expect(canAccess('/system/config', 'admin')).toBe(true);
    expect(canAccess('/system/config', 'manager')).toBe(false);
  });

  it('admin 全部已登记路由可达（表内无 admin 拒绝项）', () => {
    for (const p of Object.keys(ROUTE_ACCESS)) {
      expect(canAccess(p, 'admin'), p).toBe(true);
    }
  });

  it('动态段路由按模板匹配（/doctor/123 走 /doctor/:id 规则）', () => {
    expect(canAccess('/doctor/123', 'admin')).toBe(true);
    expect(canAccess('/doctor/123', 'medical')).toBe(false);
  });

  it('未登录/无角色一律拒绝', () => {
    expect(canAccess('/dashboard', null)).toBe(false);
    expect(canAccess('/dashboard', undefined)).toBe(false);
  });

  it('不在表内的路径不归本表管（交给 Router 404，不误变 403）', () => {
    expect(isKnownRoute('/no/such/page')).toBe(false);
    expect(isKnownRoute('/doctor/99')).toBe(true);
  });

  it('角色表覆盖全部已登记路由（防新增页面漏配）', () => {
    // 与 App.tsx 路由清单同步的硬断言：数量一旦变化须有意识地更新本表
    // （App.tsx 26 条页面路由：dashboard 1 + specialist 2 + visit/knowledge 2 +
    //  compliance 6 + data 2 + privacy/audit 2 + doctor 3 + user/filing/cert/
    //  training/skill 5 + patient-edu 2 + system 1）
    expect(Object.keys(ROUTE_ACCESS).length).toBe(26);
  });
});

describe('filterMenu（菜单按角色过滤）', () => {
  it('medical：无审计/医生管理/用户管理/系统配置，有数字专员/知识库', () => {
    const paths = filterMenu(
      [{ path: '/audit/list' }, { path: '/doctor/list' }, { path: '/user/list' },
       { path: '/system/config' }, { path: '/specialist/list' }, { path: '/knowledge/list' }],
      'medical',
    ).map((m) => m.path);
    expect(paths).toEqual(['/specialist/list', '/knowledge/list']);
  });

  it('manager：无系统配置（仅 admin），其余示例项可见', () => {
    const paths = filterMenu(
      [{ path: '/system/config' }, { path: '/audit/list' }, { path: '/user/list' }],
      'manager',
    ).map((m) => m.path);
    expect(paths).toEqual(['/audit/list', '/user/list']);
  });

  it('未登录不给菜单', () => {
    expect(filterMenu([{ path: '/dashboard' }], null)).toEqual([]);
  });
});

// 角色分层快照（后端事实源的固化；变更须对齐后端 require_roles）
describe('角色分层与后端对齐', () => {
  it('拜访管理任意登录角色（后端 get_current_user）', () => {
    for (const r of FOUR) expect(canAccess('/visit/list', r)).toBe(true);
  });

  it('知识库 KB_ADMIN_ROLES = admin/manager/medical', () => {
    expect(canAccess('/knowledge/list', 'compliance')).toBe(false);
    expect(canAccess('/knowledge/list', 'medical')).toBe(true);
  });

  it('触达统计四角色（academic-cards/stats）', () => {
    expect(canAccess('/compliance/card-stats', 'medical')).toBe(true);
  });
});
