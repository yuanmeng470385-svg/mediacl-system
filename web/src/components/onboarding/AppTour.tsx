/**
 * 新人引导 Tour（antd 5 自带 Tour，零新依赖）。
 *
 * 触发：登录进 layout 且 localStorage 未置位时自动开演；"?"按钮 replayToken 变化可重看。
 * 降级：菜单目标元素惰性查找，找不到（折叠/未渲染）时 antd Tour 自动居中显示该步，不崩。
 */
import { useEffect, useMemo, useState } from 'react';
import { Tour } from 'antd';
import type { TourProps } from 'antd';
import { getStepsForRole, tourDoneKey, type GuideStep } from './tourSteps';

const HELP_SELECTOR = '[data-tour="help-btn"]';

function toTourSteps(steps: GuideStep[]): TourProps['steps'] {
  return steps.map((s) => ({
    title: s.title,
    description: s.description,
    // 类型收窄为 () => HTMLElement（antd 类型定义不接受联合 null）；运行时
    // querySelector 为 null 时 antd Tour 内部判空降级居中显示，不会崩。
    target: s.menuPath
      ? s.menuPath === '__help__'
        ? () => document.querySelector(HELP_SELECTOR) as HTMLElement
        : () => document.querySelector(`[data-tour-menu="${s.menuPath}"]`) as HTMLElement
      : undefined,
  }));
}

interface Props {
  role?: string;
  /** 变化即重放引导（AdminLayout "?" 按钮 setReplayToken(Date.now())） */
  replayToken?: number;
}

export default function AppTour({ role, replayToken }: Props) {
  const [open, setOpen] = useState(false);

  const doneKey = tourDoneKey(role);

  // 首次进入（或换角色登录）：未看过才自动开演
  useEffect(() => {
    if (!role) return;
    if (!localStorage.getItem(doneKey)) setOpen(true);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [doneKey]);

  // "?" 重看：token 变化强制开演（无视已看过标记）
  useEffect(() => {
    if (replayToken) setOpen(true);
  }, [replayToken]);

  const steps = useMemo(() => toTourSteps(getStepsForRole(role)), [role]);

  const handleClose: TourProps['onClose'] = () => {
    localStorage.setItem(doneKey, String(Date.now()));
    setOpen(false);
  };

  return (
    <Tour
      open={open}
      onClose={handleClose}
      steps={steps}
      // 遮罩压过 ProLayout header（header 无更高 z-index，默认即可，显式声明防御性）
      zIndex={1100}
      indicatorsRender={(current, total) => (
        <span style={{ color: 'rgba(255,255,255,0.85)' }}>
          {current + 1} / {total}
        </span>
      )}
    />
  );
}
