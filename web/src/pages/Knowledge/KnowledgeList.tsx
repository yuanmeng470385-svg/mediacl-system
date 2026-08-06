import { useEffect, useRef, useState } from 'react';
import { ProTable, ModalForm } from '@ant-design/pro-components';
import type { ActionType, ProColumns } from '@ant-design/pro-components';
import {
  App, Button, Col, DatePicker, Descriptions, Form, Input, InputNumber, Modal,
  Row, Select, Tag, Upload,
} from 'antd';
import type { Dayjs } from 'dayjs';
import type { UploadFile } from 'antd';
import { PlusOutlined } from '@ant-design/icons';
import StatCard from '../../components/StatCard';
import StatusTag from '../../components/StatusTag';
import { knowledgeAPI } from '../../services/knowledge';
import type { KnowledgeDoc, KnowledgeStats } from '../../types';

// ===== 文档类型（后端枚举 product/guideline/literature/regulation/competitor/other）=====
const DOC_TYPES: { value: string; label: string; color: string }[] = [
  { value: 'product', label: '产品', color: 'blue' },
  { value: 'guideline', label: '指南', color: 'green' },
  { value: 'literature', label: '文献', color: 'purple' },
  { value: 'regulation', label: '法规', color: 'orange' },
  { value: 'competitor', label: '竞品', color: 'magenta' },
  { value: 'other', label: '其他', color: 'default' },
];
const DOC_TYPE_LABELS: Record<string, string> = Object.fromEntries(DOC_TYPES.map((t) => [t.value, t.label]));
const DOC_TYPE_COLORS: Record<string, string> = Object.fromEntries(DOC_TYPES.map((t) => [t.value, t.color]));
const DOC_TYPE_ENUM: Record<string, { text: string }> = Object.fromEntries(DOC_TYPES.map((t) => [t.value, { text: t.label }]));

// ===== 状态（后端状态机 draft/processing/ready/rejected/archived）=====
const STATUS_LABELS: Record<string, string> = {
  draft: '草稿',
  processing: '处理中',
  ready: '已上架',
  rejected: '已驳回',
  archived: '已归档',
};
const STATUS_ENUM: Record<string, { text: string }> = Object.fromEntries(
  Object.entries(STATUS_LABELS).map(([value, text]) => [value, { text }]),
);

const EVIDENCE_ENUM: Record<string, { text: string }> = {
  A: { text: 'A级' }, B: { text: 'B级' }, C: { text: 'C级' },
  expert: { text: '专家共识' }, unknown: { text: '未知' },
};
const EVIDENCE_OPTIONS = Object.entries(EVIDENCE_ENUM).map(([value, { text }]) => ({ value, label: text }));

interface UploadFormValues {
  title?: string;
  doc_type?: string;
  product_id?: number;
  evidence_level?: string;
  publish_date?: Dayjs;
  source?: string;
  version?: string;
}

function formatTime(value: string | null | undefined): string {
  if (!value) return '-';
  return value.replace('T', ' ').slice(0, 16);
}

export default function KnowledgeList() {
  const actionRef = useRef<ActionType>();
  const { message } = App.useApp();
  const [uploadOpen, setUploadOpen] = useState(false);
  const [uploadForm] = Form.useForm<UploadFormValues>();
  const [fileList, setFileList] = useState<UploadFile[]>([]);
  const [stats, setStats] = useState<KnowledgeStats>({ total: 0, by_status: {} });
  const [detailOpen, setDetailOpen] = useState(false);
  const [detailLoading, setDetailLoading] = useState(false);
  const [detailDoc, setDetailDoc] = useState<KnowledgeDoc | null>(null);

  useEffect(() => {
    knowledgeAPI.stats().then((res) => setStats(res.data.data)).catch(() => {});
  }, []);

  /** 真实上传：POST /api/v1/knowledge/upload（multipart），表单字段与后端签名对齐 */
  const handleUpload = (options: any) => {
    const values = uploadForm.getFieldsValue();
    if (!values.title?.trim()) {
      message.warning('请先填写标题');
      options.onError?.(new Error('缺少标题'));
      return;
    }
    if (!values.doc_type) {
      message.warning('请选择文档类型');
      options.onError?.(new Error('缺少文档类型'));
      return;
    }
    const fd = new FormData();
    fd.append('file', options.file as File);
    fd.append('title', values.title.trim());
    fd.append('doc_type', values.doc_type);
    if (values.product_id != null) fd.append('product_id', String(values.product_id));
    if (values.evidence_level) fd.append('evidence_level', values.evidence_level);
    if (values.publish_date) fd.append('publish_date', values.publish_date.format('YYYY-MM-DD'));
    if (values.source) fd.append('source', values.source);
    if (values.version) fd.append('version', values.version);
    knowledgeAPI
      .upload(fd)
      .then((res) => {
        options.onSuccess?.(res.data);
        message.success(`「${res.data.data?.title || values.title}」上传成功，等待审核`);
        actionRef.current?.reload();
        setUploadOpen(false);
        uploadForm.resetFields();
        setFileList([]);
      })
      .catch((err) => {
        options.onError?.(err);
        message.error(err?.response?.data?.message || '上传失败，请重试');
      });
  };

  const onReview = async (r: KnowledgeDoc, approved: boolean) => {
    try {
      await knowledgeAPI.review(r.id, approved ? 'approve' : 'reject');
      message.success(approved ? '审核通过，文档已上架' : '已驳回');
      actionRef.current?.reload();
    } catch (err: any) {
      message.error(err?.response?.data?.message || (approved ? '审核失败' : '驳回失败'));
    }
  };

  const showDetail = async (r: KnowledgeDoc) => {
    setDetailOpen(true);
    setDetailLoading(true);
    try {
      const res = await knowledgeAPI.detail(r.id);
      setDetailDoc(res.data.data);
    } catch (err: any) {
      setDetailOpen(false);
      message.error(err?.response?.data?.message || '获取详情失败');
    } finally {
      setDetailLoading(false);
    }
  };

  const columns: ProColumns<KnowledgeDoc>[] = [
    { title: '标题', dataIndex: 'title', width: 260, ellipsis: true },
    {
      title: '类型',
      dataIndex: 'doc_type',
      width: 100,
      valueEnum: DOC_TYPE_ENUM,
      render: (_, r) => (
        <Tag color={DOC_TYPE_COLORS[r.doc_type] || 'default'}>
          {DOC_TYPE_LABELS[r.doc_type] || r.doc_type || '未知'}
        </Tag>
      ),
    },
    {
      title: '关联产品',
      dataIndex: 'product_id',
      width: 110,
      valueType: 'digit',
      render: (_, r) =>
        r.product_id != null ? `#${r.product_id}` : <span style={{ color: '#999' }}>未关联</span>,
    },
    {
      title: '证据等级',
      dataIndex: 'evidence_level',
      width: 110,
      valueEnum: EVIDENCE_ENUM,
      render: (_, r) => r.evidence_level || <span style={{ color: '#999' }}>未知</span>,
    },
    {
      title: '状态',
      dataIndex: 'status',
      width: 100,
      valueEnum: STATUS_ENUM,
      render: (_, r) => <StatusTag status={r.status} labels={STATUS_LABELS} />,
    },
    {
      title: '版本',
      dataIndex: 'version',
      width: 90,
      hideInSearch: true,
      render: (_, r) => (r.version ? `v${r.version}` : '-'),
    },
    {
      title: '创建时间',
      dataIndex: 'created_at',
      width: 170,
      hideInSearch: true,
      render: (_, r) => formatTime(r.created_at),
    },
    {
      title: '操作',
      width: 190,
      hideInSearch: true,
      render: (_, r) => {
        if (r.status === 'draft' || r.status === 'rejected') {
          return (
            <>
              <a onClick={() => onReview(r, true)}>通过</a>
              {' | '}
              <a style={{ color: '#ff4d4f' }} onClick={() => onReview(r, false)}>驳回</a>
              {' | '}
              <a onClick={() => showDetail(r)}>详情</a>
            </>
          );
        }
        const statusText =
          r.status === 'processing' ? '处理中' : r.status === 'ready' ? '已上架' : r.status === 'archived' ? '已归档' : '';
        return (
          <>
            {statusText ? <span style={{ color: '#999' }}>{statusText}</span> : null}
            {statusText ? ' | ' : null}
            <a onClick={() => showDetail(r)}>详情</a>
          </>
        );
      },
    },
  ];

  return (
    <>
      <Row gutter={[16, 16]} style={{ marginBottom: 16 }}>
        <Col span={8}><StatCard title="文档总数" value={stats.total} /></Col>
        {Object.entries(stats.by_status || {}).map(([status, count]) => (
          <Col span={8} key={status}>
            <StatCard title={STATUS_LABELS[status] || status} value={count} />
          </Col>
        ))}
      </Row>
      <ProTable<KnowledgeDoc>
        headerTitle="知识库文档"
        actionRef={actionRef}
        columns={columns}
        rowKey="id"
        search={{ labelWidth: 80 }}
        request={async (params) => {
          const res = await knowledgeAPI.list({
            page: params.current || 1,
            page_size: params.pageSize || 10,
            doc_type: params.doc_type,
            status: params.status,
            product_id: params.product_id != null && params.product_id !== '' ? Number(params.product_id) : undefined,
          });
          return { data: res.data.data.items, total: res.data.data.total, success: true };
        }}
        toolBarRender={() => [
          <Button key="upload" type="primary" icon={<PlusOutlined />} onClick={() => setUploadOpen(true)}>上传文档</Button>,
        ]}
      />
      <ModalForm<UploadFormValues>
        title="上传文档"
        open={uploadOpen}
        form={uploadForm}
        onOpenChange={(open) => {
          setUploadOpen(open);
          if (!open) {
            uploadForm.resetFields();
            setFileList([]);
          }
        }}
        onFinish={async () => {
          // 文件由 Dragger customRequest 完成真实上传，此处仅关闭弹窗
          return true;
        }}
      >
        <Form.Item name="title" label="标题" rules={[{ required: true, message: '请输入标题' }]}>
          <Input placeholder="请输入文档标题" />
        </Form.Item>
        <Form.Item name="doc_type" label="文档类型" rules={[{ required: true, message: '请选择文档类型' }]}>
          <Select placeholder="请选择文档类型" options={DOC_TYPES.map(({ value, label }) => ({ value, label }))} />
        </Form.Item>
        <Form.Item name="product_id" label="关联产品" tooltip="填写产品 ID，可留空">
          <InputNumber min={1} style={{ width: '100%' }} placeholder="产品 ID（可选）" />
        </Form.Item>
        <Form.Item name="evidence_level" label="证据等级">
          <Select allowClear placeholder="请选择（可选）" options={EVIDENCE_OPTIONS} />
        </Form.Item>
        <Form.Item name="publish_date" label="发布日期">
          <DatePicker style={{ width: '100%' }} placeholder="YYYY-MM-DD（可选）" />
        </Form.Item>
        <Form.Item name="source" label="来源">
          <Input placeholder="可选" />
        </Form.Item>
        <Form.Item name="version" label="版本号">
          <Input placeholder="如 1.0（可选）" />
        </Form.Item>
        <Form.Item label="文件" required>
          <Upload.Dragger
            accept=".pdf,.doc,.docx,.ppt,.pptx,.txt"
            maxCount={1}
            fileList={fileList}
            onChange={({ fileList: list }) => setFileList(list.slice(-1))}
            onRemove={() => { setFileList([]); return true; }}
            customRequest={handleUpload}
          >
            <p className="ant-upload-drag-icon">
              <PlusOutlined />
            </p>
            <p className="ant-upload-text">点击或拖拽文件到此区域上传</p>
            <p className="ant-upload-hint">支持 PDF / Word / PPT / TXT；请先填写标题与类型再选择文件</p>
          </Upload.Dragger>
        </Form.Item>
      </ModalForm>
      <Modal
        title="文档详情"
        open={detailOpen}
        onCancel={() => setDetailOpen(false)}
        footer={null}
        width={680}
      >
        {detailLoading ? (
          <div style={{ padding: 32, textAlign: 'center', color: '#999' }}>加载中...</div>
        ) : detailDoc ? (
          <Descriptions column={1} bordered size="small">
            <Descriptions.Item label="标题">{detailDoc.title}</Descriptions.Item>
            <Descriptions.Item label="类型">
              <Tag color={DOC_TYPE_COLORS[detailDoc.doc_type] || 'default'}>
                {DOC_TYPE_LABELS[detailDoc.doc_type] || detailDoc.doc_type}
              </Tag>
            </Descriptions.Item>
            <Descriptions.Item label="状态">
              <StatusTag status={detailDoc.status} labels={STATUS_LABELS} />
            </Descriptions.Item>
            <Descriptions.Item label="版本">{detailDoc.version ? `v${detailDoc.version}` : '-'}</Descriptions.Item>
            <Descriptions.Item label="关联产品">{detailDoc.product_id != null ? `#${detailDoc.product_id}` : '未关联'}</Descriptions.Item>
            <Descriptions.Item label="证据等级">{detailDoc.evidence_level || '-'}</Descriptions.Item>
            <Descriptions.Item label="发布日期">{detailDoc.publish_date || '-'}</Descriptions.Item>
            <Descriptions.Item label="来源">{detailDoc.source || '-'}</Descriptions.Item>
            <Descriptions.Item label="标签">
              {Array.isArray(detailDoc.tags) && detailDoc.tags.length ? detailDoc.tags.join('、') : '-'}
            </Descriptions.Item>
            <Descriptions.Item label="内容摘要">
              {detailDoc.content
                ? (
                    <span style={{ whiteSpace: 'pre-wrap' }}>
                      {detailDoc.content.length > 300 ? `${detailDoc.content.slice(0, 300)}...` : detailDoc.content}
                    </span>
                  )
                : '-'}
            </Descriptions.Item>
            <Descriptions.Item label="原文">
              {detailDoc.file_url
                ? <a href={detailDoc.file_url} target="_blank" rel="noreferrer">打开文件</a>
                : '-'}
            </Descriptions.Item>
            <Descriptions.Item label="更新时间">{formatTime(detailDoc.updated_at)}</Descriptions.Item>
          </Descriptions>
        ) : null}
      </Modal>
    </>
  );
}
