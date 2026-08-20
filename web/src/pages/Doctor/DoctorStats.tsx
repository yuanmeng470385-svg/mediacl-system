import { useEffect, useState } from 'react';
import { Card, Col, Row, Statistic, Table } from 'antd';
import { doctorStatsAPI } from '../../services/doctorStats';
import type { DoctorActivity, TwinRankingItem } from '../../types';

export default function DoctorStats() {
  const [activity, setActivity] = useState<DoctorActivity | null>(null);
  const [ranking, setRanking] = useState<TwinRankingItem[]>([]);

  useEffect(() => {
    doctorStatsAPI.activity().then(r => setActivity(r.data.data)).catch(() => {});
    doctorStatsAPI.twinRanking().then(r => setRanking(r.data.data.items)).catch(() => {});
  }, []);

  return (
    <div>
      <Row gutter={16}>
        <Col span={8}><Card><Statistic title="日活医生" value={activity?.dau ?? 0} /></Card></Col>
        <Col span={8}><Card><Statistic title="周活医生" value={activity?.wau ?? 0} /></Card></Col>
        <Col span={8}><Card><Statistic title="月活医生" value={activity?.mau ?? 0} /></Card></Col>
      </Row>
      <Card title="数字分身使用排行（Top10）" style={{ marginTop: 16 }}>
        <Table<TwinRankingItem>
          rowKey="twin_id"
          dataSource={ranking}
          pagination={false}
          size="small"
          columns={[
            { title: '分身', dataIndex: 'name' },
            { title: '状态', dataIndex: 'status' },
            { title: '服务医生数', dataIndex: 'added_count' },
            { title: '好评率', dataIndex: 'approval_rate', render: v => v == null ? '—' : `${(v * 100).toFixed(1)}%` },
          ]}
        />
      </Card>
    </div>
  );
}
