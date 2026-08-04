import { Tag } from 'antd';

const STATUS_COLOR: Record<string, string> = {
  pending: 'orange',
  approved: 'blue',
  rejected: 'red',
  published: 'green',
  expired: 'default',
};

interface Props {
  status: string;
  labels?: Record<string, string>;
}

export default function StatusTag({ status, labels }: Props) {
  const defaultLabels: Record<string, string> = {
    pending: '待审核', approved: '已审核', rejected: '已驳回',
    published: '已上线', expired: '已过期',
  };
  const labelMap = labels || defaultLabels;
  return (
    <Tag color={STATUS_COLOR[status] || 'default'}>
      {labelMap[status] || status}
    </Tag>
  );
}
