import { useCallback, useEffect, useRef, useState } from 'react';
import { ProTable, ModalForm } from '@ant-design/pro-components';
import type { ProColumns, ActionType } from '@ant-design/pro-components';
import { Button, Tag, Space, Row, Col, App } from 'antd';
import { PlusOutlined } from '@ant-design/icons';
import StatCard from '../../components/StatCard';
import SpecialistForm from './SpecialistForm';
import { specialistAPI } from '../../services/specialist';
import type { Specialist } from '../../types';

const STATUS_MAP: Record<string, { color: string; text: string }> = {
  draft: { color: 'default', text: '草稿' },
  active: { color: 'green', text: '正式' },
  disabled: { color: 'red', text: '停用' },
};

/** axios 错误里取后端 message（ParamError 400 / 404 / 403 均带 message） */
function errMsg(err: unknown, fallback: string): string {
  const resp = (err as { response?: { data?: { message?: string } } })?.response;
  return resp?.data?.message || fallback;
}

/** 表单值 → 后端白名单 payload：空值不提交，product_id 转数字 */
function toPayload(values: Record<string, unknown>): Record<string, unknown> {
  const payload: Record<string, unknown> = {};
  for (const [key, value] of Object.entries(values)) {
    if (value === undefined || value === null || value === '') continue;
    payload[key] = key === 'product_id' ? Number(value) : value;
  }
  return payload;
}

export default function SpecialistList() {
  const actionRef = useRef<ActionType>();
  const [formOpen, setFormOpen] = useState(false);
  const [editing, setEditing] = useState<Specialist | null>(null);
  // 聚合卡片：全部/在线 总数（来自列表接口 total，非硬编码假数）
  const [counts, setCounts] = useState<{ total: number; active: number } | null>(null);
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
    } catch (err) {
      message.error(errMsg(err, '状态更新失败'));
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
    } catch (err) {
      message.error(errMsg(err, '保存失败'));
      return false; // 保留弹窗让用户修改
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
    { title: '创建时间', dataIndex: 'created_at', width: 170 },
    {
      title: '操作', width: 150,
      render: (_, r) => (
        <Space>
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
      <ModalForm
        title={editing ? '编辑专员' : '新增专员'}
        open={formOpen}
        onOpenChange={setFormOpen}
        onFinish={handleFinish}
        modalProps={{ destroyOnHidden: true }}
        initialValues={editing ? {
          ...editing,
          persona: typeof editing.persona === 'string' ? editing.persona : JSON.stringify(editing.persona ?? ''),
          knowledge_scope: typeof editing.knowledge_scope === 'string'
            ? editing.knowledge_scope
            : JSON.stringify(editing.knowledge_scope ?? ''),
        } : undefined}
      >
        <SpecialistForm />
      </ModalForm>
    </>
  );
}
