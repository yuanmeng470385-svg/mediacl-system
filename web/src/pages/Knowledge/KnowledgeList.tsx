import { useRef, useState, useEffect } from 'react';
import { ProTable, ModalForm } from '@ant-design/pro-components';
import type { ProColumns, ActionType } from '@ant-design/pro-components';
import { Button, Row, Col, Upload, App } from 'antd';
import { PlusOutlined, UploadOutlined } from '@ant-design/icons';
import StatCard from '../../components/StatCard';
import StatusTag from '../../components/StatusTag';
import { knowledgeAPI } from '../../services/knowledge';
import type { KnowledgeDoc } from '../../types';

export default function KnowledgeList() {
  const actionRef = useRef<ActionType>();
  const [uploadOpen, setUploadOpen] = useState(false);
  const [stats, setStats] = useState({ docs: 0, tags: 0, chunks: 0 });
  const { message } = App.useApp();

  useEffect(() => {
    knowledgeAPI.stats().then((res) => setStats(res.data.data)).catch(() => {});
  }, []);

  const columns: ProColumns<KnowledgeDoc>[] = [
    { title: '标题', dataIndex: 'title', width: 240, ellipsis: true },
    { title: '类型', dataIndex: 'type', width: 100, render: (_, r) => r.type.toUpperCase(),
      valueEnum: { pdf: 'PDF', word: 'Word', ppt: 'PPT', txt: 'TXT' } },
    { title: '关联产品', dataIndex: 'product', width: 120 },
    { title: '证据等级', dataIndex: 'evidence_level', width: 100,
      valueEnum: { A: 'A级', B: 'B级', C: 'C级', expert: '专家共识', unknown: '未知' } },
    { title: '状态', dataIndex: 'status', width: 100, render: (_, r) => <StatusTag status={r.status} /> },
    { title: '版本', dataIndex: 'version', width: 80, render: (_, r) => `v${r.version}` },
    {
      title: '操作', width: 150,
      render: (_, r) => (
        r.status === 'pending' ? (
          <>
            <a onClick={() => knowledgeAPI.review(r.id, 'approve').then(() => actionRef.current?.reload())}>通过</a>
            {' | '}
            <a style={{ color: '#ff4d4f' }} onClick={() => knowledgeAPI.review(r.id, 'reject').then(() => actionRef.current?.reload())}>驳回</a>
          </>
        ) : <a onClick={() => message.info(`查看: ${r.title}`)}>详情</a>
      ),
    },
  ];

  return (
    <>
      <Row gutter={[16, 16]} style={{ marginBottom: 16 }}>
        <Col span={8}><StatCard title="文档总数" value={stats.docs} /></Col>
        <Col span={8}><StatCard title="标签数" value={stats.tags} /></Col>
        <Col span={8}><StatCard title="Chunk 数" value={stats.chunks} /></Col>
      </Row>
      <ProTable<KnowledgeDoc>
        headerTitle="知识库文档"
        actionRef={actionRef}
        columns={columns}
        request={async (params) => {
          const res = await knowledgeAPI.list({ page: params.current || 1, page_size: params.pageSize || 10, type: params.type, status: params.status, product: params.product });
          return { data: res.data.data.items, total: res.data.data.total, success: true };
        }}
        rowKey="id"
        search={{ labelWidth: 80 }}
        toolBarRender={() => [
          <Button key="upload" type="primary" icon={<PlusOutlined />} onClick={() => setUploadOpen(true)}>上传文档</Button>,
        ]}
      />
      <ModalForm title="上传文档" open={uploadOpen} onOpenChange={setUploadOpen}
        onFinish={async () => { message.success('文档已上传，等待审核'); actionRef.current?.reload(); return true; }}>
        <Upload.Dragger accept=".pdf,.doc,.docx,.ppt,.pptx,.txt" style={{ marginBottom: 16 }}>
          <UploadOutlined style={{ fontSize: 36, color: '#1677ff' }} />
          <p>点击或拖拽文件到此区域上传</p>
          <p style={{ color: '#999' }}>支持 PDF / Word / PPT / TXT</p>
        </Upload.Dragger>
      </ModalForm>
    </>
  );
}
