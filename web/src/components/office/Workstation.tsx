import { memo } from 'react';
import { Space, Tag } from 'antd';
import type { LiveStatusItem } from '../../types';
import SpecialistCharacter, { STATE_TINTS } from './SpecialistCharacter';

const CSS = `
@keyframes ws-enter { from { transform: rotateX(-18deg) translateY(10px); opacity: 0; }
  to { transform: rotateX(-18deg) translateY(0); opacity: 1; } }
.ws { position: relative; width: 150px; transform: rotateX(-18deg); animation: ws-enter .45s ease-out backwards; }
.ws-card { position: relative; background: rgba(13, 20, 34, 0.72); border: 1px solid rgba(88, 166, 255, 0.4);
  border-radius: 10px; padding: 12px 10px 8px; box-shadow: 0 0 12px rgba(88, 166, 255, 0.28); }
.ws-char { width: 46px; height: 58px; margin: 0 auto 2px; }
.ws-light { height: 4px; width: 72%; margin: 4px auto 8px; border-radius: 2px; }
@keyframes ws-light-pulse { 0%, 100% { opacity: 0.55; } 50% { opacity: 1; } }
.ws-light-working { animation: ws-light-pulse 2.4s ease-in-out infinite; }
.ws-bubble { position: absolute; top: -26px; left: 50%; transform: translateX(-50%); z-index: 3;
  background: #fff; border: 1px solid #f0f0f0; border-radius: 8px; box-shadow: 0 2px 8px rgba(0,0,0,.35);
  padding: 4px 8px; font-size: 11px; color: #595959; white-space: nowrap; max-width: 190px; overflow: hidden; text-overflow: ellipsis; }
.ws-bubble::after { content: ''; position: absolute; top: 100%; left: 50%; margin-left: -4px;
  border: 4px solid transparent; border-top-color: #fff; }
.ws-nameplate { display: flex; align-items: center; justify-content: center; gap: 5px; font-size: 12px; color: #e6edf7; }
.ws-nameplate .dot { width: 8px; height: 8px; border-radius: 50%; flex-shrink: 0; }
.ws-nameplate .count { color: #8fa3bf; }
.ws-actions { position: absolute; top: 6px; right: 6px; z-index: 4; background: rgba(255,255,255,.95);
  border: 1px solid #f0f0f0; border-radius: 6px; padding: 2px 6px; opacity: 0; transition: opacity .15s;
  box-shadow: 0 2px 8px rgba(0,0,0,.35); font-size: 12px; }
.ws:hover .ws-actions { opacity: 1; }
`;

/** 工位卡座：白色小人 + 状态灯带 + 名牌 + 头顶气泡 + 悬停操作条（billboard 反旋转保持直立） */
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
      <div className="ws-card">
        <div className="ws-char">
          <SpecialistCharacter id={item.id} state={item.state} />
        </div>
        {/* 状态灯带：工作蓝脉动 / 空闲琥珀常亮 / 离线灰熄灭 */}
        <div
          className={`ws-light${working ? ' ws-light-working' : ''}`}
          style={{
            background: tint,
            boxShadow: off ? 'none' : `0 0 10px ${tint}99, 0 0 18px ${tint}55`,
            opacity: off ? 0.28 : undefined,
          }}
        />
        <div className="ws-nameplate">
          <span className="dot" style={{ background: tint }} />
          <span style={{ fontWeight: 500 }}>{item.name}</span>
          <span className="count">今日 {item.today_conversations}</span>
          {item.lifecycle !== 'active' && (
            <Tag color={item.lifecycle === 'disabled' ? 'default' : 'orange'} style={{ marginInlineEnd: 0, fontSize: 11, lineHeight: '16px' }}>
              {item.lifecycle === 'disabled' ? '停用' : '草稿'}
            </Tag>
          )}
        </div>
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
