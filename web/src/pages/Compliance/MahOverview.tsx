import { useEffect, useState } from 'react';
import { App, Button, Card, Col, Row, Space, Statistic, Tag } from 'antd';
import { FileExcelOutlined, ReloadOutlined } from '@ant-design/icons';
import dayjs from 'dayjs';
import { specialistAPI } from '../../services/specialist';
import { complianceAPI } from '../../services/compliance';
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
  const [exporting, setExporting] = useState(false);
  const { message } = App.useApp();

  useEffect(() => {
    specialistAPI.mahOverview().then(r => setData(r.data.data)).catch(() => {});
  }, [refresh]);

  /** 监管自查报告导出（近 30 天口径，POST /compliance/report/export 返回 xlsx blob） */
  const handleExport = async () => {
    setExporting(true);
    try {
      const res = await complianceAPI.exportReport({
        start_time: dayjs().subtract(30, 'day').startOf('day').toISOString(),
        end_time: dayjs().endOf('day').toISOString(),
      });
      const blob = res.data;
      if (!(blob instanceof Blob) || blob.size === 0) {
        message.error('导出失败，请稍后重试');
        return;
      }
      const url = URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = `compliance_self_inspection_${dayjs().format('YYYYMMDD_HHMMSS')}.xlsx`;
      document.body.appendChild(a);
      a.click();
      a.remove();
      URL.revokeObjectURL(url);
      message.success('监管自查报告已导出');
    } catch {
      // HTTP 错误由全局拦截器统一弹 toast，此处不重复弹
    } finally {
      setExporting(false);
    }
  };

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
      <Space style={{ marginBottom: 16 }}>
        <Button icon={<FileExcelOutlined />} loading={exporting} onClick={handleExport}>
          导出监管自查报告（近 30 天）
        </Button>
        <Button icon={<ReloadOutlined />} onClick={() => setRefresh(r => r + 1)}>
          刷新
        </Button>
      </Space>
      <Row gutter={16}>
        <Col span={6}>
          <Card>
            <Statistic title="总代表数" value={data?.total_reps ?? 0} />
          </Card>
        </Col>
        <Col span={6}>
          <Card>
            <Statistic title="合规通过率" value={percent(data?.compliance_pass_rate)} />
            {/* 口径见 mah-overview 后端：1 − 分身对话 blocked 比例；无对话时记 1.0（无数据≠真实 100%） */}
            <div style={{ fontSize: 12, color: '#999', marginTop: 4 }}>口径：分身对话未被拦截占比，无对话时段记为 100%</div>
          </Card>
        </Col>
        <Col span={6}>
          <Card>
            <Statistic title="培训完成率" value={percent(data?.training_completed_rate)} />
            {/* 分母=总代表数（含未备案代表），非已备案代表 */}
            <div style={{ fontSize: 12, color: '#999', marginTop: 4 }}>分母：全部代表（含未备案）</div>
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
