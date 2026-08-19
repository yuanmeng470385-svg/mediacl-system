import {
  DashboardOutlined,
  RobotOutlined,
  BookOutlined,
  SafetyOutlined,
  StopOutlined,
  AuditOutlined,
  UserOutlined,
  TeamOutlined,
  SettingOutlined,
  CalendarOutlined,
  FileProtectOutlined,
  IdcardOutlined,
  ReadOutlined,
} from '@ant-design/icons';
import type { MenuDataItem } from '@ant-design/pro-components';

export const menuConfig: MenuDataItem[] = [
  { path: '/dashboard', name: '仪表盘', icon: <DashboardOutlined /> },
  { path: '/specialist/list', name: '数字专员', icon: <RobotOutlined /> },
  { path: '/visit/list', name: '拜访管理', icon: <CalendarOutlined /> },
  { path: '/knowledge/list', name: '知识库', icon: <BookOutlined /> },
  { path: '/compliance/list', name: '合规规则', icon: <SafetyOutlined /> },
  { path: '/compliance/blocks', name: '拦截记录', icon: <StopOutlined /> },
  { path: '/audit/list', name: '审计查询', icon: <AuditOutlined /> },
  { path: '/doctor/list', name: '医生管理', icon: <UserOutlined /> },
  { path: '/user/list', name: '用户管理', icon: <TeamOutlined /> },
  { path: '/filing/list', name: '备案管理', icon: <FileProtectOutlined /> },
  { path: '/doctor-cert/list', name: '医生认证', icon: <IdcardOutlined /> },
  { path: '/training/list', name: '合规培训', icon: <ReadOutlined /> },
  { path: '/system/config', name: '系统配置', icon: <SettingOutlined /> },
];
