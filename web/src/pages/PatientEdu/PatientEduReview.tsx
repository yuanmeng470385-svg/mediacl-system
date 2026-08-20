import { useRef, useState } from 'react';
import { ProTable } from '@ant-design/pro-components';
import type { ProColumns, ActionType } from '@ant-design/pro-components';
import { App, Button, Descriptions, Drawer, Input, Radio, Space, Tag } from 'antd';
import { patientEduAPI } from '../../services/patientEdu';
import type { EduContentRecord } from '../../types';

export default function PatientEduReview() {
  const actionRef = useRef<ActionType>();
  const { message } = App.useApp();
  const [current, setCurrent] = useState<EduContentRecord | null>(null);
  const [verdict, setVerdict] = useState<'approve' | 'reject'>('approve');
  const [reason, setReason] = useState('');
  const [submitting, setSubmitting] = useState(false);

  const openReview = (row: EduContentRecord) => {
    setCurrent(row);
    setVerdict('approve');
    setReason('');
  };

  const submitReview = async () => {
    if (!current) return;
    if (verdict === 'reject' && !reason.trim()) {
      message.warning('驳回必须填写原因');
      return;
    }
    setSubmitting(true);
    try {
      await patientEduAPI.reviewRecord(current.id, {
        verdict,
        reason: verdict === 'reject' ? reason.trim() : undefined,
      });
      message.success('审核完成');
      setCurrent(null);
      actionRef.current?.reload();
    } catch {
      /* client.ts 拦截器已弹错误 */
    } finally {
      setSubmitting(false);
    }
  };

  const columns: ProColumns<EduContentRecord>[] = [
    { title: '标题', dataIndex: ['content', 'title'] },
    { title: '发布医生', dataIndex: 'doctor_name', width: 120, render: (_, r) => r.doctor_name || '-' },
    {
      title: 'AI 生成', dataIndex: 'is_ai_generated', width: 100,
      render: (_, r) => (r.is_ai_generated ? <Tag color="blue">AI 生成</Tag> : <Tag>人工</Tag>),
    },
    { title: '提交时间', dataIndex: 'created_at', width: 180, hideInSearch: true },
    {
      title: '操作', width: 80,
      render: (_, r) => (r.audit_status === 'pending'
        ? <a onClick={() => openReview(r)}>审核</a>
        : <span style={{ color: '#999' }}>已处理</span>),
    },
  ];

  return (
    <>
      <ProTable<EduContentRecord>
        headerTitle="患教内容审核"
        actionRef={actionRef}
        rowKey="id"
        search={false}
        columns={columns}
        request={async (params) => {
          const res = await patientEduAPI.reviewQueue({ page: params.current || 1, page_size: params.pageSize || 10 });
          return { data: res.data.data.items, total: res.data.data.total, success: true };
        }}
      />
      <Drawer title="患教内容审核" width={520} open={!!current} onClose={() => setCurrent(null)} destroyOnHidden>
        {current && (
          <Space direction="vertical" size="middle" style={{ width: '100%' }}>
            <Descriptions column={1} size="small" bordered>
              <Descriptions.Item label="标题">{current.content.title}</Descriptions.Item>
              <Descriptions.Item label="正文"><span style={{ whiteSpace: 'pre-wrap' }}>{current.content.body}</span></Descriptions.Item>
              <Descriptions.Item label="注意事项"><span style={{ whiteSpace: 'pre-wrap' }}>{current.content.notes}</span></Descriptions.Item>
              <Descriptions.Item label="就医提示"><span style={{ whiteSpace: 'pre-wrap' }}>{current.content.seek_care}</span></Descriptions.Item>
            </Descriptions>
            <Radio.Group value={verdict} onChange={(e) => setVerdict(e.target.value)}>
              <Radio.Button value="approve">通过</Radio.Button>
              <Radio.Button value="reject">驳回</Radio.Button>
            </Radio.Group>
            {verdict === 'reject' && (
              <Input.TextArea
                rows={3}
                placeholder="驳回原因（必填）"
                value={reason}
                onChange={(e) => setReason(e.target.value)}
                maxLength={500}
              />
            )}
            <Button type="primary" block loading={submitting} onClick={submitReview}>提交审核</Button>
          </Space>
        )}
      </Drawer>
    </>
  );
}
