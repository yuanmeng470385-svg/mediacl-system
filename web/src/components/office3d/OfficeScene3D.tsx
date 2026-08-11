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
    tmpVec: THREE.Vector3;
    selected: number | null;
    hovered: number | null;
    raf: number;
    last: number;
  } | null>(null);
  const propsRef = useRef({ onSelect, onEdit, onToggleStatus, onViewData });
  propsRef.current = { onSelect, onEdit, onToggleStatus, onViewData };

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
    // 4×5 布局（间距 1.5×，±7.8 跨）拉远覆盖（边缘桌角 20° < fov 半角 22.5° 验算）
    camera.position.set(0, 13, 12);
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
      tmpVec: new THREE.Vector3(),
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
          const agent = [...ctx.sim.agents.values()].find((x) => x.desk.group.userData.slot === slot);
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
        t.obj.position.set(a.pos.x, 2.0, a.pos.z);
        t.update(a, ctx.selected === id, ctx.hovered === id);
      }
      // 选中聚焦（相机注视点平滑跟随）
      if (ctx.selected !== null) {
        const a = ctx.sim.agents.get(ctx.selected);
        if (a) {
          ctx.tmpVec.set(a.pos.x, 0, a.pos.z);
          ctx.camTarget.lerp(ctx.tmpVec, Math.min(1, dt * 2));
        }
      } else {
        ctx.tmpVec.set(0, 0, 0.5);
        ctx.camTarget.lerp(ctx.tmpVec, Math.min(1, dt * 2));
      }
      camera.lookAt(ctx.camTarget);
      renderer.render(scene as unknown as THREE.Scene, camera);
      css.render(scene as unknown as THREE.Scene, camera);
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
        if (mat) {
          mat.dispose();
          // 地板 CanvasTexture 一并释放（每次挂载新建，避免挂载循环累积纹理）
          const tex = (mat as THREE.MeshStandardMaterial).map;
          if (tex) tex.dispose();
        }
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
