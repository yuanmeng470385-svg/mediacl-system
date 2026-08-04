import { Card, Statistic } from 'antd';
import { ArrowUpOutlined, ArrowDownOutlined } from '@ant-design/icons';

interface Props {
  title: string;
  value: number | string;
  suffix?: string;
  trend?: 'up' | 'down';
  trendValue?: string;
}

export default function StatCard({ title, value, suffix, trend, trendValue }: Props) {
  return (
    <Card bordered={false}>
      <Statistic
        title={title}
        value={value}
        suffix={suffix}
        valueStyle={{ fontSize: 28, fontWeight: 700 }}
      />
      {trend && (
        <span style={{ color: trend === 'up' ? '#52c41a' : '#ff4d4f', fontSize: 13 }}>
          {trend === 'up' ? <ArrowUpOutlined /> : <ArrowDownOutlined />}
          {' '}{trendValue}
        </span>
      )}
    </Card>
  );
}
