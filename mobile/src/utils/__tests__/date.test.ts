/**
 * 本地日期工具测试：锁住"本地日期"语义，
 * 防止回退到 toISOString().split('T')[0] 的 UTC 日期 bug。
 */
import { formatLocalDate } from '../date';

describe('formatLocalDate', () => {
  it('返回本地年月日拼的 YYYY-MM-DD', () => {
    // 本地 2026-08-06 01:30（不依赖机器时区）
    const d = new Date(2026, 7, 6, 1, 30);
    expect(formatLocalDate(d)).toBe('2026-08-06');
  });

  it('补零：个位月/日补前导 0', () => {
    const d = new Date(2026, 0, 5, 10, 0);
    expect(formatLocalDate(d)).toBe('2026-01-05');
  });

  it('本地凌晨 ≠ UTC 前一天（旧 toISOString 写法会取错日期）', () => {
    const d = new Date(2026, 7, 6, 1, 30); // 本地 8 月 6 日凌晨
    // 若机器时区为 UTC+X（X>0），toISOString 的 UTC 日期是 8 月 5 日 —— 即旧实现的 bug
    expect(formatLocalDate(d)).toBe('2026-08-06');
    const utcDate = d.toISOString().split('T')[0];
    if (new Date().getTimezoneOffset() < 0) {
      expect(utcDate).not.toBe('2026-08-06');
    }
  });

  it('不带参数时返回今天（本地日期，格式正确）', () => {
    const today = formatLocalDate();
    expect(today).toMatch(/^\d{4}-\d{2}-\d{2}$/);
    expect(today).toBe(formatLocalDate(new Date()));
  });
});
