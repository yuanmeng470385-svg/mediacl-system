/**
 * MedAgent 图标组件
 *
 * 封装 MaterialCommunityIcons——统一大小、颜色、风格
 * 所有 icon name 参考: https://materialdesignicons.com
 */
import React from 'react';
import MaterialCommunityIcons from 'react-native-vector-icons/MaterialCommunityIcons';
import { Colors } from '../constants/theme';

interface IconProps {
  name: string;
  size?: number;
  color?: string;
}

export default function Icon({ name, size = 24, color = Colors.textPrimary }: IconProps) {
  return <MaterialCommunityIcons name={name} size={size} color={color} />;
}

// ==============================
// 预设图标映射——替代 emoji
// ==============================

/** Tab 栏图标 */
export const TabIcons = {
  home: 'view-dashboard-outline',
  homeActive: 'view-dashboard',
  chat: 'message-text-outline',
  chatActive: 'message-text',
  doctor: 'doctor',
  doctorActive: 'doctor',
  profile: 'account-circle-outline',
  profileActive: 'account-circle',
} as const;

/** 导航/操作图标 */
export const ActionIcons = {
  back: 'chevron-left',
  close: 'close',
  add: 'plus',
  search: 'magnify',
  filter: 'filter-variant',
  more: 'dots-vertical',
  edit: 'pencil',
  delete: 'delete-outline',
  send: 'send',
  mic: 'microphone',
  notification: 'bell-outline',
  settings: 'cog-outline',
  help: 'help-circle-outline',
  export: 'file-export-outline',
  refresh: 'refresh',
  check: 'check',
  star: 'star-outline',
  starFilled: 'star',
  thumbUp: 'thumb-up-outline',
  thumbDown: 'thumb-down-outline',
} as const;

/** 功能图标 */
export const FeatureIcons = {
  specialist: 'robot-outline',
  content: 'file-document-outline',
  doctor: 'doctor',
  compliance: 'shield-check-outline',
  visit: 'calendar-check-outline',
  knowledge: 'book-open-page-variant-outline',
  dashboard: 'chart-bar',
  audit: 'clipboard-text-outline',
} as const;

/** 状态图标 */
export const StatusIcons = {
  success: 'check-circle-outline',
  warning: 'alert-outline',
  danger: 'alert-circle-outline',
  info: 'information-outline',
  pending: 'clock-outline',
  active: 'check-circle',
  completed: 'check-circle',
  blocked: 'close-circle',
} as const;

/** 拜访相关图标 */
export const VisitIcons = {
  prepare: 'clipboard-text-outline',
  inProgress: 'record-rec',
  end: 'clipboard-check-outline',
  doctor: 'doctor',
  hospital: 'hospital-building',
  calendar: 'calendar',
  clock: 'clock-outline',
  location: 'map-marker-outline',
} as const;

/** 证据等级图标 */
export const EvidenceIcons = {
  A: 'alpha-a-circle-outline',
  B: 'alpha-b-circle-outline',
  C: 'alpha-c-circle-outline',
  expert: 'account-tie-outline',
  unknown: 'help-circle-outline',
} as const;
