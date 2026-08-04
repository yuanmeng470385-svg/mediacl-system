import { useRef } from 'react';
import { ProTable } from '@ant-design/pro-components';
import type { ProColumns, ActionType } from '@ant-design/pro-components';
import { Button, Tag, Row, Col, App } from 'antd';
import { ExportOutlined } from '@ant-design/icons';
import StatCard from '../../components/StatCard';
import { auditAPI } from '../../services/audit';
import type { AuditLog } from '../../types';
import dayjs from 'dayjs';

const RISK_COLOR: Record<string, string> = { high: 'red', medium: 'orange', low: 'green' };

export default function AuditList() {
  const actionRef = useRef<ActionType>();
  const { message } = App.useApp();

  const columns: ProColumns<AuditLog>[] = [
    { title: '时间', dataIndex: 'timestamp', width: 170,
      render: (_, r) => dayjs(r.timestamp).format('YYYY-MM-DD HH:mm:ss'), valueType: 'dateTime' },
    { title: '用户', dataIndex: 'username', width: 120 },
    { title: '服务', dataIndex: 'service', width: 120 },
    { title: '操作', dataIndex: 'operation', width: 140 },
    { title: '风险等级', dataIndex: 'risk_level', width: 100,
      render: (_, r) => <Tag color={RISK_COLOR[r.risk_level]}>{r.risk_level}</Tag> },
    { title: 'IP', dataIndex: 'ip', width: 140 },
  ];

  return (
    <>
      <Row gutter={[16, 16]} style={{ marginBottom: 16 }}>
        <Col span={12}><StatCard title="总记录数" value="15,832" /></Col>
        <Col span={12}><StatCard title="命中规则数" value="423" /></Col>
      </Row>
      <ProTable<AuditLog>
        headerTitle="审计日志"
        actionRef={actionRef}
        columns={columns}
        request={async (params) => {
          const res = await auditAPI.list({
            page: params.current || 1, page_size: params.pageSize || 10,
            start_date: params.start_date, end_date: params.end_date,
            user_id: params.user_id, service: params.service,
            operation: params.operation, risk_level: params.risk_level,
          });
          return { data: res.data.data.items, total: res.data.data.total, success: true };
        }}
        rowKey="id"
        search={{ labelWidth: 80, defaultCollapsed: false }}
        expandable={{
          expandedRowRender: () => (
            <div style={{ padding: '8px 0' }}>
              <p>对话内容（哈希）: sha256:abc123...</p>
              <p>合规检查结果: 通过</p>
            </div>
          ),
        }}
        toolBarRender={() => [
          <Button key="export" icon={<ExportOutlined />} onClick={async () => {
            await auditAPI.export(); message.success('导出已开始');
          }}>导出 Excel</Button>,
        ]}
        dateFormatter="string"
      />
    </>
  );
}
