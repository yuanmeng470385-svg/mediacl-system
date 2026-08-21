import { useState } from 'react';
import { Outlet, useNavigate, useLocation } from 'react-router-dom';
import { ProLayout } from '@ant-design/pro-components';
import { Button, Dropdown, Avatar, theme } from 'antd';
import { LogoutOutlined, UserOutlined } from '@ant-design/icons';
import { menuConfig } from '../constants/menu';
import { canAccess, filterMenu, isKnownRoute } from '../constants/routeAccess';
import Forbidden from '../components/Forbidden';
import { useAuth } from '../hooks/useAuth';

export default function AdminLayout() {
  const [collapsed, setCollapsed] = useState(false);
  const navigate = useNavigate();
  const location = useLocation();
  const { user, logout } = useAuth();

  return (
    <ProLayout
      title="MedAgent"
      logo={null}
      // M17：菜单按角色过滤（角色表单一事实源见 constants/routeAccess.ts）
      route={{ children: filterMenu(menuConfig, user?.role) }}
      location={{ pathname: location.pathname }}
      collapsed={collapsed}
      onCollapse={setCollapsed}
      menuItemRender={(item) => (
        <a onClick={() => item.path && navigate(item.path)}>{item.name}</a>
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
    </ProLayout>
  );
}
