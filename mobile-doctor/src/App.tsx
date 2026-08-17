/**
 * MedAgent 医生端 - App 入口
 *
 * 底部 3 Tab：问答 | 分身 | 我的
 * Stack 导航：登录 → 主 Tab → 子页面（分身激活/分身对话/资质上传）
 */
import React from 'react';
import { StatusBar } from 'react-native';
import { AuthProvider } from './store/AuthContext';
import AppNavigator from './navigation/AppNavigator';
import { Colors } from './constants/theme';

export default function App() {
  return (
    <AuthProvider>
      <StatusBar barStyle="light-content" backgroundColor={Colors.primary} />
      <AppNavigator />
    </AuthProvider>
  );
}
