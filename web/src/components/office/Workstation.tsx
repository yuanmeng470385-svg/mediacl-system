import { memo } from 'react';
import { Space, Tag } from 'antd';
import type { LiveStatusItem } from '../../types';
import SpecialistCharacter, { STATE_TINTS } from './SpecialistCharacter';

const CSS = `
@keyframes ws-screen-on { 0%, 100% { opacity: 1; } 50% { opacity: 0.82; } }
.ch-screen-on { animation: ws-screen-on 2.4s ease-in-out infinite; }
@keyframes ws-finger-1 { 0%, 100% { opacity: 0.25; } 20% { opacity: 1; } 60% { opacity: 0.25; } }
@keyframes ws-finger-2 { 0%, 100% { opacity: 0.25; } 45% { opacity: 1; } 80% { opacity: 0.25; } }
@keyframes ws-finger-3 { 0%, 100% { opacity: 0.25; } 30% { opacity: 1; } 70% { opacity: 0.25; } }
.ch-finger-1 { animation: ws-finger-1 1.1s infinite; }
.ch-finger-2 { animation: ws-finger-2 1.1s infinite; }
.ch-finger-3 { animation: ws-finger-3 1.1s infinite; }
@keyframes ws-steam { 0% { transform: translateY(0); opacity: 0; } 25% { opacity: 0.7; } 100% { transform: translateY(-7px); opacity: 0; } }
.ch-steam-1 { animation: ws-steam 2s ease-out infinite; }
.ch-steam-2 { animation: ws-steam 2s ease-out 1s infinite; }
@keyframes ws-enter { from { transform: translateY(10px); opacity: 0; } to { transform: translateY(0); opacity: 1; } }
.ws { position: relative; width: 170px; animation: ws-enter .45s ease-out backwards; }
.ws-bubble { position: absolute; top: -34px; left: 50%; transform: translateX(-50%); z-index: 3;
  background: #fff; border: 1px solid #f0f0f0; border-radius: 8px; box-shadow: 0 2px 8px rgba(0,0,0,.08);
  padding: 4px 8px; font-size: 11px; color: #595959; white-space: nowrap; max-width: 200px; overflow: hidden; text-overflow: ellipsis; }
.ws-bubble::after { content: ''; position: absolute; top: 100%; left: 50%; margin-left: -4px;
  border: 4px solid transparent; border-top-color: #fff; }
.ws-nameplate { display: flex; align-items: center; justify-content: center; gap: 5px; margin-top: 6px; font-size: 12px; }
.ws-nameplate .dot { width: 8px; height: 8px; border-radius: 50%; }
.ws-actions { position: absolute; top: 6px; right: 6px; z-index: 4; background: rgba(255,255,255,.95);
  border: 1px solid #f0f0f0; border-radius: 6px; padding: 2px 6px; opacity: 0; transition: opacity .15s;
  box-shadow: 0 2px 8px rgba(0,0,0,.08); font-size: 12px; }
.ws:hover .ws-actions { opacity: 1; }
`;

/** 工位：显示器 + 角色 + 桌面（键盘/咖啡）+ 名牌 + 头顶气泡 + 悬停操作条 */
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
      <svg viewBox="0 0 170 150" style={{ display: 'block', width: '100%' }}>
        {/* 显示器（工作中亮屏蓝光脉动，空闲息屏） */}
        <rect x="55" y="6" width="60" height="44" rx="3" fill={off ? '#e5e7eb' : '#1e293b'} />
        <rect x="60" y="11" width="50" height="34" rx="2" fill={working ? '#0ea5e9' : '#f8fafc'} className={working ? 'ch-screen-on' : undefined} />
        {working && (
          <g fill="#e0f2fe">
            <rect x="65" y="17" width="34" height="3" rx="1.5" />
            <rect x="65" y="24" width="26" height="3" rx="1.5" />
            <rect x="65" y="31" width="30" height="3" rx="1.5" />
          </g>
        )}
        <rect x="73" y="50" width="24" height="4" rx="2" fill="#9ca3af" />
        <rect x="61" y="54" width="48" height="6" rx="2" fill="#6b7280" />
        {/* 角色 */}
        <svg x="25" y="4" width="120" height="140" viewBox="0 0 120 140">
          <SpecialistCharacter id={item.id} state={item.state} />
        </svg>
        {/* 桌面（盖住角色下半身） */}
        <rect x="0" y="120" width="170" height="11" rx="2" fill={off ? '#b9b2a6' : '#8a5a33'} />
        <rect x="0" y="131" width="170" height="19" fill={off ? '#a39c90' : '#6b4423'} />
        {/* 工作中：键盘 + 打字的手 */}
        {working && (
          <g>
            <rect x="60" y="108" width="50" height="13" rx="2" fill="#333333" />
            <g fill="#555555">
              {[66, 75, 84, 93].map((x) => (
                <rect key={x} x={x} y="111" width="5" height="3" rx="1" />
              ))}
            </g>
            <circle cx="72" cy="106" r="4" fill="#ffd9b3" />
            <circle cx="98" cy="106" r="4" fill="#ffd9b3" />
            <circle cx="69" cy="104" r="2.2" fill="#c68a5c" className="ch-finger-1" />
            <circle cx="84" cy="103" r="2.2" fill="#c68a5c" className="ch-finger-2" />
            <circle cx="99" cy="104" r="2.2" fill="#c68a5c" className="ch-finger-3" />
          </g>
        )}
        {/* 空闲：桌面咖啡杯 + 蒸汽 */}
        {idle && (
          <g>
            <rect x="106" y="104" width="16" height="13" rx="2" fill="#ffffff" stroke="#d9d9d9" strokeWidth="1.2" />
            <path d="M122 107 q5 0 5 3.5 q0 3.5 -5 3.5" stroke="#d9d9d9" strokeWidth="1.2" fill="none" />
            <path d="M112 100 q-1.5 -3 0 -6" stroke="#d9d9d9" strokeWidth="1.5" fill="none" className="ch-steam-1" />
            <path d="M118 101 q1.5 -3 0 -6" stroke="#d9d9d9" strokeWidth="1.5" fill="none" className="ch-steam-2" />
          </g>
        )}
      </svg>
      {/* 名牌：名字 + 状态色点 + 今日次数 */}
      <div className="ws-nameplate">
        <span className="dot" style={{ background: tint }} />
        <span style={{ fontWeight: 500 }}>{item.name}</span>
        <span style={{ color: '#8c8c8c' }}>今日 {item.today_conversations}</span>
        {item.lifecycle !== 'active' && (
          <Tag color={item.lifecycle === 'disabled' ? 'default' : 'orange'} style={{ marginInlineEnd: 0, fontSize: 11, lineHeight: '16px' }}>
            {item.lifecycle === 'disabled' ? '停用' : '草稿'}
          </Tag>
        )}
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
