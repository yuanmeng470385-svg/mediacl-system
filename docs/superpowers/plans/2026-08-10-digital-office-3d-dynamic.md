# 3D 动态数字员工办公室（v4，Three.js）实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 用 Three.js 实现真 3D 动态办公室——俯视蓝图场景、每工位桌+电脑、程序化白色小人（空闲过道巡逻 / 工作走向工位坐下 / offline 灰化）、头顶名牌、raycast 交互，外加左侧团队出勤面板，双向联动。

**Architecture:** 数据流不变（3s 轮询 live-status → 页面 → 组件）。`web/src/components/office3d/` 新目录按模块拆文件：`layout.ts`（布局常量）/ `buildScene.ts`（地板/过道/灯光）/ `buildDesk.ts`（桌+电脑+凳子）/ `buildCharacter.ts`（程序化人形+姿态）/ `simulation.ts`（状态机+巡逻+走位）/ `labels.ts`（CSS2D 名牌+气泡+操作卡）/ `OfficeScene3D.tsx`（组件装配：渲染循环/raycast/选中/降级）/ `AttendancePanel.tsx`（出勤面板）。`SpecialistOffice.tsx` 整合面板+场景；删除 v3 的 `office/OfficeScene.tsx`、`office/Workstation.tsx`（保留 `office/SpecialistCharacter.tsx` 供状态条 MiniCharacter 复用）。

**Tech Stack:** three（npm，仅此一个新依赖）+ @types/three；CSS2DRenderer 用 `three/addons` 内置路径；rAF 模拟循环；antd 面板。

**执行环境**：直接 master（用户已同意）；验证门 = `npm run build`（tsc -b && vite build）。服务/登录不变（admin / MedAgent@2026；登录接口 username 或 phone 均可）。

## Global Constraints

（自 v4 规格，逐字绑定）

- **依赖**：仅 `three` + `@types/three`（web/ 下 npm 安装）。**禁止** @react-three/fiber 等任何附加 3D 依赖；CSS2DRenderer 必须用 three 内置 `three/addons/renderers/CSS2DRenderer.js`
- 地板底色 `#101828` → `#1d2a3d`；网格/过道线 `#58a6ff`
- 工位布局：每排 6 桌（PER_ROW=6），行间距 2.2 单位；过道巡逻只走排间过道带（z = 行中心 + 1.1），不进入办公区域
- 状态色（既有）：working `#1677ff` / idle `#faad14` / offline `#bfbfbf`
- 小人：白色为主 + 深灰 `#666` 四肢；offline 灰化半透明（透明度 ~0.45）静止
- 屏幕状态语义：working 亮蓝光脉动（emissiveIntensity 0.5↔1）/ idle 屏幕暗 / offline 整桌灰暗
- 姿态过渡 ~0.4s 插值（站立↔坐姿）；巡逻速度 0.8 单位/s，走向工位 1.4 单位/s；转向平滑插值
- 名牌（CSS2D）：名字 + 状态色点 + 状态文字 + 今日 N；working 附加气泡「正在回答：{snippet}…」；offline 显示「离线」
- 交互：点击人物/工位（raycast）→ `onSelect(id)` + `onViewData(item)`；点空白 → `onSelect(null)`；选中 → 名牌下浮出操作卡（数据/编辑/停用·启用，`stopPropagation` 语义）
- 回调契约（既有）：`onEdit/onToggleStatus/onViewData: (item: LiveStatusItem) => void`；编辑必须在页面层先 `specialistAPI.detail(id)`（防 persona 覆盖，组件只透传）
- 出勤面板：宽 280px；出勤率环形（antd Progress dashboard）+ 状态分布 + 今日对话（总和+人均）+ 明细列表（MiniCharacter + 名字 + 状态文字 + 今日 N + 最近活跃相对时间）；selectedId 双向联动（页面层持有，面板/场景共用）
- `LiveStatusStrip.tsx` 不改代码；`SpecialistOffice.tsx` 的轮询/toSpecialist/编辑 detail 包装/工具条逻辑保留
- 零后端改动；WebGL 不可用 → antd Alert 降级，表格视图/面板仍可用
- 性能：低多边形，N≤24 小人 60fps；rAF 卸载时 cancel + renderer/scene dispose

---

### Task 1: 布局常量 + 3D 场景骨架（layout.ts + buildScene.ts + 装依赖）

**Files:**
- Create: `web/src/components/office3d/layout.ts`
- Create: `web/src/components/office3d/buildScene.ts`
- Modify: `web/package.json`（npm i 自动）

**Interfaces:**
- Produces: `layout.ts` —— 常量 `PER_ROW/DESK_W/DESK_D/DESK_H/COL_X/ROW_Z/AISLE_PATROL_SPEED/DESK_APPROACH_SPEED/ROWS_MAX` + 函数 `deskX(col)/rowZ(ri)/aisleZ(ri)`
- Produces: `buildScene.ts` —— `buildScene(): THREE.Group`（地板/过道发光条/灯光）
- 尚未被引用（组件在 Task 6 装配），本任务只保证编译通过

- [ ] **Step 1: 安装依赖**

```bash
cd "/d/gongsi/medical system/web" && npm i three @types/three
```

Expected: package.json 增加 `three` 与 `@types/three`（devDependencies）。

- [ ] **Step 2: 创建 layout.ts**

```ts
/** 3D 办公室布局常量（世界单位）。坐标系：桌面 y=0.74，行沿 x，行距沿 z，所有桌朝 +z。 */
export const PER_ROW = 6;
export const DESK_W = 1.6;
export const DESK_D = 0.9;
export const DESK_H = 0.74;
export const COL_X = 2.2;        // 桌列间距
export const ROW_Z = 2.2;        // 行间距
export const ROWS_MAX = 4;       // 最多 4 排（24 专员）
export const AISLE_PATROL_SPEED = 0.8;
export const DESK_APPROACH_SPEED = 1.4;
export const SIT_Z_OFFSET = 0.82; // 坐姿位置 = 桌中心 z + 此偏移（桌 +z 侧）

/** 第 col 列（0..5）的 x */
export function deskX(col: number): number {
  return (col - (PER_ROW - 1) / 2) * COL_X;
}
/** 第 ri 排的 z（排居中） */
export function rowZ(ri: number): number {
  return (ri - (ROWS_MAX - 1) / 2) * ROW_Z;
}
/** 第 ri 排 +z 侧过道巡逻线的 z */
export function aisleZ(ri: number): number {
  return rowZ(ri) + ROW_Z / 2;
}
/** 专员序号 → 工位行列（按 items 顺序稳定分配） */
export function slotOf(index: number): { ri: number; col: number } {
  return { ri: Math.floor(index / PER_ROW), col: index % PER_ROW };
}
/** 坐姿目标点（桌 +z 侧凳子前） */
export function sitPosOf(index: number): { x: number; z: number } {
  const s = slotOf(index);
  return { x: deskX(s.col), z: rowZ(s.ri) + SIT_Z_OFFSET };
}
/** 排内过道巡逻起点（该排过道线上、靠桌列 x） */
export function aislePosOf(index: number): { x: number; z: number } {
  const s = slotOf(index);
  return { x: deskX(s.col), z: aisleZ(s.ri) };
}
```

- [ ] **Step 3: 创建 buildScene.ts**

```ts
import * as THREE from 'three';
import { ROWS_MAX, ROW_Z } from './layout';

/** 蓝图网格地板 + 过道发光条 + 灯光（静态场景） */
export function buildScene(): THREE.Group {
  const g = new THREE.Group();

  // 地板：程序生成蓝图网格纹理（#101828→#1d2a3d 渐变 + #58a6ff 网格线）
  const cv = document.createElement('canvas');
  cv.width = 512;
  cv.height = 512;
  const ctx = cv.getContext('2d')!;
  const grad = ctx.createLinearGradient(0, 0, 0, 512);
  grad.addColorStop(0, '#101828');
  grad.addColorStop(1, '#1d2a3d');
  ctx.fillStyle = grad;
  ctx.fillRect(0, 0, 512, 512);
  ctx.strokeStyle = 'rgba(88, 166, 255, 0.22)';
  ctx.lineWidth = 2;
  const step = 42;
  for (let x = 0; x <= 512; x += step) {
    ctx.beginPath();
    ctx.moveTo(x, 0);
    ctx.lineTo(x, 512);
    ctx.stroke();
  }
  for (let y = 0; y <= 512; y += step) {
    ctx.beginPath();
    ctx.moveTo(0, y);
    ctx.lineTo(512, y);
    ctx.stroke();
  }
  const tex = new THREE.CanvasTexture(cv);
  tex.colorSpace = THREE.SRGBColorSpace;
  const floor = new THREE.Mesh(
    new THREE.PlaneGeometry(26, 26),
    new THREE.MeshStandardMaterial({ map: tex, roughness: 0.9 }),
  );
  floor.rotation.x = -Math.PI / 2;
  g.add(floor);

  // 过道发光条（y=0.012 悬浮防 z-fight；排间 + 两端，共 ROWS_MAX+1 条）
  const aisleMat = new THREE.MeshBasicMaterial({ color: 0x58a6ff, transparent: true, opacity: 0.5 });
  const aisleGeo = new THREE.PlaneGeometry(22, 0.05);
  const zs = Array.from({ length: ROWS_MAX + 1 }, (_, i) => (i - ROWS_MAX / 2) * ROW_Z);
  for (const z of zs) {
    const line = new THREE.Mesh(aisleGeo, aisleMat);
    line.position.set(0, 0.012, z);
    line.rotation.x = -Math.PI / 2;
    g.add(line);
  }

  // 灯光：半球 + 主方向光
  const hemi = new THREE.HemisphereLight(0xdfeaff, 0x101828, 0.85);
  g.add(hemi);
  const dir = new THREE.DirectionalLight(0xffffff, 0.9);
  dir.position.set(6, 12, 8);
  g.add(dir);

  return g;
}
```

- [ ] **Step 4: 构建门**

```bash
cd "/d/gongsi/medical system/web" && npm run build
```

Expected: PASS（tsc -b && vite build 全绿；模块未被引用不影响编译）。

- [ ] **Step 5: 提交**

```bash
cd "/d/gongsi/medical system" && git add web/package.json web/package-lock.json web/src/components/office3d/layout.ts web/src/components/office3d/buildScene.ts && git commit -m "feat(web): 3D 办公室布局常量与场景骨架（地板网格+过道发光条+灯光，引 three 依赖）"
```

---

### Task 2: 工位（桌+电脑+凳子，buildDesk.ts）

**Files:**
- Create: `web/src/components/office3d/buildDesk.ts`

**Interfaces:**
- Consumes: 无（独立模块）
- Produces: `DeskState`（'working'|'idle'|'offline'）、`Desk` 接口（`group/screen/screenMat/state` + `setState(s)` + `setEmissivePulse(v)`）、`buildDesk(): Desk`、`buildDesks(count): Desk[]`（按行排布加入 scene 组）

- [ ] **Step 1: 创建 buildDesk.ts**

```ts
import * as THREE from 'three';
import { DESK_W, DESK_D, DESK_H, PER_ROW, deskX, rowZ, slotOf } from './layout';

export type DeskState = 'working' | 'idle' | 'offline';

export interface Desk {
  group: THREE.Group;
  screenMat: THREE.MeshStandardMaterial;
  /** readonly getter，与 setState 同步（实现须用 getter，否则公共字段恒为初始值） */
  readonly state: DeskState;
  setState(s: DeskState): void;
  /** working 时每帧调用：0..1 脉动强度 */
  setEmissivePulse(v: number): void;
}

/** 单张工位：桌面 + 桌腿 + 桌沿发光条 + 电脑（底座/支架/屏幕/外框）+ 凳子 */
export function buildDesk(): Desk {
  const group = new THREE.Group();
  const wood = new THREE.MeshStandardMaterial({ color: 0x2b3a52, roughness: 0.8 });
  const dark = new THREE.MeshStandardMaterial({ color: 0x1a2536, roughness: 0.9 });
  const edgeMat = new THREE.MeshBasicMaterial({ color: 0x58a6ff, transparent: true, opacity: 0.5 });

  // 桌面 + 桌腿
  const top = new THREE.Mesh(new THREE.BoxGeometry(DESK_W, 0.08, DESK_D), wood);
  top.position.y = DESK_H;
  group.add(top);
  for (const sx of [-0.7, 0.7]) {
    for (const sz of [-0.35, 0.35]) {
      const leg = new THREE.Mesh(new THREE.BoxGeometry(0.08, DESK_H - 0.04, 0.08), dark);
      leg.position.set(sx, (DESK_H - 0.04) / 2, sz);
      group.add(leg);
    }
  }
  // 桌沿发光条（前缘，浅蓝）
  const edge = new THREE.Mesh(new THREE.BoxGeometry(DESK_W + 0.02, 0.02, 0.02), edgeMat);
  edge.position.set(0, DESK_H + 0.05, DESK_D / 2);
  group.add(edge);

  // 电脑：底座 + 支架 + 屏幕 + 外框（屏幕朝 +z）
  const base = new THREE.Mesh(new THREE.BoxGeometry(0.5, 0.04, 0.3), dark);
  base.position.set(0, DESK_H + 0.04, 0.08);
  group.add(base);
  const stand = new THREE.Mesh(new THREE.BoxGeometry(0.06, 0.14, 0.06), dark);
  stand.position.set(0, DESK_H + 0.13, 0.08);
  group.add(stand);
  const screenMat = new THREE.MeshStandardMaterial({
    color: 0x0e1c2e, roughness: 0.35, emissive: 0x1677ff, emissiveIntensity: 0,
  });
  const screen = new THREE.Mesh(new THREE.BoxGeometry(1.0, 0.58, 0.06), screenMat);
  screen.position.set(0, DESK_H + 0.34, 0.1);
  group.add(screen);
  const bezel = new THREE.Mesh(new THREE.BoxGeometry(1.06, 0.64, 0.02), dark);
  bezel.position.set(0, DESK_H + 0.34, 0.135);
  group.add(bezel);

  // 凳子（坐姿支撑）
  const stool = new THREE.Mesh(new THREE.BoxGeometry(0.36, 0.4, 0.36), dark);
  stool.position.set(0, 0.2, DESK_D / 2 + 0.33);
  group.add(stool);

  let state: DeskState = 'idle';
  const desk: Desk = {
    group, screenMat,
    get state() { return state; },
    setState(s) {
      state = s;
      if (s === 'working') {
        screenMat.emissive.set(0x1677ff);
        screenMat.emissiveIntensity = 0.7;
      } else if (s === 'idle') {
        screenMat.emissive.set(0x0a1a2e);
        screenMat.emissiveIntensity = 0.08;
      } else {
        screenMat.emissive.set(0x1a1a1a);
        screenMat.emissiveIntensity = 0;
      }
      const dim = s === 'offline';
      group.traverse((o) => {
        // Material 基类（含 edgeMat 的 MeshBasicMaterial），保证与 edgeMat 比较可编译
        const m = (o as THREE.Mesh).material as THREE.Material | undefined;
        // edgeMat 保持构造态（transparent+opacity 0.5），offline 只暗化主体材质且可逆
        if (m && m !== screenMat && m !== edgeMat) {
          m.transparent = dim;
          m.opacity = dim ? 0.5 : 1;
        }
      });
    },
    setEmissivePulse(v) {
      if (state === 'working') screenMat.emissiveIntensity = 0.5 + 0.5 * v;
    },
  };
  desk.setState('idle'); // 构造时归一到 idle 材质态（emissive 0x0a1a2e/0.08）
  return desk;
}

/** 按专员数建工位组（每排 6，多行居中），返回 Desk[]（按 items 序号索引） */
export function buildDesks(count: number): Desk[] {
  const desks: Desk[] = [];
  for (let i = 0; i < count; i += 1) {
    const desk = buildDesk();
    const s = slotOf(i);
    desk.group.position.set(deskX(s.col), 0, rowZ(s.ri));
    desk.group.userData.slot = i;
    desk.group.traverse((o) => {
      o.userData.slot = i;
      o.userData.kind = 'desk';
    });
    desks.push(desk);
  }
  return desks;
}
```

- [ ] **Step 2: 构建门**

```bash
cd "/d/gongsi/medical system/web" && npm run build
```

Expected: PASS。

- [ ] **Step 3: 提交**

```bash
cd "/d/gongsi/medical system" && git add web/src/components/office3d/buildDesk.ts && git commit -m "feat(web): 3D 工位构建器（桌+电脑+凳子+发光描边，屏幕状态材质）"
```

---

### Task 3: 程序化人形（buildCharacter.ts）

**Files:**
- Create: `web/src/components/office3d/buildCharacter.ts`

**Interfaces:**
- Produces: `CharacterRig`（`group/legL/legR/armL/armR/torso/head/mats` + `setPose(pose, phase, typing)` + `setDim(a)`）、`buildCharacter(): CharacterRig`。`pose` 0=站立/走，1=坐；`phase` 走路/打字相位；`typing` 坐姿打字标志；`setDim(a)` a=0..1 灰化（offline）

- [ ] **Step 1: 创建 buildCharacter.ts**

```ts
import * as THREE from 'three';

export interface CharacterRig {
  group: THREE.Group;
  legL: THREE.Object3D;
  legR: THREE.Object3D;
  armL: THREE.Object3D;
  armR: THREE.Object3D;
  torso: THREE.Object3D;
  head: THREE.Object3D;
  mats: THREE.MeshStandardMaterial[];
  /** pose 0=站立/走路, 1=坐；phase=走动/打字相位；typing=坐姿打字 */
  setPose(pose: number, phase: number, typing: boolean): void;
  /** a=0..1 灰化（offline） */
  setDim(a: number): void;
}

/** 程序化白色小人（低多边形，无外部模型）：腿/躯干/臂/头 + 姿态插值 */
export function buildCharacter(): CharacterRig {
  const group = new THREE.Group();
  const white = new THREE.MeshStandardMaterial({ color: 0xffffff, roughness: 0.6 });
  const gray = new THREE.MeshStandardMaterial({ color: 0x666666, roughness: 0.7 });
  const shoe = new THREE.MeshStandardMaterial({ color: 0x3f3f46, roughness: 0.8 });

  // 腿（髋 pivot 0.42，向下）
  const legL = new THREE.Group();
  legL.position.y = 0.42;
  const thighL = new THREE.Mesh(new THREE.BoxGeometry(0.12, 0.34, 0.12), gray);
  thighL.position.y = -0.17;
  legL.add(thighL);
  const footL = new THREE.Mesh(new THREE.BoxGeometry(0.13, 0.07, 0.2), shoe);
  footL.position.set(0, -0.37, 0.04);
  legL.add(footL);
  const legR = new THREE.Group();
  legR.position.y = 0.42;
  const thighR = new THREE.Mesh(new THREE.BoxGeometry(0.12, 0.34, 0.12), gray);
  thighR.position.y = -0.17;
  legR.add(thighR);
  const footR = new THREE.Mesh(new THREE.BoxGeometry(0.13, 0.07, 0.2), shoe);
  footR.position.set(0, -0.37, 0.04);
  legR.add(footR);

  // 躯干
  const torso = new THREE.Group();
  torso.position.y = 0.68;
  const chest = new THREE.Mesh(new THREE.BoxGeometry(0.36, 0.5, 0.2), white);
  torso.add(chest);

  // 手臂（肩 pivot 0.84）
  const armL = new THREE.Group();
  armL.position.set(-0.21, 0.84, 0);
  const upL = new THREE.Mesh(new THREE.BoxGeometry(0.09, 0.4, 0.09), gray);
  upL.position.y = -0.2;
  armL.add(upL);
  const armR = new THREE.Group();
  armR.position.set(0.21, 0.84, 0);
  const upR = new THREE.Mesh(new THREE.BoxGeometry(0.09, 0.4, 0.09), gray);
  upR.position.y = -0.2;
  armR.add(upR);

  // 头
  const head = new THREE.Mesh(new THREE.SphereGeometry(0.19, 14, 12), white);
  head.position.y = 1.08;
  head.scale.y = 0.92;

  group.add(legL, legR, torso, armL, armR, head);
  const mats = [white, gray, shoe];

  const dimColor = new THREE.Color(0xb0b0b0);
  const baseColors = mats.map((m) => m.color.clone());

  const rig: CharacterRig = {
    group, legL, legR, armL, armR, torso, head, mats,
    setPose(pose, phase, typing) {
      const p = THREE.MathUtils.clamp(pose, 0, 1);
      const swing = Math.sin(phase);
      const typingOffset = typing ? Math.sin(phase * 4) * 0.04 : 0;
      // 坐姿正旋转：小人面朝 -Z 坐向桌子（heading π），手/腿向 -Z 前收才落到桌面/桌下
      const seatedArm = 1.35 + typingOffset;
      legL.rotation.x = (1 - p) * (swing * 0.65) + p * 1.2;
      legR.rotation.x = (1 - p) * (-swing * 0.65) + p * 1.2;
      armL.rotation.x = (1 - p) * (-swing * 0.5) + p * seatedArm;
      armR.rotation.x = (1 - p) * (swing * 0.5) + p * (seatedArm + 0.05);
      torso.rotation.x = p * 0.12 + (1 - p) * Math.sin(phase * 2) * 0.03; // 走路躯干轻微起伏
      head.rotation.x = p * 0.04;
      // 坐姿不再抬升 group：髋 pivot 0.42 ≈ 凳面 0.4 贴合
    },
    setDim(a) {
      // 按各材质初始色灰化（a=0 恢复初始色，四肢 #666 / 鞋 #3f3f46 不被刷白）
      for (let i = 0; i < mats.length; i += 1) {
        const c = baseColors[i].clone().lerp(dimColor, a);
        const m = mats[i];
        m.color.copy(c);
        m.transparent = a > 0;
        m.opacity = 1 - 0.55 * a;
      }
    },
  };
  return rig;
}
```

- [ ] **Step 2: 构建门**

```bash
cd "/d/gongsi/medical system/web" && npm run build
```

Expected: PASS。

- [ ] **Step 3: 提交**

```bash
cd "/d/gongsi/medical system" && git add web/src/components/office3d/buildCharacter.ts && git commit -m "feat(web): 程序化白色人形（走/坐姿态插值+打字+灰化）"
```

---

### Task 4: 模拟状态机（simulation.ts）

**Files:**
- Create: `web/src/components/office3d/simulation.ts`

**Interfaces:**
- Consumes: T1 `layout`、T2 `buildDesk/Desk`、T3 `buildCharacter/CharacterRig`；`LiveStatusItem`
- Produces: `Agent`（含 `item` 快照、`rig`、`desk`、`pos/heading/pose/poseTarget/target/aisleZ/dim/dimTarget/moving/walkPhase/typing`）、`Simulation` 类（`agents: Map<number, Agent>`、`scene: THREE.Group`、`update(dt, time)`、`upsert(item, index, desks)`、`remove(id)`、`dispose()`）

- [ ] **Step 1: 创建 simulation.ts**

```ts
import * as THREE from 'three';
import { buildCharacter, CharacterRig } from './buildCharacter';
import type { Desk } from './buildDesk';
import {
  AISLE_PATROL_SPEED, DESK_APPROACH_SPEED, aislePosOf, sitPosOf,
} from './layout';
import type { LiveStatusItem } from '../../types';

export interface Agent {
  id: number;
  item: LiveStatusItem;
  rig: CharacterRig;
  desk: Desk;
  index: number;
  pos: THREE.Vector3;
  heading: number;
  pose: number;        // 0 站立/走 → 1 坐
  poseTarget: number;
  target: THREE.Vector3 | null;
  aisleZ: number;
  dim: number;         // 0 正常 → 1 offline 灰化
  dimTarget: number;
  moving: boolean;
  typing: boolean;
  walkPhase: number;
}

const PATROL_X_RANGE = 5.6; // 巡逻 x 范围（桌列范围 ± 余量）

/** 小人模拟：数据由 upsert 驱动，update 每帧推进运动/姿态 */
export class Simulation {
  agents = new Map<number, Agent>();

  constructor(public scene: THREE.Group) {}

  upsert(item: LiveStatusItem, index: number, desks: Desk[]) {
    let a = this.agents.get(item.id);
    if (!a) {
      const rig = buildCharacter();
      const desk = desks[index % desks.length];
      const start = aislePosOf(index);
      a = {
        id: item.id, item, rig, desk, index,
        pos: new THREE.Vector3(start.x, 0, start.z),
        heading: 0, pose: 0, poseTarget: 0,
        target: null,
        aisleZ: start.z, dim: 0, dimTarget: 0,
        moving: false, typing: false, walkPhase: Math.random() * Math.PI * 2,
      };
      rig.group.position.copy(a.pos);
      rig.group.traverse((o) => { o.userData.agentId = item.id; });
      this.scene.add(rig.group);
      this.agents.set(item.id, a);
    }
    const prevState = a.item.state;
    a.item = item;
    a.index = index;
    a.desk = desks[index % desks.length]; // 工位组重建后自动重绑
    a.desk.setState(item.state);
    if (item.state === 'offline') {
      a.dimTarget = 1;
      a.poseTarget = 0;
      a.target = null;
    } else {
      a.dimTarget = 0;
      if (item.state === 'working') {
        // 每次 upsert 无条件重定向坐姿目标（覆盖 idle 巡逻残留点 / offline 停留点）
        a.target = new THREE.Vector3(sitPosOf(index).x, 0, sitPosOf(index).z);
        if (a.pos.distanceTo(a.target) < 0.05) a.poseTarget = 1; // 已在坐点才坐，避免半路坐下
      } else if (prevState === 'working') {
        // working→idle 起身：清掉坐姿目标，转入巡逻
        a.target = null;
        a.poseTarget = 0;
      }
    }
  }

  remove(id: number) {
    const a = this.agents.get(id);
    if (!a) return;
    this.scene.remove(a.rig.group);
    a.rig.group.traverse((o) => {
      const m = o as THREE.Mesh;
      if (m.geometry) m.geometry.dispose();
      const mat = m.material as THREE.Material | undefined;
      if (mat) mat.dispose();
    });
    this.agents.delete(id);
  }

  dispose() {
    for (const a of this.agents.values()) this.remove(a.id);
  }

  /** 每帧推进 */
  update(dt: number, time: number) {
    for (const a of this.agents.values()) {
      // 灰化 / 姿态过渡（≈0.4s 到达）
      a.dim += (a.dimTarget - a.dim) * Math.min(1, dt * 3);
      a.rig.setDim(a.dim);
      a.pose += (a.poseTarget - a.pose) * Math.min(1, dt * 3);
      const standing = a.pose < 0.5;

      if (a.item.state === 'idle' && standing) {
        // 过道巡逻：无目标/到达 → 换随机点（walkPhase 由 moveToward 连续推进，不跳变）
        if (!a.target || a.pos.distanceTo(a.target) < 0.06) {
          a.target = new THREE.Vector3(
            (Math.random() * 2 - 1) * PATROL_X_RANGE, 0,
            a.aisleZ + (Math.random() - 0.5) * 0.4,
          );
        }
        this.moveToward(a, a.target, AISLE_PATROL_SPEED, dt);
      } else if (a.item.state === 'working' && standing) {
        // 走向工位：到点坐下（target 由 upsert 无条件指向坐点，这里兜底）
        if (!a.target) a.target = new THREE.Vector3(sitPosOf(a.index).x, 0, sitPosOf(a.index).z);
        if (a.pos.distanceTo(a.target) < 0.05) {
          a.poseTarget = 1;
          a.moving = false;
        } else {
          this.moveToward(a, a.target, DESK_APPROACH_SPEED, dt);
        }
      } else if (a.item.state === 'working') {
        a.moving = false;
        a.typing = true;
        a.walkPhase += dt * 5;
      } else if (a.item.state === 'idle') {
        a.typing = false;
      } else {
        a.moving = false;
        a.typing = false;
      }

      // 姿态 + 位置 + 朝向
      a.rig.setPose(a.pose, a.walkPhase, a.typing);
      a.rig.group.position.set(a.pos.x, a.rig.group.position.y, a.pos.z);
      a.rig.group.rotation.y = a.heading;
      // 屏幕脉动
      if (a.desk.state === 'working') a.desk.setEmissivePulse((Math.sin(time * 2.4) + 1) / 2);
    }
  }

  private moveToward(a: Agent, target: THREE.Vector3, speed: number, dt: number) {
    const dx = target.x - a.pos.x;
    const dz = target.z - a.pos.z;
    const dist = Math.hypot(dx, dz);
    if (dist < 0.001) { a.moving = false; return; }
    const step = speed * dt;
    if (step >= dist) {
      a.pos.copy(target);
      a.moving = false;
    } else {
      a.pos.x += (dx / dist) * step;
      a.pos.z += (dz / dist) * step;
      a.moving = true;
    }
    // 朝向平滑插值（rotation.y，0 = 朝 +z）
    const desired = Math.atan2(dx, dz);
    const diff = Math.atan2(Math.sin(desired - a.heading), Math.cos(desired - a.heading));
    a.heading += diff * Math.min(1, dt * 8);
    a.walkPhase += dt * speed * 2.6;
  }
}
```

注意：working 的坐姿目标在每次 upsert 无条件重定向（覆盖 idle 巡逻残留点与 offline 停留点）；poseTarget 只在到点（dist<0.05）时置 1，避免半路坐下；工位组重建（数量变化）时 `a.desk` 在下次 upsert 重绑。Minor 已修：巡逻换点不再跳变 walkPhase；remove 释放 rig 几何/材质。Minor deferred：aisleZ 固定于出生排（items 重排序后巡逻道与工位行可能不一致，可接受偏差）。

- [ ] **Step 2: 构建门**

```bash
cd "/d/gongsi/medical system/web" && npm run build
```

Expected: PASS。

- [ ] **Step 3: 提交**

```bash
cd "/d/gongsi/medical system" && git add web/src/components/office3d/simulation.ts && git commit -m "feat(web): 小人模拟状态机（过道巡逻/走向工位坐下/offline 灰化/屏幕脉动）"
```

---

### Task 5: CSS2D 名牌（labels.ts）

**Files:**
- Create: `web/src/components/office3d/labels.ts`

**Interfaces:**
- Consumes: T4 `Agent`；`LiveStatusItem`；`STATE_TINTS`（从 `office/SpecialistCharacter` 导入，值不变）
- Produces: `TagHandle`（`el/obj(CSS2DObject)/update(agent, selected, hovered)`）、`createTag(actions): TagHandle`。`actions: { onViewData, onEdit, onToggleStatus }` 接收 `LiveStatusItem`

- [ ] **Step 1: 创建 labels.ts**

```ts
import * as THREE from 'three';
import { CSS2DObject } from 'three/addons/renderers/CSS2DRenderer.js';
import { STATE_TINTS } from '../office/SpecialistCharacter';
import type { Agent } from './simulation';
import type { LiveStatusItem } from '../../types';

export interface TagActions {
  onViewData: (item: LiveStatusItem) => void;
  onEdit: (item: LiveStatusItem) => void;
  onToggleStatus: (item: LiveStatusItem) => void;
}

export interface TagHandle {
  el: HTMLDivElement;
  obj: CSS2DObject;
  update(agent: Agent, selected: boolean, hovered: boolean): void;
}

const CSS = `
.otag { position: absolute; top: 0; left: 0; transform: translate(-50%, -110%);
  display: flex; flex-direction: column; align-items: center; gap: 2px; pointer-events: none;
  font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'PingFang SC', 'Microsoft YaHei', sans-serif; }
.otag-main { display: flex; align-items: center; gap: 5px; background: rgba(255,255,255,.95);
  border: 1px solid rgba(88,166,255,.5); border-radius: 10px; padding: 2px 8px; font-size: 11px;
  color: #333; box-shadow: 0 2px 8px rgba(0,0,0,.35); white-space: nowrap; }
.otag-main .dot { width: 7px; height: 7px; border-radius: 50%; flex-shrink: 0; }
.otag-main .nm { font-weight: 600; }
.otag-main .st { color: #8c8c8c; }
.otag.hover .otag-main { border-color: #1677ff; box-shadow: 0 0 0 1px #1677ff, 0 2px 8px rgba(0,0,0,.35); }
.otag.sel .otag-main { border-color: #1677ff; background: #e8f1ff; }
.otag-bubble { background: rgba(255,255,255,.95); border: 1px solid #f0f0f0; border-radius: 8px;
  padding: 2px 8px; font-size: 11px; color: #595959; box-shadow: 0 2px 8px rgba(0,0,0,.35);
  max-width: 220px; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.otag-actions { display: flex; gap: 10px; background: rgba(255,255,255,.98); border: 1px solid #e5e5e5;
  border-radius: 8px; padding: 3px 10px; font-size: 12px; pointer-events: auto; box-shadow: 0 2px 10px rgba(0,0,0,.4); }
.otag-actions a { cursor: pointer; }
`;

/** 状态文字（与名牌显示一致） */
export function stateText(item: LiveStatusItem): string {
  if (item.state === 'working') return item.phase_text ?? '工作中';
  if (item.state === 'idle') return '空闲中';
  return '离线';
}

let styleInjected = false;

/** 创建跟随人形的名牌 DOM（CSS2D），update 按数据刷新 */
export function createTag(actions: TagActions): TagHandle {
  if (!styleInjected) {
    const s = document.createElement('style');
    s.textContent = CSS;
    document.head.appendChild(s);
    styleInjected = true;
  }
  const el = document.createElement('div');
  el.className = 'otag';
  el.innerHTML = `
    <div class="otag-main">
      <span class="dot"></span><span class="nm"></span><span class="st"></span>
    </div>
    <div class="otag-bubble" style="display:none"></div>
    <div class="otag-actions" style="display:none">
      <a data-act="data">数据</a><a data-act="edit">编辑</a><a data-act="toggle"></a>
    </div>`;
  const obj = new CSS2DObject(el);
  obj.position.set(0, 1.55, 0);

  const qDot = el.querySelector('.dot') as HTMLSpanElement;
  const qNm = el.querySelector('.nm') as HTMLSpanElement;
  const qSt = el.querySelector('.st') as HTMLSpanElement;
  const qBubble = el.querySelector('.otag-bubble') as HTMLDivElement;
  const qActions = el.querySelector('.otag-actions') as HTMLDivElement;
  const qToggle = el.querySelector('[data-act="toggle"]') as HTMLAnchorElement;

  el.addEventListener('click', (e) => {
    if (e.target instanceof HTMLAnchorElement) {
      const act = e.target.dataset.act;
      // 通过 update 保存的 lastItem 取数据
      const item = (el as unknown as { _item?: LiveStatusItem })._item;
      if (!item) return;
      if (act === 'data') actions.onViewData(item);
      else if (act === 'edit') actions.onEdit(item);
      else if (act === 'toggle') actions.onToggleStatus(item);
      e.stopPropagation();
    }
  });

  const handle: TagHandle = {
    el, obj,
    update(agent, selected, hovered) {
      (el as unknown as { _item?: LiveStatusItem })._item = agent.item;
      const tint = STATE_TINTS[agent.item.state];
      qDot.style.background = tint;
      qNm.textContent = agent.item.name;
      qSt.textContent = `今日 ${agent.item.today_conversations} · ${stateText(agent.item)}`;
      const showBubble = agent.item.state === 'working';
      qBubble.style.display = showBubble ? '' : 'none';
      if (showBubble) {
        qBubble.textContent = agent.item.phase_text
          ? `${agent.item.phase_text}${agent.item.question_snippet ? ` · 正在回答：${agent.item.question_snippet}…` : ''}`
          : `正在回答：${agent.item.question_snippet}…`;
      }
      const sel = selected;
      qActions.style.display = sel ? '' : 'none';
      qToggle.textContent = agent.item.lifecycle === 'active' ? '停用' : '启用';
      qToggle.style.color = agent.item.lifecycle === 'active' ? '#ff4d4f' : '#52c41a';
      el.classList.toggle('sel', sel);
      el.classList.toggle('hover', hovered && !sel);
    },
  };
  return handle;
}
```

- [ ] **Step 2: 构建门**

```bash
cd "/d/gongsi/medical system/web" && npm run build
```

Expected: PASS。

- [ ] **Step 3: 提交**

```bash
cd "/d/gongsi/medical system" && git add web/src/components/office3d/labels.ts && git commit -m "feat(web): CSS2D 头顶名牌（名字/状态色点/气泡/选中操作卡）"
```

---

### Task 6: 3D 场景组件（OfficeScene3D.tsx，装配所有系统）

**Files:**
- Create: `web/src/components/office3d/OfficeScene3D.tsx`

**Interfaces:**
- Consumes: T1-T5 全部模块；`LiveStatusItem`
- Produces: 默认导出 `OfficeScene3D({ items, selectedId, onSelect, onEdit, onToggleStatus, onViewData })`——raycast 点击/悬停/选中/相机注视/WebGL 降级/销毁清理

- [ ] **Step 1: 创建 OfficeScene3D.tsx**

```tsx
import { useEffect, useRef, useState } from 'react';
import * as THREE from 'three';
import { CSS2DRenderer } from 'three/addons/renderers/CSS2DRenderer.js';
import { Alert, Empty, Button } from 'antd';
import { PlusOutlined } from '@ant-design/icons';
import { buildScene } from './buildScene';
import { buildDesks, type Desk } from './buildDesk';
import { Simulation } from './simulation';
import { createTag, type TagHandle, type TagActions } from './labels';
import type { LiveStatusItem } from '../../types';

export interface OfficeScene3DProps {
  items: LiveStatusItem[];
  selectedId: number | null;
  onSelect: (id: number | null) => void;
  onAdd: () => void;
  onEdit: (item: LiveStatusItem) => void;
  onToggleStatus: (item: LiveStatusItem) => void;
  onViewData: (item: LiveStatusItem) => void;
}

const CSS = `
.o3d-wrap { position: relative; border-radius: 12px; overflow: hidden; min-height: 420px;
  background: #0b1220; border: 1px solid rgba(88,166,255,.25); }
.o3d-canvas { position: absolute; inset: 0; }
.o3d-css { position: absolute; inset: 0; pointer-events: none; }
.o3d-empty { position: absolute; inset: 0; display: flex; align-items: center; justify-content: center; }
`;

/** 3D 动态办公室：Three.js 场景 + 小人模拟 + CSS2D 名牌 + raycast 交互 */
export default function OfficeScene3D({
  items, selectedId, onSelect, onAdd, onEdit, onToggleStatus, onViewData,
}: OfficeScene3DProps) {
  const mountRef = useRef<HTMLDivElement>(null);
  const [fatal, setFatal] = useState(false);
  const ctxRef = useRef<{
    renderer: THREE.WebGLRenderer;
    css: CSS2DRenderer;
    scene: THREE.Group;
    camera: THREE.PerspectiveCamera;
    sim: Simulation;
    tags: Map<number, TagHandle>;
    desks: Desk[];
    raycaster: THREE.Raycaster;
    pointer: THREE.Vector2;
    camTarget: THREE.Vector3;
    selected: number | null;
    hovered: number | null;
    raf: number;
    last: number;
  } | null>(null);
  const propsRef = useRef({ onEdit, onToggleStatus, onViewData });
  propsRef.current = { onEdit, onToggleStatus, onViewData };

  // 首次挂载：建渲染器/场景/模拟/标签层
  useEffect(() => {
    const mount = mountRef.current;
    if (!mount) return;

    let renderer: THREE.WebGLRenderer;
    try {
      renderer = new THREE.WebGLRenderer({ antialias: true });
    } catch {
      setFatal(true);
      return;
    }
    renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2));
    renderer.setSize(mount.clientWidth, mount.clientHeight);
    renderer.domElement.className = 'o3d-canvas';

    const css = new CSS2DRenderer();
    css.setSize(mount.clientWidth, mount.clientHeight);
    css.domElement.className = 'o3d-css';

    mount.appendChild(renderer.domElement);
    mount.appendChild(css.domElement);

    const scene = buildScene();
    const camera = new THREE.PerspectiveCamera(45, mount.clientWidth / mount.clientHeight, 0.1, 100);
    camera.position.set(0, 16, 14);
    const camTarget = new THREE.Vector3(0, 0, 0.5);
    camera.lookAt(camTarget);

    const ctx = {
      renderer, css, scene, camera,
      sim: new Simulation(scene),
      tags: new Map<number, TagHandle>(),
      desks: [] as Desk[],
      raycaster: new THREE.Raycaster(),
      pointer: new THREE.Vector2(-2, -2),
      camTarget,
      selected: null as number | null,
      hovered: null as number | null,
      raf: 0,
      last: performance.now(),
    };
    ctxRef.current = ctx;

    // 尺寸自适应
    const ro = new ResizeObserver(() => {
      const w = mount.clientWidth;
      const h = mount.clientHeight;
      renderer.setSize(w, h);
      css.setSize(w, h);
      camera.aspect = w / h;
      camera.updateProjectionMatrix();
    });
    ro.observe(mount);

    // 指针交互
    const toNDC = (e: PointerEvent) => {
      const r = mount.getBoundingClientRect();
      ctx.pointer.set(((e.clientX - r.left) / r.width) * 2 - 1, -((e.clientY - r.top) / r.height) * 2 + 1);
    };
    const pick = (): number | null => {
      ctx.raycaster.setFromCamera(ctx.pointer, camera);
      const hits = ctx.raycaster.intersectObjects(scene.children, true);
      for (const h of hits) {
        const id = (h.object as THREE.Object3D).userData.agentId as number | undefined;
        if (id !== undefined) return id;
        const slot = (h.object as THREE.Object3D).userData.slot as number | undefined;
        if (slot !== undefined) {
          const agent = [...sim.agents.values()].find((x) => x.desk.group.userData.slot === slot);
          if (agent) return agent.id;
        }
      }
      return null;
    };
    const onPointerMove = (e: PointerEvent) => {
      toNDC(e);
      const id = pick();
      if (id !== ctx.hovered) {
        ctx.hovered = id;
        mount.style.cursor = id !== null ? 'pointer' : 'default';
      }
    };
    const onClick = (e: PointerEvent) => {
      toNDC(e);
      const id = pick();
      if (id !== null) {
        propsRef.current.onSelect(id);
        const a = ctx.sim.agents.get(id);
        if (a) propsRef.current.onViewData(a.item);
      } else {
        propsRef.current.onSelect(null);
      }
    };
    mount.addEventListener('pointermove', onPointerMove);
    mount.addEventListener('click', onClick);

    // 主循环
    const loop = (now: number) => {
      const dt = Math.min(0.05, (now - ctx.last) / 1000);
      ctx.last = now;
      ctx.sim.update(dt, now / 1000);
      // 标签跟随 + 刷新
      for (const [id, t] of ctx.tags) {
        const a = ctx.sim.agents.get(id);
        if (!a) continue;
        t.obj.position.set(a.pos.x, 1.55, a.pos.z);
        t.update(a, ctx.selected === id, ctx.hovered === id);
      }
      // 选中聚焦（相机注视点平滑跟随）
      if (ctx.selected !== null) {
        const a = ctx.sim.agents.get(ctx.selected);
        if (a) ctx.camTarget.lerp(new THREE.Vector3(a.pos.x, 0, a.pos.z), Math.min(1, dt * 2));
      } else {
        ctx.camTarget.lerp(new THREE.Vector3(0, 0, 0.5), Math.min(1, dt * 2));
      }
      camera.lookAt(ctx.camTarget);
      renderer.render(scene, camera);
      css.render(scene, camera);
      ctx.raf = requestAnimationFrame(loop);
    };
    ctx.raf = requestAnimationFrame(loop);

    // 清理
    return () => {
      cancelAnimationFrame(ctx.raf);
      ro.disconnect();
      mount.removeEventListener('pointermove', onPointerMove);
      mount.removeEventListener('click', onClick);
      ctx.sim.dispose();
      scene.traverse((o) => {
        const m = o as THREE.Mesh;
        if (m.geometry) m.geometry.dispose();
        const mat = m.material as THREE.Material | undefined;
        if (mat) mat.dispose();
      });
      renderer.dispose();
      mount.removeChild(renderer.domElement);
      mount.removeChild(css.domElement);
      ctxRef.current = null;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // 选中同步到 3D（selectedId prop 变化）
  useEffect(() => {
    const ctx = ctxRef.current;
    if (!ctx) return;
    ctx.selected = selectedId;
  }, [selectedId]);

  // 数据同步：items 变化 → 工位组重建（仅数量变化）+ upsert/移除小人 + 标签增补
  useEffect(() => {
    const ctx = ctxRef.current;
    if (!ctx) return;
    const n = items.length;
    if (n !== ctx.desks.length) {
      for (const d of ctx.desks) {
        ctx.scene.remove(d.group);
        d.group.traverse((o) => {
          const m = o as THREE.Mesh;
          if (m.geometry) m.geometry.dispose();
          const mat = m.material as THREE.Material | undefined;
          if (mat) mat.dispose();
        });
      }
      ctx.desks = buildDesks(n);
      for (const d of ctx.desks) ctx.scene.add(d.group);
    }
    const seen = new Set<number>();
    items.forEach((item, index) => {
      seen.add(item.id);
      ctx.sim.upsert(item, index, ctx.desks);
    });
    for (const id of [...ctx.sim.agents.keys()]) {
      if (!seen.has(id)) {
        ctx.sim.remove(id);
        const t = ctx.tags.get(id);
        if (t) { ctx.scene.remove(t.obj); ctx.tags.delete(id); }
      }
    }
    for (const a of ctx.sim.agents.values()) {
      let t = ctx.tags.get(a.id);
      if (!t) {
        t = createTag({
          onViewData: (it) => propsRef.current.onViewData(it),
          onEdit: (it) => propsRef.current.onEdit(it),
          onToggleStatus: (it) => propsRef.current.onToggleStatus(it),
        });
        ctx.tags.set(a.id, t);
        ctx.scene.add(t.obj);
      }
      t.update(a, ctx.selected === a.id, ctx.hovered === a.id);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [items]);

  if (fatal) {
    return (
      <div className="o3d-wrap">
        <Alert type="warning" showIcon message="3D 场景不可用" description="当前浏览器不支持 WebGL，可切换到表格视图使用。" />
      </div>
    );
  }

  return (
    <div className="o3d-wrap">
      <style>{CSS}</style>
      {items.length === 0 && (
        <div className="o3d-empty">
          <Empty description="暂无数字专员">
            <Button type="primary" icon={<PlusOutlined />} onClick={onAdd}>新增专员</Button>
          </Empty>
        </div>
      )}
      <div ref={mountRef} style={{ width: '100%', height: items.length === 0 ? 420 : 560, position: 'relative' }} />
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
cd "/d/gongsi/medical system" && git add web/src/components/office3d/OfficeScene3D.tsx && git commit -m "feat(web): 3D 办公室场景组件（渲染循环/数据同步/raycast 选中/相机注视/WebGL 降级）"
```

---

### Task 7: 出勤面板 + 页面整合（AttendancePanel.tsx + SpecialistOffice.tsx）

**Files:**
- Create: `web/src/components/office3d/AttendancePanel.tsx`
- Modify: `web/src/pages/Specialist/SpecialistOffice.tsx`（布局改造：工具条 + 左面板 + 右场景）
- Delete: `web/src/components/office/OfficeScene.tsx`、`web/src/components/office/Workstation.tsx`

**Interfaces:**
- Consumes: `LiveStatusItem`、`MiniCharacter`/`STATE_TINTS`（office/SpecialistCharacter，保留）、T6 `OfficeScene3D`
- Produces: `AttendancePanel({ items, selectedId, onSelect, onAdd })`

- [ ] **Step 1: 创建 AttendancePanel.tsx**

```tsx
import { Button, Empty, Progress } from 'antd';
import { PlusOutlined } from '@ant-design/icons';
import { MiniCharacter, STATE_TINTS } from '../office/SpecialistCharacter';
import { stateText } from './labels';
import type { LiveStatusItem } from '../../types';

const CSS = `
.att-panel { background: #fafafa; border: 1px solid #f0f0f0; border-radius: 12px; padding: 14px 12px; }
.att-title { font-weight: 600; font-size: 14px; margin-bottom: 6px; }
.att-rate-wrap { text-align: center; }
.att-rate { font-size: 20px; font-weight: 600; }
.att-stats { margin-top: 10px; display: flex; flex-direction: column; gap: 6px; font-size: 13px; color: #595959; }
.att-stats .dot { width: 8px; height: 8px; border-radius: 50%; display: inline-block; margin-right: 6px; }
.att-today { margin-top: 4px; color: #8c8c8c; font-size: 12px; }
.att-list { margin-top: 10px; max-height: 320px; overflow-y: auto; display: flex; flex-direction: column; gap: 4px; }
.att-row { display: flex; align-items: center; gap: 8px; padding: 6px 8px; border-radius: 8px; cursor: pointer; }
.att-row:hover { background: #f0f0f0; }
.att-row.sel { background: #e8f1ff; outline: 1px solid #91caff; }
.att-row-main { flex: 1; min-width: 0; }
.att-row-name { font-size: 13px; font-weight: 500; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.att-row-st { font-size: 11px; color: #8c8c8c; }
`;

function relTime(iso: string | null): string {
  if (!iso) return '从未';
  const ms = Date.now() - new Date(iso).getTime();
  if (ms < 0) return '刚刚';
  const min = Math.floor(ms / 60000);
  if (min < 1) return '刚刚';
  if (min < 60) return `${min} 分钟前`;
  const h = Math.floor(min / 60);
  if (h < 24) return `${h} 小时前`;
  return `${Math.floor(h / 24)} 天前`;
}

/** 团队出勤面板：出勤率环形 + 状态分布 + 今日对话 + 在岗明细（与 3D 场景双向联动） */
export default function AttendancePanel({
  items, selectedId, onSelect, onAdd,
}: {
  items: LiveStatusItem[];
  selectedId: number | null;
  onSelect: (id: number | null) => void;
  onAdd: () => void;
}) {
  const total = items.length;
  const working = items.filter((i) => i.state === 'working').length;
  const idle = items.filter((i) => i.state === 'idle').length;
  const offline = total - working - idle;
  const rate = total ? Math.round(((working + idle) / total) * 100) : 0;
  const todayTotal = items.reduce((s, i) => s + i.today_conversations, 0);
  const todayAvg = total ? todayTotal / total : 0;

  return (
    <div className="att-panel">
      <style>{CSS}</style>
      <div className="att-title">团队出勤</div>
      {total === 0 ? (
        <Empty description="暂无数字专员" imageStyle={{ height: 60 }}>
          <Button type="primary" size="small" icon={<PlusOutlined />} onClick={onAdd}>新增专员</Button>
        </Empty>
      ) : (
        <>
          <div className="att-rate-wrap">
            <Progress
              type="dashboard"
              percent={rate}
              size={140}
              strokeColor={{ '0%': '#1677ff', '100%': '#58a6ff' }}
              format={(p) => <span className="att-rate">{p}%</span>}
            />
          </div>
          <div className="att-stats">
            <div><span className="dot" style={{ background: STATE_TINTS.working }} />工作中 <b>{working}</b></div>
            <div><span className="dot" style={{ background: STATE_TINTS.idle }} />空闲 <b>{idle}</b></div>
            <div><span className="dot" style={{ background: STATE_TINTS.offline }} />离线 <b>{offline}</b></div>
            <div className="att-today">今日对话 {todayTotal} · 人均 {todayAvg.toFixed(1)}</div>
          </div>
          <div className="att-list">
            {items.map((it) => (
              <div
                key={it.id}
                className={`att-row${selectedId === it.id ? ' sel' : ''}`}
                onClick={() => onSelect(selectedId === it.id ? null : it.id)}
              >
                <MiniCharacter id={it.id} state={it.state} size={26} />
                <div className="att-row-main">
                  <div className="att-row-name">{it.name}</div>
                  <div className="att-row-st">{stateText(it)} · 今日 {it.today_conversations} · {relTime(it.last_active_at)}</div>
                </div>
                <span style={{ width: 8, height: 8, borderRadius: '50%', background: STATE_TINTS[it.state], flexShrink: 0 }} />
              </div>
            ))}
          </div>
        </>
      )}
    </div>
  );
}
```

- [ ] **Step 2: 改造 SpecialistOffice.tsx**

整体替换为（轮询/toSpecialist/编辑 detail 包装/工具条逻辑保留，布局改为 面板+场景）：

```tsx
import { useEffect, useRef, useState } from 'react';
import {
  Tag, Switch, Button, Space, App, Flex,
} from 'antd';
import { PlusOutlined, ReloadOutlined } from '@ant-design/icons';
import { specialistAPI } from '../../services/specialist';
import OfficeScene3D from '../../components/office3d/OfficeScene3D';
import AttendancePanel from '../../components/office3d/AttendancePanel';
import type { LiveStatus, LiveStatusItem, Specialist } from '../../types';

const POLL_INTERVAL_MS = 3000;

/** live 条目 → Specialist：live 用 lifecycle、Specialist 用 status，映射补 status 供父组件 toggleStatus 判定 */
function toSpecialist(sp: LiveStatusItem): Specialist {
  return { ...sp, created_at: '', status: sp.lifecycle } as unknown as Specialist;
}

/** 数字员工办公室：3s 轮询 live-status，3D 动态场景 + 团队出勤面板 */
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
  const [selectedId, setSelectedId] = useState<number | null>(null);
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
      <Flex gap={16} align="flex-start">
        <div style={{ width: 280, flexShrink: 0 }}>
          <AttendancePanel items={items} selectedId={selectedId} onSelect={setSelectedId} onAdd={onAdd} />
        </div>
        <div style={{ flex: 1, minWidth: 0 }}>
          <OfficeScene3D
            items={items}
            selectedId={selectedId}
            onSelect={setSelectedId}
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
      </Flex>
    </div>
  );
}
```

- [ ] **Step 3: 删除 v3 遗留组件**

```bash
cd "/d/gongsi/medical system" && git rm web/src/components/office/OfficeScene.tsx web/src/components/office/Workstation.tsx
```

Expected: 无其它文件引用（grep `OfficeScene`/`Workstation` 在 web/src 应只命中已删文件自身）。

- [ ] **Step 4: 构建门**

```bash
cd "/d/gongsi/medical system/web" && npm run build
```

Expected: PASS。

- [ ] **Step 5: 提交**

```bash
cd "/d/gongsi/medical system" && git add -A && git commit -m "feat(web): 团队出勤面板 + 3D 场景接入专员办公室页（删除 v3 场景组件）"
```

---

### Task 8: E2E 验证（验证任务）

**Files:**
- 新建：`t10-office3d/`（截图/录屏输出，不提交）

**Interfaces:** 无产出。验证 T1-T7 集成效果。

前置：8 个服务 + web dev 运行中（v3 遗留环境；若停则按 CLAUDE.md native 路径启动）。登录 admin / MedAgent@2026。

- [ ] **Step 1: 构建门**

```bash
cd "/d/gongsi/medical system/web" && npm run build
```

Expected: PASS。

- [ ] **Step 2: 环境自检 + 专员数**

登录拿 token（POST /api/v1/auth/login，body 放 UTF-8 文件），`GET /api/v1/specialists/live-status` 确认 items 返回。若专员 < 3，用 POST /api/v1/specialists 补到 ≥3（draft，offline 态）。

- [ ] **Step 3: Playwright 截图/录屏**（脚本放 `t10-office3d/e2e_v4.py`）

Chromium（支持 WebGL）登录 → 专员办公室页，验证并截图：
1. `scene.png` — 3D 俯视场景（网格地板/过道发光条/桌+电脑+凳子）
2. `panel.png` — 左侧出勤面板（出勤率环形/分布/今日对话/明细列表）
3. `walk.png` — 空闲小人正在过道走动（两帧间隔 ~1.5s 对比位置变化：`walk-a.png` + `walk-b.png`）
4. `sit.png` — 对某 active 专员发真实对话（curl chat，UTF-8 payload 文件），等待 2-4s 后截图：小人走到工位坐下 + 屏幕蓝光 + 名牌气泡
5. `offline.png` — 面板/场景中 offline 专员灰化静止
6. `sel.png` — 点击一个工位/小人：数据抽屉打开 + 名牌下操作卡（数据/编辑/停用·启用）
7. `link.png` — 点击出勤面板某行 → 3D 场景该小人名牌高亮（选中样式）

断言：截图内可见对应元素（或两帧位置差 > 阈值证明走动）。

- [ ] **Step 4: 状态流转**

真实对话触发 working → 观察坐下+蓝光+名牌阶段流转；对话结束 → 观察起身回巡逻；停用 → 灰化；启用恢复。

- [ ] **Step 5: 回归**

- 编辑：选中操作卡「编辑」→ 表单 persona/knowledge_scope 预填全量 → 取消
- 数据抽屉：「数据」按钮与点击工位均可打开
- 切表：Segmented 表格↔办公室来回切换无报错
- 状态条：MiniCharacter 白色头像 + 色点 + 跳转正常
- 面板联动：点明细行 → 3D 高亮；3D 选中 → 面板行高亮
- 页面离开（切到其它页）无 console 报错（rAF 清理）

- [ ] **Step 6: 结果记录**

按 controller 指示回报；任何失败附截图路径与复现步骤。
