import { Button, Result } from 'antd';
import { useNavigate } from 'react-router-dom';

/** M17：无权访问落地页（守卫已挡请求，页面数据 403 不会再打到后端） */
export default function Forbidden() {
  const navigate = useNavigate();
  return (
    <Result
      status="403"
      title="403"
      subTitle="抱歉，您没有权限访问此页面。"
      extra={
        <Button type="primary" onClick={() => navigate('/dashboard')}>
          返回仪表盘
        </Button>
      }
    />
  );
}
