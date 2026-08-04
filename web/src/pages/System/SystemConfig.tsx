import { PageContainer, ProForm, ProFormText, ProFormDigit } from '@ant-design/pro-components';
import { Card, App } from 'antd';

export default function SystemConfig() {
  const { message } = App.useApp();

  return (
    <PageContainer header={{ title: '系统配置' }}>
      <ProForm
        onFinish={async () => { message.success('配置已保存'); return true; }}
        submitter={{ searchConfig: { submitText: '保存配置' } }}
      >
        <Card title="阿里云配置" style={{ marginBottom: 24 }}>
          <ProFormText name="aliyun_account_id" label="Account ID" />
          <ProFormText name="aliyun_region" label="区域" initialValue="cn-hangzhou" />
          <ProFormText name="bailian_app_id" label="百炼 App ID" placeholder="mm_xxx" />
          <ProFormText name="dashscope_api_key" label="通义千问 API Key" />
          <ProFormText name="tingwu_app_key" label="通义听悟 App Key" />
        </Card>
        <Card title="通知配置" style={{ marginBottom: 24 }}>
          <ProFormDigit name="compliance_notify" label="合规拦截通知" fieldProps={{ addonAfter: '次后通知' }} initialValue={3} />
          <ProFormDigit name="error_notify" label="系统异常通知" fieldProps={{ addonAfter: '次后通知' }} initialValue={1} />
          <ProFormText name="notify_receiver" label="通知接收人" placeholder="多个用逗号分隔" />
        </Card>
        <Card title="日志配置">
          <ProFormDigit name="log_retention_days" label="日志保留天数" fieldProps={{ addonAfter: '天' }} initialValue={1095} />
        </Card>
      </ProForm>
    </PageContainer>
  );
}
