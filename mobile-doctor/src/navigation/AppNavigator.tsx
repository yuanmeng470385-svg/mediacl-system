/**
 * 主导航器 - 医生端
 * Stack：登录 → 主 Tab（问答/分身/我的）→ 分身激活/分身对话/资质上传
 */
import React, { useEffect } from 'react';
import { ActivityIndicator, View, Text, StyleSheet, Linking } from 'react-native';
import { NavigationContainer, createNavigationContainerRef, type LinkingOptions } from '@react-navigation/native';
import { createNativeStackNavigator } from '@react-navigation/native-stack';
import { createBottomTabNavigator } from '@react-navigation/bottom-tabs';
import { useAuth } from '../store/AuthContext';
import Icon, { TabIcons, FeatureIcons } from '../components/Icon';
import { Colors, FontSize, Shadow } from '../constants/theme';
import type { RootStackParamList, MainTabParamList } from './types';

// Screens
import LoginScreen from '../screens/Login/LoginScreen';
import MedicalQAScreen from '../screens/MedicalQA/MedicalQAScreen';
import MyTwinsScreen from '../screens/MyTwins/MyTwinsScreen';
import ProfileScreen from '../screens/Profile/ProfileScreen';
import TwinActivateScreen from '../screens/TwinActivate/TwinActivateScreen';
import TwinChatScreen from '../screens/TwinChat/TwinChatScreen';
import CertUploadScreen from '../screens/CertUpload/CertUploadScreen';
import InboxScreen from '../screens/Inbox/InboxScreen';
import CardDetailScreen from '../screens/Inbox/CardDetailScreen';
import NotificationsScreen from '../screens/Notifications/NotificationsScreen';
import PreferenceScreen from '../screens/Preferences/PreferenceScreen';
import PlazaScreen from '../screens/Plaza/PlazaScreen';
import PatientEduScreen from '../screens/PatientEdu/PatientEduScreen';
import PatientEduZoneScreen from '../screens/PatientEdu/PatientEduZoneScreen';
import FavoritesScreen from '../screens/Profile/FavoritesScreen';
import GuideController from '../screens/Onboarding/GuideController';
import { DOCTOR_GUIDE_STEPS, DOCTOR_GUIDE_DONE_KEY, DOCTOR_GUIDE_PROGRESS_KEY } from '../screens/Onboarding/doctorGuideSteps';
import PrivacyCenterScreen from '../screens/Privacy/PrivacyCenterScreen';
import PrivacyRequestsScreen from '../screens/Privacy/PrivacyRequestsScreen';

const Stack = createNativeStackNavigator<RootStackParamList>();
const Tab = createBottomTabNavigator<MainTabParamList>();

/** 深链配置（Task 9）：medagent-doctor://twin/:token → 分身激活页
 *  深链参数为 string，TwinActivate 的 token 参数即 { token?: string }。
 *  iOS 侧 URL scheme 注册待有 Xcode 环境验证（挂账，见 CLAUDE.md Known Gaps）。 */
const linking: LinkingOptions<RootStackParamList> = {
  prefixes: ['medagent-doctor://'],
  config: {
    screens: {
      TwinActivate: 'twin/:token',
    },
  },
};

const navigationRef = createNavigationContainerRef<RootStackParamList>();

/** 深链 token 解析：medagent-doctor://twin/:token → 取单段 token（排除 query/锚点） */
function extractTwinToken(url: string | null): string | null {
  if (!url) return null;
  const match = url.match(/twin\/([^?#/]+)/);
  return match ? decodeURIComponent(match[1]) : null;
}

/** 底部 3 Tab：问答 / 分身 / 我的 */
// 陪玩式新人引导（模块级定义保引用稳定）：GuideController 包住 MainTabs，首登自动开演（深链 pendingToken 优先，不打断激活）
function GatedMainTabs() {
  return (
    <GuideController
      steps={DOCTOR_GUIDE_STEPS}
      doneKey={DOCTOR_GUIDE_DONE_KEY}
      progressKey={DOCTOR_GUIDE_PROGRESS_KEY}
    >
      <MainTabs />
    </GuideController>
  );
}

function MainTabs() {
  return (
    <Tab.Navigator
      screenOptions={{
        headerShown: false,
        tabBarActiveTintColor: Colors.primary,
        tabBarInactiveTintColor: Colors.tabInactive,
        tabBarStyle: {
          backgroundColor: Colors.white,
          borderTopColor: Colors.divider,
          paddingBottom: 4,
          height: 60,
          ...Shadow.header,
        },
        tabBarLabelStyle: { fontSize: 11, fontWeight: '600' },
      }}
    >
      <Tab.Screen
        name="MedicalQA"
        component={MedicalQAScreen}
        options={{
          tabBarLabel: '问答',
          tabBarIcon: ({ color, focused }) => (
            <Icon name={focused ? TabIcons.chatActive : TabIcons.chat} size={24} color={color} />
          ),
        }}
      />
      <Tab.Screen
        name="MyTwins"
        component={MyTwinsScreen}
        options={{
          tabBarLabel: '分身',
          tabBarIcon: ({ color }) => (
            <Icon name={FeatureIcons.specialist} size={24} color={color} />
          ),
        }}
      />
      <Tab.Screen
        name="Profile"
        component={ProfileScreen}
        options={{
          tabBarLabel: '我的',
          tabBarIcon: ({ color, focused }) => (
            <Icon name={focused ? TabIcons.profileActive : TabIcons.profile} size={24} color={color} />
          ),
        }}
      />
    </Tab.Navigator>
  );
}

/** 加载页 */
function SplashScreen() {
  return (
    <View style={styles.splash}>
      <View style={styles.splashLogo}>
        <Text style={styles.splashLogoText}>MD</Text>
      </View>
      <Text style={styles.splashTitle}>MedAgent·医生端</Text>
      <ActivityIndicator style={{ marginTop: 24 }} size="small" color={Colors.primary} />
    </View>
  );
}

/** 根导航器 */
export default function AppNavigator() {
  const { isLoggedIn, isLoading, pendingToken, setPendingToken } = useAuth();

  // F2（2026-08-18）：运行中收到深链时，未登录态先把 token 暂存 pendingToken
  //（登录态由 linking 直接导航到 TwinActivate，这里不重复存，避免二次跳转）
  useEffect(() => {
    const sub = Linking.addEventListener('url', ({ url }) => {
      const token = extractTwinToken(url);
      if (token && !isLoggedIn) setPendingToken(token);
    });
    return () => sub.remove();
  }, [isLoggedIn, setPendingToken]);

  // F2：冷启动深链——登录态确定后（未登录）才捕获暂存；已登录交 linking 导航
  useEffect(() => {
    if (isLoading || isLoggedIn) return;
    Linking.getInitialURL().then((url) => {
      const token = extractTwinToken(url);
      if (token) setPendingToken(token);
    });
  }, [isLoading, isLoggedIn, setPendingToken]);

  // F2：登录成功后消费 pendingToken → 跳转分身激活页并清空
  useEffect(() => {
    if (isLoggedIn && pendingToken && navigationRef.isReady()) {
      navigationRef.navigate('TwinActivate', { token: pendingToken });
      setPendingToken(null);
    }
  }, [isLoggedIn, pendingToken, setPendingToken]);

  if (isLoading) {
    return <SplashScreen />;
  }

  return (
    <NavigationContainer linking={linking} ref={navigationRef}>
      <Stack.Navigator screenOptions={{ headerShown: false }}>
        {isLoggedIn ? (
          <>
            <Stack.Screen name="MainTabs" component={GatedMainTabs} />
            <Stack.Screen
              name="TwinActivate"
              component={TwinActivateScreen}
              options={{ animation: 'slide_from_right' }}
            />
            <Stack.Screen
              name="TwinChat"
              component={TwinChatScreen}
              options={{ animation: 'slide_from_right' }}
            />
            <Stack.Screen
              name="CertUpload"
              component={CertUploadScreen}
              options={{ animation: 'slide_from_right' }}
            />
            <Stack.Screen
              name="Inbox"
              component={InboxScreen}
              options={{ animation: 'slide_from_right' }}
            />
            <Stack.Screen
              name="CardDetail"
              component={CardDetailScreen}
              options={{ animation: 'slide_from_right' }}
            />
            <Stack.Screen
              name="Notifications"
              component={NotificationsScreen}
              options={{ animation: 'slide_from_right' }}
            />
            <Stack.Screen
              name="Preferences"
              component={PreferenceScreen}
              options={{ animation: 'slide_from_right' }}
            />
            <Stack.Screen
              name="DoctorPlaza"
              component={PlazaScreen}
              options={{ animation: 'slide_from_right' }}
            />
            <Stack.Screen
              name="PatientEdu"
              component={PatientEduScreen}
              options={{ animation: 'slide_from_right' }}
            />
            <Stack.Screen
              name="PatientEduZone"
              component={PatientEduZoneScreen}
              options={{ animation: 'slide_from_right' }}
            />
            <Stack.Screen
              name="Favorites"
              component={FavoritesScreen}
              options={{ animation: 'slide_from_right' }}
            />
            <Stack.Screen
              name="PrivacyCenter"
              component={PrivacyCenterScreen}
              options={{ title: '隐私中心' }}
            />
            <Stack.Screen
              name="PrivacyRequests"
              component={PrivacyRequestsScreen}
              options={{ title: '我的隐私请求' }}
            />
          </>
        ) : (
          <Stack.Screen
            name="Login"
            component={LoginScreen}
            options={{ animationTypeForReplace: 'pop' }}
          />
        )}
      </Stack.Navigator>
    </NavigationContainer>
  );
}

const styles = StyleSheet.create({
  splash: {
    flex: 1,
    justifyContent: 'center',
    alignItems: 'center',
    backgroundColor: Colors.white,
  },
  splashLogo: {
    width: 80,
    height: 80,
    borderRadius: 20,
    backgroundColor: Colors.primary,
    alignItems: 'center',
    justifyContent: 'center',
    marginBottom: 16,
  },
  splashLogoText: {
    fontSize: 30,
    fontWeight: '800',
    color: Colors.textWhite,
    letterSpacing: -1,
  },
  splashTitle: {
    fontSize: 32,
    fontWeight: '700',
    color: Colors.textPrimary,
    marginTop: 16,
  },
});
