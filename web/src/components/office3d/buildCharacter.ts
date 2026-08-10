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
  // 亮白主体（微弱自发光，与蓝灰背景拉开对比）+ 深炭四肢/鞋
  const white = new THREE.MeshStandardMaterial({ color: 0xffffff, roughness: 0.5, emissive: 0xffffff, emissiveIntensity: 0.12 });
  const gray = new THREE.MeshStandardMaterial({ color: 0x333333, roughness: 0.7 });
  const shoe = new THREE.MeshStandardMaterial({ color: 0x2b2b2e, roughness: 0.8 });
  // 整体等比放大 1.3×（与工位/间距同倍率，保持手落桌面等几何关系）
  group.scale.setScalar(1.3);

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

  // offline 灰化：不透明（用户要求不要太过透明），靠颜色灰化与背景区分
  const dimColor = new THREE.Color(0x8a9099);
  const baseColors = mats.map((m) => m.color.clone());

  const rig: CharacterRig = {
    group, legL, legR, armL, armR, torso, head, mats,
    setPose(pose, phase, typing) {
      const p = THREE.MathUtils.clamp(pose, 0, 1);
      const swing = Math.sin(phase);
      const typingOffset = typing ? Math.sin(phase * 4) * 0.04 : 0;
      const seatedArm = 1.35 + typingOffset;
      legL.rotation.x = (1 - p) * (swing * 0.65) + p * 1.2;
      legR.rotation.x = (1 - p) * (-swing * 0.65) + p * 1.2;
      armL.rotation.x = (1 - p) * (-swing * 0.5) + p * seatedArm;
      armR.rotation.x = (1 - p) * (swing * 0.5) + p * (seatedArm + 0.05);
      torso.rotation.x = p * 0.12 + (1 - p) * Math.sin(phase * 2) * 0.03;
      head.rotation.x = p * 0.04;
    },
    setDim(a) {
      for (let i = 0; i < mats.length; i++) {
        const c = baseColors[i].clone().lerp(dimColor, a);
        mats[i].color.copy(c);
        mats[i].transparent = false;
        mats[i].opacity = 1;
      }
    },
  };
  return rig;
}
