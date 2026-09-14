/** 分享落地页纯逻辑（部署挂账 §4）：抽出以便 vitest 直测（项目无组件测试基建） */

export const TWIN_DEEP_LINK_PREFIX = 'medagent-doctor://twin/';

/** 医生端 App 深链：落地页「打开 App」按钮与后端深链形态共用同一拼法 */
export function buildTwinDeepLink(token: string): string {
  return `${TWIN_DEEP_LINK_PREFIX}${token}`;
}

/** token 合法形态：32 位 hex（ShareLink.url_token = uuid4().hex），手抄容错去空格 */
export function normalizeShareToken(raw: string | undefined | null): string | null {
  const token = (raw ?? '').trim();
  return /^[0-9a-f]{32}$/.test(token) ? token : null;
}
