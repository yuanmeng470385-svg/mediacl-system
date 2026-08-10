import * as THREE from 'three';
import { DESK_W, DESK_D, DESK_H, PER_ROW, deskX, rowZ, slotOf } from './layout';

export type DeskState = 'working' | 'idle' | 'offline';

export interface Desk {
  group: THREE.Group;
  screenMat: THREE.MeshStandardMaterial;
  readonly state: DeskState;
  setState(s: DeskState): void;
  /** working 时每帧调用：0..1 脉动强度 */
  setEmissivePulse(v: number): void;
}

/** 单张工位：白色桌面/桌腿 + 桌沿发光条 + 电脑（底座/支架/屏幕/外框）+ 凳子 */
export function buildDesk(): Desk {
  const group = new THREE.Group();
  const wood = new THREE.MeshStandardMaterial({ color: 0xf8fafc, roughness: 0.5 }); // 白色桌面
  const legMat = new THREE.MeshStandardMaterial({ color: 0xe2e8f0, roughness: 0.6 }); // 浅灰白桌腿
  const dark = new THREE.MeshStandardMaterial({ color: 0x27334a, roughness: 0.9 }); // 电脑/凳子深蓝灰
  const edgeMat = new THREE.MeshBasicMaterial({ color: 0x58a6ff, transparent: true, opacity: 0.5 });

  // 桌面 + 桌腿
  const top = new THREE.Mesh(new THREE.BoxGeometry(DESK_W, 0.1, DESK_D), wood);
  top.position.y = DESK_H;
  group.add(top);
  const legX = DESK_W / 2 - 0.13;
  const legZ = DESK_D / 2 - 0.1;
  for (const sx of [-legX, legX]) {
    for (const sz of [-legZ, legZ]) {
      const leg = new THREE.Mesh(new THREE.BoxGeometry(0.1, DESK_H - 0.05, 0.1), legMat);
      leg.position.set(sx, (DESK_H - 0.05) / 2, sz);
      group.add(leg);
    }
  }
  // 桌沿发光条（前缘，浅蓝）
  const edge = new THREE.Mesh(new THREE.BoxGeometry(DESK_W + 0.02, 0.026, 0.026), edgeMat);
  edge.position.set(0, DESK_H + 0.065, DESK_D / 2);
  group.add(edge);

  // 电脑：底座 + 支架 + 屏幕 + 外框（屏幕朝 +z）
  const base = new THREE.Mesh(new THREE.BoxGeometry(0.65, 0.05, 0.39), dark);
  base.position.set(0, DESK_H + 0.05, 0.1);
  group.add(base);
  const stand = new THREE.Mesh(new THREE.BoxGeometry(0.08, 0.18, 0.08), dark);
  stand.position.set(0, DESK_H + 0.17, 0.1);
  group.add(stand);
  const screenMat = new THREE.MeshStandardMaterial({
    color: 0x0e1c2e, roughness: 0.35, emissive: 0x1677ff, emissiveIntensity: 0,
  });
  const screen = new THREE.Mesh(new THREE.BoxGeometry(1.3, 0.75, 0.08), screenMat);
  screen.position.set(0, DESK_H + 0.44, 0.13);
  group.add(screen);
  const bezel = new THREE.Mesh(new THREE.BoxGeometry(1.38, 0.83, 0.026), dark);
  bezel.position.set(0, DESK_H + 0.44, 0.175);
  group.add(bezel);

  // 凳子（坐姿支撑）
  const stool = new THREE.Mesh(new THREE.BoxGeometry(0.47, 0.52, 0.47), dark);
  stool.position.set(0, 0.26, DESK_D / 2 + 0.43);
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
      // 桌子始终保持白色不透明（用户要求）；offline 语义只体现在屏幕熄灭 + 人物灰化
      group.traverse((o) => {
        const m = (o as THREE.Mesh).material as THREE.Material | undefined;
        if (m && m !== screenMat && m !== edgeMat) {
          m.transparent = false;
          m.opacity = 1;
        }
      });
    },
    setEmissivePulse(v) {
      if (state === 'working') screenMat.emissiveIntensity = 0.5 + 0.5 * v;
    },
  };
  desk.setState('idle');
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
