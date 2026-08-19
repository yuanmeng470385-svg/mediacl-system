import { useEffect, useState } from 'react';
import { Button, Card, Col, Input, Modal, Row, Statistic, Table, Tag, Typography } from 'antd';
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

  const handleFreeze = (r: ReviewQueueItem) => {
    let reason = '';
    Modal.confirm({
      title: `冻结分身「${r.name}」`,
      content: <Input.TextArea rows={3} placeholder="冻结理由（必填）" onChange={e => (reason = e.target.value)} />,
      onOk: async () => {
        if (!reason.trim()) { message.warning('请填写冻结理由'); return Promise.reject(); }
        await monitorAPI.freeze(r.specialist_id, reason.trim());
        message.success('已冻结');
        setRefresh(x => x + 1);
      },
    });
  };

  return (
    <div>
      <Row gutter={16}>
        <Col span={6}><Card><Statistic title="近 7 天拦截总量" value={summary?.total ?? 0} /></Card></Col>
        <Col span={6}><Card><Statistic title="待复核分身数" value={queue.length} /></Card></Col>
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
          rowKey="specialist_id"
          dataSource={queue}
          pagination={false}
          columns={[
            { title: '分身名', dataIndex: 'name' },
            { title: '代表', dataIndex: 'rep_name', render: v => (v ?? <Tag>官方</Tag>) },
            { title: '近 24h 拦截', dataIndex: 'block_count', render: v => <Tag color="red">{v} 次</Tag> },
            { title: '操作', render: (_, r) => <Button size="small" type="primary" danger onClick={() => handleFreeze(r)}>冻结</Button> },
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
