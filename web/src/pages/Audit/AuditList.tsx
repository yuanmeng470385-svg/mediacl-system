import { useEffect, useRef, useState } from 'react';
import { ProTable } from '@ant-design/pro-components';
import type { ProColumns, ActionType } from '@ant-design/pro-components';
import { Button, Tag, Row, Col, App, Spin } from 'antd';
import { ExportOutlined } from '@ant-design/icons';
import StatCard from '../../components/StatCard';
import { auditAPI } from '../../services/audit';
import type { AuditExportParams, AuditListParams } from '../../services/audit';
import type { AuditLog } from '../../types';
import { AUDIT_ACTION_MAP } from '../../constants/audit';
import dayjs from 'dayjs';
import utc from 'dayjs/plugin/utc';

dayjs.extend(utc);

const RISK_COLOR: Record<string, string> = { high: 'red', medium: 'orange', low: 'green' };
const RISK_ENUM = { high: '高危', medium: '中危', low: '低危' };

/** 展开行：拉取单条日志详情，展示真实字段（ai_prompt_hash / ai_response_hash 等） */
function LogDetail({ log }: { log: AuditLog }) {
  const [data, setData] = useState<AuditLog | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    auditAPI.detail(log.id)
      .then((res) => { if (!cancelled) setData(res.data.data); })
      // 失败 toast 由全局拦截器统一弹，此处不重复弹（避免双弹）
      .catch(() => {})
      .finally(() => { if (!cancelled) setLoading(false); });
    return () => { cancelled = true; };
  }, [log.id]);

  if (loading) return <Spin size="small" />;

  const d = data ?? log;
  const timeText = d.timestamp ? dayjs.utc(d.timestamp).local().format('YYYY-MM-DD HH:mm:ss') : '—';
  const rows: [string, string][] = [
    ['用户编号', d.user_id ?? '—'],
    ['服务', d.service_name ?? '—'],
    // 详情是"真实字段"展示：中文文案 + 原始 action 码，两侧信息都不丢
    ['操作', d.action ? (AUDIT_ACTION_MAP[d.action] ? `${AUDIT_ACTION_MAP[d.action]}（${d.action}）` : d.action) : '—'],
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
            // 后端 timestamp 存 UTC 字面，搜索参数也必须是 UTC 字面 ——
            // 直接用本地时间会整体偏移 8 小时（选中"8 月 1 日"实查 7 月 31 日）
            ? { start_time: dayjs.utc(value[0]).format('YYYY-MM-DDTHH:mm:ss'), end_time: dayjs.utc(value[1]).format('YYYY-MM-DDTHH:mm:ss') }
            : undefined,
      },
    },
    { title: '服务', dataIndex: 'service_name', width: 130, fieldProps: { placeholder: '如 specialist-service' } },
    {
      title: '操作', dataIndex: 'action', width: 150,
      // 下拉搜索：值仍是后端原始 action 码（搜索/导出契约不变），只把文案换成中文
      valueType: 'select',
      valueEnum: AUDIT_ACTION_MAP,
      fieldProps: { showSearch: true, placeholder: '选择操作类型' },
      render: (_, r) => AUDIT_ACTION_MAP[r.action] ?? r.action,
    },
    { title: '用户编号', dataIndex: 'user_id', width: 90, fieldProps: { placeholder: '用户编号' } },
    // 关键词搜索（B5 后端已支持 ILIKE 多字段：操作/服务/资源/请求ID/取证内容），仅作搜索列不在表格展示
    { title: '关键词', dataIndex: 'keyword', hideInTable: true, fieldProps: { placeholder: '操作/服务/资源/请求编号/取证内容' } },
    {
      title: '风险等级', dataIndex: 'risk_level', width: 100, valueEnum: RISK_ENUM,
      render: (_, r) => (r.risk_level ? <Tag color={RISK_COLOR[r.risk_level] || 'default'}>{RISK_ENUM[r.risk_level] ?? r.risk_level}</Tag> : '—'),
    },
    { title: 'IP 地址', dataIndex: 'client_ip', width: 130, hideInSearch: true, render: (_, r) => r.client_ip || '—' },
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
      // 空响应不是 HTTP 错误，拦截器不会弹 —— 这里兜底提示
      if (!(blob instanceof Blob) || blob.size === 0) {
        message.error('导出失败，请稍后重试');
        return;
      }
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
      // HTTP 错误已由全局拦截器统一弹 toast，此处不重复弹（避免双弹）
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
            keyword: params.keyword,
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
