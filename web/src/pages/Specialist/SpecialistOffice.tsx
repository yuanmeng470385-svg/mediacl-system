import { useEffect, useRef, useState } from 'react';
import {
  Row, Col, Card, Empty, Spin, Switch, Button, Space, Tag,
} from 'antd';
import {
  RobotOutlined, CoffeeOutlined, PoweroffOutlined,
  PlusOutlined, ReloadOutlined,
} from '@ant-design/icons';
import dayjs from 'dayjs';
import { specialistAPI } from '../../services/specialist';
import { STATUS_MAP } from '../../constants/specialist';
import type { LiveStatus, LiveStatusItem, Specialist } from '../../types';

const STATE_META: Record<LiveStatusItem['state'], { label: string; color: string }> = {
  working: { label: '工作中', color: '#1677ff' },
  idle: { label: '空闲中', color: '#faad14' },
  offline: { label: '离线', color: '#bfbfbf' },
};

const POLL_INTERVAL_MS = 3000;

/** 工位卡片：头像光晕 + 状态区 + 底部统计 + 悬停操作 */
function WorkstationCard({
  item, index, onEdit, onToggleStatus, onViewData,
}: {
  item: LiveStatusItem;
  index: number;
  onEdit: () => void;
  onToggleStatus: () => void;
  onViewData: () => void;
}) {
  const meta = STATE_META[item.state];
  const idle = item.state === 'idle';
  const offline = item.state === 'offline';
  return (
    <Card
      size="small"
      hoverable
      onClick={onViewData}
      style={{
        animationDelay: `${index * 120}ms`,
        borderColor: offline ? '#f0f0f0' : meta.color + '55',
      }}
    >
      <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
        <div
          style={{
            position: 'relative', width: 40, height: 40, borderRadius: 20, flexShrink: 0,
            display: 'flex', alignItems: 'center', justifyContent: 'center',
            background: offline ? '#f5f5f5' : meta.color + '1a',
            boxShadow: offline ? 'none' : `0 0 12px ${meta.color}66`,
            animation: offline ? 'none' : idle ? 'office-float 3s ease-in-out infinite' : 'office-breathe 2s ease-in-out infinite',
          }}
        >
          <RobotOutlined style={{ fontSize: 20, color: offline ? '#bfbfbf' : meta.color }} />
        </div>
        <div style={{ flex: 1, minWidth: 0 }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
            <span style={{ fontWeight: 600, fontSize: 14 }}>{item.name}</span>
            {STATUS_MAP[item.lifecycle] && (
              <Tag color={STATUS_MAP[item.lifecycle].color} style={{ marginInlineEnd: 0 }}>
                {STATUS_MAP[item.lifecycle].text}
              </Tag>
            )}
          </div>
          <div style={{ fontSize: 12, color: meta.color, marginTop: 4, display: 'flex', alignItems: 'center', gap: 6 }}>
            {item.state === 'working' && <Spin size="small" />}
            {item.state === 'idle' && <CoffeeOutlined />}
            {item.state === 'offline' && <PoweroffOutlined />}
            <span style={{ overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
              {item.state === 'working'
                ? item.phase_text ?? '正在工作'
                : meta.label}
            </span>
          </div>
        </div>
      </div>
      {item.state === 'working' && item.question_snippet && (
        <div style={{ marginTop: 8, fontSize: 12, color: '#8c8c8c', lineHeight: 1.5 }}>
          正在回答：{item.question_snippet}…
        </div>
      )}
      <div style={{ marginTop: 8, paddingTop: 8, borderTop: '1px solid #f5f5f5', display: 'flex', justifyContent: 'space-between', fontSize: 12, color: '#8c8c8c' }}>
        <span>今日 {item.today_conversations} 次</span>
        <span>{item.last_active_at ? dayjs(item.last_active_at).format('MM-DD HH:mm') : '从未'}</span>
      </div>
      <div style={{ marginTop: 6 }} onClick={(e) => e.stopPropagation()}>
        <Space size={12}>
          <a onClick={onViewData}>数据</a>
          <a onClick={onEdit}>编辑</a>
          <a style={{ color: item.lifecycle === 'active' ? '#ff4d4f' : '#52c41a' }} onClick={onToggleStatus}>
            {item.lifecycle === 'active' ? '停用' : '启用'}
          </a>
        </Space>
      </div>
    </Card>
  );
}

/** 数字员工办公室：3s 轮询 live-status，卡片化展示每个专员在干什么 */
export default function SpecialistOffice({
  onAdd, onEdit, onToggleStatus, onViewData,
}: {
  onAdd: () => void;
  onEdit: (r: Specialist) => void;
  onToggleStatus: (r: Specialist) => void;
  onViewData: (r: Specialist) => void;
}) {
  const [live, setLive] = useState<LiveStatus | null>(null);
  const [autoPoll, setAutoPoll] = useState(true);
  const [loading, setLoading] = useState(false);
  const timerRef = useRef<number | null>(null);

  const load = async () => {
    try {
      setLoading(true);
      const res = await specialistAPI.liveStatus();
      setLive(res.data.data);
    } catch {
      /* 轮询失败静默，保留上一次数据；卡片按 lifecycle 降级展示 */
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    load();
    if (autoPoll) {
      timerRef.current = window.setInterval(load, POLL_INTERVAL_MS);
    }
    return () => {
      if (timerRef.current !== null) window.clearInterval(timerRef.current);
    };
  }, [autoPoll]);

  const summary = live?.summary ?? { working: 0, idle: 0, offline: 0 };
  const items = live?.items ?? [];

  return (
    <div>
      <style>{`
        @keyframes office-breathe { 0%,100% { transform: scale(1); } 50% { transform: scale(1.08); } }
        @keyframes office-float { 0%,100% { transform: translateY(0); } 50% { transform: translateY(-3px); } }
      `}</style>
      <div style={{ display: 'flex', alignItems: 'center', gap: 16, marginBottom: 16, flexWrap: 'wrap' }}>
        <Space size={8}>
          <Tag color="blue" style={{ marginInlineEnd: 0 }}>工作中 {summary.working}</Tag>
          <Tag color="gold" style={{ marginInlineEnd: 0 }}>空闲 {summary.idle}</Tag>
          <Tag style={{ marginInlineEnd: 0 }}>离线 {summary.offline}</Tag>
        </Space>
        <span style={{ fontSize: 12, color: '#8c8c8c' }}>3s 自动刷新</span>
        <Switch size="small" checked={autoPoll} onChange={setAutoPoll} />
        <Button size="small" icon={<ReloadOutlined />} loading={loading} onClick={load}>刷新</Button>
        <Button type="primary" size="small" icon={<PlusOutlined />} onClick={onAdd}>新增专员</Button>
      </div>
      {items.length === 0 ? (
        <Empty description="暂无数字专员，点击右上角「新增专员」创建" style={{ padding: 60 }} />
      ) : (
        <Row gutter={[16, 16]}>
          {items.map((item, index) => (
            <Col key={item.id} xs={12} sm={8} lg={6}>
              <WorkstationCard
                item={item}
                index={index}
                onEdit={() => {
                  const sp = items.find((i) => i.id === item.id);
                  if (sp) onEdit({ ...sp, created_at: '' } as unknown as Specialist);
                }}
                onToggleStatus={() => {
                  const sp = items.find((i) => i.id === item.id);
                  if (sp) onToggleStatus({ ...sp, created_at: '' } as unknown as Specialist);
                }}
                onViewData={() => {
                  const sp = items.find((i) => i.id === item.id);
                  if (sp) onViewData({ ...sp, created_at: '' } as unknown as Specialist);
                }}
              />
            </Col>
          ))}
        </Row>
      )}
    </div>
  );
}
