import { useCallback, useEffect, useRef, useState } from 'react';
import dayjs from 'dayjs';
import utc from 'dayjs/plugin/utc';
import { ProTable, ModalForm } from '@ant-design/pro-components';

dayjs.extend(utc);
import type { ProColumns, ActionType } from '@ant-design/pro-components';
import { Button, Tag, Space, Row, Col, App, Drawer, Descriptions, Empty, Spin, Segmented, List, Typography } from 'antd';
import { PlusOutlined, BarChartOutlined } from '@ant-design/icons';
import StatCard from '../../components/StatCard';
import SpecialistForm from './SpecialistForm';
import SpecialistOffice from './SpecialistOffice';
import { specialistAPI, type SpecialistFeedback } from '../../services/specialist';
import { STATUS_MAP } from '../../constants/specialist';
import type { Specialist, SpecialistStats } from '../../types';

/** 表单值 → 后端白名单 payload：空值不提交，product_id 转数字 */
function toPayload(values: Record<string, unknown>): Record<string, unknown> {
  const payload: Record<string, unknown> = {};
  for (const [key, value] of Object.entries(values)) {
    if (value === undefined || value === null || value === '') continue;
    payload[key] = key === 'product_id' ? Number(value) : value;
  }
  return payload;
}

/** 专员数据抽屉：使用量 + 满意度 + 反馈明细（需求 2.2.1 专员数据看板） */
function SpecialistDataDrawer({ specialist, onClose }: { specialist: Specialist | null; onClose: () => void }) {
  const [stats, setStats] = useState<SpecialistStats | null>(null);
  const [feedback, setFeedback] = useState<SpecialistFeedback[]>([]);
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    if (!specialist) return;
    setLoading(true);
    setStats(null);
    setFeedback([]);
    specialistAPI.stats(specialist.id)
      .then((res) => setStats(res.data.data))
      .catch(() => setStats(null));
    // 反馈明细（后端 GET /specialists/{id}/feedback，2026-08-12 新增）
    specialistAPI.feedbackList(specialist.id, { page: 1, page_size: 50 })
      .then((res) => setFeedback(res.data.data.items ?? []))
      .catch(() => setFeedback([]))
      .finally(() => setLoading(false));
  }, [specialist]);

  return (
    <Drawer
      title={specialist ? `数据看板：${specialist.name}` : '数据看板'}
      width={560}
      open={!!specialist}
      onClose={onClose}
    >
      {loading ? (
        <div style={{ textAlign: 'center', padding: 60 }}><Spin /></div>
      ) : stats ? (
        <Descriptions column={1} bordered size="small" style={{ marginBottom: 16 }}>
          <Descriptions.Item label="总对话数">{stats.total_conversations}</Descriptions.Item>
          <Descriptions.Item label="反馈总数">{stats.total_feedback}</Descriptions.Item>
          <Descriptions.Item label="满意度">
            {stats.satisfaction_rate == null ? '暂无反馈' : `${stats.satisfaction_rate}%`}
          </Descriptions.Item>
        </Descriptions>
      ) : (
        <Empty description="统计加载失败" style={{ marginBottom: 16 }} />
      )}

      <Typography.Title level={5} style={{ marginTop: 8 }}>
        反馈明细（{feedback.length} 条）
      </Typography.Title>
      {feedback.length === 0 ? (
        <Empty description="暂无反馈记录" style={{ padding: 30 }} />
      ) : (
        <List
          size="small"
          dataSource={feedback}
          renderItem={(item) => (
            <List.Item style={{ alignItems: 'flex-start', padding: '12px 0' }}>
              <List.Item.Meta
                title={
                  <Space>
                    <Tag color={item.rating === 1 ? 'green' : 'red'}>
                      {item.rating === 1 ? '👍 点赞' : '👎 点踩'}
                    </Tag>
                    <span style={{ fontSize: 12, color: '#8c8c8c' }}>
                      {item.created_at ? dayjs.utc(item.created_at).local().format('YYYY-MM-DD HH:mm') : '—'}
                    </span>
                  </Space>
                }
                description={
                  <div style={{ fontSize: 13, lineHeight: 1.7 }}>
                    {item.question ? (
                      <div style={{ color: '#595959' }}>问：{item.question}</div>
                    ) : null}
                    {item.answer ? (
                      <div style={{ color: '#8c8c8c' }}>答：{item.answer.slice(0, 200)}{item.answer.length > 200 ? '…' : ''}</div>
                    ) : null}
                    {item.comment ? <div style={{ color: '#1677ff' }}>评论：{item.comment}</div> : null}
                  </div>
                }
              />
            </List.Item>
          )}
        />
      )}
    </Drawer>
  );
}

export default function SpecialistList() {
  const actionRef = useRef<ActionType>();
  const [formOpen, setFormOpen] = useState(false);
  const [editing, setEditing] = useState<Specialist | null>(null);
  // 聚合卡片：全部/在线 总数（来自列表接口 total，非硬编码假数）
  const [counts, setCounts] = useState<{ total: number; active: number } | null>(null);
  const [dataView, setDataView] = useState<Specialist | null>(null);
  const [view, setView] = useState<'office' | 'table'>('office');
  const { message } = App.useApp();

  const loadCounts = useCallback(async () => {
    try {
      const [all, active] = await Promise.all([
        specialistAPI.list({ page: 1, page_size: 1 }),
        specialistAPI.list({ page: 1, page_size: 1, status: 'active' }),
      ]);
      setCounts({ total: all.data.data.total, active: active.data.data.total });
    } catch {
      setCounts(null); // 卡片拉取失败不阻塞列表
    }
  }, []);

  useEffect(() => {
    loadCounts();
  }, [loadCounts]);

  const toggleStatus = useCallback(async (r: Specialist) => {
    const next = r.status === 'active' ? 'disabled' : 'active';
    try {
      await specialistAPI.update(r.id, { status: next });
      message.success(next === 'disabled' ? '专员已停用' : '专员已启用');
      actionRef.current?.reload();
      loadCounts();
    } catch {
      // 失败 toast 由全局拦截器统一弹，此处不重复弹（避免双弹）
    }
  }, [message, loadCounts]);

  const handleFinish = useCallback(async (values: Record<string, unknown>) => {
    const payload = toPayload(values);
    try {
      if (editing) {
        await specialistAPI.update(editing.id, payload);
        message.success('专员已更新');
      } else {
        await specialistAPI.create(payload);
        message.success('专员已创建');
      }
      setFormOpen(false);
      setEditing(null);
      actionRef.current?.reload();
      loadCounts();
      return true;
    } catch {
      return false; // 保留弹窗让用户修改；失败 toast 由全局拦截器统一弹
    }
  }, [editing, message, loadCounts]);

  const columns: ProColumns<Specialist>[] = [
    { title: '名称', dataIndex: 'name', width: 160 },
    {
      title: '关联产品', dataIndex: 'product_id', width: 120,
      render: (_, r) => r.product_id ?? '未关联',
    },
    {
      title: '百炼 App ID', dataIndex: 'bailian_app_id', width: 200, ellipsis: true,
      render: (_, r) => r.bailian_app_id || '-',
    },
    {
      title: '状态', dataIndex: 'status', width: 100,
      render: (_, r) => {
        const s = STATUS_MAP[r.status] || { color: 'default', text: r.status };
        return <Tag color={s.color}>{s.text}</Tag>;
      },
    },
    {
      title: '创建时间', dataIndex: 'created_at', width: 170,
      // created_at 为 PG UTC 字面 —— UTC 解析转本地，否则恒偏 8h
      render: (_, r) => (r.created_at
        ? dayjs.utc(r.created_at).local().format('YYYY-MM-DD HH:mm')
        : '-'),
    },
    {
      title: '操作', width: 180,
      render: (_, r) => (
        <Space>
          <a onClick={() => { setDataView(r); }}>数据</a>
          <a onClick={() => { setEditing(r); setFormOpen(true); }}>编辑</a>
          <a
            style={{ color: r.status === 'active' ? '#ff4d4f' : '#52c41a' }}
            onClick={() => toggleStatus(r)}
          >
            {r.status === 'active' ? '停用' : '启用'}
          </a>
        </Space>
      ),
    },
  ];

  return (
    <>
      <Row gutter={[16, 16]} style={{ marginBottom: 16 }}>
        <Col span={12}><StatCard title="专员总数" value={counts?.total ?? '—'} /></Col>
        <Col span={12}><StatCard title="在线专员" value={counts?.active ?? '—'} /></Col>
      </Row>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 16 }}>
        <Segmented
          value={view}
          onChange={(v) => setView(v as 'office' | 'table')}
          options={[
            { label: '数字员工办公室', value: 'office' },
            { label: '表格视图', value: 'table' },
          ]}
        />
      </div>
      {view === 'office' ? (
        <SpecialistOffice
          onAdd={() => { setEditing(null); setFormOpen(true); }}
          onEdit={(r) => { setEditing(r); setFormOpen(true); }}
          onToggleStatus={toggleStatus}
          onViewData={(r) => setDataView(r)}
        />
      ) : (
      <ProTable<Specialist>
        headerTitle="数字专员列表"
        actionRef={actionRef}
        columns={columns}
        request={async (params) => {
          const res = await specialistAPI.list({
            page: params.current || 1,
            page_size: params.pageSize || 10,
          });
          return { data: res.data.data.items, total: res.data.data.total, success: true };
        }}
        rowKey="id"
        search={false}
        toolBarRender={() => [
          <Button
            key="add"
            type="primary"
            icon={<PlusOutlined />}
            onClick={() => { setEditing(null); setFormOpen(true); }}
          >
            新增专员
          </Button>,
        ]}
      />
      )}
      <SpecialistDataDrawer specialist={dataView} onClose={() => setDataView(null)} />
      <ModalForm
        title={editing ? '编辑专员' : '新增专员'}
        open={formOpen}
        onOpenChange={setFormOpen}
        onFinish={handleFinish}
        modalProps={{ destroyOnHidden: true }}
        initialValues={editing ? {
          ...editing,
          // null/undefined 直接留空（toPayload 跳过空值），严禁 JSON.stringify 成 '""' 覆盖后端真实人设
          persona: editing.persona == null ? undefined : (
            typeof editing.persona === 'string' ? editing.persona : JSON.stringify(editing.persona)
          ),
          knowledge_scope: editing.knowledge_scope == null ? undefined : (
            typeof editing.knowledge_scope === 'string'
              ? editing.knowledge_scope
              : JSON.stringify(editing.knowledge_scope)
          ),
        } : undefined}
      >
        <SpecialistForm />
      </ModalForm>
    </>
  );
}
