import { useState } from 'react';
import { Outlet, useNavigate, useLocation } from 'react-router-dom';
import { ProLayout } from '@ant-design/pro-components';
import { Button, Dropdown, Avatar, theme } from 'antd';
import { LogoutOutlined, UserOutlined } from '@ant-design/icons';
import { menuConfig } from '../constants/menu';
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
      route={{ children: menuConfig }}
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
      <Outlet />
    </ProLayout>
  );
}
