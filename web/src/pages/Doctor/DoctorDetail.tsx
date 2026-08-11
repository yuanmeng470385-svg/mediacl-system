import { useEffect, useState } from 'react';
import { useParams } from 'react-router-dom';
import { PageContainer } from '@ant-design/pro-components';
import { Alert, App, Card, Descriptions, Empty, Space, Spin, Tag, Timeline, Typography } from 'antd';
import { PhoneOutlined } from '@ant-design/icons';
import {
  doctorAPI,
  formatProfileField,
  formatVisitTime,
  mapProfile,
} from '../../services/doctor';
import type { DoctorDetail as DoctorDetailData, DoctorInteraction, DoctorProfile } from '../../services/doctor';

export default function DoctorDetail() {
  const { id } = useParams<{ id: string }>();
  const [doctor, setDoctor] = useState<DoctorDetailData | null>(null);
  const [interactions, setInteractions] = useState<DoctorInteraction[]>([]);
  const [loading, setLoading] = useState(true);
  const [profile, setProfile] = useState<DoctorProfile | null>(null);
  const [profileLoading, setProfileLoading] = useState(false);
  const [profileFailed, setProfileFailed] = useState(false);
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

  useEffect(() => {
    if (!id) return;
    let cancelled = false;
    setProfileLoading(true);
    doctorAPI.profile(id)
      .then((res) => { if (!cancelled) setProfile(mapProfile(res.data?.data)); })
      .catch(() => { if (!cancelled) setProfileFailed(true); })
      .finally(() => { if (!cancelled) setProfileLoading(false); });
    return () => { cancelled = true; };
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
      <Card title="AI 画像" loading={profileLoading}>
        {profileFailed ? (
          <Empty description="画像生成失败，请稍后重试" />
        ) : profile && !profile.ai_available ? (
          <Alert type="info" showIcon message="AI 画像暂不可用" description={profile.ai_unavailable_reason} />
        ) : profile ? (
          <Descriptions column={1} size="small" labelStyle={{ width: 120 }}>
            <Descriptions.Item label="学术画像">{profile.academic_profile || '—'}</Descriptions.Item>
            <Descriptions.Item label="处方偏好">{profile.prescription_preference || '—'}</Descriptions.Item>
            <Descriptions.Item label="沟通建议">
              <Typography.Paragraph style={{ whiteSpace: 'pre-line', marginBottom: 0 }}>
                {profile.communication_advice || '—'}
              </Typography.Paragraph>
            </Descriptions.Item>
            <Descriptions.Item label="下一步建议">{profile.next_step_suggestion || '—'}</Descriptions.Item>
            <Descriptions.Item label="合规风险">
              {profile.risk_alerts.length
                ? <Space wrap>{profile.risk_alerts.map((r, i) => <Tag key={i} color={r.level === 'high' ? 'red' : r.level === 'medium' ? 'orange' : 'warning'}>{r.description}</Tag>)}</Space>
                : <span style={{ color: '#52c41a' }}>无风险提示</span>}
            </Descriptions.Item>
          </Descriptions>
        ) : null}
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
