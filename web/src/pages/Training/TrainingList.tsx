import { useEffect, useState } from 'react';
import { App, Button, Form, Input, Modal, Radio, Select, Tabs, Tag, Typography } from 'antd';
import { ProTable } from '@ant-design/pro-components';
import type { ProColumns } from '@ant-design/pro-components';
import { trainingAPI } from '../../services/training';
import type { ExamQuestion, ExamRecord, TrainingMaterial } from '../../types';

const MATERIAL_MAP: Record<string, string> = { regulation: '办法', rdpac: 'RDPAC', internal: '内部政策' };
const STATUS_MAP: Record<string, { color: string; text: string }> = {
  pending: { color: 'orange', text: '待审核' },
  approved: { color: 'green', text: '已通过' },
  rejected: { color: 'red', text: '已驳回' },
};
const TYPE_MAP: Record<string, string> = { single: '单选', multiple: '多选', judge: '判断' };

export default function TrainingList() {
  const { message } = App.useApp();
  const [materialModal, setMaterialModal] = useState(false);
  const [questionModal, setQuestionModal] = useState(false);
  const [editing, setEditing] = useState<TrainingMaterial | null>(null);
  const [aiQuestions, setAiQuestions] = useState<any[]>([]);
  const [materialOptions, setMaterialOptions] = useState<{ value: number; label: string }[]>([]);
  const [tabRefresh, setTabRefresh] = useState(0);
  const [materialForm] = Form.useForm();
  const [questionForm] = Form.useForm();

  // AI 出题 Modal 的材料 Select 数据源（brief 标注缺口：原 options=[] 恒空）
  useEffect(() => {
    let cancelled = false;
    trainingAPI
      .listMaterials({ page: 1, page_size: 100 })
      .then((res) => {
        if (cancelled) return;
        setMaterialOptions(res.data.data.items.map((m) => ({ value: m.id, label: m.title })));
      })
      .catch(() => {
        /* client.ts 拦截器已弹错误 */
      });
    return () => {
      cancelled = true;
    };
  }, []);

  const materialColumns: ProColumns<TrainingMaterial>[] = [
    { title: '标题', dataIndex: 'title', hideInSearch: true },
    { title: '类型', dataIndex: 'material_type', width: 90,
      valueEnum: MATERIAL_MAP,
      render: (_, r) => MATERIAL_MAP[r.material_type] || r.material_type },
    { title: '版本', dataIndex: 'version', width: 80, hideInSearch: true },
    {
      title: '操作', width: 160, hideInSearch: true,
      render: (_, r) => (
        <>
          <a onClick={() => { setEditing(r); materialForm.setFieldsValue(r); setMaterialModal(true); }}>编辑</a>
          <a style={{ marginLeft: 12 }} onClick={async () => {
            await trainingAPI.archiveMaterial(r.id);
            message.success('已归档');
            setTabRefresh(t => t + 1);
          }}>归档</a>
        </>
      ),
    },
    // 搜索参数对齐后端 list_materials：material_type/keyword
    { title: '关键词', dataIndex: 'keyword', hideInTable: true },
  ];

  const questionColumns: ProColumns<ExamQuestion>[] = [
    { title: '题干', dataIndex: 'content', ellipsis: true, hideInSearch: true },
    { title: '类型', dataIndex: 'question_type', width: 80, valueEnum: TYPE_MAP,
      render: (_, r) => TYPE_MAP[r.question_type] || r.question_type },
    { title: '审核状态', dataIndex: 'review_status', width: 100,
      valueEnum: { pending: '待审核', approved: '已通过', rejected: '已驳回' },
      render: (_, r) => { const m = STATUS_MAP[r.review_status] || { color: 'default', text: r.review_status }; return <Tag color={m.color}>{m.text}</Tag>; } },
    { title: '审核', dataIndex: 'review_reason', width: 120, hideInSearch: true },
    {
      title: '操作', width: 160, hideInSearch: true,
      render: (_, r) => r.review_status === 'pending' ? (
        <>
          <a onClick={async () => { await trainingAPI.reviewQuestion(r.id, { verdict: 'approve' }); message.success('已通过'); setTabRefresh(t => t + 1); }}>通过</a>
          <a style={{ marginLeft: 12 }} onClick={() => { Modal.confirm({ title: '驳回', content: <Input.TextArea id="reject-reason" rows={3} placeholder="驳回原因（必填）" />, onOk: async () => { const el = document.getElementById('reject-reason') as HTMLTextAreaElement; await trainingAPI.reviewQuestion(r.id, { verdict: 'reject', reason: el?.value || '' }); message.success('已驳回'); setTabRefresh(t => t + 1); } }); }}>驳回</a>
        </>
      ) : <span style={{ color: '#999' }}>已处理</span>,
    },
    // 搜索参数对齐后端 list_questions：review_status/keyword
    { title: '关键词', dataIndex: 'keyword', hideInTable: true },
  ];

  const recordColumns: ProColumns<ExamRecord>[] = [
    { title: '代表ID', dataIndex: 'representative_id', width: 90 },
    { title: '题数', dataIndex: 'question_count', width: 70 },
    { title: '答对', dataIndex: 'correct_count', width: 70 },
    { title: '分数', dataIndex: 'score', width: 70, render: (_, r) => `${r.score} 分` },
    { title: '通过', dataIndex: 'passed', width: 80, render: (_, r) => r.passed ? <Tag color="green">通过</Tag> : <Tag color="red">未过</Tag> },
    { title: '提交时间', dataIndex: 'submitted_at', hideInSearch: true },
  ];

  return (
    <Tabs defaultActiveKey="materials" items={[
      {
        key: 'materials', label: '培训材料',
        children: (
          <>
            <ProTable<TrainingMaterial>
              headerTitle="培训材料"
              rowKey="id"
              search={{ labelWidth: 80 }}
              params={{ t: tabRefresh }}
              columns={materialColumns}
              request={async (params) => {
                const res = await trainingAPI.listMaterials({ page: params.current || 1, page_size: params.pageSize || 10, material_type: params.material_type, keyword: params.keyword });
                return { data: res.data.data.items, total: res.data.data.total, success: true };
              }}
              toolBarRender={() => [<Button type="primary" key="new" onClick={() => { setEditing(null); materialForm.resetFields(); setMaterialModal(true); }}>新增材料</Button>]}
            />
            <Modal title={editing ? '编辑材料' : '新增材料'} open={materialModal} onCancel={() => setMaterialModal(false)} onOk={() => materialForm.submit()} destroyOnHidden>
              <Form form={materialForm} layout="vertical" onFinish={async (values) => {
                if (editing) await trainingAPI.updateMaterial(editing.id, values);
                else await trainingAPI.createMaterial(values);
                message.success('已保存');
                setMaterialModal(false);
                setTabRefresh(t => t + 1);
              }}>
                <Form.Item name="title" label="标题" rules={[{ required: true, message: '必填' }]}><Input maxLength={200} /></Form.Item>
                <Form.Item name="material_type" label="类型" rules={[{ required: true, message: '必选' }]}>
                  <Select options={[{ value: 'regulation', label: '办法' }, { value: 'rdpac', label: 'RDPAC 准则' }, { value: 'internal', label: '内部政策' }]} />
                </Form.Item>
                <Form.Item name="content" label="正文" rules={[{ required: true, message: '必填' }]}><Input.TextArea rows={12} /></Form.Item>
              </Form>
            </Modal>
          </>
        ),
      },
      {
        key: 'questions', label: '题库审核',
        children: (
          <>
            <ProTable<ExamQuestion>
              headerTitle="题库"
              rowKey="id"
              search={{ labelWidth: 80 }}
              params={{ t: tabRefresh }}
              columns={questionColumns}
              request={async (params) => {
                const res = await trainingAPI.listQuestions({ page: params.current || 1, page_size: params.pageSize || 10, review_status: params.review_status, keyword: params.keyword });
                return { data: res.data.data.items, total: res.data.data.total, success: true };
              }}
              toolBarRender={() => [<Button type="primary" key="ai" onClick={() => setQuestionModal(true)}>AI 出题</Button>]}
            />
            <Modal title="AI 出题" open={questionModal} onCancel={() => setQuestionModal(false)} footer={null} destroyOnHidden>
              <Form form={questionForm} layout="vertical" onFinish={async (values) => {
                const res = await trainingAPI.aiGenerate({
                  material_id: values.material_id,
                  question_type: values.question_type,
                  count: values.count != null ? Number(values.count) : 5,
                });
                setAiQuestions(res.data.data);
                message.success(`生成 ${res.data.data.length} 道草稿`);
              }}>
                <Form.Item name="material_id" label="培训材料" rules={[{ required: true, message: '必选' }]}>
                  <Select allowClear placeholder="选择材料" options={materialOptions} />
                </Form.Item>
                <Form.Item name="question_type" label="题型" initialValue="single">
                  <Radio.Group options={[{ value: 'single', label: '单选' }, { value: 'multiple', label: '多选' }, { value: 'judge', label: '判断' }]} />
                </Form.Item>
                <Form.Item name="count" label="数量" initialValue={5}><Input type="number" min={1} max={20} /></Form.Item>
                <Button type="primary" htmlType="submit">生成草稿</Button>
              </Form>
              {aiQuestions.map((q, i) => (
                <div key={i} style={{ marginTop: 8, padding: 8, background: '#fafafa', borderRadius: 4 }}>
                  <Typography.Text type="warning" style={{ display: 'block', marginBottom: 4 }}>
                    AI 生成，请人工复核后入库
                  </Typography.Text>
                  <div>{q.content}</div>
                  <div style={{ color: '#888', fontSize: 12 }}>选项：{q.options?.join(' / ')}　答案：{q.answer?.join(',')}</div>
                  <Button size="small" onClick={async () => {
                    await trainingAPI.createQuestion({ ...q, material_id: questionForm.getFieldValue('material_id') });
                    message.success('已入库待审核');
                  }}>入库待审核</Button>
                </div>
              ))}
            </Modal>
          </>
        ),
      },
      {
        key: 'records', label: '考试记录',
        children: (
          <ProTable<ExamRecord>
            headerTitle="考试记录"
            rowKey="id"
            search={false}
            columns={recordColumns}
            request={async (params) => {
              const res = await trainingAPI.listRecords({ page: params.current || 1, page_size: params.pageSize || 10 });
              return { data: res.data.data.items, total: res.data.data.total, success: true };
            }}
          />
        ),
      },
    ]} />
  );
}
