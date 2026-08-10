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
        a.poseTarget = 1;
        if (a.target === null) a.target = new THREE.Vector3(sitPosOf(index).x, 0, sitPosOf(index).z);
      } else {
        a.poseTarget = 0;
      }
    }
  }

  remove(id: number) {
    const a = this.agents.get(id);
    if (!a) return;
    this.scene.remove(a.rig.group);
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
        // 过道巡逻：无目标/到达 → 换随机点
        if (!a.target || a.pos.distanceTo(a.target) < 0.06) {
          a.target = new THREE.Vector3(
            (Math.random() * 2 - 1) * PATROL_X_RANGE, 0,
            a.aisleZ + (Math.random() - 0.5) * 0.4,
          );
          a.walkPhase += 1.7;
        }
        this.moveToward(a, a.target, AISLE_PATROL_SPEED, dt);
      } else if (a.item.state === 'working' && standing) {
        // 走向工位：到点坐下
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
