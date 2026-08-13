import { useRef, useState, useEffect } from 'react';
import {
  ProTable, ModalForm, ProFormText, ProFormTextArea, ProFormSelect, ProFormSwitch, ProFormDependency,
} from '@ant-design/pro-components';
import type { ProColumns, ActionType } from '@ant-design/pro-components';
import { Button, Tag, Space, Drawer, Input, Alert, Row, Col, App } from 'antd';
import { PlusOutlined, ExperimentOutlined, ReloadOutlined } from '@ant-design/icons';
import StatCard from '../../components/StatCard';
import { complianceAPI } from '../../services/compliance';
import type { ComplianceRule, ComplianceStats, RuleTestHit } from '../../types';

const SEVERITY_COLOR: Record<string, string> = { high: 'red', medium: 'orange', low: 'blue' };
const SEVERITY_TEXT: Record<string, string> = { high: '高', medium: '中', low: '低' };
const ACTION_TEXT: Record<string, string> = { reject: '拒绝', warn: '警告', log: '仅记录' };
const RULE_TYPE_TEXT: Record<string, string> = { keyword: '关键词', regex: '正则', semantic: '语义' };

export default function ComplianceList() {
  const actionRef = useRef<ActionType>();
  const [formOpen, setFormOpen] = useState(false);
  const [editing, setEditing] = useState<ComplianceRule | null>(null);
  const [testOpen, setTestOpen] = useState(false);
  const [testContent, setTestContent] = useState('');
  const [testing, setTesting] = useState(false);
  const [testResult, setTestResult] = useState<RuleTestHit[]>([]);
  const [testTotal, setTestTotal] = useState(0);
  const [stats, setStats] = useState<ComplianceStats>({ total_rules: 0, enabled_rules: 0, loaded_memory_rules: 0 });
  const { message } = App.useApp();

  const refreshStats = () => {
    complianceAPI.stats().then((res) => setStats(res.data.data)).catch(() => {});
  };

  useEffect(() => {
    refreshStats();
  }, []);

  const handleReload = async () => {
    try {
      const res = await complianceAPI.reload();
      message.success(`规则热更新完成，共加载 ${res.data.data?.reloaded_rules ?? 0} 条`);
      actionRef.current?.reload();
    } catch {
      // 失败 toast 由全局拦截器统一弹，此处不重复弹（避免双弹）
    }
  };

  const columns: ProColumns<ComplianceRule>[] = [
    { title: '编码', dataIndex: 'rule_code', width: 110, hideInSearch: true },
    { title: '名称', dataIndex: 'rule_name', width: 180, hideInSearch: true },
    {
      title: '类型', dataIndex: 'rule_type', width: 100,
      valueEnum: { keyword: '关键词', regex: '正则', semantic: '语义' },
      render: (_, r) => <Tag color="blue">{RULE_TYPE_TEXT[r.rule_type] || r.rule_type}</Tag>,
    },
    {
      title: '严重程度', dataIndex: 'severity', width: 100, hideInSearch: true,
      render: (_, r) => <Tag color={SEVERITY_COLOR[r.severity]}>{SEVERITY_TEXT[r.severity] || r.severity}</Tag>,
    },
    {
      title: '动作', dataIndex: 'action', width: 100, hideInSearch: true,
      valueEnum: { reject: '拒绝', warn: '警告', log: '仅记录' },
      render: (_, r) => <Tag>{ACTION_TEXT[r.action] || r.action}</Tag>,
    },
    {
      title: '匹配模式', dataIndex: 'content', width: 220, ellipsis: true, hideInSearch: true,
      render: (_, r) => (r.content?.patterns?.length ? r.content.patterns.join('、') : '-'),
    },
    { title: '描述', dataIndex: 'description', width: 200, ellipsis: true, hideInSearch: true, render: (_, r) => r.description || '-' },
    {
      title: '状态', dataIndex: 'enabled', width: 90,
      valueEnum: { true: '启用', false: '停用' },
      render: (_, r) => <Tag color={r.enabled ? 'green' : 'default'}>{r.enabled ? '启用' : '停用'}</Tag>,
    },
    {
      title: '操作', width: 140, hideInSearch: true,
      render: (_, r) => (
        <Space>
          <a onClick={() => { setEditing(r); setFormOpen(true); }}>编辑</a>
          <a
            style={{ color: '#ff4d4f' }}
            onClick={async () => {
              try {
                await complianceAPI.delete(r.id);
                message.success('规则已禁用');
                actionRef.current?.reload();
              } catch {
                // 失败 toast 由全局拦截器统一弹，此处不重复弹（避免双弹）
              }
            }}
          >删除</a>
        </Space>
      ),
    },
  ];

  return (
    <>
      <Row gutter={[16, 16]} style={{ marginBottom: 16 }}>
        <Col span={8}><StatCard title="规则总数" value={stats.total_rules} /></Col>
        <Col span={8}><StatCard title="启用规则" value={stats.enabled_rules} /></Col>
        <Col span={8}><StatCard title="内存加载规则" value={stats.loaded_memory_rules} /></Col>
      </Row>
      <ProTable<ComplianceRule>
        headerTitle="合规规则"
        actionRef={actionRef}
        columns={columns}
        request={async (params) => {
          // 筛选参数对齐后端：rule_type / enabled（后端不识别 type/severity）
          const enabled = params.enabled === undefined || params.enabled === null || params.enabled === ''
            ? undefined
            : params.enabled === true || params.enabled === 'true';
          const res = await complianceAPI.list({
            page: params.current || 1,
            page_size: params.pageSize || 10,
            rule_type: params.rule_type || undefined,
            enabled,
          });
          return { data: res.data.data.items, total: res.data.data.total, success: true };
        }}
        rowKey="id"
        search={{ labelWidth: 80 }}
        toolBarRender={() => [
          <Button key="test" icon={<ExperimentOutlined />} onClick={() => setTestOpen(true)}>规则测试</Button>,
          <Button key="reload" icon={<ReloadOutlined />} onClick={handleReload}>热更新</Button>,
          <Button key="add" type="primary" icon={<PlusOutlined />} onClick={() => { setEditing(null); setFormOpen(true); }}>新增规则</Button>,
        ]}
      />
      <ModalForm
        title={editing ? '编辑规则' : '新增规则'}
        open={formOpen}
        onOpenChange={setFormOpen}
        key={editing ? `edit-${editing.id}` : 'create'}
        modalProps={{ destroyOnHidden: true }}
        initialValues={editing ? {
          ...editing,
          patterns_text: (editing.content?.patterns || []).join('\n'),
        } : { rule_type: 'keyword', severity: 'high', action: 'reject', enabled: true }}
        onFinish={async (values) => {
          const patterns = (values.patterns_text || '')
            .split(/\r?\n|[,，、]/)
            .map((s: string) => s.trim())
            .filter((s: string) => s.length > 0);
          const payload: Partial<ComplianceRule> = {
            rule_name: values.rule_name,
            rule_type: values.rule_type,
            severity: values.severity,
            action: values.action,
            description: values.description || '',
            enabled: values.enabled,
          };
          // 语义规则（R003-R007 等）无匹配模式，后端 _validate_rule_fields 只要求
          // keyword/regex 提供非空 patterns，且空数组一律 400 —— patterns 为空时整体省略 content
          if (patterns.length) payload.content = { patterns };
          try {
            if (editing) {
              await complianceAPI.update(editing.id, payload);
            } else {
              await complianceAPI.create({ rule_code: values.rule_code, ...payload });
            }
            message.success(`${editing ? '编辑' : '新增'}成功`);
            actionRef.current?.reload();
            refreshStats();
            return true;
          } catch {
            return false; // 保持弹窗打开，便于修正后重提；失败 toast 由全局拦截器统一弹
          }
        }}
      >
        <ProFormText
          name="rule_code" label="规则编码" disabled={!!editing}
          rules={[{ required: true, message: '请输入规则编码' }]}
          placeholder="如 R101" fieldProps={{ maxLength: 50 }}
        />
        <ProFormText name="rule_name" label="规则名称" rules={[{ required: true, message: '请输入规则名称' }]} />
        <ProFormSelect
          name="rule_type" label="规则类型" rules={[{ required: true, message: '请选择规则类型' }]}
          options={[
            { value: 'keyword', label: '关键词' },
            { value: 'regex', label: '正则' },
            { value: 'semantic', label: '语义' },
          ]}
        />
        <ProFormSelect
          name="severity" label="严重程度" rules={[{ required: true, message: '请选择严重程度' }]}
          options={[
            { value: 'high', label: '高' },
            { value: 'medium', label: '中' },
            { value: 'low', label: '低' },
          ]}
        />
        <ProFormSelect
          name="action" label="动作" rules={[{ required: true, message: '请选择动作' }]}
          options={[
            { value: 'reject', label: '拒绝（拦截）' },
            { value: 'warn', label: '警告' },
            { value: 'log', label: '仅记录' },
          ]}
        />
        {/* 语义规则（R003-R007 等）无匹配模式：semantic 时隐藏且非必填；keyword/regex 仍必填 */}
        <ProFormDependency name={['rule_type']}>
          {({ rule_type }) => {
            const isSemantic = rule_type === 'semantic';
            return (
              <ProFormTextArea
                name="patterns_text" label="匹配模式"
                hidden={isSemantic}
                rules={isSemantic ? [] : [{ required: true, message: '请输入匹配模式' }]}
                placeholder={'每行一个匹配词或正则，例如：\n包治百病\n100%有效'}
              />
            );
          }}
        </ProFormDependency>
        <ProFormTextArea name="description" label="描述" placeholder="规则说明（语义规则建议填写，供 AI 审核参考）" />
        <ProFormSwitch name="enabled" label="启用" />
      </ModalForm>
      <Drawer title="规则测试" open={testOpen} onClose={() => { setTestOpen(false); setTestResult([]); setTestContent(''); }} width={480}>
        <Input.TextArea rows={4} value={testContent} onChange={(e) => setTestContent(e.target.value)} placeholder="输入测试内容..." />
        <Button
          type="primary" style={{ marginTop: 12 }} loading={testing}
          onClick={async () => {
            if (!testContent.trim()) {
              message.warning('请输入测试内容');
              return;
            }
            try {
              setTesting(true);
              const res = await complianceAPI.test(testContent);
              setTestResult(res.data.data.hits);
              setTestTotal(res.data.data.total_rules_tested);
            } catch {
              // 失败 toast 由全局拦截器统一弹，此处不重复弹（避免双弹）
            } finally {
              setTesting(false);
            }
          }}
        >测试</Button>
        {testResult.length > 0 && (
          <div style={{ marginTop: 16 }}>
            {testResult.filter((r) => r.hit).map((r, i) => (
              <Alert
                key={i} type="warning" showIcon style={{ marginBottom: 8 }}
                message={`${r.rule_code} ${r.rule_name}（${RULE_TYPE_TEXT[r.rule_type] || r.rule_type}）`}
                description={
                  <span>
                    严重程度: {SEVERITY_TEXT[r.severity] || r.severity}　动作: {ACTION_TEXT[r.action] || r.action}
                    {r.matched_text ? <div>命中文本: {r.matched_text}</div> : null}
                  </span>
                }
              />
            ))}
            {!testResult.some((r) => r.hit) && (
              <Alert type="success" showIcon message={`未命中任何规则（共测试 ${testTotal} 条规则）`} />
            )}
          </div>
        )}
      </Drawer>
    </>
  );
}
