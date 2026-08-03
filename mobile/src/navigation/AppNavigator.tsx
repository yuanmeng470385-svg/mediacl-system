/**
 * 主导航器 - 登录态守卫 + Stack 路由
 */
import React from 'react';
import { ActivityIndicator, View, Text, StyleSheet } from 'react-native';
import { NavigationContainer } from '@react-navigation/native';
import { createNativeStackNavigator } from '@react-navigation/native-stack';
import { createBottomTabNavigator } from '@react-navigation/bottom-tabs';
import { useAuth } from '../store/AuthContext';
import { Colors } from '../constants/theme';
import type { RootStackParamList, MainTabParamList } from './types';

// Screens
import LoginScreen from '../screens/Login/LoginScreen';
import HomeScreen from '../screens/Home/HomeScreen';
import SpecialistListScreen from '../screens/Specialists/SpecialistListScreen';
import ChatScreen from '../screens/Chat/ChatScreen';
import HCPSearchScreen from '../screens/HCPSearch/HCPSearchScreen';
import HCPDetailScreen from '../screens/HCPDetail/HCPDetailScreen';
import VisitPrepareScreen from '../screens/VisitPrepare/VisitPrepareScreen';
import VisitInProgressScreen from '../screens/VisitInProgress/VisitInProgressScreen';
import VisitEndScreen from '../screens/VisitEnd/VisitEndScreen';
import ContentScreen from '../screens/Content/ContentScreen';
import ComplianceScreen from '../screens/Compliance/ComplianceScreen';
import ProfileScreen from '../screens/Profile/ProfileScreen';

const Stack = createNativeStackNavigator<RootStackParamList>();
const Tab = createBottomTabNavigator<MainTabParamList>();

/** 底部 4 Tab */
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
          height: 56,
        },
        tabBarLabelStyle: {
          fontSize: 11,
          fontWeight: '600',
        },
      }}
    >
      <Tab.Screen
        name="Home"
        component={HomeScreen}
        options={{
          tabBarLabel: '工作台',
          tabBarIcon: ({ color }) => (
            <Text style={{ fontSize: 22, color }}>🏠</Text>
          ),
        }}
      />
      <Tab.Screen
        name="Specialists"
        component={SpecialistListScreen}
        options={{
          tabBarLabel: '对话',
          tabBarIcon: ({ color }) => (
            <Text style={{ fontSize: 22, color }}>💬</Text>
          ),
        }}
      />
      <Tab.Screen
        name="HCPs"
        component={HCPSearchScreen}
        options={{
          tabBarLabel: '医生',
          tabBarIcon: ({ color }) => (
            <Text style={{ fontSize: 22, color }}>👨‍⚕️</Text>
          ),
        }}
      />
      <Tab.Screen
        name="Profile"
        component={ProfileScreen}
        options={{
          tabBarLabel: '我的',
          tabBarIcon: ({ color }) => (
            <Text style={{ fontSize: 22, color }}>👤</Text>
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
      <Text style={styles.splashIcon}>💊</Text>
      <Text style={styles.splashTitle}>MedAgent</Text>
      <ActivityIndicator
        style={{ marginTop: 24 }}
        size="small"
        color={Colors.primary}
      />
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
    <NavigationContainer>
      <Stack.Navigator screenOptions={{ headerShown: false }}>
        {isLoggedIn ? (
          <>
            {/* 主 Tab */}
            <Stack.Screen name="MainTabs" component={MainTabs} />
            {/* 数字专员对话 */}
            <Stack.Screen
              name="Chat"
              component={ChatScreen}
              options={{ animation: 'slide_from_right' }}
            />
            {/* 医生详情 */}
            <Stack.Screen
              name="HCPDetail"
              component={HCPDetailScreen}
              options={{ animation: 'slide_from_right' }}
            />
            {/* 拜访流程 */}
            <Stack.Screen
              name="VisitPrepare"
              component={VisitPrepareScreen}
              options={{ animation: 'slide_from_right' }}
            />
            <Stack.Screen
              name="VisitInProgress"
              component={VisitInProgressScreen}
              options={{ animation: 'slide_from_bottom', gestureEnabled: false }}
            />
            <Stack.Screen
              name="VisitEnd"
              component={VisitEndScreen}
              options={{ animation: 'slide_from_right', gestureEnabled: false }}
            />
            {/* 学术内容（独立页，不在 Tab 内） */}
            <Stack.Screen
              name="ContentDetail"
              component={ContentScreen}
              options={{ animation: 'slide_from_right' }}
            />
            {/* 合规手册 */}
            <Stack.Screen
              name="ComplianceManual"
              component={ComplianceScreen}
              options={{ animation: 'slide_from_right' }}
            />
            {/* 占位页面 */}
            <Stack.Screen name="Settings" component={PlaceholderScreen} />
            <Stack.Screen name="NotificationSettings" component={PlaceholderScreen} />
            <Stack.Screen name="HelpCenter" component={PlaceholderScreen} />
            <Stack.Screen name="VisitDetail" component={PlaceholderScreen} />
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

/** 开发中占位页 */
function PlaceholderScreen() {
  return (
    <View style={styles.placeholder}>
      <Text style={styles.placeholderIcon}>🚧</Text>
      <Text style={styles.placeholderText}>功能开发中</Text>
    </View>
  );
}

const styles = StyleSheet.create({
  splash: {
    flex: 1,
    justifyContent: 'center',
    alignItems: 'center',
    backgroundColor: Colors.white,
  },
  splashIcon: { fontSize: 72 },
  splashTitle: {
    fontSize: 32,
    fontWeight: '700',
    color: Colors.textPrimary,
    marginTop: 16,
  },
  placeholder: {
    flex: 1,
    justifyContent: 'center',
    alignItems: 'center',
    backgroundColor: Colors.background,
  },
  placeholderIcon: { fontSize: 48, marginBottom: 16 },
  placeholderText: { fontSize: 16, color: Colors.textHint },
});
