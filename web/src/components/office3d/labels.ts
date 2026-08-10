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
    e.stopPropagation();
    if (e.target instanceof HTMLAnchorElement) {
      const act = e.target.dataset.act;
      // 通过 update 保存的 lastItem 取数据
      const item = (el as unknown as { _item?: LiveStatusItem })._item;
      if (!item) return;
      if (act === 'data') actions.onViewData(item);
      else if (act === 'edit') actions.onEdit(item);
      else if (act === 'toggle') actions.onToggleStatus(item);
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
          ? `${agent.item.phase_text}${agent.item.question_snippet ? ` · 正在回答：${agent.item.question_snippet ?? ''}…` : ''}`
          : `正在回答：${agent.item.question_snippet ?? ''}…`;
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
