import { useEffect, useState } from 'react';
import { Card, Col, Row, Statistic, Table } from 'antd';
import { cardStatsAPI } from '../../services/cardStats';
import type { CardStats } from '../../types';

export default function CardStats() {
  const [stats, setStats] = useState<CardStats | null>(null);

  useEffect(() => {
    cardStatsAPI.stats(30).then(r => setStats(r.data.data)).catch(() => {});
  }, []);

  return (
    <div>
      <Row gutter={16}>
        <Col span={6}><Card><Statistic title="总推送" value={stats?.total_pushes ?? 0} /></Card></Col>
        <Col span={6}>
          <Card>
            <Statistic title="已读" value={stats?.total_reads ?? 0} />
            <div style={{ fontSize: 12, color: '#999', marginTop: 4 }}>口径：被打开（客户端自报即计）</div>
          </Card>
        </Col>
        <Col span={6}>
          <Card>
            <Statistic title="点击率" value={(stats?.read_rate ?? 0) * 100} precision={2} suffix="%" />
            <div style={{ fontSize: 12, color: '#999', marginTop: 4 }}>已读 / 总推送</div>
          </Card>
        </Col>
        <Col span={6}>
          <Card>
            <Statistic title="有效阅读率" value={(stats?.effective_read_rate ?? 0) * 100} precision={2} suffix="%" />
            <div style={{ fontSize: 12, color: '#999', marginTop: 4 }}>口径：已读且停留 ≥3 秒 / 总推送</div>
          </Card>
        </Col>
      </Row>
      <Card title="代表触达排名（近 30 天，按已读数排序）" style={{ marginTop: 16 }}>
        <Table
          rowKey="representative_id"
          dataSource={stats?.rep_ranking ?? []}
          pagination={false}
          size="small"
          columns={[
            { title: '代表ID', dataIndex: 'representative_id' },
            { title: '推送数', dataIndex: 'pushes' },
            { title: '已读数', dataIndex: 'reads' },
            {
              title: '已读率',
              dataIndex: 'read_rate',
              render: (v: number) => ((v ?? 0) * 100).toFixed(1) + '%',
            },
          ]}
        />
      </Card>
    </div>
  );
}
