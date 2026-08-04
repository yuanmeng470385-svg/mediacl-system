import { Badge, Space } from 'antd';

interface Props {
  services: { name: string; status: 'up' | 'down' }[];
}

export default function HealthDot({ services }: Props) {
  return (
    <Space direction="vertical" size="small">
      {services.map((s) => (
        <Badge
          key={s.name}
          status={s.status === 'up' ? 'success' : 'error'}
          text={`${s.name}: ${s.status === 'up' ? '正常' : '异常'}`}
        />
      ))}
    </Space>
  );
}
