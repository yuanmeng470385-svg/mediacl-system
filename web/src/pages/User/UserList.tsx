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
    { title: '姓名', dataIndex: 'name', width: 120 },
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
      <ModalForm title={editing ? '编辑用户' : '新增用户'} open={formOpen} onOpenChange={setFormOpen}
        onFinish={async (values) => {
          if (editing) await userAPI.update(editing.id, values);
          else await userAPI.create(values);
          message.success(`${editing ? '编辑' : '新增'}成功`);
          actionRef.current?.reload();
          return true;
        }}
        initialValues={editing || undefined}>
        <ProFormText name="name" label="姓名" rules={[{ required: true }]} />
        <ProFormText name="phone" label="手机号" rules={[{ required: true }]} />
        <ProFormSelect name="role" label="角色" rules={[{ required: true }]}
          options={Object.entries(ROLE_MAP).map(([k, v]) => ({ label: v.text, value: k }))} />
        <ProFormText name="region" label="区域" />
      </ModalForm>
    </>
  );
}
