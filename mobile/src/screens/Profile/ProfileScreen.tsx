/**
 * 我的 - 个人中心
 * 临床精准风
 */
import React, { useEffect, useState } from 'react';
import {
  View, Text, StyleSheet, ScrollView, TouchableOpacity, Alert,
} from 'react-native';
import { useNavigation } from '@react-navigation/native';
import type { NativeStackNavigationProp } from '@react-navigation/native-stack';
import { useAuth } from '../../store/AuthContext';
import { visitAPI } from '../../api/visit';
import Icon from '../../components/Icon';
import {
  Colors, FontSize, Spacing, BorderRadius, Shadow,
} from '../../constants/theme';
import type { RootStackParamList } from '../../navigation/types';

type Nav = NativeStackNavigationProp<RootStackParamList>;

const menuItems = [
  { icon: 'account-outline', label: '个人资料', route: 'Settings' as const },
  { icon: 'account-group-outline', label: '我的团队', route: 'Settings' as const },
  { icon: 'chart-box-outline', label: '我的统计', route: 'Settings' as const },
  { icon: 'bell-outline', label: '通知设置', route: 'NotificationSettings' as const },
  { icon: 'shield-check-outline', label: '合规手册', route: 'ComplianceManual' as const },
  { icon: 'help-circle-outline', label: '帮助中心', route: 'HelpCenter' as const },
  { icon: 'information-outline', label: '关于', route: 'Settings' as const },
];

export default function ProfileScreen() {
  const navigation = useNavigation<Nav>();
  const { user, logout } = useAuth();
  const [visitCount, setVisitCount] = useState<string>('--');

  useEffect(() => {
    let cancelled = false;
    visitAPI.list({ page: 1, page_size: 1 })
      .then((res) => { if (!cancelled) setVisitCount(String(res.total)); })
      .catch(() => { /* 保持 '--' */ });
    return () => { cancelled = true; };
  }, []);

  const handleLogout = () => {
    Alert.alert('退出登录', '确定要退出当前账号吗？', [
      { text: '取消', style: 'cancel' },
      { text: '确定退出', style: 'destructive', onPress: logout },
    ]);
  };

  return (
    <View style={styles.container}>
      <View style={styles.header}>
        <Text style={styles.headerTitle}>我的</Text>
      </View>

      <ScrollView style={styles.content} showsVerticalScrollIndicator={false}>
        {/* 用户信息卡片 */}
        <TouchableOpacity
          style={[styles.profileCard, Shadow.card]}
          onPress={() => navigation.navigate('Settings')}
          activeOpacity={0.7}
        >
          <View style={styles.avatar}>
            <Text style={styles.avatarText}>{user?.name?.charAt(0) || '代'}</Text>
          </View>
          <View style={styles.userInfo}>
            <Text style={styles.userName}>{user?.name || '医药代表'}</Text>
            <Text style={styles.userDept}>
              {user?.department || '肿瘤事业部'} · {user?.region || '华东区'}
            </Text>
          </View>
          <Icon name="chevron-right" size={24} color={Colors.textHint} />
        </TouchableOpacity>

        {/* 数据统计 */}
        <View style={[styles.statsCard, Shadow.card]}>
          {[
            { num: '--', label: '本月对话' },
            { num: visitCount, label: '拜访总数' },
            { num: '--', label: '收藏' },
          ].map((s, i) => (
            <React.Fragment key={s.label}>
              {i > 0 && <View style={styles.statDivider} />}
              <View style={styles.statItem}>
                <Text style={styles.statNum}>{s.num}</Text>
                <Text style={styles.statLabel}>{s.label}</Text>
              </View>
            </React.Fragment>
          ))}
        </View>

        {/* 菜单列表 */}
        <View style={[styles.menuCard, Shadow.card]}>
          {menuItems.map((item, index) => (
            <TouchableOpacity
              key={item.label}
              style={[styles.menuItem, index < menuItems.length - 1 && styles.menuItemBorder]}
              onPress={() => navigation.navigate(item.route)}
              activeOpacity={0.7}
            >
              <View style={styles.menuIconBox}>
                <Icon name={item.icon} size={20} color={Colors.primary} />
              </View>
              <Text style={styles.menuLabel}>{item.label}</Text>
              <Icon name="chevron-right" size={20} color={Colors.textHint} />
            </TouchableOpacity>
          ))}
        </View>

        <TouchableOpacity style={[styles.logoutBtn, Shadow.card]} onPress={handleLogout} activeOpacity={0.7}>
          <Icon name="logout" size={18} color={Colors.danger} />
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
    backgroundColor: Colors.primary, paddingHorizontal: Spacing.xxl,
    paddingTop: 52, paddingBottom: Spacing.xl,
    ...Shadow.header,
  },
  headerTitle: { color: Colors.textWhite, fontSize: FontSize.xxl, fontWeight: '700' },
  content: { flex: 1, padding: Spacing.lg },
  profileCard: {
    backgroundColor: Colors.white, borderRadius: BorderRadius.xl,
    padding: Spacing.lg, flexDirection: 'row',
    alignItems: 'center', gap: Spacing.lg, marginBottom: Spacing.md,
  },
  avatar: {
    width: 56, height: 56, borderRadius: 28,
    backgroundColor: Colors.primary, alignItems: 'center', justifyContent: 'center',
  },
  avatarText: { color: Colors.textWhite, fontSize: 22, fontWeight: '700' },
  userInfo: { flex: 1 },
  userName: { fontSize: FontSize.lg, fontWeight: '600', color: Colors.textPrimary },
  userDept: { fontSize: FontSize.sm, color: Colors.textSecondary, marginTop: 4 },
  statsCard: {
    backgroundColor: Colors.white, borderRadius: BorderRadius.xl,
    flexDirection: 'row', padding: Spacing.xl, marginBottom: Spacing.md,
  },
  statItem: { flex: 1, alignItems: 'center' },
  statNum: { fontSize: FontSize.xxl, fontWeight: '700', color: Colors.accent },
  statLabel: { fontSize: FontSize.xs, color: Colors.textSecondary, marginTop: 4 },
  statDivider: { width: 1, backgroundColor: Colors.divider },
  menuCard: { backgroundColor: Colors.white, borderRadius: BorderRadius.xl, marginBottom: Spacing.lg },
  menuItem: {
    flexDirection: 'row', alignItems: 'center',
    padding: Spacing.lg, gap: Spacing.md,
  },
  menuItemBorder: { borderBottomWidth: StyleSheet.hairlineWidth, borderBottomColor: Colors.divider },
  menuIconBox: {
    width: 32, height: 32, borderRadius: 8,
    backgroundColor: Colors.primarySurface,
    alignItems: 'center', justifyContent: 'center',
  },
  menuLabel: { flex: 1, fontSize: FontSize.md, color: Colors.textPrimary },
  logoutBtn: {
    padding: Spacing.lg, alignItems: 'center', flexDirection: 'row',
    justifyContent: 'center', gap: Spacing.sm,
    backgroundColor: Colors.white, borderRadius: BorderRadius.xl,
  },
  logoutText: { color: Colors.danger, fontSize: FontSize.md, fontWeight: '500' },
});
