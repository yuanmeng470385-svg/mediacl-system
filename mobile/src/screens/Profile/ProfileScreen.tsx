/**
 * 我的 - 个人中心
 * 临床精准风
 */
import React, { useCallback, useEffect, useState } from 'react';
import {
  View, Text, StyleSheet, ScrollView, TouchableOpacity, Alert,
} from 'react-native';
import { useNavigation } from '@react-navigation/native';
import { useFocusEffect } from '@react-navigation/native';
import type { NativeStackNavigationProp } from '@react-navigation/native-stack';
import { useAuth } from '../../store/AuthContext';
import { visitAPI } from '../../api/visit';
import { taskAPI } from '../../api/tasks';
import { specialistAPI } from '../../api/specialist';
import { academicAPI } from '../../api/academic';
import Icon from '../../components/Icon';
import {
  Colors, FontSize, Spacing, BorderRadius, Shadow,
} from '../../constants/theme';
import FirstUseTip from '../../components/FirstUseTip';
import type { RootStackParamList } from '../../navigation/types';

type Nav = NativeStackNavigationProp<RootStackParamList>;

const menuItems = [
  { icon: 'account-outline', label: '个人资料', route: 'Settings' as const },
  { icon: 'clipboard-check-outline', label: '我的任务', route: 'TaskList' as const },
  { icon: 'star-outline', label: '我的收藏', route: 'Favorites' as const },
  { icon: 'bell-badge-outline', label: '站内通知', route: 'Notifications' as const },
  { icon: 'share-variant-outline', label: '分身分享', route: 'Share' as const },
  { icon: 'weather-night', label: '夜间简报', route: 'BriefingList' as const },
  { icon: 'file-document-outline', label: '学术卡片', route: 'AcademicCardCreate' as const },
  { icon: 'robot-outline', label: 'AI 陪练', route: 'PracticeList' as const },
  { icon: 'storefront-outline', label: 'Skill 广场', route: 'Plaza' as const },
  { icon: 'account-tie-outline', label: '分身管理', route: 'TwinManage' as const },
  { icon: 'creation', label: 'Skill 发布', route: 'SkillRelease' as const },
  { icon: 'clipboard-list-outline', label: '我的 Skill', route: 'MySkillList' as const },
  // 「我的统计」已移除：无对应页面，此前误路由到 Settings
  // 「通知设置」已移除（2026-09-11）：全死开关无实际功能，站内通知走上方「站内通知」行
  { icon: 'shield-check-outline', label: '合规手册', route: 'ComplianceManual' as const },
  { icon: 'help-circle-outline', label: '帮助中心', route: 'HelpCenter' as const },
  { icon: 'information-outline', label: '关于', route: 'Settings' as const },
];

export default function ProfileScreen() {
  const navigation = useNavigation<Nav>();
  const { user, logout } = useAuth();
  const [visitCount, setVisitCount] = useState<string>('--');
  const [taskCount, setTaskCount] = useState<string>('--');
  const [favoriteCount, setFavoriteCount] = useState<string>('--');
  const [unreadCount, setUnreadCount] = useState(0);

  useEffect(() => {
    let cancelled = false;
    // 三项统计均为真实接口计数（page_size=1 只取 total，不拉全量）
    visitAPI.list({ page: 1, page_size: 1 })
      .then((res) => { if (!cancelled) setVisitCount(String(res.total)); })
      .catch(() => { /* 保持 '--' */ });
    taskAPI.list({ page: 1, page_size: 1, status: 'open' })
      .then((res) => { if (!cancelled) setTaskCount(String(res.total)); })
      .catch(() => { /* 保持 '--' */ });
    specialistAPI.listFavorites({ page: 1, page_size: 1 })
      .then((res) => { if (!cancelled) setFavoriteCount(String(res.total)); })
      .catch(() => { /* 保持 '--' */ });
    return () => { cancelled = true; };
  }, []);

  // 未读通知红点：每次回到本 Tab 刷新（通知页已读后回来即消失）
  useFocusEffect(
    useCallback(() => {
      let cancelled = false;
      academicAPI.unreadCount()
        .then((res) => { if (!cancelled) setUnreadCount(res?.unread ?? 0); })
        .catch(() => { /* 红点拿不到不阻塞页面 */ });
      return () => { cancelled = true; };
    }, [])
  );

  const handleLogout = () => {
    Alert.alert('退出登录', '确定要退出当前账号吗？', [
      { text: '取消', style: 'cancel' },
      { text: '确定退出', style: 'destructive', onPress: logout },
    ]);
  };

  return (
    <View style={styles.container}>
      {/* A 档新人引导：备案/培训深藏入口首访提示（AsyncStorage 一次性） */}
      <FirstUseTip
        storageKey="onboarding.tip.rep.profile.v1"
        title="备案与合规培训在这里"
        content="备案资质上传、合规培训与考试、承诺书签署的入口：点上方用户卡 → 设置 → 备案与资质（页面最底部）。"
      />
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
            {/* 后端 User.to_dict 无 department 字段（name/phone/role/region/status），缺省显示 '--' */}
            <Text style={styles.userDept}>
              {user?.department || '--'} · {user?.region || '--'}
            </Text>
          </View>
          <Icon name="chevron-right" size={24} color={Colors.textHint} />
        </TouchableOpacity>

        {/* 数据统计（均为真实接口计数；无后端聚合的"本月对话"已移除，不展示假数据） */}
        <View style={[styles.statsCard, Shadow.card]}>
          {[
            { num: taskCount, label: '进行中任务' },
            { num: visitCount, label: '拜访总数' },
            { num: favoriteCount, label: '收藏' },
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
              {item.route === 'Notifications' && unreadCount > 0 && (
                <View style={styles.badge}>
                  <Text style={styles.badgeText}>{unreadCount > 99 ? '99+' : unreadCount}</Text>
                </View>
              )}
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
  badge: {
    minWidth: 18, height: 18, borderRadius: 9, backgroundColor: Colors.danger,
    justifyContent: 'center', alignItems: 'center', paddingHorizontal: 5, marginRight: 4,
  },
  badgeText: { color: Colors.white, fontSize: 11, fontWeight: '600' },
  logoutBtn: {
    padding: Spacing.lg, alignItems: 'center', flexDirection: 'row',
    justifyContent: 'center', gap: Spacing.sm,
    backgroundColor: Colors.white, borderRadius: BorderRadius.xl,
  },
  logoutText: { color: Colors.danger, fontSize: FontSize.md, fontWeight: '500' },
});
