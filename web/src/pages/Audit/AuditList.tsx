import { useEffect, useRef, useState } from 'react';
import { ProTable } from '@ant-design/pro-components';
import type { ProColumns, ActionType } from '@ant-design/pro-components';
import { Button, Tag, Row, Col, App, Spin } from 'antd';
import { ExportOutlined } from '@ant-design/icons';
import StatCard from '../../components/StatCard';
import { auditAPI } from '../../services/audit';
import type { AuditExportParams, AuditListParams } from '../../services/audit';
import type { AuditLog } from '../../types';
import dayjs from 'dayjs';
import utc from 'dayjs/plugin/utc';

dayjs.extend(utc);

const RISK_COLOR: Record<string, string> = { high: 'red', medium: 'orange', low: 'green' };
const RISK_ENUM = { high: '高危', medium: '中危', low: '低危' };

/** 展开行：拉取单条日志详情，展示真实字段（ai_prompt_hash / ai_response_hash 等） */
function LogDetail({ log }: { log: AuditLog }) {
  const { message } = App.useApp();
  const [data, setData] = useState<AuditLog | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    auditAPI.detail(log.id)
      .then((res) => { if (!cancelled) setData(res.data.data); })
      .catch(() => { if (!cancelled) message.error('加载日志详情失败'); })
      .finally(() => { if (!cancelled) setLoading(false); });
    return () => { cancelled = true; };
  }, [log.id, message]);

  if (loading) return <Spin size="small" />;

  const d = data ?? log;
  const timeText = d.timestamp ? dayjs.utc(d.timestamp).local().format('YYYY-MM-DD HH:mm:ss') : '—';
  const rows: [string, string][] = [
    ['用户 ID', d.user_id ?? '—'],
    ['服务', d.service_name ?? '—'],
    ['操作', d.action ?? '—'],
    ['资源', d.resource_type && d.resource_id ? `${d.resource_type} / ${d.resource_id}` : (d.resource_type || d.resource_id || '—')],
    ['AI 模型', d.ai_model ?? '—'],
    ['AI 参与', d.ai_involved ? '是' : '否'],
    ['提示词哈希', d.ai_prompt_hash ?? '—'],
    ['回复哈希', d.ai_response_hash ?? '—'],
    ['合规检查结果', d.compliance_result ? JSON.stringify(d.compliance_result) : '—'],
    ['请求 ID', d.request_id ?? '—'],
    ['时间', timeText],
  ];

  return (
    <div style={{ padding: '8px 0', display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(360px, 1fr))', gap: '6px 24px' }}>
      {rows.map(([k, v]) => (
        <div key={k}>
          <b>{k}: </b>
          <span style={{ wordBreak: 'break-all' }}>{v}</span>
        </div>
      ))}
    </div>
  );
}

export default function AuditList() {
  const actionRef = useRef<ActionType>();
  const { message } = App.useApp();
  const [stats, setStats] = useState<{
    total: number | null;
    recent: number | null;
    high: number | null;
    serviceCount: number | null;
  }>({ total: null, recent: null, high: null, serviceCount: null });
  // 记录最近一次查询的筛选参数，导出时带上
  const filterRef = useRef<AuditListParams>({});

  useEffect(() => {
    auditAPI.stats()
      .then((res) => {
        const s = res.data.data;
        setStats({
          total: s.total_records ?? 0,
          recent: s.recent_records ?? 0,
          high: s.risk_distribution?.high ?? 0,
          serviceCount: Object.keys(s.service_distribution ?? {}).length,
        });
      })
      .catch(() => {});
  }, []);

  const columns: ProColumns<AuditLog>[] = [
    {
      title: '时间', dataIndex: 'timestamp', width: 170, hideInSearch: true,
      render: (_, r) => (r.timestamp ? dayjs.utc(r.timestamp).local().format('YYYY-MM-DD HH:mm:ss') : '—'),
    },
    {
      title: '时间范围', dataIndex: 'timeRange', valueType: 'dateTimeRange', hideInTable: true,
      search: {
        transform: (value: any) =>
          Array.isArray(value) && value?.[0]
            ? { start_time: dayjs(value[0]).format('YYYY-MM-DDTHH:mm:ss'), end_time: dayjs(value[1]).format('YYYY-MM-DDTHH:mm:ss') }
            : undefined,
      },
    },
    { title: '服务', dataIndex: 'service_name', width: 130, fieldProps: { placeholder: '如 specialist-service' } },
    { title: '操作', dataIndex: 'action', width: 150, fieldProps: { placeholder: '如 chat_response' } },
    { title: '用户 ID', dataIndex: 'user_id', width: 90, fieldProps: { placeholder: '用户 ID' } },
    {
      title: '风险等级', dataIndex: 'risk_level', width: 100, valueEnum: RISK_ENUM,
      render: (_, r) => (r.risk_level ? <Tag color={RISK_COLOR[r.risk_level] || 'default'}>{RISK_ENUM[r.risk_level] ?? r.risk_level}</Tag> : '—'),
    },
    { title: 'IP', dataIndex: 'client_ip', width: 130, hideInSearch: true, render: (_, r) => r.client_ip || '—' },
  ];

  const handleExport = async () => {
    const f = filterRef.current;
    const body: AuditExportParams = {
      start_time: f.start_time,
      end_time: f.end_time,
      service_name: f.service_name,
      risk_level: f.risk_level,
    };
    try {
      const res = await auditAPI.export(body);
      const blob = res.data;
      if (!(blob instanceof Blob) || blob.size === 0) throw new Error('empty response');
      const url = URL.createObjectURL(blob);
      const cd = res.headers?.['content-disposition'] ?? '';
      const m = /filename="?([^";]+)"?/.exec(cd);
      const filename = m?.[1] || `audit_report_${dayjs().format('YYYYMMDD_HHMMSS')}.xlsx`;
      const a = document.createElement('a');
      a.href = url;
      a.download = filename;
      document.body.appendChild(a);
      a.click();
      a.remove();
      URL.revokeObjectURL(url);
      message.success('导出成功');
    } catch {
      message.error('导出失败，请稍后重试');
    }
  };

  return (
    <>
      <Row gutter={[16, 16]} style={{ marginBottom: 16 }}>
        <Col span={6}><StatCard title="总记录数" value={stats.total ?? '—'} /></Col>
        <Col span={6}><StatCard title="近 30 天记录数" value={stats.recent ?? '—'} /></Col>
        <Col span={6}><StatCard title="近 30 天高危数" value={stats.high ?? '—'} /></Col>
        <Col span={6}><StatCard title="近 30 天服务数" value={stats.serviceCount ?? '—'} /></Col>
      </Row>
      <ProTable<AuditLog>
        headerTitle="审计日志"
        actionRef={actionRef}
        columns={columns}
        request={async (params) => {
          const query: AuditListParams = {
            page: params.current || 1,
            page_size: params.pageSize || 10,
            start_time: params.start_time,
            end_time: params.end_time,
            user_id: params.user_id,
            service_name: params.service_name,
            action: params.action,
            risk_level: params.risk_level,
          };
          filterRef.current = query;
          const res = await auditAPI.list(query);
          return { data: res.data.data.items, total: res.data.data.total, success: true };
        }}
        rowKey="id"
        search={{ labelWidth: 80, defaultCollapsed: false }}
        expandable={{
          expandedRowRender: (record) => <LogDetail log={record} />,
        }}
        toolBarRender={() => [
          <Button key="export" icon={<ExportOutlined />} onClick={handleExport}>导出 Excel</Button>,
        ]}
        dateFormatter="string"
      />
    </>
  );
}
