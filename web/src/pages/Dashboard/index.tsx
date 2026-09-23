import { useEffect, useMemo, useRef, useState } from 'react';
import { Row, Col, Card, Empty, Switch, Button, Space, Tag, Tooltip } from 'antd';
import { Column, Line, Heatmap } from '@ant-design/charts';
import { ReloadOutlined, ThunderboltOutlined } from '@ant-design/icons';
import { PageContainer } from '@ant-design/pro-components';
import StatCard from '../../components/StatCard';
import LiveStatusStrip from '../../components/LiveStatusStrip';
import { complianceAPI } from '../../services/compliance';
import { auditAPI } from '../../services/audit';
import { userAPI } from '../../services/user';
import type { AuditLog } from '../../types';
import dayjs from 'dayjs';
import utc from 'dayjs/plugin/utc';
import { getBrand } from '../../brand';

dayjs.extend(utc);

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

const ACTION_TEXT: Record<string, string> = {
  chat_response: 'AI 对话',
  login: '登录',
  logout: '登出',
  user_create: '新增用户',
  user_update: '编辑用户',
  rule_create: '新增规则',
  rule_update: '编辑规则',
  rule_disable: '禁用规则',
  rules_reload: '规则热更新',
  specialist_create: '新增专员',
  specialist_update: '编辑专员',
  specialist_disable: '停用专员',
  audit_report_export: '导出审计报告',
};

function actionText(action: string): string {
  return ACTION_TEXT[action] ?? action;
}

/** 实时动态条目：时间 / 用户 / 操作类型 / 服务 */
function RealtimeFeed({ logs, userMap }: { logs: AuditLog[]; userMap: Map<string, string> }) {
  if (logs.length === 0) {
    return <Empty description="暂无审计动态" style={{ padding: 30 }} />;
  }
  return (
    <div style={{ maxHeight: 300, overflowY: 'auto' }}>
      {logs.map((log) => (
        <div
          key={log.id}
          style={{ display: 'flex', alignItems: 'center', gap: 8, padding: '7px 0', borderBottom: '1px solid #f0f0f0' }}
        >
          <ThunderboltOutlined style={{ color: '#1677ff', fontSize: 12 }} />
          <span style={{ fontSize: 12, color: '#8c8c8c', flexShrink: 0 }}>
            {log.timestamp ? dayjs.utc(log.timestamp).local().format('MM-DD HH:mm:ss') : '—'}
          </span>
          <span style={{ fontSize: 13, flexShrink: 0 }}>
            {log.user_id != null ? (userMap.get(String(log.user_id)) ?? `用户 #${log.user_id}`) : '系统'}
          </span>
          <span style={{ fontSize: 13, flex: 1, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
            {actionText(log.action ?? '')}
          </span>
          <Tag style={{ flexShrink: 0, marginInlineEnd: 0 }}>{log.service_name ?? '—'}</Tag>
        </div>
      ))}
    </div>
  );
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

  // 热力图：区域 × 近 7 天 合规拦截量
  const [heatmapData, setHeatmapData] = useState<{ region: string; date: string; count: number }[]>([]);
  const [heatmapDimension, setHeatmapDimension] = useState<'region' | 'service' | null>(null);

  // 实时动态：审计日志倒序 10 条
  const [realtimeLogs, setRealtimeLogs] = useState<AuditLog[]>([]);
  const [autoPoll, setAutoPoll] = useState(true);
  const [realtimeLoading, setRealtimeLoading] = useState(false);
  const [userMap, setUserMap] = useState<Map<string, string>>(new Map());
  const timerRef = useRef<number | null>(null);

  const loadRealtime = async () => {
    try {
      setRealtimeLoading(true);
      const res = await auditAPI.list({ page: 1, page_size: 10 });
      setRealtimeLogs(res.data.data.items ?? []);
    } catch {
      /* 轮询失败静默，保持上一次数据 */
    } finally {
      setRealtimeLoading(false);
    }
  };

  useEffect(() => {
    // 用户总数（users 表）
    userAPI.list({ page: 1, page_size: 1 })
      .then((r) => setActiveUsers(r.data.data?.total ?? 0))
      .catch(() => {});

    // 用户 ID → 姓名映射（实时动态 / 拦截记录页展示用）
    userAPI.list({ page: 1, page_size: 100 })
      .then((r) => {
        const map = new Map<string, string>();
        (r.data.data?.items ?? []).forEach((u: any) => map.set(String(u.id), u.full_name || u.username));
        setUserMap(map);
      })
      .catch(() => {});

    // 对话量（审计里 chat_response 的次数，后端筛选参数是 action）
    auditAPI.list({ action: 'chat_response', page: 1, page_size: 1 })
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

    // 合规拦截 Top（compliance_blocks：流式答案门禁 full 复核 / 实时转写拦截时写入）
    complianceAPI.blocks({ page: 1, page_size: 100 })
      .then((r) => {
        setBlocksLoaded(true);
        const items = r.data.data?.items ?? [];
        const byRule = new Map<string, number>();
        items.forEach((b) => {
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

    // 热力图：区域 × 近 7 天拦截量（后端 join users；降级 service 维度时前端标注）
    complianceAPI.blocksStats({ days: 7 })
      .then((r) => {
        setHeatmapData(r.data.data?.items ?? []);
        setHeatmapDimension(r.data.data?.dimension ?? null);
      })
      .catch(() => setHeatmapData([]));

    // 服务健康（网关 /health 聚合，vite 代理 /health → 网关；M46 真探活 status）
    fetch('/health')
      .then((resp) => resp.json())
      .then((d) => {
        if (d?.services) {
          setServices(
            Object.entries(d.services).map(([name, status]) => ({
              name,
              status: status === 'up' ? ('up' as const) : ('down' as const),
            })),
          );
        } else {
          setServices([]);
        }
      })
      .catch(() => setServices([]));

    return () => {
      if (timerRef.current !== null) window.clearInterval(timerRef.current);
    };
  }, []);

  // 实时动态：首次加载 + 5 秒轮询（开关可关）
  useEffect(() => {
    loadRealtime();
    if (autoPoll) {
      timerRef.current = window.setInterval(loadRealtime, 5000);
    } else if (timerRef.current !== null) {
      window.clearInterval(timerRef.current);
      timerRef.current = null;
    }
    return () => {
      if (timerRef.current !== null) window.clearInterval(timerRef.current);
    };
  }, [autoPoll]);

  const heatmapChart = useMemo(
    () => (heatmapData.length > 0 ? (
      <Heatmap
        data={heatmapData}
        xField="date"
        yField="region"
        colorField="count"
        height={300}
        tooltip={{ title: (d: any) => `${d.region} · ${d.date}` }}
      />
    ) : null),
    [heatmapData],
  );

  return (
    <PageContainer header={{ title: '仪表盘', subTitle: `${getBrand().name} · 业务总览与系统监控` }}>
      <LiveStatusStrip />
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
        <Col xs={24} lg={14}>
          <Card
            title="风险热力图（区域 × 近 7 天拦截量）"
            variant="borderless"
            extra={heatmapDimension === 'service' ? (
              <Tooltip title="用户表不可达，已按服务维度兜底聚合">
                <Tag color="orange">服务维度兜底</Tag>
              </Tooltip>
            ) : null}
          >
            {heatmapChart ?? <Empty description="暂无拦截数据" style={{ padding: 60 }} />}
          </Card>
        </Col>
        <Col xs={24} lg={10}>
          <Card
            title="实时动态"
            variant="borderless"
            extra={
              <Space size={8}>
                <span style={{ fontSize: 12, color: '#8c8c8c' }}>5s 自动刷新</span>
                <Switch size="small" checked={autoPoll} onChange={setAutoPoll} />
                <Button
                  size="small" icon={<ReloadOutlined />} loading={realtimeLoading}
                  onClick={loadRealtime}
                >刷新</Button>
              </Space>
            }
          >
            <RealtimeFeed logs={realtimeLogs} userMap={userMap} />
          </Card>
        </Col>
      </Row>

      <Row gutter={[16, 16]} style={{ marginTop: 16 }}>
        <Col xs={24} md={14}>
          <Card title="合规拦截 Top 5" variant="borderless">
            {blocksLoaded && topViolations.length === 0 ? (
              <Empty description="暂无拦截记录" style={{ padding: 40 }} />
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
