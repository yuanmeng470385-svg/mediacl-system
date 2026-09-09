/**
 * 引导全局事件与状态（mini pub/sub，零依赖）：
 * - restartGuide：Settings「功能引导」清 key 后 emit，GuideController 从第 1 步重演
 * - setGuideBar/onGuideBar：体验态召回条的可见性（条挂在 App 根导航器外——
 *   native-stack push 后 MainTabs 屏视图会被 detach，条必须脱离导航器才能常驻）
 * - recallGuide：点召回条 emit，GuideController 弹出「我知道了，继续」召回卡
 */
type Cb = () => void;
type BarCb = (v: boolean) => void;

const listeners = new Set<Cb>();
const recallListeners = new Set<Cb>();
const barListeners = new Set<BarCb>();
let barVisible = false;

export function onGuideRestart(cb: Cb): () => void {
  listeners.add(cb);
  return () => {
    listeners.delete(cb);
  };
}

export function restartGuide(): void {
  listeners.forEach((cb) => cb());
}

export function onGuideRecall(cb: Cb): () => void {
  recallListeners.add(cb);
  return () => {
    recallListeners.delete(cb);
  };
}

export function recallGuide(): void {
  recallListeners.forEach((cb) => cb());
}

export function setGuideBar(v: boolean): void {
  barVisible = v;
  barListeners.forEach((cb) => cb(v));
}

/** 订阅即回调当前值（新挂载的条能立刻对齐状态） */
export function onGuideBar(cb: BarCb): () => void {
  barListeners.add(cb);
  cb(barVisible);
  return () => {
    barListeners.delete(cb);
  };
}
