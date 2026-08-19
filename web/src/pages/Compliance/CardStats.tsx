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
        <Col span={6}><Card><Statistic title="已读" value={stats?.total_reads ?? 0} /></Card></Col>
        <Col span={6}><Card><Statistic title="点击率" value={(stats?.read_rate ?? 0) * 100} precision={2} suffix="%" /></Card></Col>
      </Row>
      <Card title="代表触达排名（近 30 天）" style={{ marginTop: 16 }}>
        <Table
          rowKey="representative_id"
          dataSource={stats?.rep_ranking ?? []}
          pagination={false}
          size="small"
          columns={[
            { title: '代表ID', dataIndex: 'representative_id' },
            { title: '推送数', dataIndex: 'pushes' },
            { title: '已读数', dataIndex: 'reads' },
          ]}
        />
      </Card>
    </div>
  );
}
