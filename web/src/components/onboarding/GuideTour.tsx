import { useCallback, useEffect, useRef, useState } from 'react';
import { Button, FloatButton, Tooltip, theme } from 'antd';
import { BulbOutlined, HolderOutlined, QuestionCircleOutlined } from '@ant-design/icons';
import { useNavigate } from 'react-router-dom';
import { getStepsForRole, tourDoneKey, tourProgressKey } from './tourSteps';

/** 卡片默认宽度；高度/宽度都用来做视口夹紧，改这里即可 */
const CARD_WIDTH = 520;
/** 卡片距视口边缘的最小留白 */
const EDGE = 8;
/** 卡片位置（拖动后）持久化 key——换页/刷新后还在原地，别改 */
const POS_KEY = 'onboarding.web.tour.pos';

/** 进度持久化形状：{ c: 步号 }。lazy 页面首航时 App.tsx 外层 Suspense 会卸载整棵树（含本组件），
 *  重挂后凭此回到原步骤而不是从开头重演——所以跳步必须先落盘再 navigate。 */
interface SavedProgress {
  c: number;
}

interface CardPos {
  x: number;
  y: number;
}

function readProgress(key: string): number | null {
  try {
    const raw = localStorage.getItem(key);
    if (!raw) return null;
    // 兼容 v4 以前的 { c, t } 旧形状：t（card/trying）已随试验态下线，只取步号
    const v = JSON.parse(raw) as Partial<SavedProgress>;
    return typeof v.c === 'number' ? v.c : null;
  } catch {
    return null;
  }
}

function writeProgress(key: string, c: number) {
  localStorage.setItem(key, JSON.stringify({ c }));
}

function readPos(): CardPos | null {
  try {
    const raw = localStorage.getItem(POS_KEY);
    if (!raw) return null;
    const v = JSON.parse(raw) as Partial<CardPos>;
    return typeof v.x === 'number' && typeof v.y === 'number' ? { x: v.x, y: v.y } : null;
  } catch {
    return null;
  }
}

/**
 * 新人引导（2026-09-15 v5.1：可拖动 + 大白话详解 + 卡内「到这一页可以」提示条）。
 * 交互：点「上一个/下一个」→ 自动导航到该步页面，**卡片不收起**——页面完全可操作
 * （浮层无遮罩、不锁 body 滚动、不抢焦点），用户一边看卡一边上手；卡片可按住标题栏拖到任意位置，
 * 位置记在 localStorage（换页/刷新后不跳回中间）。结束只有两条路：点「跳过引导」，或末步点「完成」。
 * 文案面向非技术同事：每页说清「这是干什么的/在这里能做什么/到什么程度算正常」，不堆术语。
 * 进度写 localStorage 断点续传；跳过=完成不再骚扰；"?"悬浮球平时=重看入口（引导进行中隐藏）。
 * 必须挂在 AdminLayout 内（浮层跨路由存活）。
 */
export default function GuideTour({ role }: { role?: string }) {
  const navigate = useNavigate();
  const steps = getStepsForRole(role);
  const doneKey = tourDoneKey(role);
  const progressKey = tourProgressKey(role);
  const { token } = theme.useToken();

  const [active, setActive] = useState(false); // 引导进行中（卡片常驻可见）
  const [current, setCurrent] = useState(0);

  const cardRef = useRef<HTMLDivElement | null>(null);
  const dragRef = useRef<{ dx: number; dy: number } | null>(null); // 拖动时指针相对卡片左上角的偏移
  const posRef = useRef<CardPos>({ x: 0, y: 0 });
  const [dragging, setDragging] = useState(false);
  // 初始位置：优先用上次拖到的地方，否则顶部居中（落在内容区上方，不挡左侧菜单）
  const [pos, setPos] = useState<CardPos>(() => {
    const saved = readPos();
    posRef.current = saved ?? { x: Math.max(EDGE, Math.round(window.innerWidth / 2 - CARD_WIDTH / 2)), y: 88 };
    return posRef.current;
  });

  /** 把卡片夹在视口内（拖动中与窗口缩放时用）；元素未挂载时按常量估算 */
  const clampToViewport = useCallback((x: number, y: number): CardPos => {
    const el = cardRef.current;
    const w = el?.offsetWidth ?? CARD_WIDTH;
    const h = el?.offsetHeight ?? 240;
    return {
      x: Math.min(Math.max(EDGE, x), Math.max(EDGE, window.innerWidth - w - EDGE)),
      y: Math.min(Math.max(EDGE, y), Math.max(EDGE, window.innerHeight - h - EDGE)),
    };
  }, []);

  const applyPos = useCallback((p: CardPos) => {
    posRef.current = p;
    setPos(p);
  }, []);

  // 窗口大小变化后重新夹紧（把浏览器窗口拖小，卡片不至于跑到屏幕外）
  useEffect(() => {
    const onResize = () => applyPos(clampToViewport(posRef.current.x, posRef.current.y));
    window.addEventListener('resize', onResize);
    return () => window.removeEventListener('resize', onResize);
  }, [applyPos, clampToViewport]);

  /** 按住标题栏开始拖（只认左键/单指；触屏靠 touchAction:none 拿到 move 事件） */
  const onDragStart = (e: React.PointerEvent<HTMLDivElement>) => {
    if (e.button !== 0) return;
    const rect = cardRef.current?.getBoundingClientRect();
    if (!rect) return;
    dragRef.current = { dx: e.clientX - rect.left, dy: e.clientY - rect.top };
    cardRef.current?.setPointerCapture(e.pointerId); // 指针移出卡片也能继续跟手
    setDragging(true);
  };

  const onDragMove = (e: React.PointerEvent<HTMLDivElement>) => {
    const d = dragRef.current;
    if (!d) return;
    applyPos(clampToViewport(e.clientX - d.dx, e.clientY - d.dy));
  };

  const onDragEnd = () => {
    if (!dragRef.current) return;
    dragRef.current = null;
    setDragging(false); // 指针抬起时浏览器自动释放捕获
    localStorage.setItem(POS_KEY, JSON.stringify(posRef.current));
  };

  // 首登（未看过）自动开演；断点续传——从上次中断的步号继续（不主动导航，避免登录后被动跳页）
  useEffect(() => {
    if (localStorage.getItem(doneKey)) return;
    const saved = readProgress(progressKey);
    setCurrent(saved !== null && saved > 0 ? Math.min(saved, steps.length - 1) : 0);
    setActive(true);
  }, [doneKey, progressKey, steps.length]);

  const finish = useCallback(() => {
    localStorage.setItem(doneKey, '1');
    localStorage.removeItem(progressKey);
    setActive(false);
  }, [doneKey, progressKey]);

  /** 跳步：先落盘再导航（导航可能触发 Suspense 整树重挂），卡片本身不动、不收 */
  const goto = useCallback(
    (index: number) => {
      writeProgress(progressKey, index);
      setCurrent(index);
      const step = steps[index];
      if (step?.navPath) navigate(step.navPath);
    },
    [steps, navigate, progressKey],
  );

  /** 「下一个」→ 前进；末步即收尾（卡片消失的另一条路：跳过引导 / 看完最后一步） */
  const advance = useCallback(() => {
    const next = current + 1;
    if (next >= steps.length) {
      finish();
      return;
    }
    goto(next);
  }, [current, steps.length, finish, goto]);

  /** 「上一个」→ 回退重看（首步禁用），同样自动跳回该步页面 */
  const back = useCallback(() => {
    if (current > 0) goto(current - 1);
  }, [current, goto]);

  /** "?"悬浮球：平时=重看（从第 1 步重演，完成标记不动）；引导进行中卡片常驻，悬浮球不渲染 */
  const onRestart = useCallback(() => {
    localStorage.removeItem(progressKey);
    setCurrent(0);
    setActive(true);
  }, [progressKey]);

  if (!steps.length) return null;
  const step = steps[current];
  const last = current === steps.length - 1;

  return (
    <>
      {/* 常驻浮层：不用 antd Modal——Modal 的 ScrollLocker 会锁 body 滚动（mask=false 也锁），
          与「一个方向键带你看一页、页面照样能操作」冲突；这里用 fixed 卡片自持样式 */}
      {active && step && (
        <div
          ref={cardRef}
          role="dialog"
          aria-label="功能引导"
          onPointerMove={onDragMove}
          onPointerUp={onDragEnd}
          onPointerCancel={onDragEnd}
          style={{
            position: 'fixed',
            left: pos.x,
            top: pos.y,
            width: CARD_WIDTH,
            maxWidth: `calc(100vw - ${EDGE * 2}px)`,
            zIndex: 900,
            background: token.colorBgElevated,
            borderRadius: token.borderRadiusLG,
            boxShadow: token.boxShadowSecondary,
            padding: '16px 20px 20px',
            userSelect: dragging ? 'none' : undefined,
          }}
        >
          {/* 标题栏即拖动把手：按住挪到任意位置，位置会被记住 */}
          <div
            onPointerDown={onDragStart}
            style={{
              display: 'flex',
              alignItems: 'center',
              gap: 8,
              marginBottom: 10,
              cursor: 'move',
              touchAction: 'none',
              userSelect: 'none',
              marginLeft: -4,
            }}
          >
            <Tooltip title="按住这里可以把卡片拖到任意位置">
              <HolderOutlined style={{ color: token.colorTextTertiary, fontSize: 14 }} />
            </Tooltip>
            <div style={{ flex: 1, fontSize: 16, fontWeight: 600, color: token.colorTextHeading }}>
              {step.title}
            </div>
            <span style={{ color: token.colorTextTertiary, fontSize: 12, whiteSpace: 'nowrap' }}>
              第 {current + 1} / {steps.length} 步
            </span>
          </div>

          <div
            style={{
              lineHeight: 1.9,
              color: token.colorText,
              maxHeight: '48vh',
              overflowY: 'auto',
              marginBottom: 12,
            }}
          >
            {step.description}
          </div>

          {/* 到页指引常驻卡内（比一闪而过的提示更好找）：这一页上手先看什么 */}
          {step.navHint && (
            <div
              style={{
                display: 'flex',
                gap: 8,
                background: token.colorPrimaryBg,
                borderRadius: token.borderRadius,
                padding: '8px 12px',
                marginBottom: 16,
                fontSize: 13,
                lineHeight: 1.7,
                color: token.colorTextSecondary,
              }}
            >
              <BulbOutlined style={{ color: token.colorPrimary, marginTop: 3 }} />
              <span>
                <strong style={{ color: token.colorPrimary }}>到这一页可以：</strong>
                {step.navHint}
              </span>
            </div>
          )}

          <div style={{ display: 'flex', justifyContent: 'flex-end', alignItems: 'center' }}>
            <Button type="text" onClick={finish}>
              跳过引导
            </Button>
            <Button style={{ marginRight: 8 }} disabled={current === 0} onClick={back}>
              上一个
            </Button>
            <Button type="primary" onClick={advance}>
              {last ? '完成' : '下一个'}
            </Button>
          </div>
        </div>
      )}
      {/* 右下角"?"悬浮球：平时=重看入口；引导进行中卡片已常驻，不再渲染（避免死按钮） */}
      {!active && (
        <FloatButton
          data-tour="help-btn"
          tooltip="功能引导"
          icon={<QuestionCircleOutlined />}
          onClick={onRestart}
        />
      )}
    </>
  );
}
