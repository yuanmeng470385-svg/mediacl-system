import { useRef, useState } from 'react';
import { ProTable } from '@ant-design/pro-components';
import type { ProColumns, ActionType } from '@ant-design/pro-components';
import { App, Button, Descriptions, Drawer, Input, Radio, Space, Tag } from 'antd';
import { doctorCertAPI } from '../../services/doctorCert';
import type { DoctorCert } from '../../types';

const AUDIT_MAP: Record<string, { color: string; text: string }> = {
  pending: { color: 'orange', text: '待审核' },
  approved: { color: 'green', text: '已通过' },
  rejected: { color: 'red', text: '已驳回' },
};
const CERT_TYPE_MAP: Record<string, { color: string; text: string }> = {
  physician: { color: 'blue', text: '医师资格证' },
  practice: { color: 'cyan', text: '执业证' },
};

const isPdf = (url: string) => /\.pdf($|\?)/i.test(url);

export default function DoctorCertList() {
  const actionRef = useRef<ActionType>();
  const [current, setCurrent] = useState<DoctorCert | null>(null);
  const [verdict, setVerdict] = useState<'approve' | 'reject'>('approve');
  const [reason, setReason] = useState('');
  const [submitting, setSubmitting] = useState(false);
  const { message } = App.useApp();

  const openDrawer = (row: DoctorCert) => {
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
      await doctorCertAPI.review(current.id, {
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

  const columns: ProColumns<DoctorCert>[] = [
    // 搜索参数对齐后端 list_certs：仅 cert_status/keyword；
    // 以下三列 hideInSearch，避免表单输入被后端静默忽略（照 FilingList 同款修复）
    { title: '医生姓名', dataIndex: 'doctor_name', width: 120, hideInSearch: true },
    { title: '手机号', dataIndex: 'doctor_phone', width: 130, hideInSearch: true },
    {
      title: '证书类型', dataIndex: 'cert_type', width: 110, hideInSearch: true,
      render: (_, r) => {
        const m = CERT_TYPE_MAP[r.cert_type] || { color: 'default', text: r.cert_type };
        return <Tag color={m.color}>{m.text}</Tag>;
      },
    },
    {
      title: '审核状态', dataIndex: 'cert_status', width: 90,
      valueEnum: { pending: '待审核', approved: '已通过', rejected: '已驳回' },
      render: (_, r) => {
        const m = AUDIT_MAP[r.cert_status] || { color: 'default', text: r.cert_status };
        return <Tag color={m.color}>{m.text}</Tag>;
      },
    },
    {
      title: '驳回原因', dataIndex: 'reject_reason', width: 180, hideInSearch: true,
      render: (_, r) => r.reject_reason || '—',
    },
    {
      title: '操作', width: 80,
      render: (_, r) => <a onClick={() => openDrawer(r)}>审核</a>,
    },
    { title: '关键词', dataIndex: 'keyword', hideInTable: true },
  ];

  return (
    <>
      <ProTable<DoctorCert>
        headerTitle="医生认证"
        actionRef={actionRef}
        columns={columns}
        rowKey="id"
        search={{ labelWidth: 90 }}
        request={async (params) => {
          const res = await doctorCertAPI.list({
            page: params.current || 1,
            page_size: params.pageSize || 10,
            cert_status: params.cert_status,
            keyword: params.keyword,
          });
          return { data: res.data.data.items, total: res.data.data.total, success: true };
        }}
      />
      <Drawer
        title="医生资质审核"
        width={480}
        open={!!current}
        onClose={() => setCurrent(null)}
        destroyOnHidden
      >
        {current && (
          <Space direction="vertical" size="middle" style={{ width: '100%' }}>
            <Descriptions column={1} size="small">
              <Descriptions.Item label="医生">{current.doctor_name}（{current.doctor_phone}）</Descriptions.Item>
              <Descriptions.Item label="证书类型">
                {current.cert_type === 'physician' ? '医师资格证' : current.cert_type === 'practice' ? '执业证' : current.cert_type}
              </Descriptions.Item>
              <Descriptions.Item label="证书">
                {isPdf(current.cert_image_url) ? (
                  <a href={current.cert_image_url} target="_blank" rel="noreferrer">查看 PDF</a>
                ) : (
                  <img src={current.cert_image_url} style={{ maxWidth: '100%' }} alt="证书图片" />
                )}
              </Descriptions.Item>
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
            <Button
              type="primary"
              block
              loading={submitting}
              onClick={submitReview}
              disabled={current.cert_status !== 'pending'}
            >
              {current.cert_status !== 'pending' ? '当前状态不可审核' : '提交审核'}
            </Button>
          </Space>
        )}
      </Drawer>
    </>
  );
}
