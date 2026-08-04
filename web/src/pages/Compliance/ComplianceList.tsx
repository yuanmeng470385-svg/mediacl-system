import { useRef, useState, useEffect } from 'react';
import { ProTable, ModalForm, ProFormText } from '@ant-design/pro-components';
import type { ProColumns, ActionType } from '@ant-design/pro-components';
import { Button, Tag, Space, Drawer, Input, Alert, Row, Col, App } from 'antd';
import { PlusOutlined, ExperimentOutlined, ReloadOutlined } from '@ant-design/icons';
import StatCard from '../../components/StatCard';
import { complianceAPI } from '../../services/compliance';
import type { ComplianceRule } from '../../types';

const SEVERITY_COLOR: Record<string, string> = { high: 'red', medium: 'orange', low: 'blue' };

export default function ComplianceList() {
  const actionRef = useRef<ActionType>();
  const [formOpen, setFormOpen] = useState(false);
  const [editing, setEditing] = useState<ComplianceRule | null>(null);
  const [testOpen, setTestOpen] = useState(false);
  const [testContent, setTestContent] = useState('');
  const [testResult, setTestResult] = useState<{ rule: string; severity: string }[]>([]);
  const [stats, setStats] = useState({ total: 0, today_blocks: 0, block_rate: 0 });
  const { message } = App.useApp();

  useEffect(() => {
    complianceAPI.stats().then((res) => setStats(res.data.data)).catch(() => {});
  }, []);

  const columns: ProColumns<ComplianceRule>[] = [
    { title: '编码', dataIndex: 'code', width: 100 },
    { title: '名称', dataIndex: 'name', width: 160 },
    { title: '类型', dataIndex: 'type', width: 100, valueEnum: { keyword: '关键词', regex: '正则', semantic: '语义' } },
    { title: '严重程度', dataIndex: 'severity', width: 100, render: (_, r) => <Tag color={SEVERITY_COLOR[r.severity]}>{r.severity}</Tag> },
    { title: '动作', dataIndex: 'action', width: 100, valueEnum: { reject: '拒绝', warn: '警告', log: '仅记录' } },
    { title: '匹配模式', dataIndex: 'pattern', width: 200, ellipsis: true },
    { title: '拦截次数', dataIndex: 'block_count', width: 100, sorter: true },
    { title: '状态', dataIndex: 'enabled', width: 80, render: (_, r) => <Tag color={r.enabled ? 'green' : 'default'}>{r.enabled ? '启用' : '停用'}</Tag> },
    {
      title: '操作', width: 150,
      render: (_, r) => (
        <Space>
          <a onClick={() => { setEditing(r); setFormOpen(true); }}>编辑</a>
          <a style={{ color: '#ff4d4f' }} onClick={() => { complianceAPI.delete(r.id).then(() => actionRef.current?.reload()); }}>删除</a>
        </Space>
      ),
    },
  ];

  return (
    <>
      <Row gutter={[16, 16]} style={{ marginBottom: 16 }}>
        <Col span={8}><StatCard title="启用规则" value={stats.total} /></Col>
        <Col span={8}><StatCard title="今日拦截" value={stats.today_blocks} trend="up" trendValue="12%" /></Col>
        <Col span={8}><StatCard title="拦截率" value={`${stats.block_rate}%`} /></Col>
      </Row>
      <ProTable<ComplianceRule>
        headerTitle="合规规则"
        actionRef={actionRef}
        columns={columns}
        request={async (params) => {
          const res = await complianceAPI.list({ page: params.current || 1, page_size: params.pageSize || 10, type: params.type, severity: params.severity });
          return { data: res.data.data.items, total: res.data.data.total, success: true };
        }}
        rowKey="id"
        search={{ labelWidth: 80 }}
        toolBarRender={() => [
          <Button key="test" icon={<ExperimentOutlined />} onClick={() => setTestOpen(true)}>规则测试</Button>,
          <Button key="reload" icon={<ReloadOutlined />} onClick={() => { complianceAPI.reload(); message.success('规则已热更新'); }}>热更新</Button>,
          <Button key="add" type="primary" icon={<PlusOutlined />} onClick={() => { setEditing(null); setFormOpen(true); }}>新增规则</Button>,
        ]}
      />
      <ModalForm title={editing ? '编辑规则' : '新增规则'} open={formOpen} onOpenChange={setFormOpen}
        onFinish={async (values) => {
          if (editing) await complianceAPI.update(editing.id, values);
          else await complianceAPI.create(values);
          message.success(`${editing ? '编辑' : '新增'}成功`);
          actionRef.current?.reload();
          return true;
        }}
        initialValues={editing || undefined}>
        <ProFormText name="code" label="规则编码" rules={[{ required: true }]} />
        <ProFormText name="name" label="规则名称" rules={[{ required: true }]} />
        <ProFormText name="pattern" label="匹配模式" rules={[{ required: true }]} />
      </ModalForm>
      <Drawer title="规则测试" open={testOpen} onClose={() => { setTestOpen(false); setTestResult([]); setTestContent(''); }} width={480}>
        <Input.TextArea rows={4} value={testContent} onChange={(e) => setTestContent(e.target.value)} placeholder="输入测试内容..." />
        <Button type="primary" style={{ marginTop: 12 }} onClick={async () => {
          const res = await complianceAPI.test(testContent);
          setTestResult(res.data.data.hits);
        }}>测试</Button>
        {testResult.length > 0 && (
          <div style={{ marginTop: 16 }}>
            {testResult.map((r, i) => (
              <Alert key={i} type="warning" showIcon message={`命中规则: ${r.rule}`} description={`严重程度: ${r.severity}`} style={{ marginBottom: 8 }} />
            ))}
          </div>
        )}
      </Drawer>
    </>
  );
}
