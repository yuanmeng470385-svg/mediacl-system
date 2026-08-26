import { useRef, useState } from 'react';
import { ProTable, ModalForm, ProFormText } from '@ant-design/pro-components';
import type { ProColumns, ActionType } from '@ant-design/pro-components';
import { App, Button, Descriptions, Drawer, Input, Radio, Space, Tag } from 'antd';
import { privacyAPI } from '../../services/privacy';
import type { PrivacyRequest } from '../../types';

const TYPE_MAP: Record<string, { color: string; text: string }> = {
  view: { color: 'default', text: '查阅' },
  correct: { color: 'blue', text: '更正' },
  delete: { color: 'orange', text: '删除' },
  export: { color: 'purple', text: '导出' },
  account_delete: { color: 'red', text: '注销' },
};

const STATUS_MAP: Record<string, { color: string; text: string }> = {
  pending: { color: 'orange', text: '待处理' },
  processing: { color: 'blue', text: '处理中' },
  done: { color: 'green', text: '已完成' },
  rejected: { color: 'red', text: '已驳回' },
};

export default function PrivacyRequests() {
  const actionRef = useRef<ActionType>();
  const { message } = App.useApp();
  const [current, setCurrent] = useState<PrivacyRequest | null>(null);
  const [detail, setDetail] = useState<PrivacyRequest | null>(null);
  const [action, setAction] = useState<'processing' | 'done' | 'rejected'>('done');
  const [response, setResponse] = useState('');
  const [submitting, setSubmitting] = useState(false);

  const openHandle = (row: PrivacyRequest) => {
    setCurrent(row);
    setAction('done');
    setResponse('');
  };

  const submitHandle = async () => {
    if (!current) return;
    if (action !== 'processing' && !response.trim()) {
      message.warning('完成/驳回必须填写回复');
      return;
    }
    setSubmitting(true);
    try {
      await privacyAPI.handle(current.id, { action, response });
      message.success('处理成功');
      setCurrent(null);
      actionRef.current?.reload();
    } catch {
      /* HTTP 错误已由全局拦截器统一弹 toast，此处不重复弹 */
    } finally {
      setSubmitting(false);
    }
  };

  const columns: ProColumns<PrivacyRequest>[] = [
    { title: '编号', dataIndex: 'id', width: 60, search: false },
    { title: '医生', dataIndex: 'doctor_name', search: false },
    {
      title: '类型',
      dataIndex: 'request_type',
      valueType: 'select',
      valueEnum: Object.fromEntries(
        Object.entries(TYPE_MAP).map(([k, v]) => [k, { text: v.text }]),
      ),
      render: (_, row) => <Tag color={TYPE_MAP[row.request_type]?.color}>{TYPE_MAP[row.request_type]?.text ?? row.request_type}</Tag>,
    },
    {
      title: '状态',
      dataIndex: 'status',
      valueType: 'select',
      valueEnum: Object.fromEntries(
        Object.entries(STATUS_MAP).map(([k, v]) => [k, { text: v.text }]),
      ),
      render: (_, row) => (
        <Space size={4}>
          <Tag color={STATUS_MAP[row.status]?.color}>{STATUS_MAP[row.status]?.text ?? row.status}</Tag>
          {row.sla_overdue && <Tag color="red">办理超时</Tag>}
        </Space>
      ),
    },
    {
      title: '申请说明',
      dataIndex: ['content', 'detail'],
      ellipsis: true,
      search: false,
    },
    { title: '申请时间', dataIndex: 'created_at', search: false, width: 170 },
    { title: '办理时限', dataIndex: 'sla_deadline', search: false, width: 170 },
    {
      title: '操作',
      valueType: 'option',
      render: (_, row) => [
        <a key="detail" onClick={() => setDetail(row)}>详情</a>,
        ...(row.status === 'pending' || row.status === 'processing'
          ? [<a key="handle" onClick={() => openHandle(row)}>处理</a>]
          : []),
      ],
    },
  ];

  return (
    <>
      <ProTable<PrivacyRequest>
        headerTitle="隐私请求处理"
        rowKey="id"
        actionRef={actionRef}
        columns={columns}
        search={{ labelWidth: 'auto' }}
        request={async (params) => {
          const res = await privacyAPI.list({
            page: params.current,
            page_size: params.pageSize,
            status: params.status,
            request_type: params.request_type,
          });
          return { data: res.data.data.items, total: res.data.data.total, success: true };
        }}
      />
      <Drawer
        open={!!detail}
        title={`请求 #${detail?.id ?? ''}`}
        width={480}
        onClose={() => setDetail(null)}
      >
        {detail && (
          <Descriptions column={1} size="small" bordered>
            <Descriptions.Item label="医生">{detail.doctor_name ?? detail.doctor_id}</Descriptions.Item>
            <Descriptions.Item label="类型">{TYPE_MAP[detail.request_type]?.text}</Descriptions.Item>
            <Descriptions.Item label="状态">{STATUS_MAP[detail.status]?.text}</Descriptions.Item>
            <Descriptions.Item label="申请说明">{detail.content?.detail || '—'}</Descriptions.Item>
            {detail.content?.fields && (detail.content.fields.full_name || detail.content.fields.phone) && (
              <Descriptions.Item label="待更正字段">
                {detail.content.fields.full_name && <>姓名 → {detail.content.fields.full_name}<br /></>}
                {detail.content.fields.phone && <>手机号 → {detail.content.fields.phone}</>}
              </Descriptions.Item>
            )}
            <Descriptions.Item label="办理时限">{detail.sla_deadline ?? '—'}</Descriptions.Item>
            <Descriptions.Item label="处理回复">{detail.content?.response || '—'}</Descriptions.Item>
            <Descriptions.Item label="数据包">{detail.file_url || '—'}</Descriptions.Item>
          </Descriptions>
        )}
      </Drawer>
      <ModalForm
        title={`处理请求 #${current?.id ?? ''}（${current ? TYPE_MAP[current.request_type]?.text : ''}）`}
        open={!!current}
        onFinish={async () => {
          await submitHandle();
          return false; /* 成功时由 submitHandle 关闭，返回 false 阻止自动关 */
        }}
        modalProps={{ onCancel: () => setCurrent(null), confirmLoading: submitting }}
      >
        <Radio.Group
          value={action}
          onChange={(e) => setAction(e.target.value)}
          options={[
            { value: 'done', label: '完成（落地执行）' },
            { value: 'rejected', label: '驳回' },
            { value: 'processing', label: '标记处理中' },
          ]}
        />
        <Input.TextArea
          rows={3}
          maxLength={500}
          value={response}
          onChange={(e) => setResponse(e.target.value)}
          placeholder={
            action === 'done'
              ? '处理回复（必填）：更正已生效 / 数据包已生成，线下交付 / 已注销去标识化…'
              : action === 'rejected'
                ? '驳回原因（必填）：依法须留存 / 信息不符…'
                : '备注（可选）：已联系医生核实中…'
          }
          style={{ marginTop: 12 }}
        />
      </ModalForm>
    </>
  );
}
