import { useEffect, useState } from 'react';
import { Alert, Card, Descriptions, Row, Col, Tag, Typography } from 'antd';
import { PageContainer } from '@ant-design/pro-components';
import { systemAPI, type SystemConfigItem } from '../../services/system';

const { Text } = Typography;

export default function SystemConfig() {
  const [items, setItems] = useState<SystemConfigItem[]>([]);
  const [info, setInfo] = useState<{ rate_limit_per_minute?: number; log_level?: string }>({});
  const [loading, setLoading] = useState(true);
  const [loadError, setLoadError] = useState('');

  useEffect(() => {
    systemAPI
      .config()
      .then((r) => {
        setItems(r.data.data?.items ?? []);
        setInfo(r.data.data?.info ?? {});
      })
      .catch(() => setLoadError('配置状态加载失败：请确认网关服务可用（本页仅管理员可访问）'))
      .finally(() => setLoading(false));
  }, []);

  return (
    <PageContainer header={{ title: '系统配置', subTitle: '只读状态页：配置由 .env 环境变量管理' }}>
      <Alert
        type="info"
        showIcon
        message="本页为只读状态页，不支持在线保存"
        description="阿里云、短信、大模型（通义千问 / 百炼）、NLS 语音等密钥类配置通过服务的 .env 环境变量管理，修改后需重启对应服务生效。此处仅展示各配置项是否已配置。"
        style={{ marginBottom: 24 }}
      />

      <Card title="关键配置状态" style={{ marginBottom: 24 }} loading={loading}>
        {loadError && <Alert type="error" showIcon message={loadError} style={{ marginBottom: 16 }} />}
        {!loadError && items.length === 0 && (
          <Text type="secondary">暂无配置状态数据</Text>
        )}
        <Row gutter={[16, 8]}>
          {items.map((it) => (
            <Col xs={24} sm={12} lg={8} key={it.key}>
              <div
                style={{
                  display: 'flex',
                  justifyContent: 'space-between',
                  alignItems: 'center',
                  padding: '8px 0',
                  borderBottom: '1px solid #f0f0f0',
                }}
              >
                <Text ellipsis title={`${it.label}（${it.key}）`}>
                  {it.label}
                </Text>
                <Tag color={it.configured ? 'success' : 'warning'}>
                  {it.configured ? '已配置' : '未配置'}
                </Tag>
              </div>
            </Col>
          ))}
        </Row>
      </Card>

      <Card title="系统信息">
        <Descriptions column={2} size="small">
          <Descriptions.Item label="网关限流（次/分钟）">
            {info.rate_limit_per_minute ?? '—'}
          </Descriptions.Item>
          <Descriptions.Item label="日志级别">{info.log_level ?? '—'}</Descriptions.Item>
          <Descriptions.Item label="审计日志保留天数" span={2}>
            由环境变量 AUDIT_LOG_RETENTION_DAYS 控制（默认 1095 天），修改后重启
            audit-service 生效
          </Descriptions.Item>
          <Descriptions.Item label="通知阈值 / 接收人" span={2}>
            由环境变量控制（合规拦截通知、系统异常通知等），修改后重启对应服务生效
          </Descriptions.Item>
        </Descriptions>
      </Card>
    </PageContainer>
  );
}
