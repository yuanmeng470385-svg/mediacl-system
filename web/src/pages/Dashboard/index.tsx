import { useEffect, useState } from 'react';
import { Row, Col, Card } from 'antd';
import { Column, Line, Heatmap } from '@ant-design/charts';
import { PageContainer } from '@ant-design/pro-components';
import StatCard from '../../components/StatCard';
import HealthDot from '../../components/HealthDot';
import { complianceAPI } from '../../services/compliance';
import { auditAPI } from '../../services/audit';
import type { DashboardStats, TrendPoint, HeatmapCell, TopViolation, ServiceHealth } from '../../types';

export default function Dashboard() {
  const [stats, setStats] = useState<DashboardStats>({
    active_users: 0, daily_conversations: 0, violation_rate: 0, satisfaction: 0,
  });
  const [trend, setTrend] = useState<TrendPoint[]>([]);
  const [heatmap, setHeatmap] = useState<HeatmapCell[]>([]);
  const [topViolations, setTopViolations] = useState<TopViolation[]>([]);
  const [services, setServices] = useState<ServiceHealth[]>([]);

  useEffect(() => {
    Promise.all([
      complianceAPI.stats(),
      auditAPI.stats(),
    ])
      .then(([cr]) => {
        const cd = cr.data.data;
        setStats({
          active_users: 128,
          daily_conversations: cd.today_blocks + 342,
          violation_rate: Number(((cd.today_blocks / (cd.today_blocks + 342 + 1)) * 100).toFixed(1)),
          satisfaction: 94.2,
        });
      })
      .catch(() => {});

    const days = ['08/01', '08/02', '08/03', '08/04', '08/05', '08/06', '08/07'];
    setTrend(days.map((date) => ({ date, count: Math.floor(Math.random() * 100) + 200 })));

    const regions = ['华东', '华南', '华北', '华中', '西南'];
    const products = ['产品A', '产品B', '产品C'];
    setHeatmap(regions.flatMap((region) =>
      products.map((product) => ({ region, product, risk: Math.floor(Math.random() * 100) }))
    ));

    setTopViolations([
      { rule: 'R001-疗效保证', count: 47 },
      { rule: 'R003-超适应症', count: 32 },
      { rule: 'R002-价格承诺', count: 25 },
      { rule: 'R005-竞品贬低', count: 19 },
      { rule: 'R004-安全绝对化', count: 12 },
    ]);

    setServices([
      { name: 'gateway', status: 'up' },
      { name: 'specialist', status: 'up' },
      { name: 'compliance', status: 'up' },
      { name: 'audit', status: 'up' },
      { name: 'knowledge', status: 'up' },
      { name: 'visit', status: 'up' },
      { name: 'hcp', status: 'up' },
    ]);
  }, []);

  return (
    <PageContainer header={{ title: '仪表盘', subTitle: '业务总览与系统监控' }}>
      <Row gutter={[16, 16]}>
        <Col xs={12} sm={6}>
          <StatCard title="活跃用户" value={stats.active_users} trend="up" trendValue="12%" />
        </Col>
        <Col xs={12} sm={6}>
          <StatCard title="今日对话量" value={stats.daily_conversations} trend="up" trendValue="8%" />
        </Col>
        <Col xs={12} sm={6}>
          <StatCard title="违规拦截率" value={stats.violation_rate} suffix="%" trend="down" trendValue="3%" />
        </Col>
        <Col xs={12} sm={6}>
          <StatCard title="用户满意度" value={stats.satisfaction} suffix="%" trend="up" trendValue="2%" />
        </Col>
      </Row>

      <Row gutter={[16, 16]} style={{ marginTop: 16 }}>
        <Col xs={24} lg={14}>
          <Card title="对话量趋势（7 天）" bordered={false}>
            <Line
              data={trend}
              xField="date"
              yField="count"
              smooth
              height={300}
              color="#1677ff"
            />
          </Card>
        </Col>
        <Col xs={24} lg={10}>
          <Card title="风险热力图" bordered={false}>
            <Heatmap
              data={heatmap}
              xField="product"
              yField="region"
              colorField="risk"
              height={300}
              color={['#e6f4ff', '#1677ff', '#ff4d4f']}
            />
          </Card>
        </Col>
      </Row>

      <Row gutter={[16, 16]} style={{ marginTop: 16 }}>
        <Col xs={24} md={14}>
          <Card title="合规拦截 Top 5" bordered={false}>
            <Column
              data={topViolations}
              xField="rule"
              yField="count"
              height={260}
              color="#ff7875"
              label={{ position: 'top' }}
            />
          </Card>
        </Col>
        <Col xs={24} md={10}>
          <Card title="服务状态" bordered={false}>
            <HealthDot services={services} />
          </Card>
        </Col>
      </Row>
    </PageContainer>
  );
}
