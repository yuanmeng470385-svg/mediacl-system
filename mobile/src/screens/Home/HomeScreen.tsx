/**
 * 工作台 - 今日工作总览
 */
import React, { useEffect, useState, useCallback } from 'react';
import {
  View,
  Text,
  StyleSheet,
  ScrollView,
  RefreshControl,
  TouchableOpacity,
} from 'react-native';
import { useNavigation } from '@react-navigation/native';
import type { NativeStackNavigationProp } from '@react-navigation/native-stack';
import ProgressRing from '../../components/ProgressRing';
import VisitCard from '../../components/VisitCard';
import EmptyState from '../../components/EmptyState';
import FAB from '../../components/FAB';
import { visitAPI } from '../../api/visit';
import { useAuth } from '../../store/AuthContext';
import { Colors, FontSize, Spacing, BorderRadius, Shadow } from '../../constants/theme';
import type { VisitRecord } from '../../types';
import type { RootStackParamList } from '../../navigation/types';

type Nav = NativeStackNavigationProp<RootStackParamList>;

export default function HomeScreen() {
  const navigation = useNavigation<Nav>();
  const { user } = useAuth();
  const [visits, setVisits] = useState<VisitRecord[]>([]);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);

  const loadVisits = useCallback(async () => {
    try {
      const today = new Date().toISOString().split('T')[0];
      const result = await visitAPI.list({
        page: 1,
        page_size: 20,
        start_date: today,
        end_date: today,
      });
      setVisits(result.items || []);
    } catch {
      // Mock 数据——后端不可用时展示
      setVisits([]);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    loadVisits();
  }, [loadVisits]);

  const onRefresh = async () => {
    setRefreshing(true);
    await loadVisits();
    setRefreshing(false);
  };

  const completed = visits.filter((v) => v.status === 'completed').length;
  const total = visits.length;
  const inProgress = visits.filter((v) => v.status === 'in_progress');

  // 问候语
  const hour = new Date().getHours();
  const greeting = hour < 12 ? '早上好' : hour < 18 ? '下午好' : '晚上好';
  const today = new Date();
  const weekDays = ['日', '一', '二', '三', '四', '五', '六'];
  const dateStr = `${today.getFullYear()}年${today.getMonth() + 1}月${today.getDate()}日 星期${weekDays[today.getDay()]}`;

  return (
    <View style={styles.container}>
      {/* 头部 */}
      <View style={styles.header}>
        <View>
          <Text style={styles.greeting}>
            {greeting}，{user?.name || '医药代表'}
          </Text>
          <Text style={styles.date}>{dateStr}</Text>
        </View>
        <View style={styles.headerRight}>
          <TouchableOpacity
            style={styles.notifyBtn}
            onPress={() => navigation.navigate('NotificationSettings')}
          >
            <Text style={styles.notifyIcon}>🔔</Text>
          </TouchableOpacity>
        </View>
      </View>

      <ScrollView
        style={styles.content}
        showsVerticalScrollIndicator={false}
        refreshControl={
          <RefreshControl
            refreshing={refreshing}
            onRefresh={onRefresh}
            colors={[Colors.primary]}
          />
        }
      >
        {/* 今日进度 */}
        <View style={[styles.card, Shadow.card]}>
          <Text style={styles.sectionTitle}>今日拜访进度</Text>
          <ProgressRing completed={completed} total={total} />
          {inProgress.length > 0 && (
            <View style={styles.inProgressBar}>
              <Text style={styles.inProgressText}>
                🔵 {inProgress.length} 场拜访进行中
              </Text>
            </View>
          )}
        </View>

        {/* 快捷功能 */}
        <View style={styles.quickActions}>
          {[
            { icon: '💬', label: '数字专员', route: 'Specialists' as const },
            { icon: '📄', label: '学术内容', route: 'ContentDetail' as const, params: { contentId: 0 } },
            { icon: '👨‍⚕️', label: '找医生', route: 'HCPs' as const },
            { icon: '📋', label: '合规手册', route: 'ComplianceManual' as const },
          ].map((item, i) => (
            <TouchableOpacity
              key={i}
              style={[styles.quickBtn, Shadow.card]}
              onPress={() => {
                if (item.route === 'ContentDetail') {
                  // ContentDetail needs contentId, fallback to main tab
                  navigation.navigate('MainTabs' as any);
                  // Then navigate to HCPs as a fallback
                  (navigation as any).navigate('HCPs');
                } else if (item.route === 'ComplianceManual') {
                  navigation.navigate('ComplianceManual');
                } else {
                  (navigation as any).navigate(item.route);
                }
              }}
              activeOpacity={0.7}
            >
              <Text style={styles.quickIcon}>{item.icon}</Text>
              <Text style={styles.quickLabel}>{item.label}</Text>
            </TouchableOpacity>
          ))}
        </View>

        {/* 今日拜访列表 */}
        <Text style={styles.sectionTitle}>今日拜访</Text>
        {loading ? (
          <View style={styles.loading}>
            <Text style={styles.loadingText}>加载中...</Text>
          </View>
        ) : visits.length === 0 ? (
          <EmptyState
            icon="📅"
            title="暂无拜访安排"
            description="点击右下角 + 添加新的拜访计划"
          />
        ) : (
          visits.map((visit) => (
            <VisitCard
              key={visit.id}
              visit={visit}
              onPress={() =>
                navigation.navigate('VisitDetail', { visitId: visit.id })
              }
            />
          ))
        )}
        {/* 底部留白 */}
        <View style={{ height: 100 }} />
      </ScrollView>

      {/* FAB - 新增拜访 */}
      <FAB
        icon="+"
        label="新增拜访"
        onPress={() => {
          // 简单提示选医生后进入准备页
          (navigation as any).navigate('HCPs');
        }}
      />
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
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'flex-end',
  },
  headerRight: { flexDirection: 'row', gap: Spacing.md },
  greeting: { color: Colors.textWhite, fontSize: FontSize.xl, fontWeight: '700' },
  date: { color: 'rgba(255,255,255,0.8)', fontSize: FontSize.sm, marginTop: 4 },
  notifyBtn: {
    width: 40,
    height: 40,
    borderRadius: 20,
    backgroundColor: 'rgba(255,255,255,0.2)',
    alignItems: 'center',
    justifyContent: 'center',
  },
  notifyIcon: { fontSize: 18 },
  content: { flex: 1, padding: Spacing.lg },
  sectionTitle: {
    fontSize: FontSize.lg,
    fontWeight: '700',
    color: Colors.textPrimary,
    marginBottom: Spacing.md,
    marginTop: Spacing.sm,
  },
  card: {
    backgroundColor: Colors.white,
    borderRadius: BorderRadius.lg,
    padding: Spacing.xl,
    marginBottom: Spacing.lg,
    alignItems: 'center',
  },
  inProgressBar: {
    marginTop: Spacing.lg,
    paddingTop: Spacing.md,
    borderTopWidth: 1,
    borderTopColor: Colors.divider,
    width: '100%',
    alignItems: 'center',
  },
  inProgressText: {
    fontSize: FontSize.sm,
    color: Colors.primary,
    fontWeight: '600',
  },
  quickActions: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    marginBottom: Spacing.xl,
  },
  quickBtn: {
    flex: 1,
    backgroundColor: Colors.white,
    borderRadius: BorderRadius.lg,
    padding: Spacing.lg,
    alignItems: 'center',
    marginHorizontal: 4,
    gap: Spacing.sm,
  },
  quickIcon: { fontSize: 28 },
  quickLabel: { fontSize: FontSize.xs, color: Colors.textSecondary, fontWeight: '500' },
  loading: { padding: Spacing.xxxl, alignItems: 'center' },
  loadingText: { color: Colors.textHint, fontSize: FontSize.sm },
});
