/**
 * MedAgent 移动端 - App 入口
 * 底部 4 Tab: 工作台 | 对话 | 医生 | 我的
 */
import React from 'react';
import { NavigationContainer } from '@react-navigation/native';
import { createBottomTabNavigator } from '@react-navigation/bottom-tabs';
import { StatusBar } from 'react-native';

// TODO: 替换为真实页面
import HomeScreen from './screens/Home/HomeScreen';
import SpecialistListScreen from './screens/Specialists/SpecialistListScreen';
import HCPSearchScreen from './screens/HCPSearch/HCPSearchScreen';
import ProfileScreen from './screens/Profile/ProfileScreen';

const Tab = createBottomTabNavigator();

export default function App() {
  return (
    <NavigationContainer>
      <StatusBar barStyle="dark-content" />
      <Tab.Navigator
        screenOptions={{
          headerShown: false,
          tabBarActiveTintColor: '#3b82f6',
          tabBarInactiveTintColor: '#999',
        }}
      >
        <Tab.Screen
          name="Home"
          component={HomeScreen}
          options={{ tabBarLabel: '工作台' }}
        />
        <Tab.Screen
          name="Specialists"
          component={SpecialistListScreen}
          options={{ tabBarLabel: '对话' }}
        />
        <Tab.Screen
          name="HCPs"
          component={HCPSearchScreen}
          options={{ tabBarLabel: '医生' }}
        />
        <Tab.Screen
          name="Profile"
          component={ProfileScreen}
          options={{ tabBarLabel: '我的' }}
        />
      </Tab.Navigator>
    </NavigationContainer>
  );
}
