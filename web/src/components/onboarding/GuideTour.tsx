import { useCallback, useEffect, useState } from 'react';
import { Modal, Button, FloatButton, message } from 'antd';
import { QuestionCircleOutlined, ArrowRightOutlined } from '@ant-design/icons';
import { useNavigate } from 'react-router-dom';
import { getStepsForRole, tourDoneKey, tourProgressKey } from './tourSteps';

/** card=讲解卡；trying=已导航到目标页，页面完全可操作，悬浮球挂「继续」召回 */
type Phase = 'card' | 'trying';

/** 进度持久化形状：{ c: 步号, t: 'card'|'trying' }。trying 也落盘——lazy 页面首航时
 *  App.tsx 外层 Suspense 会卸载整棵树（含本组件），重挂后凭此恢复体验态而不是误弹卡。 */
interface SavedProgress {
  c: number;
  t: Phase;
}

function readProgress(key: string): SavedProgress | null {
  try {
    const raw = localStorage.getItem(key);
    if (!raw) return null;
    const v = JSON.parse(raw) as Partial<SavedProgress>;
    if (typeof v.c !== 'number' || (v.t !== 'card' && v.t !== 'trying')) return null;
    return { c: v.c, t: v.t };
  } catch {
    return null;
  }
}

function writeProgress(key: string, c: number, t: Phase) {
  localStorage.setItem(key, JSON.stringify({ c, t }));
}

/**
 * 陪玩式新人引导（2026-09-10 v4，替代 v1 antd Tour——Tour 气泡无法跨页导航/收卡召回）。
 * 状态机：card（讲解卡）→「去试试」→ navigate(tryPath) 收卡、目标页自由体验 →
 * 点悬浮球「继续」→ 召回卡 →「下一个」→ 下一步；「上一个」可回退重看（首步禁用）。
 * v4：每张讲解卡固定四按钮——跳过引导 / 上一个（首步禁用）/ 下一个（末步收尾）/ 去试试
 * （v4 起全部步骤都配 tryPath，见 tourSteps.ts）。
 * 进度写 localStorage 断点续传；跳过=完成不再骚扰；"?"悬浮球平时=重看入口。
 * 必须挂在 AdminLayout 内（Modal 跨路由存活）。
 */
export default function GuideTour({ role }: { role?: string }) {
  const navigate = useNavigate();
  const steps = getStepsForRole(role);
  const doneKey = tourDoneKey(role);
  const progressKey = tourProgressKey(role);

  const [active, setActive] = useState(false); // 引导进行中（含看卡/体验两态）
  const [open, setOpen] = useState(false); // 讲解/召回卡可见
  const [current, setCurrent] = useState(0);
  const [phase, setPhase] = useState<Phase>('card');

  // 首登（未看过）自动开演；断点续传——上次中断在体验态则恢复体验态（不弹卡，悬浮球召回）
  useEffect(() => {
    if (!localStorage.getItem(doneKey)) {
      const saved = readProgress(progressKey);
      const c = saved && saved.c > 0 ? Math.min(saved.c, steps.length - 1) : 0;
      setActive(true);
      setCurrent(c);
      if (saved?.t === 'trying') {
        setPhase('trying');
        setOpen(false);
      } else {
        setPhase('card');
        setOpen(true);
      }
    }
  }, [doneKey, progressKey, steps.length]);

  const finish = useCallback(() => {
    localStorage.setItem(doneKey, '1');
    localStorage.removeItem(progressKey);
    setActive(false);
    setOpen(false);
  }, [doneKey, progressKey]);

  /** 「下一个」→ 前进；末步收尾（进度持久化） */
  const advance = useCallback(() => {
    const next = current + 1;
    if (next >= steps.length) {
      finish();
      return;
    }
    writeProgress(progressKey, next, 'card');
    setCurrent(next);
    setPhase('card');
    setOpen(true);
  }, [current, steps.length, finish, progressKey]);

  /** 「上一个」→ 回退重看（首步禁用；体验态召回卡里点也回上一步的讲解卡） */
  const back = useCallback(() => {
    if (current === 0) return;
    const prev = current - 1;
    writeProgress(progressKey, prev, 'card');
    setCurrent(prev);
    setPhase('card');
    setOpen(true);
  }, [current, progressKey]);

  /** 「去试试」→ 导航到目标页，收卡进体验态 */
  const goTry = useCallback(() => {
    const step = steps[current];
    if (!step?.tryPath) return;
    writeProgress(progressKey, current, 'trying');
    setPhase('trying');
    setOpen(false);
    navigate(step.tryPath);
    if (step.tryHint) {
      message.info({ content: step.tryHint, duration: 5 });
    }
  }, [current, steps, navigate]);

  /** 悬浮球：体验中=召回「我知道了」；平时=重看（从第 1 步重演，完成标记不动） */
  const onFloatClick = useCallback(() => {
    if (active && phase === 'trying') {
      setOpen(true);
      return;
    }
    if (!active) {
      localStorage.removeItem(progressKey);
      setCurrent(0);
      setPhase('card');
      setActive(true);
      setOpen(true);
    }
  }, [active, phase]);

  if (!steps.length) return null;
  const step = steps[current];
  const recall = active && phase === 'trying';
  const stepLabel = (
    <span style={{ color: 'rgba(0,0,0,0.45)', fontSize: 13 }}>
      第 {current + 1} / {steps.length} 步
    </span>
  );

  return (
    <>
      <Modal
        open={open && active}
        closable={false}
        keyboard={false}
        maskClosable={false}
        footer={null}
        width={480}
        title={recall ? `在「${step?.tryName ?? '目标页'}」逛得如何？` : step?.title}
      >
        <p style={{ lineHeight: 1.8, marginBottom: 20 }}>{recall ? step?.tryHint : step?.description}</p>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
          {recall ? (
            <>
              {stepLabel}
              <div>
                <Button style={{ marginRight: 8 }} disabled={current === 0} onClick={back}>
                  上一个
                </Button>
                <Button style={{ marginRight: 8 }} onClick={() => setOpen(false)}>
                  先收起，继续逛
                </Button>
                <Button type="primary" onClick={advance}>
                  下一个
                </Button>
              </div>
            </>
          ) : (
            <>
              {stepLabel}
              <div>
                <Button type="text" onClick={finish}>
                  跳过引导
                </Button>
                <Button style={{ marginRight: 8 }} disabled={current === 0} onClick={back}>
                  上一个
                </Button>
                <Button style={{ marginRight: 8 }} onClick={advance}>
                  下一个
                </Button>
                <Button type="primary" icon={<ArrowRightOutlined />} onClick={goTry}>
                  去试试
                </Button>
              </div>
            </>
          )}
        </div>
      </Modal>
      {/* 纯侧边布局无顶栏（headerContentRender 死代码）——固定右下角"?"悬浮球；体验态变「继续」召回锚点 */}
      <FloatButton
        data-tour="help-btn"
        tooltip={recall ? '继续引导' : '功能引导'}
        badge={recall ? { count: '继续' } : undefined}
        icon={<QuestionCircleOutlined />}
        onClick={onFloatClick}
      />
    </>
  );
}
