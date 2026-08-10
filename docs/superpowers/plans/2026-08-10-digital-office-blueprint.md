# 3D 俯视蓝图办公室（v3）实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 将数字员工办公室从 v2 正面房间场景重写为 3D 俯视工位布局蓝图——深色地板 + 浅蓝发光网格/过道线、轻微透视（`perspective` + `rotateX(18°)`）、统一白色极简小人、工位状态灯带变色。

**Architecture:** 数据流/轮询/回调完全不变（`SpecialistOffice.tsx` 不动）。纯 CSS 3D：场景容器 `perspective: 900px`，地板平面 `rotateX(18deg)` + `preserve-3d` 产生俯视纵深，每个工位 `rotateX(-18deg)` billboard 反旋转保持内容直立可读；状态通过工位灯带（蓝脉动/琥珀常亮/灰熄灭）表达。零新依赖。

**Tech Stack:** React 18 + Vite + TS + antd；动画全部 CSS keyframes（仅 opacity/transform/box-shadow）。

**执行环境**：直接在 master 上工作（沿用 v2 已获用户同意的做法）。验证门 = `npm run build`（tsc -b && vite build，项目无 JS 测试框架）。

## Global Constraints

（自 spec 视觉规范，逐字绑定）

- 透视容器 `perspective: 900px`；地板旋转 `rotateX(18deg)`、`transform-style: preserve-3d`；工位反旋转 `rotateX(-18deg)`（billboard）
- 地板底色 `#101828` → `#1d2a3d` 渐变；网格/过道线色 `#58a6ff`（发光线条，过道线加粗 + glow）
- 工位每排 6 个，flex-wrap 自动换行，`gap` ~38px
- 卡座约 150×110px，深色半透明，浅蓝发光描边
- 状态灯带：working `#1677ff` 脉动 / idle `#faad14` 常亮 / offline `#bfbfbf` 熄灭（低透明度不脉动）
- 小人纯白 + 描边 `#666`，约 40px 高（viewBox 48×60），统一形象无变体
- 动画仅 opacity / transform / box-shadow（合成层属性）
- 零新依赖（前后端）、零后端改动
- 状态色（既有）：working `#1677ff` / idle `#faad14` / offline `#bfbfbf`
- 回调契约（既有）：`onEdit/onToggleStatus/onViewData: (item: LiveStatusItem) => void`；编辑必须先 `specialistAPI.detail(id)`（防 persona 覆盖，在页面层，组件不涉及）
- `LiveStatusStrip.tsx` 不改代码（MiniCharacter 白化由 T1 组件导出自动生效；状态色点保留）

---

### Task 1: 白色极简小人组件（重写 SpecialistCharacter.tsx）

**Files:**
- Modify: `web/src/components/office/SpecialistCharacter.tsx`（整体重写）

**Interfaces:**
- Consumes: 无（v2 的 `variantForId`/`CharacterVariant` 删除；若 grep 发现其他文件引用，报告给 controller）
- Produces: `CharacterState`、`STATE_TINTS`（值不变）、默认导出 `SpecialistCharacter({ id, state })`、`MiniCharacter({ id, state, size? })`——签名与 v2 完全一致，`Workstation`/`LiveStatusStrip` 无需改动

- [ ] **Step 1: 重写组件**

用以下代码整体替换 `web/src/components/office/SpecialistCharacter.tsx`：

```tsx
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
```

- [ ] **Step 2: 确认无残留引用**

```bash
cd "/d/gongsi/medical system"
grep -rn "variantForId\|CharacterVariant" web/src --include=*.tsx --include=*.ts
```

Expected: 无输出（删除的导出不再被引用）。若 `LiveStatusStrip.tsx` 或 `Workstation.tsx` 报引用错，说明 grep 命中——把命中报告给 controller。

- [ ] **Step 3: 构建门**

```bash
cd "/d/gongsi/medical system/web" && npm run build
```

Expected: PASS（tsc -b && vite build 全绿，仅既有 chunk 大小警告）。

- [ ] **Step 4: 提交**

```bash
cd "/d/gongsi/medical system" && git add web/src/components/office/SpecialistCharacter.tsx && git commit -m "feat(web): 白色极简小人组件（统一形象+眨眼/呼吸，MiniCharacter 白化）"
```

---

### Task 2: 工位卡座（重写 Workstation.tsx）

**Files:**
- Modify: `web/src/components/office/Workstation.tsx`（整体重写）

**Interfaces:**
- Consumes: T1 的 `SpecialistCharacter`（默认导出）、`STATE_TINTS`；`LiveStatusItem`
- Produces: 默认导出 `Workstation({ item, index, onEdit, onToggleStatus, onViewData })`——props 契约与 v2 完全一致（index 用于入场延迟），`OfficeScene` 无需改调用

- [ ] **Step 1: 重写组件**

用以下代码整体替换 `web/src/components/office/Workstation.tsx`：

```tsx
import { memo } from 'react';
import { Space, Tag } from 'antd';
import type { LiveStatusItem } from '../../types';
import SpecialistCharacter, { STATE_TINTS } from './SpecialistCharacter';

const CSS = `
@keyframes ws-enter { from { transform: rotateX(-18deg) translateY(10px); opacity: 0; }
  to { transform: rotateX(-18deg) translateY(0); opacity: 1; } }
.ws { position: relative; width: 150px; transform: rotateX(-18deg); animation: ws-enter .45s ease-out backwards; }
.ws-card { position: relative; background: rgba(13, 20, 34, 0.72); border: 1px solid rgba(88, 166, 255, 0.4);
  border-radius: 10px; padding: 12px 10px 8px; box-shadow: 0 0 12px rgba(88, 166, 255, 0.28); }
.ws-char { width: 46px; height: 58px; margin: 0 auto 2px; }
.ws-light { height: 4px; width: 72%; margin: 4px auto 8px; border-radius: 2px; }
@keyframes ws-light-pulse { 0%, 100% { opacity: 0.55; } 50% { opacity: 1; } }
.ws-light-working { animation: ws-light-pulse 2.4s ease-in-out infinite; }
.ws-bubble { position: absolute; top: -26px; left: 50%; transform: translateX(-50%); z-index: 3;
  background: #fff; border: 1px solid #f0f0f0; border-radius: 8px; box-shadow: 0 2px 8px rgba(0,0,0,.35);
  padding: 4px 8px; font-size: 11px; color: #595959; white-space: nowrap; max-width: 190px; overflow: hidden; text-overflow: ellipsis; }
.ws-bubble::after { content: ''; position: absolute; top: 100%; left: 50%; margin-left: -4px;
  border: 4px solid transparent; border-top-color: #fff; }
.ws-nameplate { display: flex; align-items: center; justify-content: center; gap: 5px; font-size: 12px; color: #e6edf7; }
.ws-nameplate .dot { width: 8px; height: 8px; border-radius: 50%; flex-shrink: 0; }
.ws-nameplate .count { color: #8fa3bf; }
.ws-actions { position: absolute; top: 6px; right: 6px; z-index: 4; background: rgba(255,255,255,.95);
  border: 1px solid #f0f0f0; border-radius: 6px; padding: 2px 6px; opacity: 0; transition: opacity .15s;
  box-shadow: 0 2px 8px rgba(0,0,0,.35); font-size: 12px; }
.ws:hover .ws-actions { opacity: 1; }
`;

/** 工位卡座：白色小人 + 状态灯带 + 名牌 + 头顶气泡 + 悬停操作条（billboard 反旋转保持直立） */
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
      <div className="ws-card">
        <div className="ws-char">
          <SpecialistCharacter id={item.id} state={item.state} />
        </div>
        {/* 状态灯带：工作蓝脉动 / 空闲琥珀常亮 / 离线灰熄灭 */}
        <div
          className={`ws-light${working ? ' ws-light-working' : ''}`}
          style={{
            background: tint,
            boxShadow: off ? 'none' : `0 0 10px ${tint}99, 0 0 18px ${tint}55`,
            opacity: off ? 0.28 : undefined,
          }}
        />
        <div className="ws-nameplate">
          <span className="dot" style={{ background: tint }} />
          <span style={{ fontWeight: 500 }}>{item.name}</span>
          <span className="count">今日 {item.today_conversations}</span>
          {item.lifecycle !== 'active' && (
            <Tag color={item.lifecycle === 'disabled' ? 'default' : 'orange'} style={{ marginInlineEnd: 0, fontSize: 11, lineHeight: '16px' }}>
              {item.lifecycle === 'disabled' ? '停用' : '草稿'}
            </Tag>
          )}
        </div>
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

- [ ] **Step 2: 构建门**

```bash
cd "/d/gongsi/medical system/web" && npm run build
```

Expected: PASS。

- [ ] **Step 3: 提交**

```bash
cd "/d/gongsi/medical system" && git add web/src/components/office/Workstation.tsx && git commit -m "feat(web): 工位卡座重写（白色小人+状态灯带+billboard 反旋转）"
```

---

### Task 3: 3D 俯视蓝图场景（重写 OfficeScene.tsx）

**Files:**
- Modify: `web/src/components/office/OfficeScene.tsx`（整体重写）

**Interfaces:**
- Consumes: T2 的 `Workstation`；`LiveStatusItem`
- Produces: 默认导出 `OfficeScene({ items, onAdd, onEdit, onToggleStatus, onViewData })`——props 契约与 v2 完全一致，`SpecialistOffice.tsx` 零改动

- [ ] **Step 1: 重写组件**

用以下代码整体替换 `web/src/components/office/OfficeScene.tsx`：

```tsx
import { Fragment } from 'react';
import { Button, Empty } from 'antd';
import { PlusOutlined } from '@ant-design/icons';
import Workstation from './Workstation';
import type { LiveStatusItem } from '../../types';

const PER_ROW = 6;

const CSS = `
.office-scene { position: relative; perspective: 900px; background: #0b1220; border-radius: 12px;
  padding: 20px; min-height: 360px; overflow: hidden; }
.office-floor { position: absolute; inset: 0; transform: rotateX(18deg); transform-style: preserve-3d;
  background:
    linear-gradient(90deg, rgba(88, 166, 255, 0.13) 1px, transparent 1px),
    linear-gradient(0deg, rgba(88, 166, 255, 0.13) 1px, transparent 1px),
    linear-gradient(180deg, #101828 0%, #1d2a3d 100%);
  background-size: 26px 26px, 26px 26px, 100% 100%;
  border: 1px solid rgba(88, 166, 255, 0.35); border-radius: 10px; }
.office-rows { position: relative; z-index: 2; display: flex; flex-direction: column; align-items: center;
  gap: 18px; transform-style: preserve-3d; padding: 46px 18px 26px; }
.office-row { display: flex; flex-wrap: wrap; justify-content: center; gap: 38px; transform-style: preserve-3d; }
.office-aisle { width: calc(100% - 24px); height: 10px; display: flex; align-items: center; justify-content: center; }
.office-aisle::before { content: ''; width: 100%; height: 1px; background: rgba(88, 166, 255, 0.55);
  box-shadow: 0 0 8px rgba(88, 166, 255, 0.6); }
.office-empty { position: relative; z-index: 2; display: flex; justify-content: center; align-items: center; height: 320px; }
.office-empty .ant-empty-description { color: #8fa3bf; }
`;

/** 3D 俯视蓝图办公室：perspective + 地板 rotateX(18°)，工位 billboard 反旋转直立；每排 6 个，排间浅蓝发光过道线 */
export default function OfficeScene({
  items, onAdd, onEdit, onToggleStatus, onViewData,
}: {
  items: LiveStatusItem[];
  onAdd: () => void;
  onEdit: (item: LiveStatusItem) => void;
  onToggleStatus: (item: LiveStatusItem) => void;
  onViewData: (item: LiveStatusItem) => void;
}) {
  const rows: LiveStatusItem[][] = [];
  for (let i = 0; i < items.length; i += PER_ROW) rows.push(items.slice(i, i + PER_ROW));

  return (
    <div className="office-scene">
      <style>{CSS}</style>
      {items.length === 0 ? (
        <div className="office-empty">
          <Empty description="暂无数字专员">
            <Button type="primary" icon={<PlusOutlined />} onClick={onAdd}>新增专员</Button>
          </Empty>
        </div>
      ) : (
        <div className="office-floor">
          <div className="office-rows">
            {rows.map((row, ri) => (
              <Fragment key={ri}>
                {ri > 0 && <div className="office-aisle" />}
                <div className="office-row">
                  {row.map((item, index) => (
                    <Workstation
                      key={item.id}
                      item={item}
                      index={index + ri * PER_ROW}
                      onEdit={onEdit}
                      onToggleStatus={onToggleStatus}
                      onViewData={onViewData}
                    />
                  ))}
                </div>
              </Fragment>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}
```

- [ ] **Step 2: 构建门**

```bash
cd "/d/gongsi/medical system/web" && npm run build
```

Expected: PASS。

- [ ] **Step 3: 提交**

```bash
cd "/d/gongsi/medical system" && git add web/src/components/office/OfficeScene.tsx && git commit -m "feat(web): 办公室 3D 俯视蓝图场景（perspective+发光网格+过道线，每排 6 个）"
```

---

### Task 4: E2E 验证（验证任务）

**Files:**
- 新建：`t9-blueprint-screenshots/`（截图输出目录，不提交）
- 参考：`web/src/pages/Specialist/SpecialistOffice.tsx`、`web/src/components/LiveStatusStrip.tsx`（只读验证）

**Interfaces:** 无产出。验证 T1-T3 集成效果。

前置：8 个服务 + web dev 已运行（v2 会话遗留环境；若未运行，按 CLAUDE.md native 直跑路径启动，admin/MedAgent@2026 登录）。

- [ ] **Step 1: 构建门**

```bash
cd "/d/gongsi/medical system/web" && npm run build
```

Expected: PASS。

- [ ] **Step 2: 环境自检**

```bash
curl -s http://localhost:8000/api/v1/health
```

Expected: 健康返回。再 `curl -s http://localhost:3000 | head -c 200` 确认 web dev 在跑（[::1]:3000）。

- [ ] **Step 3: 登录拿 token 并确认专员数量**

```bash
curl -s -X POST http://localhost:8000/api/v1/auth/login -H "Content-Type: application/json" -d '{"phone":"13812345678","password":"MedAgent@2026"}' | head -c 400
```

用返回的 token 请求 `GET /api/v1/specialists/live-status`（`-H "Authorization: Bearer <token>"`）。若活跃+草稿专员总数 < 7，用 `POST /api/v1/specialists`（`{"name":"演示专员N","product_id":1}`，draft 默认）补到 ≥7，触发第二排 + 展示 offline 灯带（draft = offline 态）。记录专员 id/name 清单供 Step 5 用。

- [ ] **Step 4: Playwright 截图脚本**

写 `t9-blueprint-screenshots/e2e_blueprint.py`（Playwright Python，已装 1.61.0，无新依赖）：登录 → 进专员办公室页 → 截：
1. `scene.png` — 全景（俯视透视、发光网格、过道线、白色小人、灯带）
2. `row2.png` — 第二排 + 过道分隔线细节
3. `idle-light.png` — idle 琥珀常亮灯带特写（若无 idle 专员，用空闲聊天中专员或跳过并记录）
4. 悬停 `actions.png` — 操作条浮出（hover 一个工位）
5. 名牌 `nameplate.png` — 名牌（名/色点/今日 N）
6. 仪表盘 `strip.png` — 状态条白色迷你头像 + 色点

运行：`cd "/d/gongsi/medical system" && python t9-blueprint-screenshots/e2e_blueprint.py`。

- [ ] **Step 5: 状态流转验证**

a) **offline 灯带**：在页面点某 active 专员工位悬停条「停用」→ 立即截图 `offline.png`（灰熄灭灯带 + 小人灰化 + 名牌 Tag 停用）→ 再点「启用」恢复。
b) **working 灯带 + 气泡**：对 1 个 active 专员发真实对话（curl POST `/api/v1/specialists/{id}/chat`，body 放 UTF-8 文件避免中文损坏，如 `{"question":"肺癌用药注意事项"}` 写入 `t9-blueprint-screenshots/q.json`，`curl -H "Content-Type: application/json" -d @q.json`），在 generating 阶段连拍 `working.png`（蓝灯脉动 + 头顶气泡 phase_text）；结束后回 idle。

- [ ] **Step 6: 回归**

- 编辑：hover 工位 → 编辑 → 表单应预填全量（persona/knowledge_scope 非空——detail() 先拉全量防覆盖）→ 取消
- 数据抽屉：点击工位 → 数据看板 Drawer 打开
- 表格切换：Segmented 切回表格视图 → 切回办公室视图
- 状态条：迷你白色头像 + 状态色点 + 「查看全部」跳转正常

全部通过 → 浏览器验证透视成立（地板有纵深、工位/名牌/气泡直立可读、第二排布局正常、无元素重叠遮挡）。

- [ ] **Step 7: 结果记录**

在 `.superpowers/sdd/2026-08-10-digital-office-blueprint/progress.md`（由 controller 建立）追加 `Task 4: complete (E2E 全过: ...)` 一行，或按 controller 指示回报。如有任何失败，按 report 契约返回 BLOCKED/NEEDS_CONTEXT 并附截图路径。
