/**
 * 工作台 - 今日工作总览
 * 临床精准风：深海军蓝头部 + 纯白卡片 + 青蓝数据高亮
 */
import React, { useState, useCallback } from 'react';
import {
  View,
  Text,
  StyleSheet,
  ScrollView,
  RefreshControl,
  TouchableOpacity,
} from 'react-native';
import { useNavigation, useFocusEffect } from '@react-navigation/native';
import type { NativeStackNavigationProp } from '@react-navigation/native-stack';
import ProgressRing from '../../components/ProgressRing';
import VisitCard from '../../components/VisitCard';
import EmptyState from '../../components/EmptyState';
import FAB from '../../components/FAB';
import Icon from '../../components/Icon';
import { ActionIcons, FeatureIcons } from '../../components/Icon';
import { visitAPI } from '../../api/visit';
import { useAuth } from '../../store/AuthContext';
import { formatLocalDate } from '../../utils/date';
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
  const [error, setError] = useState('');

  const loadVisits = useCallback(async () => {
    try {
      // 本地日期（toISOString 是 UTC，东八区凌晨 0-8 点会取成昨天）。
      // date_to 必须带 T23:59:59：后端 visit_repo 把 date_to 解析为当日 00:00:00 做 <= 过滤，
      // 传纯日期会让今日拜访恒为空
      const today = formatLocalDate();
      const result = await visitAPI.list({
        page: 1, page_size: 20,
        date_from: today, date_to: `${today}T23:59:59`,
      });
      setVisits(result.items || []);
      setError('');
    } catch (e: any) {
      // G4：失败不再静默置空 —— 断网时置空会误显示"暂无拜访安排"，改错误态 + 重试
      setError(e?.message || '拜访列表加载失败，请检查网络');
    } finally {
      setLoading(false);
    }
  }, []);

  // 挂载只拉一次会让返回场景吃旧快照：拜访结束后回到工作台，
  // 进度环/「进行中」仍显示结束前的状态 —— 聚焦时重拉
  useFocusEffect(
    useCallback(() => {
      loadVisits();
    }, [loadVisits])
  );

  const handleRetry = () => {
    setLoading(true);
    setError('');
    loadVisits();
  };

  const onRefresh = async () => {
    setRefreshing(true);
    await loadVisits();
    setRefreshing(false);
  };

  const completed = visits.filter((v) => v.status === 'completed').length;
  const total = visits.length;
  const inProgress = visits.filter((v) => v.status === 'in_progress');

  const hour = new Date().getHours();
  const greeting = hour < 12 ? '早上好' : hour < 18 ? '下午好' : '晚上好';
  const today = new Date();
  const weekDays = ['日', '一', '二', '三', '四', '五', '六'];
  const dateStr = `${today.getFullYear()}年${today.getMonth() + 1}月${today.getDate()}日 星期${weekDays[today.getDay()]}`;

  return (
    <View style={styles.container}>

      {/* 头部 */}
      <View style={styles.header}>
        <View style={styles.headerContent}>
          <View>
            <Text style={styles.greeting}>
              {greeting}，{user?.name || '医药代表'}
            </Text>
            <Text style={styles.date}>{dateStr}</Text>
          </View>
          {/* 工作台铃铛 → 站内通知中心（2026-09-11 死页清理：原指「通知设置」全是死开关） */}
          <TouchableOpacity
            style={styles.notifyBtn}
            onPress={() => navigation.navigate('Notifications')}
          >
            <Icon name={ActionIcons.notification} size={20} color={Colors.textWhite} />
          </TouchableOpacity>
        </View>
      </View>
      <ScrollView
        style={styles.body}
        showsVerticalScrollIndicator={false}
        refreshControl={
          <RefreshControl
            refreshing={refreshing}
            onRefresh={onRefresh}
            tintColor={Colors.primary}
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
              <View style={styles.inProgressDot} />
              <Text style={styles.inProgressText}>
                {inProgress.length} 场拜访进行中
              </Text>
            </View>
          )}
        </View>

        {/* 快捷功能 */}
        <View style={styles.quickActions}>
          {[
            { icon: FeatureIcons.specialist, label: '数字专员', route: 'Specialists' as const },
            { icon: FeatureIcons.content, label: '学术内容', route: 'Content' as const },
            { icon: FeatureIcons.doctor, label: '找医生', route: 'HCPs' as const },
            { icon: FeatureIcons.compliance, label: '合规手册', route: 'ComplianceManual' as const },
          ].map((item, i) => (
            <TouchableOpacity
              key={i}
              style={[styles.quickBtn, Shadow.card]}
              onPress={() => {
                (navigation as any).navigate(item.route);
              }}
              activeOpacity={0.7}
            >
              <View style={styles.quickIconCircle}>
                <Icon name={item.icon} size={24} color={Colors.primary} />
              </View>
              <Text style={styles.quickLabel}>{item.label}</Text>
            </TouchableOpacity>
          ))}
        </View>

        {/* 今日拜访列表 */}
        <Text style={styles.sectionTitle}>今日拜访</Text>
        {loading ? (
          <View style={styles.loading}><Text style={styles.loadingText}>加载中...</Text></View>
        ) : error && visits.length === 0 ? (
          // G4：加载失败显示错误 + 重试（与全站错误态一致），不伪装成"暂无拜访安排"
          <View style={styles.errorBox}>
            <Text style={styles.errorText}>{error}</Text>
            <TouchableOpacity style={styles.retryBtn} onPress={handleRetry} activeOpacity={0.8}>
              <Text style={styles.retryText}>重试</Text>
            </TouchableOpacity>
          </View>
        ) : visits.length === 0 ? (
          <EmptyState
            icon="calendar-blank-outline"
            title="暂无拜访安排"
            description="点击右下角 + 添加新的拜访计划"
          />
        ) : (
          visits.map((visit) => (
            <VisitCard
              key={visit.id}
              visit={visit}
              onPress={() =>
                visit.status === 'in_progress'
                  ? navigation.navigate('VisitInProgress', { visitId: visit.id, hcpName: visit.hcp_name })
                  : navigation.navigate('VisitDetail', { visitId: visit.id })
              }
            />
          ))
        )}
        <View style={{ height: 100 }} />
      </ScrollView>

      <FAB icon="plus" label="新增拜访" onPress={() => (navigation as any).navigate('HCPs')} />
    </View>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1, backgroundColor: Colors.background },
  header: {
    backgroundColor: Colors.primary,
    paddingTop: 52,
    paddingBottom: Spacing.xxl,
    ...Shadow.header,
  },
  headerContent: {
    paddingHorizontal: Spacing.xxl,
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'flex-end',
  },
  greeting: { color: Colors.textWhite, fontSize: FontSize.xxl, fontWeight: '700' },
  date: { color: 'rgba(255,255,255,0.7)', fontSize: FontSize.sm, marginTop: 6 },
  notifyBtn: {
    width: 40, height: 40, borderRadius: 20,
    backgroundColor: 'rgba(255,255,255,0.15)',
    alignItems: 'center', justifyContent: 'center',
  },
  body: { flex: 1, padding: Spacing.lg },
  sectionTitle: {
    fontSize: FontSize.lg, fontWeight: '700',
    color: Colors.textPrimary,
    marginBottom: Spacing.md, marginTop: Spacing.sm,
  },
  card: {
    backgroundColor: Colors.white,
    borderRadius: BorderRadius.xl,
    padding: Spacing.xl,
    marginBottom: Spacing.lg,
    alignItems: 'center',
  },
  inProgressBar: {
    marginTop: Spacing.lg, paddingTop: Spacing.md,
    borderTopWidth: 1, borderTopColor: Colors.divider,
    width: '100%', alignItems: 'center',
    flexDirection: 'row', justifyContent: 'center', gap: Spacing.sm,
  },
  inProgressDot: {
    width: 8, height: 8, borderRadius: 4,
    backgroundColor: Colors.info,
  },
  inProgressText: {
    fontSize: FontSize.sm, color: Colors.info, fontWeight: '600',
  },
  quickActions: {
    flexDirection: 'row', justifyContent: 'space-between',
    marginBottom: Spacing.xl,
  },
  quickBtn: {
    flex: 1,
    backgroundColor: Colors.white,
    borderRadius: BorderRadius.xl,
    padding: Spacing.md,
    alignItems: 'center',
    marginHorizontal: 4,
    gap: Spacing.sm,
  },
  quickIconCircle: {
    width: 44, height: 44, borderRadius: 22,
    backgroundColor: Colors.primarySurface,
    alignItems: 'center', justifyContent: 'center',
  },
  quickLabel: { fontSize: FontSize.xs, color: Colors.textSecondary, fontWeight: '600' },
  loading: { padding: Spacing.xxxl, alignItems: 'center' },
  loadingText: { color: Colors.textHint, fontSize: FontSize.sm },
  errorBox: { alignItems: 'center', padding: Spacing.xxxl },
  errorText: {
    fontSize: FontSize.md, color: Colors.danger,
    marginBottom: Spacing.lg, paddingHorizontal: Spacing.xl, textAlign: 'center',
  },
  retryBtn: {
    backgroundColor: Colors.primary, borderRadius: BorderRadius.md,
    paddingHorizontal: Spacing.xl, paddingVertical: Spacing.sm,
  },
  retryText: { color: Colors.textWhite, fontSize: FontSize.md, fontWeight: '600' },
});
