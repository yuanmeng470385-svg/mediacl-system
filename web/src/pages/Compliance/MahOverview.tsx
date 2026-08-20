import { useEffect, useState } from 'react';
import { Button, Card, Col, Row, Space, Statistic, Tag } from 'antd';
import { specialistAPI } from '../../services/specialist';
import type { MahOverview } from '../../types';

/** 0-1 小数转百分数展示（后端 rate 口径同 CardStats.read_rate） */
const percent = (v: number | undefined | null) =>
  (v === undefined || v === null ? 0 : v * 100).toFixed(1) + '%';

const FILING_MAP: Record<string, { color: string; text: string }> = {
  valid: { color: 'green', text: '有效' },
  expired: { color: 'red', text: '已过期' },
  not_filed: { color: 'default', text: '未备案' },
  pending_review: { color: 'orange', text: '待审核' },
  rejected: { color: 'magenta', text: '已驳回' },
};

export default function MahOverview() {
  const [data, setData] = useState<MahOverview | null>(null);
  const [refresh, setRefresh] = useState(0);

  useEffect(() => {
    specialistAPI.mahOverview().then(r => setData(r.data.data)).catch(() => {});
  }, [refresh]);

  const filing = data?.filing;
  const filingItems = filing
    ? ([
        ['valid', filing.valid],
        ['expired', filing.expired],
        ['not_filed', filing.not_filed],
        ['pending_review', filing.pending_review],
        ['rejected', filing.rejected],
      ] as const)
    : [];

  return (
    <div>
      <Row gutter={16}>
        <Col span={6}>
          <Card>
            <Statistic title="总代表数" value={data?.total_reps ?? 0} />
          </Card>
        </Col>
        <Col span={6}>
          <Card>
            <Statistic title="合规通过率" value={percent(data?.compliance_pass_rate)} />
          </Card>
        </Col>
        <Col span={6}>
          <Card>
            <Statistic title="培训完成率" value={percent(data?.training_completed_rate)} />
          </Card>
        </Col>
        <Col span={6}>
          <Card>
            <Statistic title="承诺签署率" value={percent(data?.commitment_signed_rate)} />
          </Card>
        </Col>
      </Row>

      <Card
        title="备案分布"
        style={{ marginTop: 16 }}
        extra={<Button size="small" onClick={() => setRefresh(r => r + 1)}>刷新</Button>}
      >
        <Space size="large" wrap>
          {filingItems.map(([key, count]) => {
            const m = FILING_MAP[key] || { color: 'default', text: key };
            return (
              <span key={key}>
                <Tag color={m.color}>{m.text}</Tag>
                <Statistic value={count} style={{ display: 'inline-block', marginLeft: 8, minWidth: 60 }} />
              </span>
            );
          })}
        </Space>
      </Card>
    </div>
  );
}
