import { memo } from 'react';

export type CharacterState = 'working' | 'idle' | 'offline';

export const STATE_TINTS: Record<CharacterState, string> = {
  working: '#1677ff',
  idle: '#faad14',
  offline: '#bfbfbf',
};

/** 眨眼相位按 id 错开（负延迟 = 从动画中途开始） */
function blinkDelay(id: number): string {
  return `${-(id % 7) * 0.4}s`;
}

const CSS = `
@keyframes ch-blink { 0%, 5%, 100% { transform: scaleY(0.08); } 7.5% { transform: scaleY(1); } }
.ch-blink { animation: ch-blink 4s infinite; transform-origin: 50% 0; transform-box: fill-box; }
@keyframes ch-breathe { 0%, 100% { transform: scale(1); } 50% { transform: scale(1.012); } }
.ch-breathe { animation: ch-breathe 3s ease-in-out infinite; transform-origin: 24px 54px; }
.ch-dim { opacity: 0.45; }
`;

/** 极简扁平 3D 白色小人（统一形象，身份由名牌区分；viewBox 48×60） */
function SpecialistCharacter({ id, state }: { id: number; state: CharacterState }) {
  const off = state === 'offline';
  const fill = off ? '#e3e3e3' : '#ffffff';
  const stroke = off ? '#b0b0b0' : '#666666';
  const eye = off ? '#bdbdbd' : '#333333';

  return (
    <svg viewBox="0 0 48 60" role="img" style={{ display: 'block', width: '100%', height: '100%' }}>
      <style>{CSS}</style>
      {/* 脚下椭圆投影（站立/棋子感） */}
      <ellipse cx="24" cy="57.5" rx="14" ry="2.5" fill="rgba(0,0,0,0.28)" />
      <g className={off ? 'ch-dim' : 'ch-breathe'}>
        {/* 腿 */}
        <rect x="18" y="50" width="5" height="8" rx="2.2" fill={fill} stroke={stroke} strokeWidth="0.8" />
        <rect x="25" y="50" width="5" height="8" rx="2.2" fill={fill} stroke={stroke} strokeWidth="0.8" />
        {/* 躯干（圆角） */}
        <rect x="15.5" y="30" width="17" height="21" rx="6" fill={fill} stroke={stroke} strokeWidth="1" />
        {/* 手臂（两侧小圆角条） */}
        <rect x="9" y="33" width="5.5" height="14" rx="2.7" fill={fill} stroke={stroke} strokeWidth="0.8" />
        <rect x="33.5" y="33" width="5.5" height="14" rx="2.7" fill={fill} stroke={stroke} strokeWidth="0.8" />
        {/* 脖子 + 头 */}
        <rect x="21" y="25" width="6" height="5" fill={fill} stroke={stroke} strokeWidth="0.6" />
        <circle cx="24" cy="16" r="12" fill={fill} stroke={stroke} strokeWidth="1" />
        {/* 眼 + 眨眼（白色眼皮在 7.5% 扫下盖住，静止时缩成顶部细线露出眼睛） */}
        <circle cx="19.5" cy="16.5" r="1.7" fill={eye} />
        <circle cx="28.5" cy="16.5" r="1.7" fill={eye} />
        <rect x="16.2" y="13" width="6.6" height="5" rx="2" fill={fill} className="ch-blink" style={{ animationDelay: blinkDelay(id) }} />
        <rect x="25.2" y="13" width="6.6" height="5" rx="2" fill={fill} className="ch-blink" style={{ animationDelay: blinkDelay(id) }} />
        {/* 微笑 */}
        <path d="M21 21.5 Q24 23.8 27 21.5" stroke={off ? '#c4c4c4' : '#8a8a8a'} strokeWidth="1.1" fill="none" strokeLinecap="round" />
      </g>
    </svg>
  );
}

/** 迷你角色（头部+肩部特写，状态条用；白色化，offline 灰化） */
export function MiniCharacter({ id, state, size = 24 }: { id: number; state: CharacterState; size?: number }) {
  const off = state === 'offline';
  const fill = off ? '#e3e3e3' : '#ffffff';
  const stroke = off ? '#b0b0b0' : '#666666';
  const eye = off ? '#bdbdbd' : '#333333';
  return (
    <svg width={size} height={size} viewBox="0 0 44 44" role="img" style={{ display: 'block', flexShrink: 0 }}>
      <path d="M6 44 Q22 33 38 44 Z" fill={fill} stroke={stroke} strokeWidth="1" />
      <circle cx="22" cy="17" r="12" fill={fill} stroke={stroke} strokeWidth="1" />
      <circle cx="18" cy="18" r="1.5" fill={eye} />
      <circle cx="26" cy="18" r="1.5" fill={eye} />
      <path d="M19 22 Q22 24 25 22" stroke={off ? '#c4c4c4' : '#8a8a8a'} strokeWidth="1.1" fill="none" strokeLinecap="round" />
    </svg>
  );
}

export default memo(SpecialistCharacter);
