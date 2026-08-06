import { useRef, useState } from 'react';
import { ProTable, ModalForm, ProFormText, ProFormSelect } from '@ant-design/pro-components';
import type { ProColumns, ActionType } from '@ant-design/pro-components';
import { Button, Tag, App } from 'antd';
import { PlusOutlined } from '@ant-design/icons';
import { userAPI } from '../../services/user';
import type { User } from '../../types';

const ROLE_MAP: Record<string, { color: string; text: string }> = {
  admin: { color: 'red', text: '管理员' }, manager: { color: 'blue', text: '管理者' },
  rep: { color: 'green', text: '代表' }, compliance: { color: 'orange', text: '合规' },
  medical: { color: 'purple', text: '医学' }, finance: { color: 'cyan', text: '财务' },
};

export default function UserList() {
  const actionRef = useRef<ActionType>();
  const [formOpen, setFormOpen] = useState(false);
  const [editing, setEditing] = useState<User | null>(null);
  const { message } = App.useApp();

  const columns: ProColumns<User>[] = [
    { title: '用户名', dataIndex: 'username', width: 120 },
    { title: '姓名', dataIndex: 'full_name', width: 120 },
    { title: '手机号', dataIndex: 'phone', width: 140 },
    { title: '角色', dataIndex: 'role', width: 100,
      render: (_, r) => { const rm = ROLE_MAP[r.role] || { color: 'default', text: r.role }; return <Tag color={rm.color}>{rm.text}</Tag>; },
      valueEnum: { admin: '管理员', manager: '管理者', rep: '代表', compliance: '合规', medical: '医学', finance: '财务' } },
    { title: '区域', dataIndex: 'region', width: 120 },
    { title: '状态', dataIndex: 'status', width: 80,
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
          const res = await userAPI.list({ page: params.current || 1, page_size: params.pageSize || 10, role: params.role });
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
              await userAPI.update(editing.id, {
                full_name: values.full_name,
                phone: values.phone,
                role: values.role,
                region: values.region,
              });
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
        <ProFormText name="phone" label="手机号" rules={[{ required: true }]} />
        <ProFormSelect name="role" label="角色" rules={[{ required: true }]}
          options={Object.entries(ROLE_MAP).map(([k, v]) => ({ label: v.text, value: k }))} />
        <ProFormText name="region" label="区域" />
      </ModalForm>
    </>
  );
}
