import { useRef, useState } from 'react';
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
  intern: { color: 'blue', text: '实习' },
  active: { color: 'green', text: '正式' },
  disabled: { color: 'red', text: '停用' },
};

export default function SpecialistList() {
  const actionRef = useRef<ActionType>();
  const [formOpen, setFormOpen] = useState(false);
  const [editing, setEditing] = useState<Specialist | null>(null);
  const { message } = App.useApp();

  const columns: ProColumns<Specialist>[] = [
    { title: '名称', dataIndex: 'name', width: 160 },
    { title: '关联产品', dataIndex: 'product', width: 120 },
    { title: '百炼 App ID', dataIndex: 'app_id', width: 200, ellipsis: true },
    {
      title: '状态', dataIndex: 'status', width: 100,
      render: (_, r) => {
        const s = STATUS_MAP[r.status] || { color: 'default', text: r.status };
        return <Tag color={s.color}>{s.text}</Tag>;
      },
    },
    { title: '今日使用量', dataIndex: 'daily_usage', width: 110, sorter: true },
    { title: '满意度', dataIndex: 'satisfaction', width: 100, sorter: true,
      render: (_, r) => `${r.satisfaction}%` },
    {
      title: '操作', width: 150,
      render: (_, r) => (
        <Space>
          <a onClick={() => { setEditing(r); setFormOpen(true); }}>编辑</a>
          <a style={{ color: r.status === 'active' ? '#ff4d4f' : '#52c41a' }}
             onClick={() => message.info(`${r.status === 'active' ? '停用' : '启用'}操作已提交`)}>
            {r.status === 'active' ? '停用' : '启用'}
          </a>
        </Space>
      ),
    },
  ];

  return (
    <>
      <Row gutter={[16, 16]} style={{ marginBottom: 16 }}>
        <Col span={8}><StatCard title="专员总数" value={12} /></Col>
        <Col span={8}><StatCard title="在线专员" value={10} trend="up" trendValue="1" /></Col>
        <Col span={8}><StatCard title="今日总对话" value={1342} /></Col>
      </Row>
      <ProTable<Specialist>
        headerTitle="数字专员列表"
        actionRef={actionRef}
        columns={columns}
        request={async (params) => {
          const res = await specialistAPI.list({ page: params.current || 1, page_size: params.pageSize || 10 });
          return { data: res.data.data.items, total: res.data.data.total, success: true };
        }}
        rowKey="id"
        search={{ labelWidth: 80 }}
        toolBarRender={() => [
          <Button key="add" type="primary" icon={<PlusOutlined />} onClick={() => { setEditing(null); setFormOpen(true); }}>
            新增专员
          </Button>,
        ]}
      />
      <ModalForm
        title={editing ? '编辑专员' : '新增专员'}
        open={formOpen}
        onOpenChange={setFormOpen}
        onFinish={async () => { message.success(`${editing ? '编辑' : '新增'}成功`); actionRef.current?.reload(); return true; }}
        initialValues={editing || undefined}
      >
        <SpecialistForm />
      </ModalForm>
    </>
  );
}
