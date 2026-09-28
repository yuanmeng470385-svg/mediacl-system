/**
 * MedAgent 医生端 - App 入口
 *
 * 底部 3 Tab：问答 | 分身 | 我的
 * Stack 导航：登录 → 主 Tab → 子页面（分身激活/分身对话/资质上传）
 */
import React from 'react';
import { StatusBar, View } from 'react-native';
import { AuthProvider } from './store/AuthContext';
import AppNavigator from './navigation/AppNavigator';
import GuideBar from './components/GuideBar';
import UpdateGate from './components/UpdateGate';
import BrandBar from './components/BrandBar';
import { Colors } from './constants/theme';

export default function App() {
  return (
    <AuthProvider>
      <StatusBar barStyle="light-content" backgroundColor={Colors.primary} />
      {/* GuideBar 挂导航器外：体验态召回条要覆盖一切屏（含 Stack push 后 MainTabs 被 detach） */}
      <View style={{ flex: 1 }}>
        {/* v1.1.2：全局品牌条——所有页面顶部常驻（母版 BRAND=null 不渲染） */}
        <BrandBar />
        <AppNavigator />
        <GuideBar />
        {/* 版本更新门：启动/回前台静默查版本，有新版本才弹（强制更新时盖住整个 App） */}
        <UpdateGate />
      </View>
    </AuthProvider>
  );
}
