import { useRef, useState } from 'react';
import { ProTable } from '@ant-design/pro-components';
import type { ProColumns, ActionType } from '@ant-design/pro-components';
import { App, Button, Descriptions, Drawer, Input, Radio, Space, Tag, Typography } from 'antd';
import { practiceAPI } from '../../services/practice';
import type { ObjectionScript } from '../../types';

const { Text } = Typography;
const STATUS_MAP: Record<string, { color: string; text: string }> = {
  pending: { color: 'orange', text: '待审核' },
  approved: { color: 'green', text: '已通过' },
  rejected: { color: 'red', text: '已驳回' },
};

/** 异议话术库审核页（3.2(5)）：后端 objection-scripts 三端点早已就绪，此前纯缺 UI
 *  （2026-09-01 审核盲审修复批补齐）。审核人可见 objection_content/response_guidance 全文。 */
export default function ObjectionList() {
  const actionRef = useRef<ActionType>();
  const { message } = App.useApp();
  const [current, setCurrent] = useState<ObjectionScript | null>(null);
  const [verdict, setVerdict] = useState<'approve' | 'reject'>('approve');
  const [reason, setReason] = useState('');
  const [submitting, setSubmitting] = useState(false);

  const openReview = (row: ObjectionScript) => {
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
      await practiceAPI.objectionReview(current.id, {
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

  const columns: ProColumns<ObjectionScript>[] = [
    { title: 'ID', dataIndex: 'id', width: 60, hideInSearch: true },
    { title: '场景类型', dataIndex: 'scenario_type', width: 140 },
    {
      title: '医生异议', dataIndex: 'objection_content', ellipsis: true, hideInSearch: true,
      render: (_, r) => <span style={{ whiteSpace: 'pre-wrap' }}>{r.objection_content}</span>,
    },
    { title: '版本', dataIndex: 'version', width: 80, hideInSearch: true },
    {
      title: '审核状态', dataIndex: 'review_status', width: 100,
      valueEnum: { pending: '待审核', approved: '已通过', rejected: '已驳回' },
      render: (_, r) => {
        const m = STATUS_MAP[r.review_status] || { color: 'default', text: r.review_status };
        return (
          <Tag color={m.color}>
            {m.text}
            {r.review_status === 'rejected' && r.review_reason ? `：${r.review_reason.slice(0, 20)}` : ''}
          </Tag>
        );
      },
    },
    { title: '创建时间', dataIndex: 'created_at', width: 170, hideInSearch: true },
    {
      title: '操作', width: 80,
      render: (_, r) => (r.review_status === 'pending'
        ? <a onClick={() => openReview(r)}>审核</a>
        : <a onClick={() => openReview(r)}>查看</a>),
    },
  ];

  return (
    <>
      <ProTable<ObjectionScript>
        headerTitle="异议话术审核"
        actionRef={actionRef}
        rowKey="id"
        search={{ labelWidth: 80 }}
        columns={columns}
        request={async (params) => {
          const res = await practiceAPI.objectionList({
            page: params.current || 1,
            page_size: params.pageSize || 10,
            review_status: params.review_status,
            scenario_type: params.scenario_type,
          });
          return { data: res.data.data.items, total: res.data.data.total, success: true };
        }}
      />
      <Drawer
        title={current?.review_status === 'pending' ? '异议话术审核' : '异议话术详情'}
        width={520}
        open={!!current}
        onClose={() => setCurrent(null)}
        destroyOnHidden
      >
        {current && (
          <Space direction="vertical" size="middle" style={{ width: '100%' }}>
            <Descriptions column={1} size="small" bordered>
              <Descriptions.Item label="场景类型">{current.scenario_type}</Descriptions.Item>
              <Descriptions.Item label="版本">{current.version || '-'}</Descriptions.Item>
              <Descriptions.Item label="医生异议（原文）">
                <span style={{ whiteSpace: 'pre-wrap' }}>{current.objection_content}</span>
              </Descriptions.Item>
              <Descriptions.Item label="应对指引（原文）">
                <span style={{ whiteSpace: 'pre-wrap' }}>{current.response_guidance || '-'}</span>
              </Descriptions.Item>
              {current.review_status === 'rejected' && current.review_reason && (
                <Descriptions.Item label="驳回原因">{current.review_reason}</Descriptions.Item>
              )}
            </Descriptions>
            {current.review_status === 'pending' && (
              <>
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
              </>
            )}
            {current.review_status !== 'pending' && (
              <Text type="secondary">已处理（{STATUS_MAP[current.review_status]?.text || current.review_status}），仅供查看</Text>
            )}
          </Space>
        )}
      </Drawer>
    </>
  );
}
