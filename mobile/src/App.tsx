/**
 * MedAgent 移动端 - App 入口
 *
 * 底部 4 Tab：工作台 | 对话 | 医生 | 我的
 * Stack 导航：登录 → 主 Tab → 子页面（对话/拜访/医生详情等）
 */
import React from 'react';
import { StatusBar } from 'react-native';
import { AuthProvider } from './store/AuthContext';
import AppNavigator from './navigation/AppNavigator';

export default function App() {
  return (
    <AuthProvider>
      <StatusBar barStyle="light-content" backgroundColor="#3b82f6" />
      <AppNavigator />
    </AuthProvider>
  );
}
