import { useEffect, useState } from 'react';
import { Alert, Card, Table, Tag } from 'antd';
import { complianceAPI } from '../../services/compliance';
import type { DataAssetCategory } from '../../types';

const LEVEL_MAP: Record<string, { color: string; text: string }> = {
  敏感: { color: 'red', text: '敏感' },
  内部: { color: 'orange', text: '内部' },
  审计留存: { color: 'blue', text: '审计留存' },
};

export default function DataAssets() {
  const [data, setData] = useState<DataAssetCategory[]>([]);

  useEffect(() => {
    complianceAPI.dataAssets().then(r => setData(r.data.data ?? [])).catch(() => {});
  }, []);

  return (
    <div>
      <Alert
        type="warning"
        showIcon
        style={{ marginBottom: 16 }}
        message="敏感类别（个人信息/对话明细）导出必走数据导出审批流"
      />
      <Card>
        <Table<DataAssetCategory>
          rowKey="category"
          dataSource={data}
          pagination={false}
          columns={[
            { title: '数据类别', dataIndex: 'category', width: 220 },
            {
              title: '级别',
              dataIndex: 'level',
              width: 120,
              render: (v: string) => {
                const m = LEVEL_MAP[v] || { color: 'default', text: v };
                return <Tag color={m.color}>{m.text}</Tag>;
              },
            },
            {
              title: '表清单',
              dataIndex: 'tables',
              render: (v: string[]) => (v ?? []).map(t => <Tag key={t}>{t}</Tag>),
            },
          ]}
        />
      </Card>
    </div>
  );
}
