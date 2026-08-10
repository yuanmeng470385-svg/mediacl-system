import { memo, type ReactNode } from 'react';

export type CharacterState = 'working' | 'idle' | 'offline';

export interface CharacterVariant {
  hairStyle: 'short' | 'long' | 'bun' | 'crew' | 'curly';
  hairColor: string;
  skin: string;
  suit: string;
  glasses: boolean;
}

export const STATE_TINTS: Record<CharacterState, string> = {
  working: '#1677ff',
  idle: '#faad14',
  offline: '#bfbfbf',
};

const HAIR_STYLES = ['short', 'long', 'bun', 'crew', 'curly'] as const;
const HAIR_COLORS = ['#333333', '#5b3a1e', '#b8860b', '#7a3b3b'];
const SKIN_TONES = ['#ffd9b3', '#c68a5c'];
const SUITS = ['#1f4e79', '#4a4a4a'];

/** 按专员 id 确定性分配形象 —— 同一专员每次渲染长相一致 */
export function variantForId(id: number): CharacterVariant {
  return {
    hairStyle: HAIR_STYLES[id % HAIR_STYLES.length],
    hairColor: HAIR_COLORS[id % HAIR_COLORS.length],
    skin: SKIN_TONES[(id >> 1) % SKIN_TONES.length],
    suit: SUITS[(id >> 2) % SUITS.length],
    glasses: id % 4 === 0,
  };
}

/** 眨眼相位按 id 错开（负延迟 = 从动画中途开始） */
function blinkDelay(id: number): string {
  return `${-(id % 7) * 0.4}s`;
}

const CSS = `
@keyframes ch-blink { 0%, 5%, 100% { transform: scaleY(0.08); } 7.5% { transform: scaleY(1); } }
.ch-blink { animation: ch-blink 4s infinite; transform-origin: 50% 0; transform-box: fill-box; }
@keyframes ch-breathe { 0%, 100% { transform: scale(1); } 50% { transform: scale(1.015); } }
.ch-breathe { animation: ch-breathe 3s ease-in-out infinite; transform-origin: 60px 116px; }
.ch-dim { opacity: 0.45; filter: grayscale(1); }
`;

/** 头部+躯干角色（viewBox 120×140，桌面以下不可见，手臂由工位组件画） */
function SpecialistCharacter({ id, state }: { id: number; state: CharacterState }) {
  const v = variantForId(id);
  const off = state === 'offline';
  const skin = off ? '#d9d9d9' : v.skin;
  const hair = off ? '#b5b5b5' : v.hairColor;
  const suit = off ? '#8c8c8c' : v.suit;
  const shirt = off ? '#e8e8e8' : '#f2f2f2';
  const eye = off ? '#a8a8a8' : '#333333';

  const hairPath: Record<CharacterVariant['hairStyle'], ReactNode> = {
    crew: <path d="M40 38 Q42 22 60 22 Q78 22 80 38 Q78 33 60 32 Q42 33 40 38 Z" fill={hair} />,
    short: <path d="M40 38 Q40 18 60 18 Q80 18 80 38 L80 41 Q74 31 60 31 Q46 31 40 41 Z" fill={hair} />,
    bun: (
      <g fill={hair}>
        <path d="M42 38 Q42 20 60 20 Q78 20 78 38 Q78 33 60 32 Q42 33 42 38 Z" />
        <circle cx="60" cy="13" r="7" />
      </g>
    ),
    long: (
      <g fill={hair}>
        <path d="M42 38 Q42 20 60 20 Q78 20 78 38 L78 46 Q74 58 66 64 Q64 58 60 56 Q56 58 54 64 Q46 58 42 46 Z" />
      </g>
    ),
    curly: (
      <g fill={hair}>
        <path d="M40 38 Q40 20 60 20 Q80 20 80 38 Q80 33 60 32 Q40 33 40 38 Z" />
        <circle cx="50" cy="20" r="6" />
        <circle cx="60" cy="17" r="6" />
        <circle cx="70" cy="20" r="6" />
      </g>
    ),
  };

  return (
    <svg viewBox="0 0 120 140" role="img" style={{ display: 'block', width: '100%', height: '100%' }}>
      <style>{CSS}</style>
      <g className={off ? 'ch-dim' : 'ch-breathe'}>
        {/* 躯干：西装外套 + 衬衫 + 领带 */}
        <path d="M38 74 L34 116 L86 116 L82 74 Q60 66 38 74 Z" fill={suit} />
        <path d="M47 76 L60 92 L73 76 L73 116 L47 116 Z" fill={shirt} />
        <path d="M57 78 L63 78 L63 97 L60 102 L57 97 Z" fill={off ? '#bdbdbd' : STATE_TINTS[state]} />
        {/* 脖子 */}
        <rect x="54" y="58" width="12" height="10" fill={skin} />
        {/* 头 */}
        <circle cx="60" cy="42" r="22" fill={skin} />
        {/* 发型（按变体） */}
        {hairPath[v.hairStyle]}
        {/* 眼 + 眨眼眼皮 */}
        <g>
          <circle cx="52" cy="42" r="2.6" fill={eye} />
          <circle cx="68" cy="42" r="2.6" fill={eye} />
          <rect x="47" y="38" width="10" height="6" rx="2" fill={skin} className="ch-blink" style={{ animationDelay: blinkDelay(id) }} />
          <rect x="63" y="38" width="10" height="6" rx="2" fill={skin} className="ch-blink" style={{ animationDelay: blinkDelay(id) }} />
        </g>
        {/* 眼镜（约 1/4 专员） */}
        {v.glasses && (
          <g stroke="#444444" strokeWidth="1.5" fill="none">
            <circle cx="52" cy="42" r="7" />
            <circle cx="68" cy="42" r="7" />
            <path d="M59 42 L61 42" />
            <path d="M45 40 L43 36" />
            <path d="M75 40 L77 36" />
          </g>
        )}
        {/* 微笑 */}
        <path d="M54 50 Q60 54 66 50" stroke={off ? '#a8a8a8' : '#a06a3f'} strokeWidth="1.6" fill="none" strokeLinecap="round" />
      </g>
    </svg>
  );
}

/** 迷你角色（头部+肩部特写，状态条用） */
export function MiniCharacter({ id, state, size = 24 }: { id: number; state: CharacterState; size?: number }) {
  const v = variantForId(id);
  const off = state === 'offline';
  const skin = off ? '#d9d9d9' : v.skin;
  const hair = off ? '#b5b5b5' : v.hairColor;
  const suit = off ? '#8c8c8c' : v.suit;
  return (
    <svg width={size} height={size} viewBox="0 0 44 44" role="img" style={{ display: 'block', flexShrink: 0 }}>
      <path d="M6 44 Q22 33 38 44 Z" fill={suit} />
      <circle cx="22" cy="17" r="12" fill={skin} />
      <path d="M10 19 Q10 7 22 7 Q34 7 34 19 Q34 14 22 13 Q10 14 10 19 Z" fill={hair} />
      {v.hairStyle === 'bun' && <circle cx="22" cy="4" r="3.5" fill={hair} />}
      <circle cx="18" cy="18" r="1.5" fill={off ? '#a8a8a8' : '#333'} />
      <circle cx="26" cy="18" r="1.5" fill={off ? '#a8a8a8' : '#333'} />
      {v.glasses && (
        <g stroke="#444444" strokeWidth="1" fill="none">
          <circle cx="18" cy="18" r="4" />
          <circle cx="26" cy="18" r="4" />
        </g>
      )}
    </svg>
  );
}

export default memo(SpecialistCharacter);
