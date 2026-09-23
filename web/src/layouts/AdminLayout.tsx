import { getBrand } from '../brand';
import { useCallback, useEffect, useState } from 'react';
import { Outlet, useNavigate, useLocation } from 'react-router-dom';
import { ProLayout } from '@ant-design/pro-components';
import { Badge, Button, Dropdown, Avatar, theme } from 'antd';
import { LogoutOutlined, UserOutlined } from '@ant-design/icons';
import { menuConfig } from '../constants/menu';
import { canAccess, filterMenu, isKnownRoute } from '../constants/routeAccess';
import Forbidden from '../components/Forbidden';
import GuideTour from '../components/onboarding/GuideTour';
import AssistantChat from '../components/Assistant/AssistantChat';
import { fetchTodoCounts, sumTodoCounts } from '../services/todo';
import { useAuth } from '../hooks/useAuth';

export default function AdminLayout() {
  const [collapsed, setCollapsed] = useState(false);
  const navigate = useNavigate();
  const location = useLocation();
  const { user, logout } = useAuth();
  // 待办徽标（2026-09-15）：60s 轮询两端 todo-summary 合计；菜单项红色数字（微信样式）
  const [todoTotal, setTodoTotal] = useState(0);

  const refreshTodo = useCallback(async () => {
    try {
      setTodoTotal(sumTodoCounts(await fetchTodoCounts()));
    } catch {
      // 轮询失败保持旧值，不打扰用户（TodoCenter 页内有手动刷新兜底）
    }
  }, []);

  useEffect(() => {
    refreshTodo();
    const timer = setInterval(refreshTodo, 60_000);
    return () => clearInterval(timer);
    // 路由切换也刷新：审核完回到菜单，红色数字立即归零（count 查询很轻）
  }, [refreshTodo, location.pathname]);

  return (
    <ProLayout
      title={getBrand().short || getBrand().name}
      logo={null}
      // M17：菜单按角色过滤（角色表单一事实源见 constants/routeAccess.ts）
      route={{ children: filterMenu(menuConfig, user?.role) }}
      location={{ pathname: location.pathname }}
      collapsed={collapsed}
      onCollapse={setCollapsed}
      menuItemRender={(item) => (
        <a onClick={() => item.path && navigate(item.path)}>
          {item.path === '/todos' ? (
            // Badge 根元素自带亮色主题文字色（rgba(0,0,0,.88) 黑），会盖掉深色菜单的白字。
            // 注意 antd Badge 的 style prop 只作用于红色数字角标（scrollNumber），
            // 覆盖根元素文字色必须用 styles.root（语义化 DOM API），随菜单项配色
            // （未选 0.65 白 / 选中纯白，与「数字专员」等分组标题同款）
            <Badge count={todoTotal} overflowCount={99} offset={[10, 0]} size="small" styles={{ root: { color: 'inherit' } }}>
              {item.name}
            </Badge>
          ) : (
            item.name
          )}
        </a>
      )}
      siderWidth={220}
      headerContentRender={() => (
        <div style={{ flex: 1, textAlign: 'right', paddingRight: 24 }}>
          <Dropdown
            menu={{
              items: [
                { key: 'logout', icon: <LogoutOutlined />, label: '退出登录', onClick: logout },
              ],
            }}
          >
            <Button type="text" icon={<Avatar size="small" icon={<UserOutlined />} />}>
              {user?.name || '管理员'}
            </Button>
          </Dropdown>
        </div>
      )}
      footerRender={() => (
        <div style={{ textAlign: 'center', padding: '12px 0', color: 'rgba(0,0,0,0.45)', fontSize: 12 }}>
          © {new Date().getFullYear()} {getBrand().name}
        </div>
      )}
      token={{
        header: { colorBgHeader: '#001529' },
        sider: {
          colorMenuBackground: '#001529',
          colorTextMenu: 'rgba(255,255,255,0.65)',
          colorTextMenuSelected: '#fff',
          colorBgMenuItemSelected: '#1890ff',
        },
      }}
    >
      {/* M17：已知路由越权访问 → 403 落地页（后端 403 兜底仍在前，此处先挡请求） */}
      {isKnownRoute(location.pathname) && !canAccess(location.pathname, user?.role) ? (
        <Forbidden />
      ) : (
        <Outlet />
      )}
      {/* 新人引导（v5）：常驻浮层 + 右下角"?"悬浮球，跨路由存活 */}
      <GuideTour role={user?.role} />
      {/* 产品使用 AI 助手（2026-09-15 三端）：悬浮球 + Drawer 聊天，跨路由存活 */}
      <AssistantChat />
    </ProLayout>
  );
}
