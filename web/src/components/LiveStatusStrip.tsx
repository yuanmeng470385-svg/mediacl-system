import { useEffect, useRef, useState } from 'react';
import { Tooltip } from 'antd';
import { ArrowRightOutlined } from '@ant-design/icons';
import { MiniCharacter } from './office/SpecialistCharacter';
import { useNavigate } from 'react-router-dom';
import { specialistAPI } from '../services/specialist';
import type { LiveStatus, LiveStatusItem } from '../types';

const MAX_STATIONS = 8;
const POLL_INTERVAL_MS = 5000;

const STATE_COLOR: Record<LiveStatusItem['state'], string> = {
  working: '#1677ff',
  idle: '#faad14',
  offline: '#bfbfbf',
};

/** 仪表盘顶部「数字员工实时状态」条：迷你工位 + 汇总 + 跳转 */
export default function LiveStatusStrip() {
  const [live, setLive] = useState<LiveStatus | null>(null);
  const timerRef = useRef<number | null>(null);
  const navigate = useNavigate();

  useEffect(() => {
    const load = async () => {
      try {
        const res = await specialistAPI.liveStatus();
        setLive(res.data.data);
      } catch {
        /* 静默：接口不可达时隐藏状态条 */
      }
    };
    load();
    timerRef.current = window.setInterval(load, POLL_INTERVAL_MS);
    return () => {
      if (timerRef.current !== null) window.clearInterval(timerRef.current);
    };
  }, []);

  if (!live) return null;
  const { items, summary } = live;
  const shown = items.slice(0, MAX_STATIONS);
  const rest = items.length - shown.length;

  return (
    <div style={{
      display: 'flex', alignItems: 'center', gap: 12, marginBottom: 16,
      padding: '10px 16px', background: '#fafafa', borderRadius: 8,
      border: '1px solid #f0f0f0', fontSize: 13,
    }}>
      <span style={{ fontWeight: 600, flexShrink: 0 }}>数字员工</span>
      <div style={{ display: 'flex', alignItems: 'center', gap: 6, flex: 1, flexWrap: 'wrap' }}>
        {shown.map((item) => (
          <Tooltip
            key={item.id}
            title={`${item.name} · ${item.phase_text ?? (item.state === 'working' ? '工作中' : item.state === 'idle' ? '空闲中' : '离线')}${item.question_snippet ? ` · ${item.question_snippet}` : ''}`}
          >
            <span
              onClick={() => navigate('/specialist/list')}
              style={{
                display: 'inline-flex', alignItems: 'center', gap: 5, cursor: 'pointer',
                padding: '2px 8px', borderRadius: 12, background: '#fff',
                border: `1px solid ${STATE_COLOR[item.state]}44`,
              }}
            >
              <MiniCharacter id={item.id} state={item.state} />
              <span style={{ width: 8, height: 8, borderRadius: '50%', background: STATE_COLOR[item.state], flexShrink: 0 }} />
              {item.name}
            </span>
          </Tooltip>
        ))}
        {rest > 0 && <span style={{ color: '#8c8c8c' }}>+{rest}</span>}
      </div>
      <span style={{ color: '#8c8c8c', flexShrink: 0 }}>
        工作中 {summary.working} · 空闲 {summary.idle} · 离线 {summary.offline}
      </span>
      <a style={{ flexShrink: 0 }} onClick={() => navigate('/specialist/list')}>
        查看全部 <ArrowRightOutlined />
      </a>
    </div>
  );
}
