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
