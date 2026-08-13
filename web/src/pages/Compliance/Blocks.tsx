import { useEffect, useRef, useState } from 'react';
import { ProTable } from '@ant-design/pro-components';
import type { ProColumns, ActionType } from '@ant-design/pro-components';
import { Spin, Tag } from 'antd';
import { complianceAPI } from '../../services/compliance';
import { userAPI } from '../../services/user';
import type { ComplianceBlock } from '../../types';
import dayjs from 'dayjs';
import utc from 'dayjs/plugin/utc';

dayjs.extend(utc);

const SEVERITY_COLOR: Record<string, string> = { high: 'red', medium: 'orange', low: 'blue' };
const SEVERITY_TEXT: Record<string, string> = { high: '高', medium: '中', low: '低' };
const ACTION_TEXT: Record<string, string> = { reject: '拒绝', warn: '警告', log: '仅记录' };
const SEVERITY_ENUM = { high: '高', medium: '中', low: '低' };

/** 展开行：拉取单条拦截详情，展示完整内容与上下文（列表接口 content 截断 200 字、不含 context） */
function BlockDetail({ block, userName }: { block: ComplianceBlock; userName: string }) {
  const [data, setData] = useState<ComplianceBlock | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    complianceAPI.blockDetail(block.id)
      .then((res) => { if (!cancelled) setData(res.data.data); })
      // 失败 toast 由全局拦截器统一弹，此处不重复弹（避免双弹）
      .catch(() => {})
      .finally(() => { if (!cancelled) setLoading(false); });
    return () => { cancelled = true; };
  }, [block.id]);

  if (loading) return <Spin size="small" />;

  const d = data ?? block;
  const context = d.context && Object.keys(d.context).length > 0 ? d.context : null;

  return (
    <div style={{ padding: '8px 0', maxWidth: 900 }}>
      <div style={{ marginBottom: 8 }}>
        <b>完整内容：</b>
      </div>
      <div style={{ whiteSpace: 'pre-wrap', wordBreak: 'break-all', background: '#fafafa', padding: 10, borderRadius: 6, marginBottom: 12 }}>
        {d.content || '（无内容）'}
      </div>
      {context && (
        <>
          <div style={{ marginBottom: 8 }}><b>上下文（context）：</b></div>
          <pre style={{ whiteSpace: 'pre-wrap', wordBreak: 'break-all', background: '#fafafa', padding: 10, borderRadius: 6, margin: 0, fontSize: 12 }}>
            {JSON.stringify(context, null, 2)}
          </pre>
        </>
      )}
      {!context && <div style={{ color: '#8c8c8c', fontSize: 12 }}>无上下文信息</div>}
      <div style={{ marginTop: 12, color: '#8c8c8c', fontSize: 12 }}>
        用户：{userName}　规则：{d.rule_code} {d.rule_name}　时间：{d.blocked_at ? dayjs.utc(d.blocked_at).local().format('YYYY-MM-DD HH:mm:ss') : '—'}
      </div>
    </div>
  );
}

export default function ComplianceBlocks() {
  const actionRef = useRef<ActionType>();
  const [userMap, setUserMap] = useState<Map<string, string>>(new Map());

  // 用户 ID → 姓名映射（拦截记录的"用户"列）
  useEffect(() => {
    userAPI.list({ page: 1, page_size: 100 })
      .then((r) => {
        const map = new Map<string, string>();
        (r.data.data?.items ?? []).forEach((u: any) => map.set(String(u.id), u.full_name || u.username));
        setUserMap(map);
      })
      .catch(() => {});
  }, []);

  const userNameOf = (userId: number | null): string => {
    if (userId == null) return '系统';
    return userMap.get(String(userId)) ?? `用户 #${userId}`;
  };

  const columns: ProColumns<ComplianceBlock>[] = [
    {
      title: '时间', dataIndex: 'blocked_at', width: 170, hideInSearch: true,
      render: (_, r) => (r.blocked_at ? dayjs.utc(r.blocked_at).local().format('YYYY-MM-DD HH:mm:ss') : '—'),
    },
    {
      title: '用户', dataIndex: 'user_id', width: 130,
      fieldProps: { placeholder: '用户 ID' },
      render: (_, r) => userNameOf(r.user_id),
    },
    {
      title: '服务', dataIndex: 'service_name', width: 130, hideInSearch: true,
      render: (_, r) => r.service_name || '—',
    },
    {
      title: '内容摘要', dataIndex: 'content', ellipsis: true, hideInSearch: true,
      render: (_, r) => r.content || '—',
    },
    { title: '规则编码', dataIndex: 'rule_code', width: 110, fieldProps: { placeholder: '如 R101' } },
    {
      title: '严重度', dataIndex: 'severity', width: 90, hideInSearch: true, valueEnum: SEVERITY_ENUM,
      render: (_, r) => <Tag color={SEVERITY_COLOR[r.severity]}>{SEVERITY_TEXT[r.severity] || r.severity}</Tag>,
    },
    {
      title: '动作', dataIndex: 'action', width: 90, hideInSearch: true,
      render: (_, r) => <Tag>{ACTION_TEXT[r.action] || r.action}</Tag>,
    },
  ];

  return (
    <ProTable<ComplianceBlock>
      headerTitle="合规拦截记录"
      actionRef={actionRef}
      columns={columns}
      request={async (params) => {
        // 筛选参数对齐后端：user_id / rule_code（后端不识别时间/服务等其余筛选）
        const uid = params.user_id === undefined || params.user_id === '' || params.user_id === null
          ? undefined
          : Number(params.user_id);
        const res = await complianceAPI.blocks({
          page: params.current || 1,
          page_size: params.pageSize || 10,
          user_id: uid !== undefined && !Number.isNaN(uid) ? uid : undefined,
          rule_code: params.rule_code || undefined,
        });
        return { data: res.data.data.items, total: res.data.data.total, success: true };
      }}
      rowKey="id"
      search={{ labelWidth: 80 }}
      expandable={{
        expandedRowRender: (record) => <BlockDetail block={record} userName={userNameOf(record.user_id)} />,
      }}
      dateFormatter="string"
    />
  );
}
