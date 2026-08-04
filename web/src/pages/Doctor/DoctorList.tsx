import { useRef } from 'react';
import { useNavigate } from 'react-router-dom';
import { ProTable } from '@ant-design/pro-components';
import type { ProColumns, ActionType } from '@ant-design/pro-components';
import { Button, Tag, Space, App } from 'antd';
import { PlusOutlined } from '@ant-design/icons';
import { doctorAPI } from '../../services/doctor';
import type { Doctor } from '../../types';

export default function DoctorList() {
  const actionRef = useRef<ActionType>();
  const navigate = useNavigate();
  const { message } = App.useApp();

  const columns: ProColumns<Doctor>[] = [
    { title: '姓名', dataIndex: 'name', width: 100 },
    { title: '医院', dataIndex: 'hospital', width: 180, ellipsis: true },
    { title: '科室', dataIndex: 'department', width: 120 },
    { title: '职称', dataIndex: 'title', width: 100 },
    { title: '标签', dataIndex: 'tags', width: 200,
      render: (_, r) => <Space wrap>{r.tags?.map((t) => <Tag key={t}>{t}</Tag>)}</Space> },
    { title: '拜访次数', dataIndex: 'visit_count', width: 100, sorter: true },
    { title: '满意度', dataIndex: 'satisfaction', width: 100, sorter: true,
      render: (_, r) => `${r.satisfaction}%` },
    { title: '操作', width: 100,
      render: (_, r) => <a onClick={() => navigate(`/doctor/${r.id}`)}>查看详情</a> },
  ];

  return (
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
      toolBarRender={() => [
        <Button key="add" type="primary" icon={<PlusOutlined />} onClick={() => message.info('新增医生功能')}>新增医生</Button>,
      ]}
    />
  );
}
