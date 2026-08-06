import { useEffect, useState } from 'react';
import { useParams } from 'react-router-dom';
import { PageContainer } from '@ant-design/pro-components';
import { Card, Descriptions, Tag, Timeline, Space, Spin, App, Empty } from 'antd';
import { PhoneOutlined } from '@ant-design/icons';
import {
  doctorAPI,
  formatProfileField,
  formatVisitTime,
} from '../../services/doctor';
import type { DoctorDetail as DoctorDetailData, DoctorInteraction } from '../../services/doctor';

export default function DoctorDetail() {
  const { id } = useParams<{ id: string }>();
  const [doctor, setDoctor] = useState<DoctorDetailData | null>(null);
  const [interactions, setInteractions] = useState<DoctorInteraction[]>([]);
  const [loading, setLoading] = useState(true);
  const { message } = App.useApp();

  useEffect(() => {
    if (!id) return;
    Promise.all([doctorAPI.detail(id), doctorAPI.interactions(id)])
      .then(([dr, ir]) => {
        setDoctor(dr.data.data);
        setInteractions(ir.data.data);
      })
      .catch(() => message.error('加载失败'))
      .finally(() => setLoading(false));
  }, [id]);

  if (loading) return <Spin size="large" style={{ display: 'block', margin: '40vh auto' }} />;
  if (!doctor) return <div>医生不存在</div>;

  const academic = formatProfileField(doctor.academic_background);
  const prescription = formatProfileField(doctor.prescription_preference);

  return (
    <PageContainer header={{ title: doctor.name, subTitle: `${doctor.hospital} - ${doctor.department}` }}>
      <Card title="基本信息" style={{ marginBottom: 16 }}>
        <Descriptions column={3}>
          <Descriptions.Item label="职称">{doctor.title || '--'}</Descriptions.Item>
          <Descriptions.Item label="科室">{doctor.department || '--'}</Descriptions.Item>
          <Descriptions.Item label="医院">{doctor.hospital || '--'}</Descriptions.Item>
          <Descriptions.Item label="电话"><Space><PhoneOutlined />{doctor.phone || '--'}</Space></Descriptions.Item>
          <Descriptions.Item label="标签">
            <Space wrap>{doctor.tags?.length ? doctor.tags.map((t: string) => <Tag key={t}>{t}</Tag>) : '--'}</Space>
          </Descriptions.Item>
        </Descriptions>
      </Card>
      <Card title="学术背景" style={{ marginBottom: 16 }}>
        <p>{academic || '暂无学术背景信息'}</p>
        <p><strong>处方偏好：</strong>{prescription || '暂无'}</p>
      </Card>
      <Card title="互动历史">
        {interactions.length === 0 ? (
          <Empty description="暂无互动记录" />
        ) : (
          <Timeline
            items={interactions.map((item, idx) => {
              const time = formatVisitTime(item.visit_time);
              return {
                key: item.id || idx,
                children: (
                  <div>
                    <p style={{ fontWeight: 600 }}>{time || `拜访记录 #${idx + 1}`}</p>
                    <p style={{ color: '#666' }}>{item.ai_summary || '暂无摘要'}</p>
                    {item.key_points && item.key_points.length > 0 && (
                      <p style={{ fontSize: 12, color: '#999' }}>
                        要点：{item.key_points.join('、')}
                      </p>
                    )}
                  </div>
                ),
              };
            })}
          />
        )}
      </Card>
    </PageContainer>
  );
}
