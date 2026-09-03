import { Button, Result, Space } from 'antd';
import { useNavigate } from 'react-router-dom';
import { useAuth } from '../hooks/useAuth';
import { ROUTE_ACCESS } from '../constants/routeAccess';

/** M17：无权访问落地页（守卫已挡请求，页面数据 403 不会再打到后端） */
export default function Forbidden() {
  const navigate = useNavigate();
  const { user, logout } = useAuth();
  // rep/finance 等 Web 后台无任何可访问路由的角色，固定跳 /dashboard 会
  // 再落回本页形成死循环——改为跳「第一个可访问路由」，全无则只给退出
  const fallback = Object.keys(ROUTE_ACCESS).find((p) =>
    ROUTE_ACCESS[p].includes(user?.role ?? ''),
  );
  return (
    <Result
      status="403"
      title="403"
      subTitle={
        fallback
          ? '抱歉，您没有权限访问此页面。'
          : '当前角色无 Web 后台权限，请使用移动端 App 或切换账号。'
      }
      extra={
        fallback ? (
          <Button type="primary" onClick={() => navigate(fallback)}>
            返回首页
          </Button>
        ) : (
          <Button type="primary" onClick={logout}>
            退出登录
          </Button>
        )
      }
    />
  );
}
