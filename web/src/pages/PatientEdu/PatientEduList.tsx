import { useRef, useState } from 'react';
import { ProTable, ModalForm, ProFormText, ProFormTextArea, ProFormSelect } from '@ant-design/pro-components';
import type { ProColumns, ActionType } from '@ant-design/pro-components';
import { App, Button, Drawer, Input, Radio, Space, Tag } from 'antd';
import { patientEduAPI } from '../../services/patientEdu';
import type { PatientEduTemplate } from '../../types';

const STATUS_MAP: Record<string, { color: string; text: string }> = {
  pending: { color: 'orange', text: '待审核' },
  approved: { color: 'green', text: '已通过' },
  rejected: { color: 'red', text: '已驳回' },
};

export default function PatientEduList() {
  const actionRef = useRef<ActionType>();
  const { message } = App.useApp();
  const [current, setCurrent] = useState<PatientEduTemplate | null>(null);
  const [verdict, setVerdict] = useState<'approve' | 'reject'>('approve');
  const [reason, setReason] = useState('');
  const [createOpen, setCreateOpen] = useState(false);

  const columns: ProColumns<PatientEduTemplate>[] = [
    { title: '标题', dataIndex: 'title' },
    { title: '疾病领域', dataIndex: 'disease_area', width: 100,
      valueEnum: { 心血管: '心血管', 肿瘤: '肿瘤', 内分泌: '内分泌', 呼吸: '呼吸', 神经: '神经' } },
    { title: '审核状态', dataIndex: 'review_status', width: 100,
      valueEnum: { pending: '待审核', approved: '已通过', rejected: '已驳回' },
      render: (_, r) => { const m = STATUS_MAP[r.review_status] || { color: 'default', text: r.review_status }; return <Tag color={m.color}>{m.text}</Tag>; } },
    { title: '操作', width: 80, render: (_, r) => r.review_status === 'pending' ? <a onClick={() => { setCurrent(r); setVerdict('approve'); setReason(''); }}>审核</a> : <span style={{ color: '#999' }}>已处理</span> },
  ];

  return (
    <>
      <ProTable<PatientEduTemplate>
        headerTitle="患教模板库"
        actionRef={actionRef}
        rowKey="id"
        search={{ labelWidth: 80 }}
        columns={columns}
        request={async (params) => {
          const res = await patientEduAPI.list({ page: params.current || 1, page_size: params.pageSize || 10, disease_area: params.disease_area });
          return { data: res.data.data.items, total: res.data.data.total, success: true };
        }}
        toolBarRender={() => [<Button type="primary" key="new" onClick={() => setCreateOpen(true)}>新建患教模板</Button>]}
      />
      <ModalForm title="新建患教模板" open={createOpen} onOpenChange={setCreateOpen}
        onFinish={async (values) => {
          await patientEduAPI.create({ title: values.title, disease_area: values.disease_area, content: values.content });
          message.success('已创建，待审核');
          setCreateOpen(false);
          actionRef.current?.reload();
          return true;
        }}>
        <ProFormText name="title" label="标题" rules={[{ required: true }]} />
        <ProFormSelect name="disease_area" label="疾病领域" rules={[{ required: true }]}
          options={[{ value: '心血管', label: '心血管' }, { value: '肿瘤', label: '肿瘤' }, { value: '内分泌', label: '内分泌' }, { value: '呼吸', label: '呼吸' }, { value: '神经', label: '神经' }]} />
        <ProFormTextArea name="content" label="模板正文" rules={[{ required: true }]} rows={6} />
      </ModalForm>
      <Drawer title="患教模板审核" width={480} open={!!current} onClose={() => setCurrent(null)} destroyOnHidden>
        {current && (
          <Space direction="vertical" size="middle" style={{ width: '100%' }}>
            <p><strong>{current.title}</strong>（{current.disease_area}）</p>
            <p style={{ whiteSpace: 'pre-wrap' }}>{current.content}</p>
            <Radio.Group value={verdict} onChange={(e) => setVerdict(e.target.value)}>
              <Radio.Button value="approve">通过</Radio.Button>
              <Radio.Button value="reject">驳回</Radio.Button>
            </Radio.Group>
            {verdict === 'reject' && <Input.TextArea rows={3} placeholder="驳回原因（必填）" value={reason} onChange={(e) => setReason(e.target.value)} />}
            <Button type="primary" block onClick={async () => {
              if (verdict === 'reject' && !reason.trim()) { message.warning('驳回必须填原因'); return; }
              await patientEduAPI.review(current.id, { verdict, reason: verdict === 'reject' ? reason.trim() : undefined });
              message.success('审核完成');
              setCurrent(null);
              actionRef.current?.reload();
            }}>提交审核</Button>
          </Space>
        )}
      </Drawer>
    </>
  );
}
