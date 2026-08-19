import { useEffect, useState } from 'react';
import { Button, Card, Col, Row, Statistic, Table, Tag, Typography } from 'antd';
import { App } from 'antd';
import { monitorAPI } from '../../services/monitor';
import type { ComplianceDailySummary, ComplianceTrends, ReviewQueueItem } from '../../types';

const { Text } = Typography;

export default function Monitor() {
  const { message } = App.useApp();
  const [summary, setSummary] = useState<ComplianceDailySummary | null>(null);
  const [trends, setTrends] = useState<ComplianceTrends | null>(null);
  const [queue, setQueue] = useState<ReviewQueueItem[]>([]);
  const [refresh, setRefresh] = useState(0);

  useEffect(() => {
    monitorAPI.dailySummary(7).then(r => setSummary(r.data.data)).catch(() => {});
    monitorAPI.trends(30).then(r => setTrends(r.data.data)).catch(() => {});
    monitorAPI.reviewQueue().then(r => setQueue(r.data.data.items)).catch(() => {});
  }, [refresh]);

  const maxDay = Math.max(1, ...(trends?.time_series ?? []).map(t => t.count));

  return (
    <div>
      <Row gutter={16}>
        <Col span={6}><Card><Statistic title="近 7 天拦截总量" value={summary?.total ?? 0} /></Card></Col>
        <Col span={6}><Card><Statistic title="待复核代表数" value={queue.length} /></Card></Col>
        <Col span={12}><Card title="违规趋势（近 30 天）" extra={<Button size="small" onClick={() => setRefresh(r => r + 1)}>刷新</Button>}>
          {(trends?.time_series ?? []).map(t => (
            <div key={t.date} style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 4 }}>
              <Text style={{ width: 90 }}>{t.date}</Text>
              <div style={{ flex: 1, background: '#f0f2f5', borderRadius: 4, height: 16 }}>
                <div style={{ width: `${(t.count / maxDay) * 100}%`, background: '#1677ff', height: 16, borderRadius: 4 }} />
              </div>
              <Text>{t.count}</Text>
            </div>
          ))}
        </Card></Col>
      </Row>

      <Card title="待复核冻结流（24h 拦截 ≥5 次，人工确认后冻结）" style={{ marginTop: 16 }}>
        <Table<ReviewQueueItem>
          rowKey="user_id"
          dataSource={queue}
          pagination={false}
          columns={[
            { title: '代表', dataIndex: 'rep_name' },
            { title: '手机号', dataIndex: 'rep_phone' },
            { title: '近 24h 拦截', dataIndex: 'block_count', render: v => <Tag color="red">{v} 次</Tag> },
            { title: '操作', render: (_, r) => <Button size="small" type="primary" danger onClick={() => message.info(`人工冻结流程：请到「分身监控」页对 ${r.rep_name} 的分身执行冻结（跳转见侧栏）`)}>待复核</Button> },
          ]}
        />
      </Card>

      <Card title="规则命中频率" style={{ marginTop: 16 }}>
        <Table
          rowKey="rule_code"
          dataSource={trends?.rule_frequency ?? []}
          pagination={false}
          size="small"
          columns={[
            { title: '规则', dataIndex: 'rule_code' },
            { title: '规则名', dataIndex: 'rule_name' },
            { title: '命中次数', dataIndex: 'count' },
          ]}
        />
      </Card>
    </div>
  );
}
