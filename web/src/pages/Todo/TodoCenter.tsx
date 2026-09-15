/**
 * 待办中心（2026-09-15 C 批）：八类待审/待办事务集中列表。
 * 计数来自 auth + specialist 两端 todo-summary（并行拉取）；行按当前角色
 * canAccess(目标页) 过滤（compliance 看不到仅 admin/manager 的页面就不给入口）。
 * 菜单徽标（红色数字）在 AdminLayout 轮询同一数据源。
 */
import { useCallback, useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { Badge, Button, Card, Empty, List, Space, Spin, Tag, Typography, message } from 'antd';
import {
  FileProtectOutlined, IdcardOutlined, LockOutlined, OrderedListOutlined,
  ExperimentOutlined, ReadOutlined, CommentOutlined, ExportOutlined, RightOutlined,
} from '@ant-design/icons';
import { fetchTodoCounts } from '../../services/todo';
import { canAccess } from '../../constants/routeAccess';
import { useAuth } from '../../hooks/useAuth';

/** 待办类别配置：key 对齐后端 todo-summary；label/path 给 UI 与跳转 */
const TODO_ITEMS: Array<{
  key: string;
  label: string;
  desc: string;
  path: string;
  filterHint: string;
  icon: React.ReactNode;
}> = [
  {
    key: 'qualification_pending', label: '备案资质审核', path: '/filing/list', filterHint: '待审核',
    desc: '代表提交的备案资质（学历/培训证明），审核通过才算合规上岗',
    icon: <FileProtectOutlined />,
  },
  {
    key: 'doctor_cert_pending', label: '医生认证审核', path: '/doctor-cert/list', filterHint: '待审核',
    desc: '医生端提交的执业资质（资格证/执业证）',
    icon: <IdcardOutlined />,
  },
  {
    key: 'exam_question_pending', label: '考试题目审核', path: '/training/list', filterHint: '待审核',
    desc: '题库中待人工复核的题目（AI 出题草稿入库后同样送审）',
    icon: <OrderedListOutlined />,
  },
  {
    key: 'privacy_open', label: '隐私请求处理', path: '/privacy/requests', filterHint: '待处理',
    desc: '医生的查阅/更正/删除/导出等隐私请求（30 日 SLA）',
    icon: <LockOutlined />,
  },
  {
    key: 'skill_package_pending', label: 'Skill 模版审核', path: '/skill/list', filterHint: '待审核',
    desc: '代表发布到公共空间的 Skill 模版，审核通过后进广场',
    icon: <ExperimentOutlined />,
  },
  {
    key: 'patient_edu_pending', label: '患教内容审核', path: '/patient-edu/review', filterHint: '待审核',
    desc: '医生分享到患教专区的内容',
    icon: <ReadOutlined />,
  },
  {
    key: 'objection_script_pending', label: '异议话术审核', path: '/practice/objections', filterHint: '待审核',
    desc: '话术库新增/编辑的异议话术（含 AI 起草与真实数据提取草稿）',
    icon: <CommentOutlined />,
  },
  {
    key: 'data_export_pending', label: '数据导出审批', path: '/data/exports', filterHint: '待审批',
    desc: '敏感数据导出申请（对话明细，3 日 SLA 提醒）',
    icon: <ExportOutlined />,
  },
];

export default function TodoCenter() {
  const navigate = useNavigate();
  const { user } = useAuth();
  const [counts, setCounts] = useState<Record<string, number> | null>(null);

  const load = useCallback(async () => {
    try {
      setCounts(await fetchTodoCounts());
    } catch {
      // allSettled 只在网络层全挂时 reject；client.ts 已弹错误
      setCounts({});
    }
  }, []);

  useEffect(() => {
    load();
    const timer = setInterval(load, 60_000);
    return () => clearInterval(timer);
  }, [load]);

  const visible = TODO_ITEMS.filter((it) => canAccess(it.path, user?.role));
  const withCounts = visible.map((it) => ({ ...it, count: counts?.[it.key] ?? 0 }));
  const pending = withCounts.filter((it) => it.count > 0);
  const total = withCounts.reduce((a, b) => a + b.count, 0);

  return (
    <Card
      title={
        <Space>
          <span>待办中心</span>
          {counts && total > 0 && <Badge count={total} overflowCount={99} />}
          {counts && total === 0 && <Tag color="success">全部办结</Tag>}
        </Space>
      }
      extra={
        <Button size="small" onClick={load}>
          刷新
        </Button>
      }
    >
      <Typography.Paragraph type="secondary" style={{ marginBottom: 16 }}>
        待审与待处理事务集中在这里：审核完成后计数自动归零，左侧菜单的红色数字同步消失（每分钟刷新）。
      </Typography.Paragraph>

      {counts === null ? (
        <div style={{ textAlign: 'center', padding: 48 }}>
          <Spin />
        </div>
      ) : pending.length === 0 ? (
        <Empty description="暂无待办事务" style={{ padding: 32 }} />
      ) : (
        <List
          dataSource={pending}
          renderItem={(item) => (
            <List.Item
              actions={[
                <Button
                  key="go"
                  type="link"
                  onClick={() => {
                    if (item.count === 0) {
                      message.info('该项暂无待办');
                      return;
                    }
                    navigate(item.path);
                  }}
                >
                  去处理 <RightOutlined />
                </Button>,
              ]}
            >
              <List.Item.Meta
                avatar={
                  <Badge count={item.count} overflowCount={99} size="small" offset={[-4, 28]}>
                    <span style={{ fontSize: 22, color: '#1677ff' }}>{item.icon}</span>
                  </Badge>
                }
                title={
                  <Space>
                    {item.label}
                    <Tag color="orange">{item.filterHint} {item.count}</Tag>
                  </Space>
                }
                description={item.desc}
              />
            </List.Item>
          )}
        />
      )}

      {counts !== null && withCounts.length > pending.length && (
        <Typography.Paragraph type="secondary" style={{ marginTop: 16, marginBottom: 0, fontSize: 12 }}>
          其余 {withCounts.length - pending.length} 类（{withCounts.filter((i) => i.count === 0).map((i) => i.label).join('、')}）当前无待办。
        </Typography.Paragraph>
      )}
    </Card>
  );
}
