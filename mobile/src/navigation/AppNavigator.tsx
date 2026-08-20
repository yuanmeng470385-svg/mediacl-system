/**
 * 主导航器 - 登录态守卫 + Stack 路由
 */
import React from 'react';
import { ActivityIndicator, View, Text, StyleSheet } from 'react-native';
import { NavigationContainer } from '@react-navigation/native';
import { createNativeStackNavigator } from '@react-navigation/native-stack';
import { createBottomTabNavigator } from '@react-navigation/bottom-tabs';
import { useAuth } from '../store/AuthContext';
import Icon from '../components/Icon';
import { TabIcons } from '../components/Icon';
import { Colors, FontSize, Shadow } from '../constants/theme';
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
import ContentDetailScreen from '../screens/Content/ContentDetailScreen';
import ComplianceScreen from '../screens/Compliance/ComplianceScreen';
import ProfileScreen from '../screens/Profile/ProfileScreen';
import SettingsScreen from '../screens/Settings/SettingsScreen';
import ComplianceCenterScreen from '../screens/Compliance/ComplianceCenterScreen';
import TrainingMaterialScreen from '../screens/Compliance/TrainingMaterialScreen';
import ExamScreen from '../screens/Compliance/ExamScreen';
import CommitmentScreen from '../screens/Compliance/CommitmentScreen';
import NotificationSettingsScreen from '../screens/NotificationSettings/NotificationSettingsScreen';
import HelpCenterScreen from '../screens/HelpCenter/HelpCenterScreen';
import VisitDetailScreen from '../screens/VisitDetail/VisitDetailScreen';
import TaskListScreen from '../screens/TaskList/TaskListScreen';
import FavoritesScreen from '../screens/Favorites/FavoritesScreen';
import ShareScreen from '../screens/Share/ShareScreen';
import BriefingListScreen from '../screens/Briefing/BriefingListScreen';
import BriefingDetailScreen from '../screens/Briefing/BriefingDetailScreen';
import CardCreateScreen from '../screens/Academic/CardCreateScreen';
import CardListScreen from '../screens/Academic/CardListScreen';
import PracticeListScreen from '../screens/Practice/PracticeListScreen';
import PracticeChatScreen from '../screens/Practice/PracticeChatScreen';
import PlazaScreen from '../screens/Plaza/PlazaScreen';
import TwinManageScreen from '../screens/Twin/TwinManageScreen';
import SkillReleaseScreen from '../screens/Skill/SkillReleaseScreen';
import MySkillListScreen from '../screens/Skill/MySkillListScreen';

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
          height: 60,
          ...Shadow.header,
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
          tabBarIcon: ({ color, focused }) => (
            <Icon name={focused ? TabIcons.homeActive : TabIcons.home} size={24} color={color} />
          ),
        }}
      />
      <Tab.Screen
        name="Specialists"
        component={SpecialistListScreen}
        options={{
          tabBarLabel: '对话',
          tabBarIcon: ({ color, focused }) => (
            <Icon name={focused ? TabIcons.chatActive : TabIcons.chat} size={24} color={color} />
          ),
        }}
      />
      <Tab.Screen
        name="HCPs"
        component={HCPSearchScreen}
        options={{
          tabBarLabel: '医生',
          tabBarIcon: ({ color }) => (
            <Icon name={TabIcons.doctor} size={24} color={color} />
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
      <View style={styles.splashLogo}><Text style={styles.splashLogoText}>MA</Text></View>
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
              name="Content"
              component={ContentScreen}
              options={{ animation: 'slide_from_right' }}
            />
            <Stack.Screen
              name="ContentDetail"
              component={ContentDetailScreen}
              options={{ animation: 'slide_from_right' }}
            />
            {/* 合规手册 */}
            <Stack.Screen
              name="ComplianceManual"
              component={ComplianceScreen}
              options={{ animation: 'slide_from_right' }}
            />
            {/* 任务 & 收藏 */}
            <Stack.Screen name="TaskList" component={TaskListScreen} options={{ animation: 'slide_from_right' }} />
            <Stack.Screen name="Favorites" component={FavoritesScreen} options={{ animation: 'slide_from_right' }} />
            {/* 辅助页面 */}
            <Stack.Screen name="Settings" component={SettingsScreen} options={{ animation: 'slide_from_right' }} />
            <Stack.Screen name="ComplianceCenter" component={ComplianceCenterScreen} options={{ animation: 'slide_from_right' }} />
            {/* 合规培训考试（二期 F） */}
            <Stack.Screen name="TrainingMaterial" component={TrainingMaterialScreen} options={{ animation: 'slide_from_right' }} />
            <Stack.Screen name="Exam" component={ExamScreen} options={{ animation: 'slide_from_right' }} />
            <Stack.Screen name="Commitment" component={CommitmentScreen} options={{ animation: 'slide_from_right' }} />
            <Stack.Screen name="NotificationSettings" component={NotificationSettingsScreen} options={{ animation: 'slide_from_right' }} />
            <Stack.Screen name="HelpCenter" component={HelpCenterScreen} options={{ animation: 'slide_from_right' }} />
            <Stack.Screen name="VisitDetail" component={VisitDetailScreen} options={{ animation: 'slide_from_right' }} />
            {/* 分身分享 & 夜间简报 */}
            <Stack.Screen name="Share" component={ShareScreen} options={{ animation: 'slide_from_right' }} />
            <Stack.Screen name="BriefingList" component={BriefingListScreen} options={{ animation: 'slide_from_right' }} />
            <Stack.Screen name="BriefingDetail" component={BriefingDetailScreen} options={{ animation: 'slide_from_right' }} />
            {/* 学术卡片（二期 G） */}
            <Stack.Screen name="AcademicCardCreate" component={CardCreateScreen} options={{ animation: 'slide_from_right' }} />
            <Stack.Screen name="AcademicCardList" component={CardListScreen} options={{ animation: 'slide_from_right' }} />
            {/* AI 陪练 / Skill 广场 / 分身管理（二期 H） */}
            <Stack.Screen name="PracticeList" component={PracticeListScreen} options={{ animation: 'slide_from_right' }} />
            <Stack.Screen name="PracticeChat" component={PracticeChatScreen} options={{ animation: 'slide_from_right' }} />
            <Stack.Screen name="Plaza" component={PlazaScreen} options={{ animation: 'slide_from_right' }} />
            <Stack.Screen name="TwinManage" component={TwinManageScreen} options={{ animation: 'slide_from_right' }} />
            {/* Skill 生态（三期 J） */}
            <Stack.Screen name="SkillRelease" component={SkillReleaseScreen} options={{ animation: 'slide_from_right' }} />
            <Stack.Screen name="MySkillList" component={MySkillListScreen} options={{ animation: 'slide_from_right' }} />
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
  splashIcon: { fontSize: 72 },
  splashLogo: { width: 80, height: 80, borderRadius: 20, backgroundColor: Colors.primary, alignItems: 'center', justifyContent: 'center', marginBottom: 16 },
  splashLogoText: { fontSize: 30, fontWeight: '800', color: Colors.textWhite, letterSpacing: -1 },
  splashTitle: {
    fontSize: 32,
    fontWeight: '700',
    color: Colors.textPrimary,
    marginTop: 16,
  },
});
