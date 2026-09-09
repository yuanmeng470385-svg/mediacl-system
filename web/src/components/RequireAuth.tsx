import { Navigate, useNavigate } from 'react-router-dom';
import { Spin, Result, Button } from 'antd';
import { useAuth } from '../hooks/useAuth';
import type { ReactNode } from 'react';

export default function RequireAuth({ children }: { children: ReactNode }) {
  const { isLoggedIn, loading, bootFailed, retry, logout } = useAuth();
  const navigate = useNavigate();
  if (loading) {
    return (
      <div style={{ display: 'flex', justifyContent: 'center', alignItems: 'center', height: '100vh' }}>
        <Spin size="large" />
      </div>
    );
  }
  // 启动自检因 429 限流/网络抖动失败：token 还在，给重试，不误踢登录页
  if (bootFailed) {
    return (
      <Result
        status="warning"
        title="暂时无法确认登录状态"
        subTitle="网络波动或服务繁忙（如短时间内请求过多触发限流），你的登录状态没有失效。"
        extra={[
          <Button key="retry" type="primary" onClick={retry}>
            重试
          </Button>,
          <Button
            key="relogin"
            onClick={() => {
              logout();
              navigate('/login', { replace: true });
            }}
          >
            重新登录
          </Button>,
        ]}
      />
    );
  }
  if (!isLoggedIn) return <Navigate to="/login" replace />;
  return <>{children}</>;
}
