/**
 * 日期工具
 */

/**
 * 取本地日期 YYYY-MM-DD。
 *
 * 不要用 toISOString().split('T')[0] —— 那是 UTC 日期，东八区凌晨 0-8 点
 * 会取到"昨天"（audit 2026-08-06 UTC 日期 bug）。这里用本地年月日拼。
 */
export function formatLocalDate(date: Date = new Date()): string {
  const y = date.getFullYear();
  const m = String(date.getMonth() + 1).padStart(2, '0');
  const d = String(date.getDate()).padStart(2, '0');
  return `${y}-${m}-${d}`;
}
