# 数字员工办公室活人版 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 把数字专员办公室视图从卡片网格升级为正面房间场景 —— 所有专员以「活的」商务角色（SVG）同处一室，姿态随实时状态变化，仪表盘状态条同步迷你角色化。

**Architecture:** 纯前端改造。新增 `web/src/components/office/` 三个组件：`SpecialistCharacter`（形象变体 + 状态姿态 + 微动画）、`Workstation`（工位：显示器/桌面/角色/名牌/气泡/悬停操作）、`OfficeScene`（房间 + 排布 + 空态）。`SpecialistOffice.tsx` 把卡片网格换成场景（轮询/事件全部复用），`LiveStatusStrip.tsx` 的机器人图标换成迷你角色头像。零新依赖、零后端改动。

**Tech Stack:** React 18 + TypeScript + Vite + antd；动画用内联 SVG + CSS keyframes。

## Global Constraints

（摘自规格 `docs/superpowers/specs/2026-08-10-digital-office-scene-design.md`，逐条生效）

- **不加新依赖**（npm 包零新增；动画只许用 CSS keyframes）
- **零后端改动**；live-status 数据流与轮询逻辑原封不动
- 状态色固定：working `#1677ff` / idle `#faad14` / offline `#bfbfbf`
- 形象变体按 `specialist.id` 确定性分配（同一专员每次渲染长相一致）：发型 5 种 / 发色 4 种 / 肤色 2 种 / 眼镜约 1/4 / 西装 2 色
- 角色姿态：working=前倾敲键盘、idle=靠椅捧咖啡、offline=灰化半透明
- 微动画：眨眼 / 呼吸 / 打字手指 / 咖啡蒸汽 / 显示器蓝光脉动；按工位索引错开 delay
- 编辑必须先 `specialistAPI.detail(id)` 拉全量记录再开表单（防 persona 覆盖，既有修复必须保留）
- 交互保留：点工位=数据看板、悬停操作条（数据/编辑/停用·启用）、顶部工具条（汇总 Tag/3s 刷新开关/刷新/新增/Segmented 切表）
- 状态条保留：5s 轮询、最多 8 个、+N 折叠、点击跳转 `/specialist/list`
- 验证 = `cd web && npm run build` 全绿（项目无 JS 测试框架）；类型契约由 tsc 把关
- 提交信息用仓库惯例（中文，`feat:`/`fix:`/`refactor:` 前缀）

---

### Task 1: 角色组件 `SpecialistCharacter.tsx`

**Files:**
- Create: `web/src/components/office/SpecialistCharacter.tsx`

**Interfaces:**
- Produces（后续任务依赖）:
  - `export type CharacterState = 'working' | 'idle' | 'offline'`
  - `export const STATE_TINTS: Record<CharacterState, string>`（working `#1677ff` / idle `#faad14` / offline `#bfbfbf`）
  - `export function variantForId(id: number): CharacterVariant`（`CharacterVariant = { hairStyle: 'short'|'long'|'bun'|'crew'|'curly'; hairColor: string; skin: string; suit: string; glasses: boolean }`）
  - `export default function SpecialistCharacter({ id, state }: { id: number; state: CharacterState })` — 纯展示组件，渲染头部+躯干（无手臂/无桌面；手臂与键盘由 Workstation 负责）
  - `export function MiniCharacter({ id, state, size = 24 }: { id: number; state: CharacterState; size?: number })` — 头部特写简化版，供状态条使用

- [ ] **Step 1: 创建组件文件**

完整代码（`web/src/components/office/SpecialistCharacter.tsx`）：

```tsx
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
@keyframes ch-blink { 0%, 5%, 100% { transform: scaleY(1); } 7.5% { transform: scaleY(0.06); } }
.ch-blink { animation: ch-blink 4s infinite; transform-origin: 50% 50%; }
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
          <path d="M22 18 L22 18" />
        </g>
      )}
    </svg>
  );
}

export default memo(SpecialistCharacter);
```

- [ ] **Step 2: 构建验证**

Run: `cd D:/gongsi/medical system/web && npm run build`
Expected: `tsc -b && vite build` 全绿，无类型错误。

- [ ] **Step 3: 提交**

```bash
git add web/src/components/office/SpecialistCharacter.tsx
git commit -m "feat(web): 专员角色 SVG 组件（形象变体+眨眼/呼吸动画+迷你头像）"
```

---

### Task 2: 工位组件 `Workstation.tsx`

**Files:**
- Create: `web/src/components/office/Workstation.tsx`

**Interfaces:**
- Consumes: `SpecialistCharacter`（default export，`{ id, state }`）、`STATE_TINTS`（来自 Task 1）；`LiveStatusItem`（来自 `web/src/types`，字段：`id/name/lifecycle/state/phase/phase_text/question_snippet/today_conversations/last_active_at`）
- Produces: `export default function Workstation({ item, index, onEdit, onToggleStatus, onViewData }: { item: LiveStatusItem; index: number; onEdit: (item: LiveStatusItem) => void; onToggleStatus: (item: LiveStatusItem) => void; onViewData: (item: LiveStatusItem) => void })` — 渲染整个工位（含头顶气泡与名牌）；交互回调都带上 `item` 实参，由父组件做映射/拉取

- [ ] **Step 1: 创建工位组件**

完整代码（`web/src/components/office/Workstation.tsx`）：

```tsx
import { memo } from 'react';
import { Space, Tag } from 'antd';
import type { LiveStatusItem } from '../../types';
import SpecialistCharacter, { STATE_TINTS } from './SpecialistCharacter';

const CSS = `
@keyframes ws-screen-on { 0%, 100% { opacity: 1; } 50% { opacity: 0.82; } }
.ch-screen-on { animation: ws-screen-on 2.4s ease-in-out infinite; }
@keyframes ws-finger-1 { 0%, 100% { opacity: 0.25; } 20% { opacity: 1; } 60% { opacity: 0.25; } }
@keyframes ws-finger-2 { 0%, 100% { opacity: 0.25; } 45% { opacity: 1; } 80% { opacity: 0.25; } }
@keyframes ws-finger-3 { 0%, 100% { opacity: 0.25; } 30% { opacity: 1; } 70% { opacity: 0.25; } }
.ch-finger-1 { animation: ws-finger-1 1.1s infinite; }
.ch-finger-2 { animation: ws-finger-2 1.1s infinite; }
.ch-finger-3 { animation: ws-finger-3 1.1s infinite; }
@keyframes ws-steam { 0% { transform: translateY(0); opacity: 0; } 25% { opacity: 0.7; } 100% { transform: translateY(-7px); opacity: 0; } }
.ch-steam-1 { animation: ws-steam 2s ease-out infinite; }
.ch-steam-2 { animation: ws-steam 2s ease-out 1s infinite; }
.ws { position: relative; width: 170px; }
.ws-bubble { position: absolute; top: -34px; left: 50%; transform: translateX(-50%); z-index: 3;
  background: #fff; border: 1px solid #f0f0f0; border-radius: 8px; box-shadow: 0 2px 8px rgba(0,0,0,.08);
  padding: 4px 8px; font-size: 11px; color: #595959; white-space: nowrap; max-width: 200px; overflow: hidden; text-overflow: ellipsis; }
.ws-bubble::after { content: ''; position: absolute; top: 100%; left: 50%; margin-left: -4px;
  border: 4px solid transparent; border-top-color: #fff; }
.ws-nameplate { display: flex; align-items: center; justify-content: center; gap: 5px; margin-top: 6px; font-size: 12px; }
.ws-nameplate .dot { width: 8px; height: 8px; border-radius: 50%; }
.ws-actions { position: absolute; top: 6px; right: 6px; z-index: 4; background: rgba(255,255,255,.95);
  border: 1px solid #f0f0f0; border-radius: 6px; padding: 2px 6px; opacity: 0; transition: opacity .15s;
  box-shadow: 0 2px 8px rgba(0,0,0,.08); font-size: 12px; }
.ws:hover .ws-actions { opacity: 1; }
`;

/** 工位：显示器 + 角色 + 桌面（键盘/咖啡）+ 名牌 + 头顶气泡 + 悬停操作条 */
function Workstation({
  item, index, onEdit, onToggleStatus, onViewData,
}: {
  item: LiveStatusItem;
  index: number;
  onEdit: (item: LiveStatusItem) => void;
  onToggleStatus: (item: LiveStatusItem) => void;
  onViewData: (item: LiveStatusItem) => void;
}) {
  const tint = STATE_TINTS[item.state];
  const off = item.state === 'offline';
  const working = item.state === 'working';
  const idle = item.state === 'idle';
  const animDelay = `${index * 130}ms`;

  return (
    <div className="ws" style={{ animationDelay: animDelay }} onClick={() => onViewData(item)}>
      <style>{CSS}</style>
      {working && (
        <div className="ws-bubble" title={item.question_snippet ? `正在回答：${item.question_snippet}…` : undefined}>
          {item.phase_text ?? '正在工作'}{item.question_snippet ? ` · ${item.question_snippet}…` : ''}
        </div>
      )}
      {idle && <div className="ws-bubble">空闲中</div>}
      <svg viewBox="0 0 170 150" style={{ display: 'block', width: '100%' }}>
        {/* 显示器（工作中亮屏蓝光脉动，空闲息屏） */}
        <rect x="55" y="6" width="60" height="44" rx="3" fill={off ? '#e5e7eb' : '#1e293b'} />
        <rect x="60" y="11" width="50" height="34" rx="2" fill={working ? '#0ea5e9' : '#f8fafc'} className={working ? 'ch-screen-on' : undefined} />
        {working && (
          <g fill="#e0f2fe">
            <rect x="65" y="17" width="34" height="3" rx="1.5" />
            <rect x="65" y="24" width="26" height="3" rx="1.5" />
            <rect x="65" y="31" width="30" height="3" rx="1.5" />
          </g>
        )}
        <rect x="73" y="50" width="24" height="4" rx="2" fill="#9ca3af" />
        <rect x="61" y="54" width="48" height="6" rx="2" fill="#6b7280" />
        {/* 角色 */}
        <svg x="25" y="4" width="120" height="140" viewBox="0 0 120 140">
          <SpecialistCharacter id={item.id} state={item.state} />
        </svg>
        {/* 桌面（盖住角色下半身） */}
        <rect x="0" y="120" width="170" height="11" rx="2" fill={off ? '#b9b2a6' : '#8a5a33'} />
        <rect x="0" y="131" width="170" height="19" fill={off ? '#a39c90' : '#6b4423'} />
        {/* 工作中：键盘 + 打字的手 */}
        {working && (
          <g>
            <rect x="60" y="108" width="50" height="13" rx="2" fill="#333333" />
            <g fill="#555555">
              {[66, 75, 84, 93].map((x) => (
                <rect key={x} x={x} y="111" width="5" height="3" rx="1" />
              ))}
            </g>
            <circle cx="72" cy="106" r="4" fill="#ffd9b3" />
            <circle cx="98" cy="106" r="4" fill="#ffd9b3" />
            <circle cx="69" cy="104" r="2.2" fill="#c68a5c" className="ch-finger-1" />
            <circle cx="84" cy="103" r="2.2" fill="#c68a5c" className="ch-finger-2" />
            <circle cx="99" cy="104" r="2.2" fill="#c68a5c" className="ch-finger-3" />
          </g>
        )}
        {/* 空闲：桌面咖啡杯 + 蒸汽 */}
        {idle && (
          <g>
            <rect x="106" y="104" width="16" height="13" rx="2" fill="#ffffff" stroke="#d9d9d9" strokeWidth="1.2" />
            <path d="M122 107 q5 0 5 3.5 q0 3.5 -5 3.5" stroke="#d9d9d9" strokeWidth="1.2" fill="none" />
            <path d="M112 100 q-1.5 -3 0 -6" stroke="#d9d9d9" strokeWidth="1.5" fill="none" className="ch-steam-1" />
            <path d="M118 101 q1.5 -3 0 -6" stroke="#d9d9d9" strokeWidth="1.5" fill="none" className="ch-steam-2" />
          </g>
        )}
      </svg>
      {/* 名牌：名字 + 状态色点 + 今日次数 */}
      <div className="ws-nameplate">
        <span className="dot" style={{ background: tint }} />
        <span style={{ fontWeight: 500 }}>{item.name}</span>
        <span style={{ color: '#8c8c8c' }}>今日 {item.today_conversations}</span>
        {item.lifecycle !== 'active' && (
          <Tag color={item.lifecycle === 'disabled' ? 'default' : 'orange'} style={{ marginInlineEnd: 0, fontSize: 11, lineHeight: '16px' }}>
            {item.lifecycle === 'disabled' ? '停用' : '草稿'}
          </Tag>
        )}
      </div>
      {/* 悬停操作条 */}
      <div className="ws-actions" onClick={(e) => e.stopPropagation()}>
        <Space size={10}>
          <a onClick={() => onViewData(item)}>数据</a>
          <a onClick={() => onEdit(item)}>编辑</a>
          <a style={{ color: item.lifecycle === 'active' ? '#ff4d4f' : '#52c41a' }} onClick={() => onToggleStatus(item)}>
            {item.lifecycle === 'active' ? '停用' : '启用'}
          </a>
        </Space>
      </div>
    </div>
  );
}

export default memo(Workstation);
```

- [ ] **Step 2: 构建验证**

Run: `cd D:/gongsi/medical system/web && npm run build`
Expected: 全绿，无类型错误。

- [ ] **Step 3: 提交**

```bash
git add web/src/components/office/Workstation.tsx
git commit -m "feat(web): 专员工位组件（显示器/桌面/键盘手/咖啡杯/名牌/气泡/悬停操作）"
```

---

### Task 3: 场景组件 + 办公室页面集成

**Files:**
- Create: `web/src/components/office/OfficeScene.tsx`
- Modify: `web/src/pages/Specialist/SpecialistOffice.tsx`（把卡片网格替换为场景；轮询/汇总/事件逻辑保留）

**Interfaces:**
- Consumes: `Workstation`（Task 2）、`LiveStatusItem`/`LiveStatus`（`web/src/types`）
- Produces: `export default function OfficeScene({ items, onAdd, onEdit, onToggleStatus, onViewData }: { items: LiveStatusItem[]; onAdd: () => void; onEdit: (item: LiveStatusItem) => void; onToggleStatus: (item: LiveStatusItem) => void; onViewData: (item: LiveStatusItem) => void })` — 纯展示组件；`toSpecialist` 映射与 detail 拉取在父组件做

- [ ] **Step 1: 创建场景组件**

完整代码（`web/src/components/office/OfficeScene.tsx`）：

```tsx
import { useEffect, useState } from 'react';
import { Button, Empty } from 'antd';
import { PlusOutlined } from '@ant-design/icons';
import Workstation from './Workstation';
import type { LiveStatusItem } from '../../types';

const CSS = `
.office-scene { position: relative; background: linear-gradient(180deg, #eef4fb 0%, #f7f9fc 72%, #e8e4dc 72%, #e8e4dc 100%);
  border: 1px solid #eaeaea; border-radius: 12px; padding: 42px 24px 18px; min-height: 320px; overflow: hidden; }
.office-window { position: absolute; top: 18px; width: 90px; height: 62px; border-radius: 6px;
  background: linear-gradient(180deg, #cfe8ff 0%, #e8f4ff 100%); border: 3px solid #ffffff; box-shadow: 0 0 0 1px #dfe6ee; overflow: hidden; }
.office-window::before { content: ''; position: absolute; left: 0; right: 0; top: 28px; height: 3px; background: #dfe6ee; }
.office-window::after { content: ''; position: absolute; top: 0; bottom: 0; left: 42px; width: 3px; background: #dfe6ee; }
.office-cloud { position: absolute; background: #ffffff; border-radius: 12px; opacity: 0.85; }
.office-clock { position: absolute; top: 12px; right: 24px; width: 54px; height: 54px; border-radius: 50%;
  background: #fff; border: 2px solid #d9d9d9; box-shadow: 0 2px 6px rgba(0,0,0,.08); }
.office-plant { position: absolute; bottom: 18px; }
.office-row { display: flex; flex-wrap: wrap; justify-content: center; gap: 22px; position: relative; z-index: 2; padding-top: 10px; }
`;

/** 墙钟：按当前时间转指针 */
function WallClock() {
  const [now, setNow] = useState(() => new Date());
  useEffect(() => {
    const t = window.setInterval(() => setNow(new Date()), 30000);
    return () => window.clearInterval(t);
  }, []);
  const h = (now.getHours() % 12) * 30 + now.getMinutes() * 0.5;
  const m = now.getMinutes() * 6;
  return (
    <div className="office-clock">
      <svg viewBox="0 0 54 54" style={{ display: 'block' }}>
        {[0, 30, 60, 90].map((a) => (
          <line key={a} x1="27" y1="5" x2="27" y2="9" stroke="#8c8c8c" strokeWidth="2"
            transform={`rotate(${a} 27 27)`} />
        ))}
        <line x1="27" y1="27" x2="27" y2="16" stroke="#333" strokeWidth="2.6" strokeLinecap="round"
          transform={`rotate(${h} 27 27)`} />
        <line x1="27" y1="27" x2="27" y2="12" stroke="#1677ff" strokeWidth="1.6" strokeLinecap="round"
          transform={`rotate(${m} 27 27)`} />
        <circle cx="27" cy="27" r="2" fill="#333" />
      </svg>
    </div>
  );
}

/** 办公室场景：墙/窗/云/墙钟/绿植 + 工位排布（每排最多 5 个，超出换行） */
export default function OfficeScene({
  items, onAdd, onEdit, onToggleStatus, onViewData,
}: {
  items: LiveStatusItem[];
  onAdd: () => void;
  onEdit: (item: LiveStatusItem) => void;
  onToggleStatus: (item: LiveStatusItem) => void;
  onViewData: (item: LiveStatusItem) => void;
}) {
  return (
    <div className="office-scene">
      <style>{CSS}</style>
      {/* 装饰：两扇窗 + 云 + 墙钟 + 绿植 */}
      <div className="office-window" style={{ left: 24 }} />
      <div className="office-window" style={{ left: 132, top: 26 }} />
      <div className="office-cloud" style={{ left: 40, top: 10, width: 34, height: 12 }} />
      <div className="office-cloud" style={{ left: 205, top: 8, width: 26, height: 9 }} />
      <WallClock />
      <svg className="office-plant" viewBox="0 0 60 56" width="56" style={{ right: 24 }}>
        <path d="M30 20 Q20 4 8 8 Q16 14 30 20 Z" fill="#7cae6a" />
        <path d="M30 20 Q40 2 52 6 Q44 14 30 20 Z" fill="#6fa35c" />
        <path d="M30 22 Q30 6 30 2 Q32 8 32 14 Z" fill="#5c8f4a" />
        <path d="M30 20 Q28 40 30 56 Q32 40 30 20 Z" fill="#8a5a33" />
      </svg>
      {items.length === 0 ? (
        <div style={{ display: 'flex', justifyContent: 'center', alignItems: 'center', height: 300 }}>
          <Empty description="暂无数字专员">
            <Button type="primary" icon={<PlusOutlined />} onClick={onAdd}>新增专员</Button>
          </Empty>
        </div>
      ) : (
        <div className="office-row">
          {items.map((item, index) => (
            <Workstation
              key={item.id}
              item={item}
              index={index}
              onEdit={onEdit}
              onToggleStatus={onToggleStatus}
              onViewData={onViewData}
            />
          ))}
        </div>
      )}
    </div>
  );
}
```

- [ ] **Step 2: 改造 `SpecialistOffice.tsx`**

保持：轮询（`load`/`useEffect`/`autoPoll`）、`toSpecialist`、`summary` 计算、顶部工具条结构。替换渲染部分 —— 改动后文件如下（完整代码，`web/src/pages/Specialist/SpecialistOffice.tsx`）：

```tsx
import { useEffect, useRef, useState } from 'react';
import {
  Tag, Switch, Button, Space, App,
} from 'antd';
import { PlusOutlined, ReloadOutlined } from '@ant-design/icons';
import { specialistAPI } from '../../services/specialist';
import OfficeScene from '../../components/office/OfficeScene';
import type { LiveStatus, LiveStatusItem, Specialist } from '../../types';

const POLL_INTERVAL_MS = 3000;

/** live 条目 → Specialist：live 用 lifecycle、Specialist 用 status，映射补 status 供父组件 toggleStatus 判定 */
function toSpecialist(sp: LiveStatusItem): Specialist {
  return { ...sp, created_at: '', status: sp.lifecycle } as unknown as Specialist;
}

/** 数字员工办公室：3s 轮询 live-status，场景化展示每个专员在干什么 */
export default function SpecialistOffice({
  onAdd, onEdit, onToggleStatus, onViewData,
}: {
  onAdd: () => void;
  onEdit: (r: Specialist) => void;
  onToggleStatus: (r: Specialist) => void;
  onViewData: (r: Specialist) => void;
}) {
  const [live, setLive] = useState<LiveStatus | null>(null);
  const [autoPoll, setAutoPoll] = useState(true);
  const [loading, setLoading] = useState(false);
  const timerRef = useRef<number | null>(null);
  const { message } = App.useApp();

  const load = async () => {
    try {
      setLoading(true);
      const res = await specialistAPI.liveStatus();
      setLive(res.data.data);
    } catch {
      /* 轮询失败静默，保留上一次数据；卡片按 lifecycle 降级展示 */
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    load();
    if (autoPoll) {
      timerRef.current = window.setInterval(load, POLL_INTERVAL_MS);
    }
    return () => {
      if (timerRef.current !== null) window.clearInterval(timerRef.current);
    };
  }, [autoPoll]);

  const summary = live?.summary ?? { working: 0, idle: 0, offline: 0 };
  const items = live?.items ?? [];

  return (
    <div>
      <div style={{ display: 'flex', alignItems: 'center', gap: 16, marginBottom: 16, flexWrap: 'wrap' }}>
        <Space size={8}>
          <Tag color="blue" style={{ marginInlineEnd: 0 }}>工作中 {summary.working}</Tag>
          <Tag color="gold" style={{ marginInlineEnd: 0 }}>空闲 {summary.idle}</Tag>
          <Tag style={{ marginInlineEnd: 0 }}>离线 {summary.offline}</Tag>
        </Space>
        <span style={{ fontSize: 12, color: '#8c8c8c' }}>3s 自动刷新</span>
        <Switch size="small" checked={autoPoll} onChange={setAutoPoll} />
        <Button size="small" icon={<ReloadOutlined />} loading={loading} onClick={load}>刷新</Button>
        <Button type="primary" size="small" icon={<PlusOutlined />} onClick={onAdd}>新增专员</Button>
      </div>
      <OfficeScene
        items={items}
        onAdd={onAdd}
        onEdit={async (item) => {
          // live 数据无 persona/knowledge_scope 等字段，必须先拉全量记录再进编辑表单，
          // 否则表单会把空值 JSON 序列化提交，覆盖真实人设（既有 Critical 修复，必须保留）
          try {
            const res = await specialistAPI.detail(item.id);
            onEdit(res.data.data);
          } catch {
            message.error('获取专员详情失败，请稍后重试');
          }
        }}
        onToggleStatus={(item) => onToggleStatus(toSpecialist(item))}
        onViewData={(item) => onViewData(toSpecialist(item))}
      />
    </div>
  );
}
```

注意：`OfficeScene`/`Workstation` 的 action 回调契约是 `(item: LiveStatusItem) => void` —— 工位点击/操作条把当前 `item` 传给包装函数，由 SpecialistOffice 做 detail 拉取与 `toSpecialist` 映射（等价于旧 WorkstationCard 时代页面层闭包捕获 `item` 的做法）。

- [ ] **Step 3: 构建验证**

Run: `cd D:/gongsi/medical system/web && npm run build`
Expected: 全绿。注意移除文件顶部不再使用的 import（`Row/Col/Card/Empty/Spin`、`RobotOutlined/CoffeeOutlined/PoweroffOutlined`、`STATUS_MAP`、`LiveStatusItem` 等 —— 以 tsc 报错为准逐个清理）。

- [ ] **Step 4: 手工检查（dev server）**

Run: `cd D:/gongsi/medical system/web && npm run dev`（后台）；浏览器打开 http://localhost:3000 登录后进「数字专员」：
Expected:
- 场景渲染：墙/窗/云/墙钟（时间走动）/绿植可见；工位排成一排（≤5 个专员）
- 每个专员长相不同（发型/发色/肤色/眼镜差异），眨眼动画存在，躯干呼吸起伏
- 与专员对话进行中：该工位气泡显示动作文案+问题摘要，屏幕蓝光脉动，键盘手敲击动画；对话结束回到「空闲中」气泡 + 咖啡杯蒸汽
- 悬停工位出现操作条（数据/编辑/停用），点击工位弹出数据看板
- 顶部汇总 Tag 数字正确

- [ ] **Step 5: 提交**

```bash
git add web/src/components/office/OfficeScene.tsx web/src/pages/Specialist/SpecialistOffice.tsx
git commit -m "feat(web): 数字员工办公室场景化（正面房间+工位排布+墙钟/窗/绿植），替换卡片网格"
```

---

### Task 4: 仪表盘状态条迷你角色化

**Files:**
- Modify: `web/src/components/LiveStatusStrip.tsx`

**Interfaces:**
- Consumes: `MiniCharacter`（Task 1，`{ id, state, size }`）

- [ ] **Step 1: 替换机器人图标为迷你角色头像**

改动 `web/src/components/LiveStatusStrip.tsx`：
- 移除 `RobotOutlined` import；新增 `import { MiniCharacter } from './office/SpecialistCharacter';`
- 状态条内每个专员 chip 的渲染从 `<RobotOutlined style={{ color: STATE_COLOR[item.state] }} />` 换成 `<MiniCharacter id={item.id} state={item.state} />`

改动后 chip 渲染块（`web/src/components/LiveStatusStrip.tsx:52-69` 的 `shown.map` 内）为：

```tsx
<span
  onClick={() => navigate('/specialist/list')}
  style={{
    display: 'inline-flex', alignItems: 'center', gap: 5, cursor: 'pointer',
    padding: '2px 8px', borderRadius: 12, background: '#fff',
    border: `1px solid ${STATE_COLOR[item.state]}44`,
  }}
>
  <MiniCharacter id={item.id} state={item.state} />
  {item.name}
</span>
```

其余（5s 轮询、`MAX_STATIONS = 8`、`+N` 折叠、Tooltip、汇总文案、「查看全部」跳转）全部不动。

- [ ] **Step 2: 构建验证**

Run: `cd D:/gongsi/medical system/web && npm run build`
Expected: 全绿；若 `RobotOutlined` 不再被使用，tsc 会因未使用 import 报错 —— 删掉即可。

- [ ] **Step 3: 手工检查（dev server）**

Run: 浏览器打开 http://localhost:3000 仪表盘页：
Expected: 顶部状态条每个专员显示迷你角色头像（头部+肩部，颜色随状态），悬停 Tooltip 仍显示名字/动作/摘要；多于 8 人出现 `+N`；点击 chip 或「查看全部」跳转 `/specialist/list`。

- [ ] **Step 4: 提交**

```bash
git add web/src/components/LiveStatusStrip.tsx
git commit -m "feat(web): 仪表盘状态条迷你角色头像化"
```

---

### Task 5: 端到端验证 + 回归

**Files:** 无（验证任务）

- [ ] **Step 1: 构建 + 全量回归**

Run: `cd D:/gongsi/medical system/web && npm run build`
Expected: 全绿。

- [ ] **Step 2: 真实对话联动验证（dev server）**

条件：gateway + 8 服务已在跑（8000-8007），web dev 在 3000。操作：
1. 打开「数字专员」办公室视图，确认所有专员工位渲染、姿态正确（含 1 个停用/草稿专员 → 灰化离线）
2. 发起一次真实对话：观察该专员工位气泡三阶段流转（合规预检→检索生成→合规审核），屏幕蓝光 + 键盘敲击动画；结束后回「空闲中」+ 咖啡杯
3. 打开仪表盘：状态条迷你头像与办公室角色形象一致（同一专员同一发型/发色）
4. 表格视图切换、编辑（确认 persona 预填正常）、停用/启用、数据看板 —— 与改造前行为一致

- [ ] **Step 3: 提交检查**

Run: `git log --oneline -6`
Expected: 本功能 4 个提交齐全（Task 1-4）。

