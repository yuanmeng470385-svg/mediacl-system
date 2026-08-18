/**
 * 主导航器 - 医生端
 * Stack：登录 → 主 Tab（问答/分身/我的）→ 分身激活/分身对话/资质上传
 */
import React from 'react';
import { ActivityIndicator, View, Text, StyleSheet } from 'react-native';
import { NavigationContainer, type LinkingOptions } from '@react-navigation/native';
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

/** 底部 3 Tab：问答 / 分身 / 我的 */
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
  const { isLoggedIn, isLoading } = useAuth();

  if (isLoading) {
    return <SplashScreen />;
  }

  return (
    <NavigationContainer linking={linking}>
      <Stack.Navigator screenOptions={{ headerShown: false }}>
        {isLoggedIn ? (
          <>
            <Stack.Screen name="MainTabs" component={MainTabs} />
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
