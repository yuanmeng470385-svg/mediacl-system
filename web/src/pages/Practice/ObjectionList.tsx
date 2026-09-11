import { useEffect, useRef, useState } from 'react';
import { ProTable } from '@ant-design/pro-components';
import type { ProColumns, ActionType } from '@ant-design/pro-components';
import { App, AutoComplete, Button, Checkbox, Descriptions, Drawer, Form, Input, Modal, Radio, Space, Tag, Typography } from 'antd';
import { practiceAPI } from '../../services/practice';
import type { ObjectionScript } from '../../types';

const { Text } = Typography;
const STATUS_MAP: Record<string, { color: string; text: string }> = {
  pending: { color: 'orange', text: '待审核' },
  approved: { color: 'green', text: '已通过' },
  rejected: { color: 'red', text: '已驳回' },
};
/** 场景预设（陪练 create scenario 同款口径，仅快捷输入不作枚举限制） */
const SCENARIO_PRESETS = ['心内科推广', '肿瘤科推广', '内分泌科推广', '呼吸科推广', '神内科推广'];

/** AI 草稿条目（生成/提取后可编辑，勾选入库） */
interface DraftItem {
  checked: boolean;
  scenario_type: string;
  objection_content: string;
  response_guidance: string | null;
}

/** 异议话术库页（3.2(5)）：2026-09-01 审核盲审修复批建页（审核流）；
 * 2026-09-10 异议话术批扩创建/编辑 + AI 起草 + 真实数据提取（草稿均不落库，确认后逐条入库送审）。 */
export default function ObjectionList() {
  const actionRef = useRef<ActionType>();
  const { message } = App.useApp();
  const [current, setCurrent] = useState<ObjectionScript | null>(null);
  const [verdict, setVerdict] = useState<'approve' | 'reject'>('approve');
  const [reason, setReason] = useState('');
  const [submitting, setSubmitting] = useState(false);

  // 新建 / 编辑（2026-09-10）：编辑仅 pending/rejected 可改，保存后重置 pending 重新送审
  const [form] = Form.useForm();
  const [formModal, setFormModal] = useState<{ mode: 'create' } | { mode: 'edit'; row: ObjectionScript } | null>(null);
  const [formSaving, setFormSaving] = useState(false);

  // AI 起草 / 真实数据提取（2026-09-10）：同步 LLM 慢链（网关 120s），草稿无状态不落库
  const [draftOpen, setDraftOpen] = useState(false);
  const [draftMode, setDraftMode] = useState<'ai' | 'extract'>('ai');
  const [draftScenario, setDraftScenario] = useState('');
  const [draftItems, setDraftItems] = useState<DraftItem[]>([]);
  const [draftGenerating, setDraftGenerating] = useState(false);
  const [draftSaving, setDraftSaving] = useState(false);

  useEffect(() => {
    if (formModal?.mode === 'edit') {
      form.setFieldsValue({
        scenario_type: formModal.row.scenario_type,
        objection_content: formModal.row.objection_content,
        response_guidance: formModal.row.response_guidance || '',
        version: formModal.row.version || '1.0',
      });
    } else if (formModal?.mode === 'create') {
      form.resetFields();
    }
  }, [formModal, form]);

  const openReview = (row: ObjectionScript) => {
    setCurrent(row);
    setVerdict('approve');
    setReason('');
  };

  const submitReview = async () => {
    if (!current) return;
    if (verdict === 'reject' && !reason.trim()) {
      message.warning('驳回必须填写原因');
      return;
    }
    setSubmitting(true);
    try {
      await practiceAPI.objectionReview(current.id, {
        verdict,
        reason: verdict === 'reject' ? reason.trim() : undefined,
      });
      message.success('审核完成');
      setCurrent(null);
      actionRef.current?.reload();
    } catch {
      /* client.ts 拦截器已弹错误 */
    } finally {
      setSubmitting(false);
    }
  };

  const submitForm = async () => {
    const values = await form.validateFields();
    setFormSaving(true);
    try {
      const payload = {
        scenario_type: values.scenario_type.trim(),
        objection_content: values.objection_content,
        response_guidance: values.response_guidance?.trim() || undefined,
        version: values.version?.trim() || '1.0',
      };
      if (formModal?.mode === 'edit') {
        await practiceAPI.objectionUpdate(formModal.row.id, payload);
        message.success('已保存并重新送审');
      } else {
        await practiceAPI.objectionCreate(payload);
        message.success('已创建，进入待审核');
      }
      setFormModal(null);
      actionRef.current?.reload();
    } catch {
      /* 校验失败/拦截器已弹错误 */
    } finally {
      setFormSaving(false);
    }
  };

  const openDraft = (mode: 'ai' | 'extract') => {
    setDraftMode(mode);
    setDraftItems([]);
    setDraftScenario(mode === 'ai' ? '心内科推广' : '');
    setDraftOpen(true);
  };

  const generateDrafts = async () => {
    setDraftGenerating(true);
    try {
      let items: DraftItem[];
      if (draftMode === 'ai') {
        const res = await practiceAPI.objectionAiGenerate(draftScenario.trim());
        items = (res.data.data.items || []).map((i) => ({
          checked: true, scenario_type: i.scenario_type, objection_content: i.objection_content,
          response_guidance: i.response_guidance,
        }));
      } else {
        const res = await practiceAPI.objectionExtractDraft();
        items = (res.data.data.items || []).map((i) => ({
          checked: true, scenario_type: i.scenario_type, objection_content: i.objection_content,
          response_guidance: i.response_guidance,
        }));
        const s = res.data.data.sources;
        message.success(`已从 ${s.practice_sessions} 场陪练 + ${s.visits} 条拜访记录提取素材`);
      }
      if (!items.length) {
        message.warning('未生成有效草稿，请重试或换个场景');
      }
      setDraftItems(items);
    } catch {
      /* 拦截器已弹错误（4003 可重试） */
    } finally {
      setDraftGenerating(false);
    }
  };

  const saveDrafts = async () => {
    const picked = draftItems.filter((d) => d.checked && d.objection_content.trim() && d.scenario_type.trim());
    if (!picked.length) {
      message.warning('请至少勾选一条有效草稿');
      return;
    }
    setDraftSaving(true);
    try {
      for (const d of picked) {
        await practiceAPI.objectionCreate({
          scenario_type: d.scenario_type.trim(),
          objection_content: d.objection_content.trim(),
          response_guidance: d.response_guidance?.trim() || undefined,
        });
      }
      message.success(`已入库 ${picked.length} 条，进入待审核`);
      setDraftOpen(false);
      actionRef.current?.reload();
    } catch {
      /* 拦截器已弹错误（前序已入库的行不回滚，重开去重） */
    } finally {
      setDraftSaving(false);
    }
  };

  const columns: ProColumns<ObjectionScript>[] = [
    { title: 'ID', dataIndex: 'id', width: 60, hideInSearch: true },
    { title: '场景类型', dataIndex: 'scenario_type', width: 140 },
    {
      title: '医生异议', dataIndex: 'objection_content', ellipsis: true, hideInSearch: true,
      render: (_, r) => <span style={{ whiteSpace: 'pre-wrap' }}>{r.objection_content}</span>,
    },
    { title: '版本', dataIndex: 'version', width: 80, hideInSearch: true },
    {
      title: '审核状态', dataIndex: 'review_status', width: 100,
      valueEnum: { pending: '待审核', approved: '已通过', rejected: '已驳回' },
      render: (_, r) => {
        const m = STATUS_MAP[r.review_status] || { color: 'default', text: r.review_status };
        return (
          <Tag color={m.color}>
            {m.text}
            {r.review_status === 'rejected' && r.review_reason ? `：${r.review_reason.slice(0, 20)}` : ''}
          </Tag>
        );
      },
    },
    { title: '创建时间', dataIndex: 'created_at', width: 170, hideInSearch: true },
    {
      title: '操作', width: 120,
      render: (_, r) => (
        <Space size={0}>
          <a onClick={() => openReview(r)}>{r.review_status === 'pending' ? '审核' : '查看'}</a>
          {r.review_status !== 'approved' && (
            <a onClick={() => setFormModal({ mode: 'edit', row: r })}>编辑</a>
          )}
        </Space>
      ),
    },
  ];

  return (
    <>
      <ProTable<ObjectionScript>
        headerTitle="异议话术库"
        actionRef={actionRef}
        rowKey="id"
        search={{ labelWidth: 80 }}
        columns={columns}
        toolBarRender={() => [
          <Button key="create" type="primary" onClick={() => setFormModal({ mode: 'create' })}>
            新建话术
          </Button>,
          <Button key="ai" onClick={() => openDraft('ai')}>AI 起草</Button>,
          <Button key="extract" onClick={() => openDraft('extract')}>从真实数据提取</Button>,
        ]}
        request={async (params) => {
          const res = await practiceAPI.objectionList({
            page: params.current || 1,
            page_size: params.pageSize || 10,
            review_status: params.review_status,
            scenario_type: params.scenario_type,
          });
          return { data: res.data.data.items, total: res.data.data.total, success: true };
        }}
      />
      <Drawer
        title={current?.review_status === 'pending' ? '异议话术审核' : '异议话术详情'}
        width={520}
        open={!!current}
        onClose={() => setCurrent(null)}
        destroyOnHidden
      >
        {current && (
          <Space direction="vertical" size="middle" style={{ width: '100%' }}>
            <Descriptions column={1} size="small" bordered>
              <Descriptions.Item label="场景类型">{current.scenario_type}</Descriptions.Item>
              <Descriptions.Item label="版本">{current.version || '-'}</Descriptions.Item>
              <Descriptions.Item label="医生异议（原文）">
                <span style={{ whiteSpace: 'pre-wrap' }}>{current.objection_content}</span>
              </Descriptions.Item>
              <Descriptions.Item label="应对指引（原文）">
                <span style={{ whiteSpace: 'pre-wrap' }}>{current.response_guidance || '-'}</span>
              </Descriptions.Item>
              {current.review_status === 'rejected' && current.review_reason && (
                <Descriptions.Item label="驳回原因">{current.review_reason}</Descriptions.Item>
              )}
            </Descriptions>
            {current.review_status === 'pending' && (
              <>
                <Radio.Group value={verdict} onChange={(e) => setVerdict(e.target.value)}>
                  <Radio.Button value="approve">通过</Radio.Button>
                  <Radio.Button value="reject">驳回</Radio.Button>
                </Radio.Group>
                {verdict === 'reject' && (
                  <Input.TextArea
                    rows={3}
                    placeholder="驳回原因（必填）"
                    value={reason}
                    onChange={(e) => setReason(e.target.value)}
                    maxLength={500}
                  />
                )}
                <Button type="primary" block loading={submitting} onClick={submitReview}>提交审核</Button>
              </>
            )}
            {current.review_status !== 'pending' && (
              <Text type="secondary">已处理（{STATUS_MAP[current.review_status]?.text || current.review_status}），仅供查看</Text>
            )}
          </Space>
        )}
      </Drawer>

      {/* 新建 / 编辑：保存即 pending 送审（编辑 approved 由后端 4001 拦截，页面不放开入口） */}
      <Modal
        title={formModal?.mode === 'edit' ? `编辑话术 #${formModal.row.id}` : '新建异议话术'}
        open={!!formModal}
        onOk={submitForm}
        confirmLoading={formSaving}
        onCancel={() => setFormModal(null)}
        destroyOnHidden
      >
        <Form form={form} layout="vertical" preserve={false}>
          <Form.Item
            name="scenario_type" label="场景类型" initialValue="心内科推广"
            rules={[{ required: true, message: '场景类型必填' }, { max: 50, message: '不超过 50 字符' }]}
          >
            <AutoComplete options={SCENARIO_PRESETS.map((s) => ({ value: s }))} placeholder="如：心内科推广" />
          </Form.Item>
          <Form.Item
            name="objection_content" label="医生异议（陪练 AI 医生会按此发问）"
            rules={[{ required: true, message: '异议内容必填' }]}
          >
            <Input.TextArea rows={3} placeholder="医生视角的一句话异议，如：医生异议：这款药有头对头研究吗？" />
          </Form.Item>
          <Form.Item name="response_guidance" label="应对指引（选填，收尾考点回顾展示）">
            <Input.TextArea rows={3} placeholder="1~3 句循证合规的回应思路，代表端结束时回显" />
          </Form.Item>
          <Form.Item name="version" label="版本" initialValue="1.0" rules={[{ max: 20, message: '不超过 20 字符' }]}>
            <Input placeholder="1.0" />
          </Form.Item>
          {formModal?.mode === 'edit' && formModal.row.review_status === 'rejected' && (
            <Text type="warning">保存后将清除原驳回结论并重新送审</Text>
          )}
        </Form>
      </Modal>

      {/* AI 起草 / 真实数据提取：草稿不落库，勾选确认后逐条入库送审 */}
      <Modal
        title={draftMode === 'ai' ? 'AI 起草异议话术' : '从真实数据提取异议草稿'}
        width={720}
        open={draftOpen}
        onOk={saveDrafts}
        okText={`入库选中（${draftItems.filter((d) => d.checked).length}）`}
        okButtonProps={{ disabled: !draftItems.length }}
        confirmLoading={draftSaving}
        onCancel={() => setDraftOpen(false)}
        destroyOnHidden
      >
        <Space direction="vertical" size="middle" style={{ width: '100%' }}>
          {draftMode === 'ai' ? (
            <Space.Compact style={{ width: '100%' }}>
              <AutoComplete
                value={draftScenario}
                onChange={setDraftScenario}
                options={SCENARIO_PRESETS.map((s) => ({ value: s }))}
                style={{ flex: 1 }}
                placeholder="目标场景，如：心内科推广"
              />
              <Button type="primary" loading={draftGenerating} onClick={generateDrafts}>
                生成草稿（约 10~30s）
              </Button>
            </Space.Compact>
          ) : (
            <>
              <Text type="secondary">
                从最近 20 场陪练（AI 医生发言）与 20 条拜访记录（医生异议 + 转写中医生发言）提取草稿，草稿不落库。
              </Text>
              <Button type="primary" loading={draftGenerating} onClick={generateDrafts}>
                开始提取（约 10~30s）
              </Button>
            </>
          )}
          {draftItems.map((d, i) => (
            <div key={i} style={{ border: '1px solid #f0f0f0', borderRadius: 6, padding: 12 }}>
              <Space direction="vertical" size="small" style={{ width: '100%' }}>
                <Checkbox
                  checked={d.checked}
                  onChange={(e) => setDraftItems((prev) => prev.map((p, j) => (j === i ? { ...p, checked: e.target.checked } : p)))}
                >
                  入库此条
                </Checkbox>
                <Input
                  value={d.scenario_type}
                  onChange={(e) => setDraftItems((prev) => prev.map((p, j) => (j === i ? { ...p, scenario_type: e.target.value } : p)))}
                  addonBefore="场景" size="small"
                />
                <Input.TextArea
                  rows={2} value={d.objection_content}
                  onChange={(e) => setDraftItems((prev) => prev.map((p, j) => (j === i ? { ...p, objection_content: e.target.value } : p)))}
                  placeholder="医生异议"
                />
                <Input.TextArea
                  rows={2} value={d.response_guidance || ''}
                  onChange={(e) => setDraftItems((prev) => prev.map((p, j) => (j === i ? { ...p, response_guidance: e.target.value } : p)))}
                  placeholder="应对指引（可空）"
                />
              </Space>
            </div>
          ))}
        </Space>
      </Modal>
    </>
  );
}
