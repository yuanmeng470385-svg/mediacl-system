/**
 * 审计 action 中文映射的完整性守卫：后端各服务审计字面量（2026-08-26 全量枚举
 * 76 个）若新增 action 而本表未登记，界面会回退显示原始值——数量断言防漏配
 * （与 routeAccess.test.ts 的 26 条路由断言同款硬断言风格）。
 */
import { describe, expect, it } from 'vitest';
import { AUDIT_ACTION_MAP } from './audit';

describe('AUDIT_ACTION_MAP（审计 action → 中文文案）', () => {
  it('覆盖后端全部 76 个审计 action', () => {
    expect(Object.keys(AUDIT_ACTION_MAP).length).toBe(76);
  });

  it('key 均为 snake_case 字面量，value 均为非空中文文案', () => {
    for (const [k, v] of Object.entries(AUDIT_ACTION_MAP)) {
      expect(k, k).toMatch(/^[a-z][a-z0-9_]*$/);
      expect(v, k).not.toBe('');
      expect(v, k).toMatch(/[一-鿿]/);
    }
  });

  it('常见操作文案正确', () => {
    expect(AUDIT_ACTION_MAP.chat_response).toBe('对话回复');
    expect(AUDIT_ACTION_MAP.specialist_freeze).toBe('冻结数字专员');
    expect(AUDIT_ACTION_MAP.export_request_review).toBe('审批导出申请');
    expect(AUDIT_ACTION_MAP.auth_login_failed).toBe('登录失败');
  });
});
