import { useMemo, useState } from 'react';
import { useParams } from 'react-router-dom';
import { Card, Typography, Button, Alert, App } from 'antd';
import { CopyOutlined, MobileOutlined } from '@ant-design/icons';
import { buildTwinDeepLink, normalizeShareToken } from './deepLink';

const { Title, Text } = Typography;

/**
 * 数字分身分享落地页（部署挂账 §4，公开路由 /share/twin/:token，无需登录）。
 *
 * 背景：裸深链 medagent-doctor://twin/<token> 在微信等内置浏览器里会被吞，
 * 医生点开就是白屏。落地页替代深链作为 share_url：展示激活码（token 即码，
 * 医生端 TwinActivate 页支持手输）+ 引导唤起 App。风格对齐登录页。
 */
export default function ShareTwinPage() {
  const { token: rawToken } = useParams();
  const { message } = App.useApp();
  const [copied, setCopied] = useState(false);

  // token 形态非法（32 hex）直接判无效，不发请求不弹 App
  const token = useMemo(() => normalizeShareToken(rawToken), [rawToken]);

  if (!token) {
    return (
      <PageShell>
        <Alert type="error" showIcon message="分享链接无效"
          description="链接不完整或已损坏，请向分享您的代表索取新的分享链接。" />
      </PageShell>
    );
  }

  const deepLink = buildTwinDeepLink(token);

  const copyToken = async () => {
    try {
      await navigator.clipboard.writeText(token);
    } catch {
      // 微信内置浏览器等无 clipboard 权限的环境：execCommand 兜底
      const ta = document.createElement('textarea');
      ta.value = token;
      document.body.appendChild(ta);
      ta.select();
      try {
        document.execCommand('copy');
      } finally {
        document.body.removeChild(ta);
      }
    }
    setCopied(true);
    message.success('激活码已复制');
  };

  return (
    <PageShell>
      <div style={{ textAlign: 'center', marginBottom: 24 }}>
        <Title level={3} style={{ marginBottom: 4 }}>MedAgent</Title>
        <Text type="secondary">医生数字分身分享</Text>
      </div>
      <Text style={{ display: 'block', marginBottom: 16 }}>
        您的医药代表向您分享了「AI 数字分身」服务：添加后可在医生端 App 内
        随时咨询学术问题、接收学术卡片。请按下面任一方式完成添加。
      </Text>
      <div style={{ background: '#f6ffed', border: '1px solid #b7eb8f', borderRadius: 8,
                    padding: '16px 12px', textAlign: 'center', marginBottom: 16 }}>
        <Text type="secondary" style={{ fontSize: 12 }}>激活码（在医生端 App「添加分身」中输入）</Text>
        <div style={{ fontFamily: 'Consolas, Menlo, monospace', fontSize: 22,
                      letterSpacing: 2, wordBreak: 'break-all', marginTop: 4, color: '#389e0d' }}>
          {token}
        </div>
        <Button icon={<CopyOutlined />} size="small" style={{ marginTop: 8 }}
          onClick={copyToken}>
          {copied ? '已复制' : '复制激活码'}
        </Button>
      </div>
      <Button type="primary" size="large" block icon={<MobileOutlined />}
        onClick={() => { window.location.href = deepLink; }}>
        打开医生端 App
      </Button>
      <Text type="secondary" style={{ display: 'block', textAlign: 'center',
                                      marginTop: 16, fontSize: 12 }}>
        未安装 App？可先复制激活码，安装后登录医生端，在「我的-添加分身」中输入
      </Text>
      <Alert type="info" showIcon style={{ marginTop: 16 }} message="微信内打开的提示"
        description="微信内可能无法唤起 App：点右上角「⋯」选择「在浏览器打开」，再点击「打开医生端 App」。" />
    </PageShell>
  );
}

function PageShell({ children }: { children: React.ReactNode }) {
  return (
    <div style={{ minHeight: '100vh', display: 'flex', alignItems: 'center',
                  justifyContent: 'center', background: '#f0f2f5', padding: 16 }}>
      <Card style={{ width: 380, boxShadow: '0 4px 12px rgba(0,0,0,0.08)' }}>{children}</Card>
    </div>
  );
}
