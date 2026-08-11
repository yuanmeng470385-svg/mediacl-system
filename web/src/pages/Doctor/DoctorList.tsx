import { useRef, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { ProTable, ModalForm, ProFormText, ProFormSelect } from '@ant-design/pro-components';
import type { ProColumns, ActionType } from '@ant-design/pro-components';
import { Button, Tag, Space, App } from 'antd';
import { PlusOutlined } from '@ant-design/icons';
import { doctorAPI } from '../../services/doctor';
import { useAuth } from '../../hooks/useAuth';
import type { Doctor } from '../../types';

export default function DoctorList() {
  const actionRef = useRef<ActionType>();
  const navigate = useNavigate();
  const { message } = App.useApp();
  const [formOpen, setFormOpen] = useState(false);
  const { user: me } = useAuth();
  // 后端 POST /hcps 仅 admin/manager（require_roles），其余角色隐藏新增按钮
  const canWrite = me?.role === 'admin' || me?.role === 'manager';

  const columns: ProColumns<Doctor>[] = [
    { title: '姓名', dataIndex: 'name', width: 100 },
    { title: '医院', dataIndex: 'hospital', width: 180, ellipsis: true },
    { title: '科室', dataIndex: 'department', width: 120 },
    { title: '职称', dataIndex: 'title', width: 100 },
    { title: '标签', dataIndex: 'tags', width: 200,
      render: (_, r) => <Space wrap>{(r.tags ?? []).map((t) => <Tag key={t}>{t}</Tag>)}</Space> },
    { title: '拜访次数', dataIndex: 'visit_count', width: 100,
      render: (_, r) => (r.visit_count != null ? r.visit_count : '--') },
    { title: '满意度', dataIndex: 'satisfaction', width: 100,
      render: (_, r) => (r.satisfaction != null ? `${r.satisfaction}%` : '--') },
    { title: '操作', width: 100,
      render: (_, r) => <a onClick={() => navigate(`/doctor/${r.id}`)}>查看详情</a> },
  ];

  return (
    <>
      <ProTable<Doctor>
        headerTitle="医生管理"
        actionRef={actionRef}
        columns={columns}
        request={async (params) => {
          const res = await doctorAPI.list({
            page: params.current || 1, page_size: params.pageSize || 10,
            keyword: params.keyword, hospital: params.hospital,
            department: params.department, tag: params.tag,
          });
          return { data: res.data.data.items, total: res.data.data.total, success: true };
        }}
        rowKey="id"
        search={{ labelWidth: 80 }}
        toolBarRender={() => canWrite
          ? [<Button key="add" type="primary" icon={<PlusOutlined />} onClick={() => setFormOpen(true)}>新增医生</Button>]
          : []}
      />
      <ModalForm
        key="create"
        title="新增医生"
        open={formOpen}
        onOpenChange={setFormOpen}
        modalProps={{ destroyOnHidden: true }}
        onFinish={async (values) => {
          try {
            // 字段对齐后端白名单 HCP_WRITABLE_FIELDS；空字段以空串提交（白名单仅校验字段名）
            const payload: Partial<Doctor> = {
              name: values.name,
              hospital: values.hospital,
              department: values.department,
              title: values.title,
              specialty: values.specialty,
              phone: values.phone,
              email: values.email,
              region: values.region,
              influence_level: values.influence_level,
            };
            if (Array.isArray(values.tags) && values.tags.length) payload.tags = values.tags;
            await doctorAPI.create(payload);
            message.success('新增成功');
            actionRef.current?.reload();
            return true;
          } catch (e) {
            // 400-499 已由 client.ts 拦截器弹后端 message；网络层错误（拦截器不弹）至少留痕
            console.error('新增医生失败', e);
            return false; // 保留表单
          }
        }}>
        <ProFormText name="name" label="姓名" rules={[{ required: true }]} placeholder="医生姓名（必填）" />
        <ProFormText name="hospital" label="医院" />
        <ProFormText name="department" label="科室" />
        <ProFormText name="title" label="职称" />
        <ProFormText name="specialty" label="专业方向" />
        <ProFormText name="phone" label="电话" />
        <ProFormText name="email" label="邮箱" />
        <ProFormText name="region" label="区域" />
        <ProFormSelect name="influence_level" label="影响力"
          options={[{ label: '高', value: 'high' }, { label: '中', value: 'medium' }, { label: '低', value: 'low' }]} />
        <ProFormSelect name="tags" label="标签" mode="tags" placeholder="输入后回车添加" />
      </ModalForm>
    </>
  );
}
