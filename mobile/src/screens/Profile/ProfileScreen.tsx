/**
 * 我的 - 个人中心
 */
import React from 'react';
import {
  View,
  Text,
  StyleSheet,
  ScrollView,
  TouchableOpacity,
  Alert,
} from 'react-native';
import { useNavigation } from '@react-navigation/native';
import type { NativeStackNavigationProp } from '@react-navigation/native-stack';
import { useAuth } from '../../store/AuthContext';
import { Colors, FontSize, Spacing, BorderRadius, Shadow } from '../../constants/theme';
import type { RootStackParamList } from '../../navigation/types';

type Nav = NativeStackNavigationProp<RootStackParamList>;

const menuItems = [
  { icon: '👤', label: '个人资料', route: 'Settings' as const },
  { icon: '👥', label: '我的团队', route: 'Settings' as const },
  { icon: '📊', label: '我的统计', route: 'Settings' as const },
  { icon: '🔔', label: '通知设置', route: 'NotificationSettings' as const },
  { icon: '🛡️', label: '合规手册', route: 'ComplianceManual' as const },
  { icon: '❓', label: '帮助中心', route: 'HelpCenter' as const },
  { icon: 'ℹ️', label: '关于', route: 'Settings' as const },
];

export default function ProfileScreen() {
  const navigation = useNavigation<Nav>();
  const { user, logout } = useAuth();

  const handleLogout = () => {
    Alert.alert('退出登录', '确定要退出当前账号吗？', [
      { text: '取消', style: 'cancel' },
      {
        text: '确定退出',
        style: 'destructive',
        onPress: logout,
      },
    ]);
  };

  return (
    <View style={styles.container}>
      {/* 头部 */}
      <View style={styles.header}>
        <Text style={styles.headerTitle}>我的</Text>
      </View>

      <ScrollView
        style={styles.content}
        showsVerticalScrollIndicator={false}
      >
        {/* 用户信息 */}
        <TouchableOpacity
          style={[styles.profileCard, Shadow.card]}
          onPress={() => navigation.navigate('Settings')}
          activeOpacity={0.7}
        >
          <View
            style={[styles.avatar, { backgroundColor: Colors.primary }]}
          >
            <Text style={styles.avatarText}>
              {user?.name?.charAt(0) || '代'}
            </Text>
          </View>
          <View style={styles.userInfo}>
            <Text style={styles.userName}>{user?.name || '医药代表'}</Text>
            <Text style={styles.userDept}>
              {user?.department || '肿瘤事业部'} ·{' '}
              {user?.region || '华东区'}
            </Text>
          </View>
          <Text style={styles.arrow}>›</Text>
        </TouchableOpacity>

        {/* 数据统计 */}
        <View style={[styles.statsCard, Shadow.card]}>
          <View style={styles.statItem}>
            <Text style={styles.statNum}>--</Text>
            <Text style={styles.statLabel}>本月对话</Text>
          </View>
          <View style={styles.statDivider} />
          <View style={styles.statItem}>
            <Text style={styles.statNum}>--</Text>
            <Text style={styles.statLabel}>本月拜访</Text>
          </View>
          <View style={styles.statDivider} />
          <View style={styles.statItem}>
            <Text style={styles.statNum}>--</Text>
            <Text style={styles.statLabel}>收藏</Text>
          </View>
        </View>

        {/* 菜单 */}
        <View style={[styles.menuCard, Shadow.card]}>
          {menuItems.map((item, index) => (
            <TouchableOpacity
              key={item.label}
              style={[
                styles.menuItem,
                index < menuItems.length - 1 && styles.menuItemBorder,
              ]}
              onPress={() => navigation.navigate(item.route)}
              activeOpacity={0.7}
            >
              <Text style={styles.menuIcon}>{item.icon}</Text>
              <Text style={styles.menuLabel}>{item.label}</Text>
              <Text style={styles.menuArrow}>›</Text>
            </TouchableOpacity>
          ))}
        </View>

        {/* 退出登录 */}
        <TouchableOpacity
          style={styles.logoutBtn}
          onPress={handleLogout}
          activeOpacity={0.7}
        >
          <Text style={styles.logoutText}>退出登录</Text>
        </TouchableOpacity>

        <View style={{ height: 60 }} />
      </ScrollView>
    </View>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1, backgroundColor: Colors.background },
  header: {
    backgroundColor: Colors.primary,
    paddingHorizontal: Spacing.xl,
    paddingTop: 52,
    paddingBottom: Spacing.xl,
  },
  headerTitle: { color: Colors.textWhite, fontSize: FontSize.xl, fontWeight: '700' },
  content: { flex: 1, padding: Spacing.lg },
  // 用户信息
  profileCard: {
    backgroundColor: Colors.white,
    borderRadius: BorderRadius.lg,
    padding: Spacing.lg,
    flexDirection: 'row',
    alignItems: 'center',
    gap: Spacing.lg,
    marginBottom: Spacing.md,
  },
  avatar: {
    width: 56,
    height: 56,
    borderRadius: 28,
    alignItems: 'center',
    justifyContent: 'center',
  },
  avatarText: { color: Colors.textWhite, fontSize: 22, fontWeight: '700' },
  userInfo: { flex: 1 },
  userName: { fontSize: FontSize.lg, fontWeight: '600', color: Colors.textPrimary },
  userDept: { fontSize: FontSize.sm, color: Colors.textSecondary, marginTop: 4 },
  arrow: { fontSize: 24, color: Colors.textHint },
  // 统计
  statsCard: {
    backgroundColor: Colors.white,
    borderRadius: BorderRadius.lg,
    flexDirection: 'row',
    padding: Spacing.xl,
    marginBottom: Spacing.md,
  },
  statItem: { flex: 1, alignItems: 'center' },
  statNum: { fontSize: FontSize.xxl, fontWeight: '700', color: Colors.primary },
  statLabel: { fontSize: FontSize.xs, color: Colors.textSecondary, marginTop: 4 },
  statDivider: { width: 1, backgroundColor: Colors.divider },
  // 菜单
  menuCard: {
    backgroundColor: Colors.white,
    borderRadius: BorderRadius.lg,
    marginBottom: Spacing.lg,
  },
  menuItem: {
    flexDirection: 'row',
    alignItems: 'center',
    padding: Spacing.lg,
    gap: Spacing.md,
  },
  menuItemBorder: {
    borderBottomWidth: StyleSheet.hairlineWidth,
    borderBottomColor: Colors.divider,
  },
  menuIcon: { fontSize: 20, width: 28, textAlign: 'center' },
  menuLabel: { flex: 1, fontSize: FontSize.md, color: Colors.textPrimary },
  menuArrow: { fontSize: 20, color: Colors.textHint },
  // 退出
  logoutBtn: {
    padding: Spacing.lg,
    alignItems: 'center',
    backgroundColor: Colors.white,
    borderRadius: BorderRadius.lg,
  },
  logoutText: { color: Colors.danger, fontSize: FontSize.md, fontWeight: '500' },
});
