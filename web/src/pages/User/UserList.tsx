import { useRef, useState } from 'react';
import { ProTable, ModalForm, ProFormText, ProFormSelect } from '@ant-design/pro-components';
import type { ProColumns, ActionType } from '@ant-design/pro-components';
import { Button, Tag, App } from 'antd';
import { PlusOutlined } from '@ant-design/icons';
import { userAPI } from '../../services/user';
import { useAuth } from '../../hooks/useAuth';
import type { User } from '../../types';

const ROLE_MAP: Record<string, { color: string; text: string }> = {
  admin: { color: 'red', text: '管理员' }, manager: { color: 'blue', text: '管理者' },
  rep: { color: 'green', text: '代表' }, compliance: { color: 'orange', text: '合规' },
  medical: { color: 'purple', text: '医学' }, finance: { color: 'cyan', text: '财务' },
  doctor: { color: 'geekblue', text: '医生' },
};

export default function UserList() {
  const actionRef = useRef<ActionType>();
  const [formOpen, setFormOpen] = useState(false);
  const [editing, setEditing] = useState<User | null>(null);
  const { message } = App.useApp();
  const { user: me } = useAuth();

  // #7：后端仅 admin 可变更角色，且任何人不能改自己（users.py update_user 403 语义）
  // —— 非 admin 或编辑自己时，编辑请求不带 role、表单禁用角色选择
  const editingIsSelf = !!editing && !!me && editing.id === me.id;
  const canEditRole = me?.role === 'admin' && !editingIsSelf;

  const columns: ProColumns<User>[] = [
    { title: '用户名', dataIndex: 'username', width: 120 },
    { title: '姓名', dataIndex: 'full_name', width: 120 },
    { title: '手机号', dataIndex: 'phone', width: 140 },
    { title: '角色', dataIndex: 'role', width: 100,
      render: (_, r) => { const rm = ROLE_MAP[r.role] || { color: 'default', text: r.role }; return <Tag color={rm.color}>{rm.text}</Tag>; },
      valueEnum: { admin: '管理员', manager: '管理者', rep: '代表', compliance: '合规', medical: '医学', finance: '财务', doctor: '医生' } },
    { title: '区域', dataIndex: 'region', width: 120 },
    { title: '状态', dataIndex: 'status', width: 80,
      // valueEnum 让搜索表单渲染为 启用/禁用 下拉（后端 users.py list 支持 status 筛选）
      valueEnum: { active: '启用', disabled: '禁用' },
      render: (_, r) => <Tag color={r.status === 'active' ? 'green' : 'red'}>{r.status === 'active' ? '启用' : '禁用'}</Tag> },
    { title: '操作', width: 100,
      render: (_, r) => <a onClick={() => { setEditing(r); setFormOpen(true); }}>编辑</a> },
  ];

  return (
    <>
      <ProTable<User>
        headerTitle="用户管理"
        actionRef={actionRef}
        columns={columns}
        request={async (params) => {
          const res = await userAPI.list({ page: params.current || 1, page_size: params.pageSize || 10, role: params.role, status: params.status });
          return { data: res.data.data.items, total: res.data.data.total, success: true };
        }}
        rowKey="id"
        search={{ labelWidth: 80 }}
        toolBarRender={() => [
          <Button key="add" type="primary" icon={<PlusOutlined />} onClick={() => { setEditing(null); setFormOpen(true); }}>新增用户</Button>,
        ]}
      />
      <ModalForm
        key={editing?.id ?? 'create'}
        title={editing ? '编辑用户' : '新增用户'}
        open={formOpen}
        onOpenChange={setFormOpen}
        modalProps={{ destroyOnHidden: true }}
        onFinish={async (values) => {
          try {
            if (editing) {
              // 后端更新白名单是 full_name（users.py UPDATEABLE_FIELDS），name 不生效
              const payload: Partial<User> = {
                full_name: values.full_name,
                region: values.region,
              };
              // 手机号变更仅限 admin（users.py:158-159）：非 admin 传 phone（含原值重提）必 403。
              // 禁用输入框的值仍会进入 values，故必须按值比较，仅在确实变化时才携带
              if (values.phone !== editing.phone) payload.phone = values.phone;
              // 仅 admin 且非本人时才带 role —— 否则后端必 403
              // （manager 带 role 拒绝 / 自改 role 拒绝），manager 编辑不再 403
              if (canEditRole) payload.role = values.role;
              await userAPI.update(editing.id, payload);
            } else {
              const payload: Partial<User> = {
                username: values.username,
                full_name: values.full_name,
                phone: values.phone,
                region: values.region,
              };
              // 后端：manager 传 role 一律拒绝（仅 admin 可指定角色）；rep 是默认角色 → 不传，
              // 避免 manager 新增默认用户时误 403
              if (values.role && values.role !== 'rep') payload.role = values.role;
              await userAPI.create(payload);
            }
            message.success(`${editing ? '编辑' : '新增'}成功`);
            actionRef.current?.reload();
            setEditing(null);
            return true;
          } catch {
            return false;
          }
        }}
        initialValues={editing || undefined}>
        {!editing && (
          <ProFormText name="username" label="用户名" rules={[{ required: true }]} placeholder="登录账号（创建后不可修改）" />
        )}
        <ProFormText name="full_name" label="姓名" rules={[{ required: true }]} />
        {/* 手机号变更仅限 admin（users.py:158-159 非 admin 传 phone 必 403）—— 非 admin 编辑时禁用 */}
        <ProFormText name="phone" label="手机号" rules={[{ required: true }]}
          disabled={!!editing && me?.role !== 'admin'}
          tooltip={editing && me?.role !== 'admin' ? '仅管理员可变更用户手机号' : undefined} />
        <ProFormSelect name="role" label="角色" rules={[{ required: true }]}
          disabled={editing ? !canEditRole : me?.role !== 'admin'}
          tooltip={editing
            ? (canEditRole ? '可变更角色' : '仅管理员可修改角色，且不能修改自己的角色')
            : (me?.role === 'admin' ? '可指定角色' : '仅管理员可指定角色，将按默认角色创建')}
          options={Object.entries(ROLE_MAP).map(([k, v]) => ({ label: v.text, value: k }))} />
        <ProFormText name="region" label="区域" />
      </ModalForm>
    </>
  );
}
