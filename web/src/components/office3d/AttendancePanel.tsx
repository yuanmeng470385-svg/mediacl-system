import dayjs from 'dayjs';
import utc from 'dayjs/plugin/utc';
import { Button, Empty, Progress } from 'antd';
import { PlusOutlined } from '@ant-design/icons';
import { MiniCharacter, STATE_TINTS } from '../office/SpecialistCharacter';
import { stateText } from './labels';
import type { LiveStatusItem } from '../../types';

dayjs.extend(utc);

const CSS = `
.att-panel { background: #fafafa; border: 1px solid #f0f0f0; border-radius: 12px; padding: 14px 12px; }
.att-title { font-weight: 600; font-size: 14px; margin-bottom: 6px; }
.att-rate-wrap { text-align: center; }
.att-rate { font-size: 20px; font-weight: 600; }
.att-stats { margin-top: 10px; display: flex; flex-direction: column; gap: 6px; font-size: 13px; color: #595959; }
.att-stats .dot { width: 8px; height: 8px; border-radius: 50%; display: inline-block; margin-right: 6px; }
.att-today { margin-top: 4px; color: #8c8c8c; font-size: 12px; }
.att-list { margin-top: 10px; max-height: 320px; overflow-y: auto; display: flex; flex-direction: column; gap: 4px; }
.att-row { display: flex; align-items: center; gap: 8px; padding: 6px 8px; border-radius: 8px; cursor: pointer; }
.att-row:hover { background: #f0f0f0; }
.att-row.sel { background: #e8f1ff; outline: 1px solid #91caff; }
.att-row-main { flex: 1; min-width: 0; }
.att-row-name { font-size: 13px; font-weight: 500; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.att-row-st { font-size: 11px; color: #8c8c8c; }
`;

function relTime(iso: string | null): string {
  if (!iso) return '从未';
  // 后端存 UTC 字面（无时区后缀）—— 按 UTC 解析再转本地，否则相对时间恒偏 8h
  const ms = Date.now() - dayjs.utc(iso).valueOf();
  if (ms < 0) return '刚刚';
  const min = Math.floor(ms / 60000);
  if (min < 1) return '刚刚';
  if (min < 60) return `${min} 分钟前`;
  const h = Math.floor(min / 60);
  if (h < 24) return `${h} 小时前`;
  return `${Math.floor(h / 24)} 天前`;
}

/** 团队出勤面板：出勤率环形 + 状态分布 + 今日对话 + 在岗明细（与 3D 场景双向联动） */
export default function AttendancePanel({
  items, selectedId, onSelect, onAdd,
}: {
  items: LiveStatusItem[];
  selectedId: number | null;
  onSelect: (id: number | null) => void;
  onAdd: () => void;
}) {
  const total = items.length;
  const working = items.filter((i) => i.state === 'working').length;
  const idle = items.filter((i) => i.state === 'idle').length;
  const offline = total - working - idle;
  const rate = total ? Math.round(((working + idle) / total) * 100) : 0;
  const todayTotal = items.reduce((s, i) => s + i.today_conversations, 0);
  const todayAvg = total ? todayTotal / total : 0;

  return (
    <div className="att-panel">
      <style>{CSS}</style>
      <div className="att-title">团队出勤</div>
      {total === 0 ? (
        <Empty description="暂无数字专员" styles={{ image: { height: 60 } }}>
          <Button type="primary" size="small" icon={<PlusOutlined />} onClick={onAdd}>新增专员</Button>
        </Empty>
      ) : (
        <>
          <div className="att-rate-wrap">
            <Progress
              type="dashboard"
              percent={rate}
              size={140}
              strokeColor={{ '0%': '#1677ff', '100%': '#58a6ff' }}
              format={(p) => <span className="att-rate">{p}%</span>}
            />
          </div>
          <div className="att-stats">
            <div><span className="dot" style={{ background: STATE_TINTS.working }} />工作中 <b>{working}</b></div>
            <div><span className="dot" style={{ background: STATE_TINTS.idle }} />空闲 <b>{idle}</b></div>
            <div><span className="dot" style={{ background: STATE_TINTS.offline }} />离线 <b>{offline}</b></div>
            <div className="att-today">今日对话 {todayTotal} · 人均 {todayAvg.toFixed(1)}</div>
          </div>
          <div className="att-list">
            {items.map((it) => (
              <div
                key={it.id}
                className={`att-row${selectedId === it.id ? ' sel' : ''}`}
                onClick={() => onSelect(selectedId === it.id ? null : it.id)}
              >
                <MiniCharacter id={it.id} state={it.state} size={26} />
                <div className="att-row-main">
                  <div className="att-row-name">{it.name}</div>
                  <div className="att-row-st">{stateText(it)} · 今日 {it.today_conversations} · {relTime(it.last_active_at)}</div>
                </div>
                <span style={{ width: 8, height: 8, borderRadius: '50%', background: STATE_TINTS[it.state], flexShrink: 0 }} />
              </div>
            ))}
          </div>
        </>
      )}
    </div>
  );
}
