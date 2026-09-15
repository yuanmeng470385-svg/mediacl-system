import { useCallback, useEffect, useState } from 'react';
import {
  Alert, App, Button, Card, Descriptions, Form, Input, Modal, Row, Col, Space, Table, Tag, Typography,
} from 'antd';
import type { ColumnsType } from 'antd/es/table';
import { PageContainer } from '@ant-design/pro-components';
import { systemAPI, type SystemConfigItem } from '../../services/system';
import {
  appVersionAPI, compareVersion, isDownloadUrl, isVersionString,
  type AppPlatform, type AppVersionItem, type AppVersionUpdate,
} from '../../services/appVersion';

const { Text } = Typography;

/** 「系统配置」：上半是只读的密钥配置状态（.env 管理），下半是可在线维护的 App 版本与更新提示 */
export default function SystemConfig() {
  const { message } = App.useApp();
  const [items, setItems] = useState<SystemConfigItem[]>([]);
  const [info, setInfo] = useState<{ rate_limit_per_minute?: number; log_level?: string }>({});
  const [loading, setLoading] = useState(true);
  const [loadError, setLoadError] = useState('');

  const [apps, setApps] = useState<AppVersionItem[]>([]);
  const [appsLoading, setAppsLoading] = useState(true);
  const [editing, setEditing] = useState<AppVersionItem | null>(null);
  const [saving, setSaving] = useState(false);
  const [form] = Form.useForm<AppVersionUpdate>();

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

  const loadApps = useCallback(() => {
    setAppsLoading(true);
    appVersionAPI
      .list()
      .then((r) => setApps(r.data.data ?? []))
      .catch(() => setApps([]))
      .finally(() => setAppsLoading(false));
  }, []);

  useEffect(loadApps, [loadApps]);

  const openEdit = (row: AppVersionItem) => setEditing(row);

  // 回填用 initialValues 而不是 openEdit 里 setFieldsValue：弹窗关闭时弹窗内容被销毁，
  // Form 的 preserve={false} 会让 rc-field-form 记下这些字段，下次挂载时用 initialValues
  // 覆盖 store（prevWithoutPreserves），命令式写入会被擦掉 → 弹窗打开是空表单。
  const initialValues: Partial<AppVersionUpdate> = editing
    ? {
        latest_version: editing.latest_version,
        min_version: editing.min_version,
        download_url: editing.download_url,
        release_notes: editing.release_notes ?? '',
      }
    : {};

  const submit = async () => {
    if (!editing) return;
    let values: AppVersionUpdate;
    try {
      values = await form.validateFields();
    } catch {
      // 校验未通过：antd 已在字段下方标红，这里必须吃掉 reject（否则是 unhandledrejection）
      return;
    }
    setSaving(true);
    try {
      await appVersionAPI.update(editing.platform, values);
      message.success(`${editing.platform_label}版本配置已保存`);
      setEditing(null);
      loadApps();
    } catch {
      /* 4xx 的 message 由 axios 拦截器统一弹出，这里只负责不关窗让用户改 */
    } finally {
      setSaving(false);
    }
  };

  const columns: ColumnsType<AppVersionItem> = [
    {
      title: '平台',
      dataIndex: 'platform_label',
      width: 110,
      render: (label: string, row) => <Tag color={row.platform === 'rep' ? 'blue' : 'green'}>{label}</Tag>,
    },
    { title: '最新版本', dataIndex: 'latest_version', width: 110 },
    { title: '最低可用版本', dataIndex: 'min_version', width: 130 },
    {
      title: '下载地址（APK）',
      dataIndex: 'download_url',
      render: (url: string) => <Text ellipsis copyable={{ text: url }} style={{ maxWidth: 260 }}>{url}</Text>,
    },
    {
      title: '更新说明',
      dataIndex: 'release_notes',
      render: (notes?: string | null) =>
        notes ? <Text ellipsis style={{ maxWidth: 240 }}>{notes}</Text> : <Text type="secondary">—</Text>,
    },
    {
      title: '最后修改',
      dataIndex: 'updated_at',
      width: 170,
      render: (v?: string | null) => (v ? v.replace('T', ' ').slice(0, 19) : '—'),
    },
    {
      title: '操作',
      width: 80,
      render: (_, row) => <a onClick={() => openEdit(row)}>编辑</a>,
    },
  ];

  return (
    <PageContainer
      header={{ title: '系统配置', subTitle: '密钥类配置只读（.env 管理）；App 版本与更新提示可在线修改' }}
    >
      <Alert
        type="info"
        showIcon
        message="密钥类配置为只读状态页，App 版本与更新提示可在线保存"
        description="阿里云、短信、大模型（通义千问 / 百炼）、智能语音（NLS）等密钥类配置通过服务的 .env 环境变量管理，修改后需重启对应服务生效；此处仅展示各配置项是否已配置。「App 版本与更新」一栏保存后立即生效，无需重启。"
        style={{ marginBottom: 24 }}
      />

      <Card title="App 版本与更新" style={{ marginBottom: 24 }}>
        <Alert
          type="warning"
          showIcon
          style={{ marginBottom: 16 }}
          message="两个版本号的含义（保存后 App 下次启动或切回前台时生效）"
          description={
            <>
              <div>
                <Text strong>最新版本</Text>：手机上的版本比它低 → 弹「发现新版本」（用户可以点「暂不更新」跳过）
              </div>
              <div>
                <Text strong>最低可用版本</Text>：手机上的版本比它低 → <Text strong>强制更新</Text>
                （不更新无法继续使用），只在旧版本确实不能再用时才抬高，改了立刻对所有装旧版的用户生效
              </div>
              <div>
                下载地址填 <Text code>/apk/medagent-rep.apk</Text> 这类相对路径即可，App 会自动补上服务器地址；
                换域名后可直接填完整 https 地址。
              </div>
            </>
          }
        />
        <Table
          rowKey="platform"
          size="small"
          pagination={false}
          loading={appsLoading}
          columns={columns}
          dataSource={apps}
          locale={{ emptyText: '暂无版本配置（后端 app_versions 表未初始化）' }}
        />
      </Card>

      <Card title="关键配置状态" style={{ marginBottom: 24 }} loading={loading}>
        {loadError && <Alert type="error" showIcon message={loadError} style={{ marginBottom: 16 }} />}
        {!loadError && items.length === 0 && <Text type="secondary">暂无配置状态数据</Text>}
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

      <Modal
        title={editing ? `修改「${editing.platform_label}」版本配置` : ''}
        open={!!editing}
        onCancel={() => setEditing(null)}
        onOk={submit}
        confirmLoading={saving}
        okText="保存"
        cancelText="取消"
        destroyOnHidden
        maskClosable={false}
      >
        <Form
          key={editing?.platform ?? 'none'}
          form={form}
          layout="vertical"
          preserve={false}
          initialValues={initialValues}
          style={{ marginTop: 12 }}
        >
          <Form.Item
            label="最新版本号"
            name="latest_version"
            rules={[
              { required: true, message: '请填写最新版本号' },
              { validator: (_, v) => (isVersionString(v) ? Promise.resolve() : Promise.reject(new Error('格式应为 x.y.z，如 1.2.0'))) },
            ]}
          >
            <Input placeholder="1.2.0" style={{ maxWidth: 220 }} />
          </Form.Item>
          <Form.Item
            label="最低可用版本号"
            name="min_version"
            dependencies={['latest_version']}
            rules={[
              { required: true, message: '请填写最低可用版本号' },
              { validator: (_, v) => (isVersionString(v) ? Promise.resolve() : Promise.reject(new Error('格式应为 x.y.z，如 1.0.0'))) },
              ({ getFieldValue }) => ({
                validator: (_, v) => {
                  const latest = getFieldValue('latest_version');
                  if (isVersionString(v) && isVersionString(latest) && compareVersion(v, latest) > 0) {
                    return Promise.reject(new Error('最低可用版本不能高于最新版本（否则逻辑矛盾）'));
                  }
                  return Promise.resolve();
                },
              }),
            ]}
          >
            <Input placeholder="1.0.0" style={{ maxWidth: 220 }} />
          </Form.Item>
          <Form.Item
            label="APK 下载地址"
            name="download_url"
            rules={[
              { required: true, message: '请填写下载地址' },
              { validator: (_, v) => (isDownloadUrl(v) ? Promise.resolve() : Promise.reject(new Error('以 / 开头（如 /apk/medagent-rep.apk）或以 http://、https:// 开头'))) },
            ]}
          >
            <Input placeholder="/apk/medagent-rep.apk" />
          </Form.Item>
          <Form.Item
            label="更新说明（App 弹窗原文展示，一行一条）"
            name="release_notes"
            rules={[{ max: 2000, message: '不超过 2000 字' }]}
          >
            <Input.TextArea rows={5} maxLength={2000} showCount placeholder={'新增：AI 助手\n修复：若干问题'} />
          </Form.Item>
        </Form>
        <Space direction="vertical" size={4}>
          <Text type="secondary" style={{ fontSize: 12 }}>
            保存后 App 端无需发版：手机下次启动或从后台切回时即可看到提示。
          </Text>
        </Space>
      </Modal>
    </PageContainer>
  );
}
