import { useRef, useState } from 'react';
import { ProTable, ModalForm, ProFormText } from '@ant-design/pro-components';
import type { ProColumns, ActionType } from '@ant-design/pro-components';
import { App, Button, Input, Modal, Space, Tag } from 'antd';
import { monitorAPI } from '../../services/monitor';
import type { SpecialistMonitor } from '../../types';

const STATUS_TEXT: Record<string, { color: string; text: string }> = {
  active: { color: 'green', text: '工作中' },
  draft: { color: 'default', text: '草稿' },
  disabled: { color: 'orange', text: '已禁用' },
  frozen: { color: 'red', text: '已冻结' },
};
const HEALTH_TEXT: Record<string, { color: string; text: string }> = {
  green: { color: 'green', text: '健康' },
  yellow: { color: 'orange', text: '需关注' },
  red: { color: 'red', text: '高风险' },
};

export default function MonitorList() {
  const actionRef = useRef<ActionType>();
  const { message } = App.useApp();
  const [createOpen, setCreateOpen] = useState(false);

  const columns: ProColumns<SpecialistMonitor>[] = [
    { title: '名称', dataIndex: 'name' },
    { title: '状态', dataIndex: 'status', width: 90, valueEnum: { active: '工作中', draft: '草稿', disabled: '已禁用', frozen: '已冻结' },
      render: (_, r) => { const m = STATUS_TEXT[r.status] || { color: 'default', text: r.status }; return <Tag color={m.color}>{m.text}</Tag>; } },
    { title: '类型', dataIndex: 'is_official', width: 80, hideInSearch: true,
      render: (_, r) => r.is_official ? <Tag color="purple">官方</Tag> : <Tag>个人</Tag> },
    { title: '今日服务', dataIndex: 'today_services', width: 90, hideInSearch: true },
    { title: '平均响应(ms)', dataIndex: 'avg_latency_ms', width: 110, hideInSearch: true },
    { title: '服务医生数', dataIndex: 'service_doctors', width: 100, hideInSearch: true },
    { title: '合规健康度', dataIndex: 'compliance_health', width: 110, hideInSearch: true,
      render: (_, r) => { const m = HEALTH_TEXT[r.compliance_health] || { color: 'default', text: r.compliance_health }; return <Tag color={m.color}>{m.text}</Tag>; } },
    { title: '被添加次数', dataIndex: 'added_count', width: 100, hideInSearch: true },
    {
      title: '操作', width: 160, hideInSearch: true,
      render: (_, r) => (
        <Space>
          {r.status !== 'frozen' ? (
            <Button size="small" danger onClick={() => {
              let reason = '';
              Modal.confirm({
                title: `冻结分身「${r.name}」`,
                content: <Input.TextArea rows={3} placeholder="冻结理由（必填）" onChange={e => (reason = e.target.value)} />,
                onOk: async () => {
                  if (!reason.trim()) { message.warning('请填写冻结理由'); return Promise.reject(); }
                  await monitorAPI.freeze(r.id, reason.trim());
                  message.success('已冻结');
                  actionRef.current?.reload();
                },
              });
            }}>冻结</Button>
          ) : (
            <Button size="small" onClick={async () => { await monitorAPI.unfreeze(r.id); message.success('已解冻'); actionRef.current?.reload(); }}>解冻</Button>
          )}
        </Space>
      ),
    },
  ];

  const handleCreateFinish = async (values: Record<string, unknown>) => {
    try {
      await monitorAPI.createOfficial({
        name: String(values.name),
        product_id: Number(values.product_id),
      });
      message.success('官方分身已创建');
      setCreateOpen(false);
      actionRef.current?.reload();
      return true;
    } catch {
      return false; // 失败 toast 由全局拦截器统一弹
    }
  };

  return (
    <>
      <ProTable<SpecialistMonitor>
        headerTitle="分身监控与官方分身管理"
        actionRef={actionRef}
        rowKey="id"
        search={{ labelWidth: 80 }}
        columns={columns}
        request={async (params) => {
          const res = await monitorAPI.specialistMonitor({
            page: params.current || 1, page_size: params.pageSize || 10,
            status: params.status, official: params.official,
          });
          return { data: res.data.data.items, total: res.data.data.total, success: true };
        }}
        toolBarRender={() => [
          <Button type="primary" key="new" onClick={() => setCreateOpen(true)}>新建官方分身</Button>,
        ]}
      />
      <ModalForm
        title="新建官方分身"
        open={createOpen}
        onOpenChange={setCreateOpen}
        onFinish={handleCreateFinish}
        modalProps={{ destroyOnHidden: true }}
      >
        <ProFormText name="name" label="分身名称" rules={[{ required: true, message: '请输入分身名称' }]} />
        <ProFormText
          name="product_id"
          label="关联产品 ID"
          rules={[{ required: true, message: '请输入产品 ID' }]}
          placeholder="对应产品表的数字 ID"
          fieldProps={{ type: 'number' }}
        />
      </ModalForm>
    </>
  );
}
