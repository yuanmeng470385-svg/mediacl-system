import { useRef, useState } from 'react';
import { ProTable, ModalForm, ProFormText } from '@ant-design/pro-components';
import type { ProColumns, ActionType } from '@ant-design/pro-components';
import { App, Button, Descriptions, Drawer, Input, Radio, Space, Tag } from 'antd';
import { dataExportAPI } from '../../services/dataExports';
import { useAuth } from '../../hooks/useAuth';
import type { ExportRequest } from '../../types';

const STATUS_MAP: Record<string, { color: string; text: string }> = {
  pending: { color: 'orange', text: '待审批' },
  approved: { color: 'green', text: '已通过' },
  rejected: { color: 'red', text: '已驳回' },
};

export default function DataExports() {
  const actionRef = useRef<ActionType>();
  const { message } = App.useApp();
  const { user: me } = useAuth();
  // M-2（2026-08-24 审查修复）：审批收敛到 compliance/admin，且不能批自己
  // 提交的单（与后端 require_roles + 自批守卫对齐，前端只做可见性兜底）
  const myId = me?.id !== undefined ? Number(me.id) : null;
  const canReview =
    (me?.role === 'compliance' || me?.role === 'admin') && myId !== null;
  const reviewable = (r: ExportRequest) => canReview && r.requester_id !== myId;
  const [current, setCurrent] = useState<ExportRequest | null>(null);
  const [verdict, setVerdict] = useState<'approve' | 'reject'>('approve');
  const [reason, setReason] = useState('');
  const [submitting, setSubmitting] = useState(false);
  const [createOpen, setCreateOpen] = useState(false);
  const [downloadingId, setDownloadingId] = useState<number | null>(null);

  const openReview = (row: ExportRequest) => {
    setCurrent(row);
    setVerdict('approve');
    setReason('');
  };

  const handleDownload = async (row: ExportRequest) => {
    setDownloadingId(row.id);
    try {
      const res = await dataExportAPI.download(row.id);
      const blob = res.data;
      if (!(blob instanceof Blob) || blob.size === 0) {
        message.error('下载失败，请稍后重试');
        return;
      }
      const url = URL.createObjectURL(blob);
      const cd = res.headers?.['content-disposition'] ?? '';
      const m = /filename="?([^";]+)"?/.exec(cd);
      const filename = m?.[1] || `export_${row.id}.xlsx`;
      const a = document.createElement('a');
      a.href = url;
      a.download = filename;
      document.body.appendChild(a);
      a.click();
      a.remove();
      URL.revokeObjectURL(url);
    } catch {
      /* HTTP 错误已由全局拦截器统一弹 toast，此处不重复弹（避免双弹） */
    } finally {
      setDownloadingId(null);
    }
  };

  const submitReview = async () => {
    if (!current) return;
    if (verdict === 'reject' && !reason.trim()) {
      message.warning('驳回必须填写原因');
      return;
    }
    setSubmitting(true);
    try {
      await dataExportAPI.review(current.id, {
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

  const columns: ProColumns<ExportRequest>[] = [
    { title: '申请单号', dataIndex: 'id', width: 90, hideInSearch: true },
    { title: '申请人', dataIndex: 'requester_name', width: 120 },
    { title: '类型', dataIndex: 'export_type', width: 140, hideInSearch: true },
    {
      title: '目的', dataIndex: 'reason', ellipsis: true, hideInSearch: true,
      render: (_, r) => r.reason || '-',
    },
    {
      title: '状态', dataIndex: 'status', width: 140,
      valueEnum: { pending: '待审批', approved: '已通过', rejected: '已驳回' },
      render: (_, r) => {
        const m = STATUS_MAP[r.status] || { color: 'default', text: r.status };
        if (r.status === 'pending' && r.sla_overdue) {
          return (
            <>
              <Tag color={m.color}>{m.text}</Tag>
              <Tag color="red">超时限</Tag>
            </>
          );
        }
        return <Tag color={m.color}>{m.text}</Tag>;
      },
    },
    {
      title: '申请时间', dataIndex: 'created_at', width: 170, hideInSearch: true,
      render: (_, r) => r.created_at || '-',
    },
    {
      title: '操作', width: 140,
      render: (_, r) => (
        <Space size="middle">
          {r.status === 'pending' ? (
            reviewable(r) ? (
              <a onClick={() => openReview(r)}>审批</a>
            ) : (
              <span style={{ color: '#999' }}>无权审批</span>
            )
          ) : r.status === 'approved' ? (
            <a onClick={() => handleDownload(r)}>
              {downloadingId === r.id ? '下载中…' : '下载'}
            </a>
          ) : (
            <span style={{ color: '#999' }}>已驳回</span>
          )}
        </Space>
      ),
    },
  ];

  return (
    <>
      <ProTable<ExportRequest>
        headerTitle="导出审批"
        actionRef={actionRef}
        rowKey="id"
        search={{ labelWidth: 90 }}
        columns={columns}
        request={async (params) => {
          const res = await dataExportAPI.list({
            page: params.current || 1,
            page_size: params.pageSize || 10,
            status: params.status,
          });
          return { data: res.data.data.items, total: res.data.data.total, success: true };
        }}
        toolBarRender={() => [
          <Button type="primary" key="new" onClick={() => setCreateOpen(true)}>发起导出申请</Button>,
        ]}
      />
      <ModalForm
        key="create"
        title="发起导出申请"
        open={createOpen}
        onOpenChange={setCreateOpen}
        modalProps={{ destroyOnHidden: true }}
        onFinish={async (values) => {
          try {
            await dataExportAPI.create({
              export_type: 'conversations',
              reason: String(values.reason ?? '').trim(),
            });
            message.success('申请已提交');
            setCreateOpen(false);
            actionRef.current?.reload();
            return true;
          } catch (e) {
            console.error('发起导出申请失败', e);
            return false;
          }
        }}
      >
        <ProFormText name="export_type" label="导出类型" initialValue="conversations" disabled />
        <ProFormText
          name="reason"
          label="导出目的"
          rules={[{ required: true, message: '请填写导出目的' }]}
          fieldProps={{ maxLength: 500 }}
        />
      </ModalForm>
      <Drawer
        title="导出申请审批"
        width={520}
        open={!!current}
        onClose={() => setCurrent(null)}
        destroyOnHidden
      >
        {current && (
          <Space direction="vertical" size="middle" style={{ width: '100%' }}>
            <Descriptions column={1} size="small">
              <Descriptions.Item label="申请单号">{current.id}</Descriptions.Item>
              <Descriptions.Item label="申请人">{current.requester_name || '-'}</Descriptions.Item>
              <Descriptions.Item label="导出类型">
                {current.export_type === 'conversations' ? '对话记录' : current.export_type}
              </Descriptions.Item>
              <Descriptions.Item label="导出目的">{current.reason || '-'}</Descriptions.Item>
              <Descriptions.Item label="申请时间">{current.created_at || '-'}</Descriptions.Item>
              {current.expires_at && (
                <Descriptions.Item label="文件有效期">{current.expires_at}</Descriptions.Item>
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
              disabled={current.status !== 'pending'}
            >
              {current.status !== 'pending' ? '当前状态不可审批' : '提交审批'}
            </Button>
          </Space>
        )}
      </Drawer>
    </>
  );
}
