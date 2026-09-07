/**
 * 拜访管理页（B4 新增 2026-08-12）—— 管理端查看全公司拜访记录：
 *   列表（医生/时间/时长/状态/摘要预览）+ 详情抽屉（基本信息 + AI 总结 + 转写全文 + 跟进任务）
 * 后端 GET /api/v1/visits（admin 看全部；非 admin 后端强制只看自己）+ GET /visits/{id}/tasks
 */
import { useEffect, useRef, useState } from 'react';
import dayjs from 'dayjs';
import utc from 'dayjs/plugin/utc';
import { ProTable } from '@ant-design/pro-components';
import type { ProColumns, ActionType } from '@ant-design/pro-components';
import { Tag, Space, Drawer, Descriptions, Typography, Empty, Spin, Divider } from 'antd';
import { PageContainer } from '@ant-design/pro-components';
import { visitAPI } from '../../services/visit';
import type { VisitRecord, VisitTask } from '../../services/visit';

dayjs.extend(utc);

const STATUS_MAP: Record<string, { color: string; text: string }> = {
  in_progress: { color: 'blue', text: '进行中' },
  completed: { color: 'green', text: '已完成' },
  cancelled: { color: 'default', text: '已取消' },
};

const TASK_STATUS: Record<string, { color: string; text: string }> = {
  open: { color: 'blue', text: '进行中' },
  done: { color: 'green', text: '已完成' },
  cancelled: { color: 'default', text: '已取消' },
};

/** 拜访详情抽屉：基本信息 + AI 总结 + 跟进任务 + 转写全文 */
function VisitDetailDrawer({
  record,
  onClose,
}: {
  record: VisitRecord | null;
  onClose: () => void;
}) {
  const [tasks, setTasks] = useState<VisitTask[] | null>(null);

  // record 变化时拉取该拜访的任务（失败不阻塞详情展示）
  useEffect(() => {
    setTasks(null);
    if (!record) return;
    visitAPI.tasks(record.id)
      .then((res) => setTasks(res.data.data ?? []))
      .catch(() => setTasks([]));
  }, [record]);

  return (
    <Drawer
      title={record ? `拜访详情：${record.hcp_name || `医生 #${record.hcp_id ?? ''}`}` : '拜访详情'}
      width={560}
      open={!!record}
      onClose={onClose}
    >
      {!record ? null : (
        <>
          <Descriptions column={1} bordered size="small">
            <Descriptions.Item label="状态">
              <Tag color={STATUS_MAP[record.status]?.color || 'default'}>
                {STATUS_MAP[record.status]?.text || record.status}
              </Tag>
            </Descriptions.Item>
            <Descriptions.Item label="拜访时间">
              {record.visit_time ? dayjs.utc(record.visit_time).local().format('YYYY-MM-DD HH:mm') : '—'}
            </Descriptions.Item>
            <Descriptions.Item label="时长">
              {record.duration_minutes != null ? `${record.duration_minutes} 分钟` : '—'}
            </Descriptions.Item>
            <Descriptions.Item label="情绪">
              {record.sentiment || '—'}
            </Descriptions.Item>
          </Descriptions>

          <Divider style={{ margin: '16px 0' }} />
          <Typography.Title level={5}>AI 总结</Typography.Title>
          {record.ai_summary ? (
            <Typography.Paragraph style={{ whiteSpace: 'pre-wrap', color: '#595959' }}>
              {record.ai_summary}
            </Typography.Paragraph>
          ) : (
            <Empty description="暂无总结（拜访未结束或生成失败）" image={Empty.PRESENTED_IMAGE_SIMPLE} />
          )}

          <Divider style={{ margin: '16px 0' }} />
          <Typography.Title level={5}>跟进任务（{tasks?.length ?? '…'}）</Typography.Title>
          {tasks === null ? (
            <div style={{ textAlign: 'center', padding: 20 }}><Spin size="small" /></div>
          ) : tasks.length === 0 ? (
            <Empty description="暂无任务" image={Empty.PRESENTED_IMAGE_SIMPLE} />
          ) : (
            tasks.map((t) => (
              <div
                key={t.id}
                style={{
                  display: 'flex', justifyContent: 'space-between', alignItems: 'center',
                  padding: '8px 0', borderBottom: '1px solid #f0f0f0', gap: 12,
                }}
              >
                <div style={{ flex: 1, minWidth: 0 }}>
                  <Space size={6}>
                    <Tag color={TASK_STATUS[t.status]?.color}>{TASK_STATUS[t.status]?.text || t.status}</Tag>
                    <Typography.Text strong ellipsis style={{ maxWidth: 220 }}>{t.title}</Typography.Text>
                  </Space>
                  {t.due_date ? (
                    <div style={{ fontSize: 12, color: '#8c8c8c', marginTop: 2 }}>截止 {t.due_date}</div>
                  ) : null}
                </div>
                {t.channel ? (
                  <Tag color="blue" style={{ flexShrink: 0 }}>{t.channel}</Tag>
                ) : null}
              </div>
            ))
          )}

          {record.conversation_transcript ? (
            <>
              <Divider style={{ margin: '16px 0' }} />
              <Typography.Title level={5}>转写全文</Typography.Title>
              <div
                style={{
                  maxHeight: 240, overflowY: 'auto', background: '#fafafa',
                  padding: 12, borderRadius: 8, fontSize: 13, color: '#595959', lineHeight: 1.8,
                  whiteSpace: 'pre-wrap',
                }}
              >
                {record.conversation_transcript}
              </div>
            </>
          ) : null}
        </>
      )}
    </Drawer>
  );
}

export default function VisitList() {
  const actionRef = useRef<ActionType>();
  const [detail, setDetail] = useState<VisitRecord | null>(null);

  const columns: ProColumns<VisitRecord>[] = [
    { title: '医生', dataIndex: 'hcp_name', width: 160, ellipsis: true },
    {
      title: '拜访时间', dataIndex: 'visit_time', width: 170,
      render: (_, r) => (r.visit_time ? dayjs.utc(r.visit_time).local().format('YYYY-MM-DD HH:mm') : '—'),
    },
    {
      title: '状态', dataIndex: 'status', width: 100,
      valueType: 'select',
      valueEnum: {
        in_progress: { text: '进行中' },
        completed: { text: '已完成' },
        cancelled: { text: '已取消' },
      },
      render: (_, r) => (
        <>
          <Tag color={STATUS_MAP[r.status]?.color || 'default'}>
            {STATUS_MAP[r.status]?.text || r.status}
          </Tag>
          {/* 进行中超 24h 未结束 = 忘点结束的僵尸记录（时长口径见后端 A-6 clamp） */}
          {r.status === 'in_progress' && r.visit_time &&
            dayjs.utc(r.visit_time).local().isBefore(dayjs().subtract(24, 'hour')) && (
              <Tag color="default" style={{ marginLeft: 4 }}>未正常结束</Tag>
            )}
        </>
      ),
    },
    {
      title: '时长', dataIndex: 'duration_minutes', width: 90,
      render: (_, r) => (r.duration_minutes != null ? `${r.duration_minutes} 分钟` : '—'),
    },
    {
      title: 'AI 摘要', dataIndex: 'ai_summary', ellipsis: true,
      render: (_, r) => {
        const s = r.ai_summary || '';
        return s.length > 60 ? `${s.slice(0, 60)}…` : s || '—';
      },
    },
    {
      title: '操作', width: 100,
      render: (_, r) => <a onClick={() => setDetail(r)}>查看详情</a>,
    },
  ];

  return (
    <PageContainer header={{ title: '拜访管理', subTitle: '全公司拜访记录与跟进任务' }}>
      <ProTable<VisitRecord>
        headerTitle="拜访列表"
        actionRef={actionRef}
        columns={columns}
        request={async (params) => {
          const res = await visitAPI.list({
            page: params.current || 1,
            page_size: params.pageSize || 10,
            status: params.status || undefined,
          });
          return { data: res.data.data.items, total: res.data.data.total, success: true };
        }}
        rowKey="id"
      />
      <VisitDetailDrawer record={detail} onClose={() => setDetail(null)} />
    </PageContainer>
  );
}
