import { useState } from 'react';
import { Navigate } from 'react-router-dom';
import { Card, Form, Input, Button, Typography, Alert } from 'antd';
import { UserOutlined, LockOutlined } from '@ant-design/icons';
import { useAuth } from '../../hooks/useAuth';
import { getBrand } from '../../brand';
import BrandLogo from '../../components/BrandLogo';

const { Title, Text } = Typography;

export default function LoginPage() {
  const { login, isLoggedIn, loading } = useAuth();
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState('');
  const brand = getBrand();
  // 等启动 me() 完成，避免误重定向；已登录直接回 /dashboard
  if (loading) return null;
  if (isLoggedIn) return <Navigate to="/dashboard" replace />;

  const onFinish = async (values: { username: string; password: string }) => {
    setSubmitting(true);
    setError('');
    try {
      await login(values.username, values.password);
      // 登录成功后路由守卫（Task 3）自动把已登录用户从 /login 重定向到 /dashboard
    } catch (e: any) {
      setError(e?.response?.data?.message || e?.response?.data?.detail?.message || '登录失败，请检查账号密码');
    } finally {
      setSubmitting(false);
    }
  };

  // 品牌主场：主色 8% 双辐射渐变铺底 + 卡片顶主色饰条 + 大字标（无主色的 MedAgent 回退态退回素灰）
  const tint = brand.primary ? brand.primary + '14' : undefined;
  const bg = tint
    ? `radial-gradient(1100px 560px at 18% -8%, ${tint}, transparent), radial-gradient(900px 480px at 92% 108%, ${tint}, transparent), #f0f2f5`
    : '#f0f2f5';

  return (
    <div style={{ minHeight: '100vh', display: 'flex', alignItems: 'center', justifyContent: 'center', background: bg }}>
      <Card style={{ width: 400, boxShadow: '0 8px 24px rgba(0,0,0,0.12)', overflow: 'hidden', padding: 0 }} styles={{ body: { padding: 0 } }}>
        <div style={{ height: 4, background: brand.primary || '#1677ff' }} />
        <div style={{ padding: '32px 32px 24px' }}>
          <div style={{ textAlign: 'center', marginBottom: 28 }}>
            <div style={{ display: 'flex', justifyContent: 'center', marginBottom: 16 }}>
              <BrandLogo size={64} />
            </div>
            <Title level={3} style={{ marginBottom: 4 }}>{brand.short || brand.name}</Title>
            <Text type="secondary">{brand.tagline || '药企 AI 数字员工系统'} · 管理后台</Text>
          </div>
          {error && <Alert type="error" message={error} showIcon style={{ marginBottom: 16 }} />}
          <Form onFinish={onFinish} size="large">
            <Form.Item name="username" rules={[{ required: true, message: '请输入用户名' }]}>
              <Input prefix={<UserOutlined />} placeholder="用户名" autoComplete="username" />
            </Form.Item>
            <Form.Item name="password" rules={[{ required: true, message: '请输入密码' }]}>
              <Input.Password prefix={<LockOutlined />} placeholder="密码" autoComplete="current-password" />
            </Form.Item>
            <Form.Item style={{ marginBottom: 0 }}>
              <Button type="primary" htmlType="submit" block loading={submitting}>
                登录
              </Button>
            </Form.Item>
          </Form>
          <Text type="secondary" style={{ display: 'block', textAlign: 'center', marginTop: 16, fontSize: 12 }}>
            管理员账号需先执行 scripts/seed_admin.py 设置密码
          </Text>
          <Text type="secondary" style={{ display: 'block', textAlign: 'center', marginTop: 8, fontSize: 12 }}>
            © {new Date().getFullYear()} {brand.name}
          </Text>
        </div>
      </Card>
    </div>
  );
}
