import { ProTable } from '@ant-design/pro-components';
import type { ProColumns } from '@ant-design/pro-components';
import { Tag, Typography } from 'antd';
import { monitorAPI } from '../../services/monitor';
import type { ConvSearchItem } from '../../types';

const { Text } = Typography;

export default function ConvSearch() {
  const columns: ProColumns<ConvSearchItem>[] = [
    { title: '内容', dataIndex: 'content', ellipsis: true },
    { title: '代表ID', dataIndex: 'user_id', width: 90 },
    { title: '分身ID', dataIndex: 'specialist_id', width: 90 },
    { title: '角色', dataIndex: 'role', width: 90, hideInSearch: true, render: (_, r) => r.role === 'user' ? <Tag color="blue">代表</Tag> : <Tag>AI</Tag> },
    { title: '被拦', dataIndex: 'blocked', width: 70, hideInSearch: true, render: (_, r) => r.blocked ? <Tag color="red">是</Tag> : <Tag color="green">否</Tag> },
    { title: '时间', dataIndex: 'created_at', width: 180, hideInSearch: true },
    { title: '检索词', dataIndex: 'keyword', hideInTable: true },
  ];

  return (
    <ProTable<ConvSearchItem>
      headerTitle="对话日志全文检索"
      rowKey="id"
      search={{ labelWidth: 90 }}
      expandable={{
        expandedRowRender: r => (
          <div>
            <Text type="secondary">完整会话上下文（{r.context.length} 条）：</Text>
            {r.context.map((c, i) => (
              <div key={i} style={{ marginTop: 4, padding: 8, background: c.role === 'user' ? '#e6f4ff' : '#f6ffed', borderRadius: 4 }}>
                <Text strong>{c.role === 'user' ? '代表' : 'AI'}</Text>
                {c.blocked && <Tag color="red" style={{ marginLeft: 8 }}>被拦</Tag>}
                <div>{c.content}</div>
              </div>
            ))}
          </div>
        ),
      }}
      columns={columns}
      request={async (params) => {
        const res = await monitorAPI.convSearch({
          page: params.current || 1,
          page_size: params.pageSize || 10,
          keyword: params.keyword,
          user_id: params.user_id,
          specialist_id: params.specialist_id,
        });
        return { data: res.data.data.items, total: res.data.data.total, success: true };
      }}
    />
  );
}
