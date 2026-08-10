import * as THREE from 'three';
import { DESK_W, DESK_D, DESK_H, PER_ROW, deskX, rowZ, slotOf } from './layout';

export type DeskState = 'working' | 'idle' | 'offline';

export interface Desk {
  group: THREE.Group;
  screenMat: THREE.MeshStandardMaterial;
  state: DeskState;
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
    group, screenMat, state,
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
        const m = (o as THREE.Mesh).material as THREE.MeshStandardMaterial | undefined;
        if (m && m !== screenMat) {
          m.transparent = true;
          m.opacity = dim ? 0.5 : 1;
        }
      });
    },
    setEmissivePulse(v) {
      if (state === 'working') screenMat.emissiveIntensity = 0.5 + 0.5 * v;
    },
  };
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
