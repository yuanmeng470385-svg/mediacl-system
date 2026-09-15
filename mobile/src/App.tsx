/**
 * MedAgent 移动端 - App 入口
 *
 * 底部 4 Tab：工作台 | 对话 | 医生 | 我的
 * Stack 导航：登录 → 主 Tab → 子页面（对话/拜访/医生详情等）
 */
import React from 'react';
import { StatusBar, View } from 'react-native';
import { AuthProvider } from './store/AuthContext';
import AppNavigator from './navigation/AppNavigator';
import GuideBar from './components/GuideBar';
import UpdateGate from './components/UpdateGate';

export default function App() {
  return (
    <AuthProvider>
      <StatusBar barStyle="light-content" backgroundColor="#3b82f6" />
      {/* GuideBar 挂导航器外：体验态召回条要覆盖一切屏（含 Stack push 后 MainTabs 被 detach） */}
      <View style={{ flex: 1 }}>
        <AppNavigator />
        <GuideBar />
        {/* 版本更新门：启动/回前台静默查版本，有新版本才弹（强制更新时盖住整个 App） */}
        <UpdateGate />
      </View>
    </AuthProvider>
  );
}
