import { useRef, useState } from 'react';
import { ProTable } from '@ant-design/pro-components';
import type { ProColumns, ActionType } from '@ant-design/pro-components';
import { App, Button, DatePicker, Descriptions, Drawer, Input, Radio, Space, Tag } from 'antd';
import dayjs, { Dayjs } from 'dayjs';
import { filingAPI } from '../../services/filing';
import type { Qualification } from '../../types';

const AUDIT_MAP: Record<string, { color: string; text: string }> = {
  pending: { color: 'orange', text: '待审核' },
  approved: { color: 'green', text: '已通过' },
  rejected: { color: 'red', text: '已驳回' },
};
const FILING_MAP: Record<string, { color: string; text: string }> = {
  valid: { color: 'green', text: '有效' },
  expired: { color: 'red', text: '已过期' },
  not_filed: { color: 'default', text: '未备案' },
};

export default function FilingList() {
  const actionRef = useRef<ActionType>();
  const [current, setCurrent] = useState<Qualification | null>(null);
  const [verdict, setVerdict] = useState<'approve' | 'reject'>('approve');
  const [reason, setReason] = useState('');
  const [expireDate, setExpireDate] = useState<Dayjs | null>(null);
  const [submitting, setSubmitting] = useState(false);
  const { message } = App.useApp();

  const openDrawer = (row: Qualification) => {
    setCurrent(row);
    setVerdict('approve');
    setReason('');
    setExpireDate(row.filing_expire_date ? dayjs(row.filing_expire_date) : null);
  };

  const submitReview = async () => {
    if (!current) return;
    if (verdict === 'reject' && !reason.trim()) {
      message.warning('驳回必须填写原因');
      return;
    }
    setSubmitting(true);
    try {
      await filingAPI.review(current.id, {
        verdict,
        reason: verdict === 'reject' ? reason.trim() : undefined,
        filing_expire_date: expireDate ? expireDate.format('YYYY-MM-DD') : undefined,
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

  const columns: ProColumns<Qualification>[] = [
    { title: '代表', dataIndex: 'rep_name', width: 120 },
    { title: '手机号', dataIndex: 'rep_phone', width: 130 },
    { title: '备案号', dataIndex: 'filing_number', width: 160 },
    {
      title: '备案状态', dataIndex: 'filing_status', width: 90,
      valueEnum: { valid: '有效', expired: '已过期', not_filed: '未备案' },
      render: (_, r) => {
        const m = FILING_MAP[r.filing_status] || { color: 'default', text: r.filing_status };
        return <Tag color={m.color}>{m.text}</Tag>;
      },
    },
    {
      title: '备案有效期', dataIndex: 'filing_expire_date', width: 160,
      render: (_, r) => {
        if (!r.filing_expire_date) return '—';
        const d = r.days_until_expiry;
        const expiring = d !== null && d !== undefined && d <= 90 && d > 0;
        return (
          <span>
            {r.filing_expire_date}
            {expiring && <Tag color="red" style={{ marginLeft: 8 }}>{d} 天后到期</Tag>}
          </span>
        );
      },
    },
    {
      title: '资质审核', dataIndex: 'audit_status', width: 100,
      valueEnum: { pending: '待审核', approved: '已通过', rejected: '已驳回' },
      render: (_, r) => {
        const m = AUDIT_MAP[r.audit_status] || { color: 'default', text: r.audit_status };
        return <Tag color={m.color}>{m.text}</Tag>;
      },
    },
    {
      title: '操作', width: 80,
      render: (_, r) => <a onClick={() => openDrawer(r)}>审核</a>,
    },
  ];

  return (
    <>
      <ProTable<Qualification>
        headerTitle="备案管理"
        actionRef={actionRef}
        columns={columns}
        rowKey="id"
        search={{ labelWidth: 90 }}
        request={async (params) => {
          const res = await filingAPI.list({
            page: params.current || 1,
            page_size: params.pageSize || 10,
            audit_status: params.audit_status,
            filing_status: params.filing_status,
            keyword: params.keyword,
          });
          return { data: res.data.data.items, total: res.data.data.total, success: true };
        }}
      />
      <Drawer
        title="备案与资质审核"
        width={480}
        open={!!current}
        onClose={() => setCurrent(null)}
        destroyOnHidden
      >
        {current && (
          <Space direction="vertical" size="middle" style={{ width: '100%' }}>
            <Descriptions column={1} size="small">
              <Descriptions.Item label="代表">{current.rep_name}（{current.rep_phone}）</Descriptions.Item>
              <Descriptions.Item label="备案号">{current.filing_number || '—'}</Descriptions.Item>
              <Descriptions.Item label="备案有效期">{current.filing_expire_date || '—'}</Descriptions.Item>
              <Descriptions.Item label="学历证明">
                <a href={current.education_cert} target="_blank" rel="noreferrer">查看</a>
              </Descriptions.Item>
              {current.training_cert && (
                <Descriptions.Item label="培训证明">
                  <a href={current.training_cert} target="_blank" rel="noreferrer">查看</a>
                </Descriptions.Item>
              )}
              {current.reject_reason && (
                <Descriptions.Item label="驳回原因">{current.reject_reason}</Descriptions.Item>
              )}
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
            <DatePicker
              placeholder="确认备案有效期（按凭证核对）"
              value={expireDate}
              onChange={setExpireDate}
              style={{ width: '100%' }}
            />
            <Button
              type="primary"
              block
              loading={submitting}
              onClick={submitReview}
              disabled={current.audit_status !== 'pending'}
            >
              {current.audit_status !== 'pending' ? '当前状态不可审核' : '提交审核'}
            </Button>
          </Space>
        )}
      </Drawer>
    </>
  );
}
