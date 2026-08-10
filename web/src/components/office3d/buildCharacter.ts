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
  const baseColor = new THREE.Color(0xffffff);

  const rig: CharacterRig = {
    group, legL, legR, armL, armR, torso, head, mats,
    setPose(pose, phase, typing) {
      const p = THREE.MathUtils.clamp(pose, 0, 1);
      const swing = Math.sin(phase);
      const typingOffset = typing ? Math.sin(phase * 4) * 0.04 : 0;
      const seatedArm = -1.35 + typingOffset;
      legL.rotation.x = (1 - p) * (swing * 0.65) + p * -1.2;
      legR.rotation.x = (1 - p) * (-swing * 0.65) + p * -1.2;
      armL.rotation.x = (1 - p) * (-swing * 0.5) + p * seatedArm;
      armR.rotation.x = (1 - p) * (swing * 0.5) + p * (seatedArm + 0.05);
      torso.rotation.x = p * 0.12;
      head.rotation.x = p * 0.04;
      group.position.y = p * 0.1;
    },
    setDim(a) {
      const c = baseColor.clone().lerp(dimColor, a);
      for (const m of mats) {
        m.color.copy(c);
        m.transparent = a > 0;
        m.opacity = 1 - 0.55 * a;
      }
    },
  };
  return rig;
}
