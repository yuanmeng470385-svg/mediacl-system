import {
  DashboardOutlined,
  RobotOutlined,
  BookOutlined,
  SafetyOutlined,
  AuditOutlined,
  TeamOutlined,
  CalendarOutlined,
  FileProtectOutlined,
  SettingOutlined,
} from '@ant-design/icons';
import type { MenuDataItem } from '@ant-design/pro-components';

/**
 * 侧边菜单（按领域分组）。分组父项须设 key（无 path，点击不跳转）；
 * ProLayout 会依据 key 自动展开当前路由所在分组，无需手动管理 openKeys。
 * 新增页面时：App.tsx 路由、routeAccess.ts 角色表、routeAccess.test.ts 数量断言三处同步。
 */
export const menuConfig: MenuDataItem[] = [
  { path: '/dashboard', name: '仪表盘', icon: <DashboardOutlined /> },
  {
    key: 'g-specialist',
    name: '数字专员',
    icon: <RobotOutlined />,
    children: [
      { path: '/specialist/list', name: '专员列表' },
      { path: '/specialist/monitor', name: '分身监控' },
    ],
  },
  {
    key: 'g-operation',
    name: '业务运营',
    icon: <CalendarOutlined />,
    children: [
      { path: '/visit/list', name: '拜访管理' },
      { path: '/doctor/stats', name: '运营统计' },
    ],
  },
  {
    key: 'g-content',
    name: '内容中心',
    icon: <BookOutlined />,
    children: [
      { path: '/knowledge/list', name: '知识库' },
      { path: '/skill/list', name: '技能管理' },
      { path: '/patient-edu/list', name: '患教模板' },
      { path: '/patient-edu/review', name: '患教内容' },
      { path: '/practice/objections', name: '异议话术' },
    ],
  },
  {
    key: 'g-compliance',
    name: '合规风控',
    icon: <SafetyOutlined />,
    children: [
      { path: '/compliance/list', name: '合规规则' },
      { path: '/compliance/blocks', name: '拦截记录' },
      { path: '/compliance/monitor', name: '合规风控' },
      { path: '/compliance/mah-overview', name: '药企全景' },
      { path: '/compliance/conv-search', name: '对话检索' },
      { path: '/compliance/card-stats', name: '触达统计' },
    ],
  },
  {
    key: 'g-data',
    name: '数据与审计',
    icon: <AuditOutlined />,
    children: [
      { path: '/data/assets', name: '数据治理' },
      { path: '/data/exports', name: '导出审批' },
      { path: '/privacy/requests', name: '隐私请求' },
      { path: '/audit/list', name: '审计查询' },
    ],
  },
  {
    key: 'g-people',
    name: '人员管理',
    icon: <TeamOutlined />,
    children: [
      { path: '/doctor/list', name: '医生管理' },
      { path: '/doctor-cert/list', name: '医生认证' },
      { path: '/user/list', name: '用户管理' },
    ],
  },
  {
    key: 'g-filing',
    name: '资质与培训',
    icon: <FileProtectOutlined />,
    children: [
      { path: '/filing/list', name: '备案管理' },
      { path: '/training/list', name: '合规培训' },
    ],
  },
  { path: '/system/config', name: '系统配置', icon: <SettingOutlined /> },
];
