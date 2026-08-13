import { useEffect, useRef, useState } from 'react';
import {
  Tag, Switch, Button, Space, Flex,
} from 'antd';
import { PlusOutlined, ReloadOutlined } from '@ant-design/icons';
import { specialistAPI } from '../../services/specialist';
import OfficeScene3D from '../../components/office3d/OfficeScene3D';
import AttendancePanel from '../../components/office3d/AttendancePanel';
import type { LiveStatus, LiveStatusItem, Specialist } from '../../types';

const POLL_INTERVAL_MS = 3000;

/** live 条目 → Specialist：live 用 lifecycle、Specialist 用 status，映射补 status 供父组件 toggleStatus 判定 */
function toSpecialist(sp: LiveStatusItem): Specialist {
  return { ...sp, created_at: '', status: sp.lifecycle } as unknown as Specialist;
}

/** 数字员工办公室：3s 轮询 live-status，3D 动态场景 + 团队出勤面板 */
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
  const [selectedId, setSelectedId] = useState<number | null>(null);
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

  // 清理失效选中（T6 评审结论）：items 变化后 selectedId 指向的专员不在当前列表时置空，
  // 避免 3D 相机持续悬停在已删除/下线的专员上
  useEffect(() => {
    setSelectedId((cur) => (cur === null || items.some((i) => i.id === cur) ? cur : null));
  }, [items]);

  return (
    <div>
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
      <Flex gap={16} align="flex-start">
        <div style={{ width: 280, flexShrink: 0 }}>
          <AttendancePanel items={items} selectedId={selectedId} onSelect={setSelectedId} onAdd={onAdd} />
        </div>
        <div style={{ flex: 1, minWidth: 0 }}>
          <OfficeScene3D
            items={items}
            selectedId={selectedId}
            onSelect={setSelectedId}
            onAdd={onAdd}
            onEdit={async (item) => {
              // live 数据无 persona/knowledge_scope 等字段，必须先拉全量记录再进编辑表单，
              // 否则表单会把空值 JSON 序列化提交，覆盖真实人设（既有 Critical 修复，必须保留）
              try {
                const res = await specialistAPI.detail(item.id);
                onEdit(res.data.data);
              } catch {
                // 失败 toast 由全局拦截器统一弹，此处不重复弹（避免双弹）
              }
            }}
            onToggleStatus={(item) => onToggleStatus(toSpecialist(item))}
            onViewData={(item) => onViewData(toSpecialist(item))}
          />
        </div>
      </Flex>
    </div>
  );
}
