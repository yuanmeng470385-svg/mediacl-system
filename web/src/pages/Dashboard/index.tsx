import { useEffect, useState } from 'react';
import { Row, Col, Card, Empty } from 'antd';
import { Column, Line } from '@ant-design/charts';
import { PageContainer } from '@ant-design/pro-components';
import StatCard from '../../components/StatCard';
import { complianceAPI } from '../../services/compliance';
import { auditAPI } from '../../services/audit';
import { userAPI } from '../../services/user';

/** 仪表盘全部接真实后端接口；无数据源的口径显示空态，不再 Math.random()/硬编码 */

interface AuditStats {
  total_records: number;
  recent_records: number;
  risk_distribution: Record<string, number>;
  service_distribution: Record<string, number>;
  trend_daily: { date: string; count: number }[];
}

interface ServiceHealth {
  name: string;
  status: 'up' | 'down';
}

export default function Dashboard() {
  const [activeUsers, setActiveUsers] = useState(0);          // users 表总数
  const [conversations, setConversations] = useState(0);      // audit: action=chat_response
  const [violationRate, setViolationRate] = useState(0);      // audit: risk=high 占比
  const [auditTotal, setAuditTotal] = useState(0);            // audit: 记录总数
  const [trend, setTrend] = useState<{ date: string; count: number }[]>([]);
  const [riskDist, setRiskDist] = useState<{ level: string; count: number }[]>([]);
  const [topViolations, setTopViolations] = useState<{ rule: string; count: number }[]>([]);
  const [services, setServices] = useState<ServiceHealth[]>([]);
  const [blocksLoaded, setBlocksLoaded] = useState(false);

  useEffect(() => {
    // 用户总数（users 表）
    userAPI.list({ page: 1, page_size: 1 })
      .then((r) => setActiveUsers(r.data.data?.total ?? 0))
      .catch(() => {});

    // 对话量（审计里 chat_response 的次数）
    auditAPI.list({ operation: 'chat_response', page: 1, page_size: 1 })
      .then((r) => setConversations(r.data.data?.total ?? 0))
      .catch(() => {});

    // 审计聚合统计：违规率 / 记录总量 / 趋势 / 风险分布
    auditAPI.stats()
      .then((r) => {
        const s = r.data.data as AuditStats;
        setAuditTotal(s.total_records ?? 0);
        const high = (s.risk_distribution ?? {}).high ?? 0;
        const recent = s.recent_records ?? 0;
        setViolationRate(recent > 0 ? Number(((high / recent) * 100).toFixed(1)) : 0);
        setTrend(s.trend_daily ?? []);
        setRiskDist(Object.entries(s.risk_distribution ?? {}).map(([level, count]) => ({ level, count })));
      })
      .catch(() => {});

    // 合规拦截 Top（compliance_blocks，当前无写入方 → 空态；有数据后自动展示）
    complianceAPI.blocks({ page: 1, page_size: 100 })
      .then((r) => {
        setBlocksLoaded(true);
        const items = r.data.data?.items ?? [];
        const byRule = new Map<string, number>();
        items.forEach((b: any) => {
          const key = `${b.rule_code ?? '未知'}-${b.rule_name ?? ''}`;
          byRule.set(key, (byRule.get(key) ?? 0) + 1);
        });
        setTopViolations(
          [...byRule.entries()]
            .sort((a, b) => b[1] - a[1])
            .slice(0, 5)
            .map(([rule, count]) => ({ rule, count })),
        );
      })
      .catch(() => setBlocksLoaded(true));

    // 服务健康（网关 /health 聚合）
    fetch('/health')
      .then((resp) => resp.json())
      .then((d) => {
        if (d?.backends) {
          setServices(Object.entries(d.backends).map(([name]) => ({ name, status: 'up' as const })));
        }
      })
      .catch(() => setServices([]));
  }, []);

  return (
    <PageContainer header={{ title: '仪表盘', subTitle: '业务总览与系统监控' }}>
      <Row gutter={[16, 16]}>
        <Col xs={12} sm={6}>
          <StatCard title="用户总数" value={activeUsers} />
        </Col>
        <Col xs={12} sm={6}>
          <StatCard title="对话总量" value={conversations} />
        </Col>
        <Col xs={12} sm={6}>
          <StatCard title="高危违规率" value={violationRate} suffix="%" />
        </Col>
        <Col xs={12} sm={6}>
          <StatCard title="审计记录总量" value={auditTotal} />
        </Col>
      </Row>

      <Row gutter={[16, 16]} style={{ marginTop: 16 }}>
        <Col xs={24} lg={14}>
          <Card title="审计记录趋势（近 30 天）" variant="borderless">
            {trend.length > 0 ? (
              <Line data={trend} xField="date" yField="count" smooth height={300} color="#1677ff" />
            ) : (
              <Empty description="暂无审计数据" style={{ padding: 60 }} />
            )}
          </Card>
        </Col>
        <Col xs={24} lg={10}>
          <Card title="风险等级分布" variant="borderless">
            {riskDist.length > 0 ? (
              <Column
                data={riskDist}
                xField="level"
                yField="count"
                height={300}
                color={({ level }: any) => (level === 'high' ? '#ff4d4f' : level === 'medium' ? '#faad14' : '#1677ff')}
              />
            ) : (
              <Empty description="暂无风险数据" style={{ padding: 60 }} />
            )}
          </Card>
        </Col>
      </Row>

      <Row gutter={[16, 16]} style={{ marginTop: 16 }}>
        <Col xs={24} md={14}>
          <Card title="合规拦截 Top 5" variant="borderless">
            {blocksLoaded && topViolations.length === 0 ? (
              <Empty description="暂无拦截记录（compliance_blocks 尚未有写入方）" style={{ padding: 40 }} />
            ) : (
              topViolations.map((v, i) => (
                <div key={v.rule} style={{ display: 'flex', justifyContent: 'space-between', padding: '8px 0', borderBottom: '1px solid #f0f0f0' }}>
                  <span>{i + 1}. {v.rule}</span>
                  <b>{v.count}</b>
                </div>
              ))
            )}
          </Card>
        </Col>
        <Col xs={24} md={10}>
          <Card title="服务状态" variant="borderless">
            {services.length === 0 ? (
              <Empty description="网关不可达" style={{ padding: 40 }} />
            ) : (
              services.map((s) => (
                <div key={s.name} style={{ display: 'flex', justifyContent: 'space-between', padding: '6px 0' }}>
                  <span>{s.name}</span>
                  <span style={{ color: s.status === 'up' ? '#52c41a' : '#ff4d4f' }}>{s.status}</span>
                </div>
              ))
            )}
          </Card>
        </Col>
      </Row>
    </PageContainer>
  );
}
