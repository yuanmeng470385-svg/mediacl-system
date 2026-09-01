import { useRef, useState } from 'react';
import { ProTable, ModalForm, ProFormText, ProFormSwitch } from '@ant-design/pro-components';
import type { ProColumns, ActionType } from '@ant-design/pro-components';
import { App, Button, Descriptions, Drawer, Input, Radio, Space, Spin, Tag, Tooltip, Typography } from 'antd';
import { skillAPI } from '../../services/skill';
import { practiceAPI } from '../../services/practice';
import { useAuth } from '../../context/AuthContext';
import type { PracticeTranscript, SkillAuditRecord, SkillPackage } from '../../types';

const { Text } = Typography;
const AUDIT_MAP: Record<string, { color: string; text: string }> = {
  pending: { color: 'orange', text: '待审核' },
  approved: { color: 'green', text: '已通过' },
  rejected: { color: 'red', text: '已驳回' },
};
const CREATOR_ROLE_MAP: Record<string, { color: string; text: string }> = {
  rep: { color: 'blue', text: '代表发布' },
  admin: { color: 'purple', text: '管理员' },
  manager: { color: 'geekblue', text: '经理' },
  compliance: { color: 'cyan', text: '合规' },
  medical: { color: 'green', text: '医学部' },
};
// 键对齐后端 skill_audits.audit_result（存的是 audit_status：approved/rejected）
const RESULT_MAP: Record<string, { color: string; text: string }> = {
  approved: { color: 'green', text: '通过' },
  rejected: { color: 'red', text: '驳回' },
};
// 与后端 skill_packages.py 对齐：审核=全 SKILL_ADMIN_ROLES（2026-09-01 当日二调，
// 曾收敛合规/医学部后按用户拍板恢复——小公司单账号审核；受控查看同范围）
const SKILL_REVIEW_ROLES = ['admin', 'manager', 'compliance', 'medical'];

export default function SkillList() {
  const actionRef = useRef<ActionType>();
  const { message } = App.useApp();
  const { user } = useAuth();
  const canReview = SKILL_REVIEW_ROLES.includes(user?.role || '');
  const [current, setCurrent] = useState<SkillPackage | null>(null);
  const [audits, setAudits] = useState<SkillAuditRecord[]>([]);
  const [verdict, setVerdict] = useState<'approve' | 'reject'>('approve');
  const [reason, setReason] = useState('');
  const [submitting, setSubmitting] = useState(false);
  const [createOpen, setCreateOpen] = useState(false);
  const [offShelfTarget, setOffShelfTarget] = useState<SkillPackage | null>(null);
  const [offType, setOffType] = useState<'compliance' | 'author'>('compliance');
  const [offReason, setOffReason] = useState('');
  const [offSubmitting, setOffSubmitting] = useState(false);
  const [transcript, setTranscript] = useState<PracticeTranscript | null>(null);
  const [transcriptLoading, setTranscriptLoading] = useState(false);

  // 受控查看：列表接口不返回 content/skill_weights/source_session_ids（隐私边界附录B-1），
  // 审核/查看前走 detail 拿受控字段 + audits 拿审核留痕（2026-09-01 审核盲审修复）
  const openReview = async (row: SkillPackage) => {
    try {
      const [detailRes, auditsRes] = await Promise.all([
        skillAPI.detail(row.id),
        skillAPI.audits(row.id),
      ]);
      setCurrent(detailRes.data.data);
      setAudits(auditsRes.data.data || []);
      setVerdict('approve');
      setReason('');
    } catch {
      /* client.ts 拦截器已弹错误 */
    }
  };

  const submitReview = async () => {
    if (!current) return;
    if (verdict === 'reject' && !reason.trim()) {
      message.warning('驳回必须填写原因');
      return;
    }
    setSubmitting(true);
    try {
      await skillAPI.review(current.id, {
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

  // 下架前也走 detail：下架裁决同样要看清被处置内容（2026-09-01）
  const openOffShelf = async (row: SkillPackage) => {
    setOffType('compliance');
    setOffReason('');
    setOffShelfTarget(row);
    try {
      const res = await skillAPI.detail(row.id);
      setOffShelfTarget(res.data.data);
    } catch {
      /* 拉不到受控字段时保底展示列表元数据 */
    }
  };

  const submitOffShelf = async () => {
    if (!offShelfTarget) return;
    if (!offReason.trim()) {
      message.warning('下架原因必填');
      return;
    }
    setOffSubmitting(true);
    try {
      await skillAPI.offShelf(offShelfTarget.id, { type: offType, reason: offReason.trim() });
      message.success('已下架');
      setOffShelfTarget(null);
      actionRef.current?.reload();
    } catch {
      /* client.ts 拦截器已弹错误 */
    } finally {
      setOffSubmitting(false);
    }
  };

  // 审核溯源：受控查看提取来源会话的原始对话（后端记 practice_source_view 审计）
  const openTranscript = async (sessionId: number) => {
    setTranscriptLoading(true);
    try {
      const res = await practiceAPI.reviewTranscript(sessionId);
      setTranscript(res.data.data);
    } catch {
      /* client.ts 拦截器已弹错误 */
    } finally {
      setTranscriptLoading(false);
    }
  };

  const creatorText = (r: SkillPackage) => {
    if (!r.creator_name) return '-';
    const m = CREATOR_ROLE_MAP[r.creator_role || ''] || { color: 'default', text: r.creator_role || '官方' };
    return (
      <Space size={4}>
        <span>{r.creator_name}</span>
        <Tag color={m.color}>{m.text}</Tag>
      </Space>
    );
  };

  const columns: ProColumns<SkillPackage>[] = [
    { title: '名称', dataIndex: 'name' },
    { title: '说明', dataIndex: 'description', hideInSearch: true, ellipsis: true },
    { title: '风格标签', dataIndex: 'style_tags', hideInSearch: true, render: (_, r) => (r.style_tags || []).join(' / ') },
    { title: '创建者', dataIndex: 'creator_name', hideInSearch: true, render: (_, r) => creatorText(r) },
    {
      title: '审核状态', dataIndex: 'audit_status', width: 100,
      valueEnum: { pending: '待审核', approved: '已通过', rejected: '已驳回' },
      render: (_, r) => {
        const m = AUDIT_MAP[r.audit_status] || { color: 'default', text: r.audit_status };
        return <Tag color={m.color}>{m.text}</Tag>;
      },
    },
    {
      title: '下架状态', dataIndex: 'off_shelf_status', width: 100,
      valueEnum: { active: '已上架', off_shelved: '已下架' },
      render: (_, r) => {
        const off = r.off_shelf_status === 'off_shelved';
        return (
          <Tooltip title={off && r.off_shelf_reason ? r.off_shelf_reason : undefined}>
            <Tag color={off ? 'red' : 'green'}>{off ? '已下架' : '已上架'}</Tag>
          </Tooltip>
        );
      },
    },
    { title: '热度', dataIndex: 'heat', width: 70, hideInSearch: true },
    { title: '好评率', dataIndex: 'approval_rate', width: 90, hideInSearch: true },
    {
      title: '操作', width: 140,
      render: (_, r) => (
        <Space size="middle">
          {/* 审核裁决收敛合规/医学部；其余管理角色保留「查看」受控详情（方案 B） */}
          <a onClick={() => openReview(r)}>{r.audit_status === 'pending' && canReview ? '审核' : '查看'}</a>
          {r.off_shelf_status === 'active' && <a onClick={() => openOffShelf(r)}>下架</a>}
        </Space>
      ),
    },
  ];

  return (
    <>
      <ProTable<SkillPackage>
        headerTitle="技能模版管理"
        actionRef={actionRef}
        rowKey="id"
        search={{ labelWidth: 80 }}
        columns={columns}
        request={async (params) => {
          const res = await skillAPI.assetList({
            page: params.current || 1,
            page_size: params.pageSize || 10,
            audit_status: params.audit_status,
            off_shelf_status: params.off_shelf_status,
          });
          return { data: res.data.data.items, total: res.data.data.total, success: true };
        }}
        toolBarRender={() => [<Button type="primary" key="new" onClick={() => setCreateOpen(true)}>新建官方模版</Button>]}
      />
      <ModalForm
        key="create"
        title="新建官方技能模版"
        open={createOpen}
        onOpenChange={setCreateOpen}
        modalProps={{ destroyOnHidden: true }}
        onFinish={async (values) => {
          try {
            // style_tags 逗号分隔输入 → 字符串数组（后端 skill_packages.style_tags 为 JSONB 数组）
            const styleTags: string[] = values.style_tags
              ? String(values.style_tags).split(/[,，]/).map((s: string) => s.trim()).filter(Boolean)
              : [];
            await skillAPI.create({
              name: values.name,
              style_tags: styleTags,
              skill_weights: {
                formal_level: values.formal_level,
                reply_length: values.reply_length,
                opening_mode: values.opening_mode,
              },
              // 官方模版默认上架代表侧广场（后端 create 已支持 is_public；审核通过后 approved+is_public 才生效）
              is_public: values.is_public !== false,
            });
            message.success('已创建，待审核');
            setCreateOpen(false);
            actionRef.current?.reload();
            return true;
          } catch (e) {
            // 400-499 已由 client.ts 拦截器弹后端 message；网络层错误至少留痕
            console.error('新建技能模版失败', e);
            return false; // 保留表单
          }
        }}
      >
        <ProFormText name="name" label="名称" rules={[{ required: true }]} />
        <ProFormText name="style_tags" label="风格标签（逗号分隔）" placeholder="严谨学术, 亲和力" />
        <ProFormText name="formal_level" label="正式程度" initialValue="标准学术" />
        <ProFormText name="reply_length" label="回复长度" initialValue="标准" />
        <ProFormText name="opening_mode" label="开场白模式" initialValue="直切主题" />
        <ProFormSwitch name="is_public" label="上架代表广场" initialValue tooltip="开启后审核通过即上架广场并可在陪练场加载" />
      </ModalForm>
      <Drawer title={canReview ? '技能审核' : '技能详情'} width={560} open={!!current} onClose={() => setCurrent(null)} destroyOnHidden>
        {current && (
          <Space direction="vertical" size="middle" style={{ width: '100%' }}>
            <Descriptions column={1} size="small" bordered>
              <Descriptions.Item label="名称">{current.name}</Descriptions.Item>
              <Descriptions.Item label="创建者">{creatorText(current)}</Descriptions.Item>
              <Descriptions.Item label="说明">
                <span style={{ whiteSpace: 'pre-wrap' }}>{current.description || '-'}</span>
              </Descriptions.Item>
              <Descriptions.Item label="风格标签">{(current.style_tags || []).join(' / ')}</Descriptions.Item>
              <Descriptions.Item label="话术内容（受控查看）">
                <span style={{ whiteSpace: 'pre-wrap' }}>{current.content || '（无内容）'}</span>
              </Descriptions.Item>
              <Descriptions.Item label="沟通风格参数（受控查看）">
                <Text code>{JSON.stringify(current.skill_weights, null, 2)}</Text>
              </Descriptions.Item>
              <Descriptions.Item label="提取来源会话">
                {(current.source_session_ids || []).length
                  ? (
                    <Space wrap>
                      {(current.source_session_ids || []).map((sid) => (
                        <Button key={sid} size="small" onClick={() => openTranscript(sid)}>会话 #{sid}</Button>
                      ))}
                    </Space>
                  )
                  : '（未携带/官方模版）'}
              </Descriptions.Item>
            </Descriptions>
            <div>
              <Text type="secondary">审核历史（{audits.length}）</Text>
              {audits.length === 0
                ? <div style={{ color: '#999', marginTop: 4 }}>暂无审核记录</div>
                : (
                  <div style={{ marginTop: 4 }}>
                    {audits.map((a) => {
                      const m = RESULT_MAP[a.audit_result] || { color: 'default', text: a.audit_result };
                      return (
                        <div key={a.id} style={{ padding: '4px 0', borderBottom: '1px solid #f0f0f0' }}>
                          <Space size={8} wrap>
                            <Tag color={m.color}>{m.text}</Tag>
                            <span>{a.auditor_name || '审核人 #' + a.auditor_id}</span>
                            <Text type="secondary">{a.created_at || ''}</Text>
                          </Space>
                          {a.reason && <div style={{ marginTop: 2 }}>原因：{a.reason}</div>}
                        </div>
                      );
                    })}
                  </div>
                )}
            </div>
            {canReview && (
              <>
                <Radio.Group value={verdict} onChange={(e) => setVerdict(e.target.value)} disabled={current.audit_status !== 'pending'}>
                  <Radio.Button value="approve">通过</Radio.Button>
                  <Radio.Button value="reject">驳回</Radio.Button>
                </Radio.Group>
                {verdict === 'reject' && current.audit_status === 'pending' && (
                  <Input.TextArea
                    rows={3}
                    placeholder="驳回原因（必填）"
                    value={reason}
                    onChange={(e) => setReason(e.target.value)}
                    maxLength={500}
                  />
                )}
                <Button
                  type="primary"
                  block
                  loading={submitting}
                  onClick={submitReview}
                  disabled={current.audit_status !== 'pending'}
                >
                  {current.audit_status !== 'pending' ? '当前状态不可审核' : '提交审核'}
                </Button>
              </>
            )}
          </Space>
        )}
      </Drawer>
      <Drawer title="技能下架" width={560} open={!!offShelfTarget} onClose={() => setOffShelfTarget(null)} destroyOnHidden>
        {offShelfTarget && (
          <Space direction="vertical" size="middle" style={{ width: '100%' }}>
            <Descriptions column={1} size="small" bordered>
              <Descriptions.Item label="名称">{offShelfTarget.name}</Descriptions.Item>
              <Descriptions.Item label="创建者">{creatorText(offShelfTarget)}</Descriptions.Item>
              <Descriptions.Item label="说明">
                <span style={{ whiteSpace: 'pre-wrap' }}>{offShelfTarget.description || '-'}</span>
              </Descriptions.Item>
              <Descriptions.Item label="话术内容（受控查看）">
                <span style={{ whiteSpace: 'pre-wrap' }}>{offShelfTarget.content || '（无内容）'}</span>
              </Descriptions.Item>
            </Descriptions>
            <Radio.Group value={offType} onChange={(e) => setOffType(e.target.value)}>
              <Radio value="compliance">合规下架</Radio>
              <Radio value="author">作者申请下架</Radio>
            </Radio.Group>
            <Input.TextArea
              rows={4}
              placeholder="下架原因（必填）"
              value={offReason}
              onChange={(e) => setOffReason(e.target.value)}
              maxLength={500}
            />
            <Button
              type="primary"
              danger
              block
              loading={offSubmitting}
              onClick={submitOffShelf}
            >
              确认下架
            </Button>
          </Space>
        )}
      </Drawer>
      <Drawer
        title={transcript ? '来源会话 #' + transcript.id : '来源会话'}
        width={520}
        open={transcriptLoading || !!transcript}
        onClose={() => setTranscript(null)}
        destroyOnHidden
      >
        {transcriptLoading && !transcript ? (
          <div style={{ textAlign: 'center', padding: 40 }}><Spin /></div>
        ) : transcript && (
          <Space direction="vertical" size="middle" style={{ width: '100%' }}>
            <Descriptions column={1} size="small" bordered>
              <Descriptions.Item label="代表">{transcript.rep_name || '#' + transcript.representative_id}</Descriptions.Item>
              <Descriptions.Item label="场景">{transcript.scenario}</Descriptions.Item>
              <Descriptions.Item label="轮次">{transcript.turn_count}</Descriptions.Item>
              <Descriptions.Item label="时间">{transcript.created_at || '-'}</Descriptions.Item>
            </Descriptions>
            <div>
              <Text type="secondary">原始对话（核对提取摘录是否忠于本人原文）</Text>
              <div style={{ marginTop: 8 }}>
                {(transcript.transcript || []).map((t, i) => (
                  <div key={i} style={{ marginBottom: 8 }}>
                    <Tag color={t.role === 'rep' ? 'blue' : 'green'}>{t.role === 'rep' ? '代表' : t.role === 'doctor' ? '医生' : t.role}</Tag>
                    <span style={{ whiteSpace: 'pre-wrap' }}>{t.content}</span>
                  </div>
                ))}
              </div>
            </div>
          </Space>
        )}
      </Drawer>
    </>
  );
}
