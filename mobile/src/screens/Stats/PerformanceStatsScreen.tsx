/**
 * 业绩统计页（2026-09-11 死页清理批：原设置页「业绩统计」是敬请期待壳，此页做真）。
 * 三块全部真实数据、零新端点：
 *   - 我的拜访：GET /visits（本人，取最近 100 条算本月/进行中，total 为累计）
 *   - AI 陪练：GET /practices（本人会话，场均分与最近 5 场趋势均取 scores.overall）
 *   - 学术卡片：GET /academic-cards（本人卡片 total）
 * 口径写在页脚：不虚构没有的维度（rep 无会话列表端点，不统计对话数）。
 */
import React, { useCallback, useEffect, useState } from 'react';
import {
  View, Text, ScrollView, StyleSheet, TouchableOpacity,
  ActivityIndicator, RefreshControl,
} from 'react-native';
import { useNavigation } from '@react-navigation/native';
import Icon from '../../components/Icon';
import { visitAPI } from '../../api/visit';
import { practiceAPI } from '../../api/practice';
import { academicAPI } from '../../api/academic';
import { Colors, FontSize, Spacing, BorderRadius, Shadow } from '../../constants/theme';
import type { NativeStackNavigationProp } from '@react-navigation/native-stack';
import type { RootStackParamList } from '../../navigation/types';

type Nav = NativeStackNavigationProp<RootStackParamList>;

/** 拜访统计窗口：状态分布/本月按最近 N 条计算（超出的在页脚注明） */
const VISIT_WINDOW = 100;
/** 陪练趋势取最近 N 场已评分会话 */
const TREND_N = 5;
/** 陪练 overall 评分口径：0~1 分制（与 PracticeListScreen 展示及后端 complete 契约一致） */
const SCORE_MAX = 1;

interface StatsState {
  visitTotal: number;
  visitMonth: number;
  visitInProgress: number;
  visitTruncated: boolean;
  practiceTotal: number;
  practiceScored: number;
  practiceAvg: number | null;
  recentScores: number[];
  cardTotal: number;
}

const EMPTY: StatsState = {
  visitTotal: 0, visitMonth: 0, visitInProgress: 0, visitTruncated: false,
  practiceTotal: 0, practiceScored: 0, practiceAvg: null, recentScores: [], cardTotal: 0,
};

/** 当前本地年月 'YYYY-MM'（visit_time 为本地字面量，按字符串前缀比对最稳） */
function currentMonthPrefix(): string {
  const d = new Date();
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}`;
}

function computeStats(visits: any[], visitTotal: number, practices: any[], cardTotal: number): StatsState {
  const month = currentMonthPrefix();
  const visitMonth = visits.filter((v) => typeof v?.visit_time === 'string' && v.visit_time.slice(0, 7) === month).length;
  const visitInProgress = visits.filter((v) => v?.status === 'in_progress').length;
  const scored = practices
    .map((p) => (typeof p?.scores?.overall === 'number' ? p.scores.overall : null))
    .filter((s: number | null): s is number => s !== null);
  const avg = scored.length ? scored.reduce((a, b) => a + b, 0) / scored.length : null;
  return {
    visitTotal,
    visitMonth,
    visitInProgress,
    visitTruncated: visitTotal > visits.length,
    practiceTotal: practices.length,
    practiceScored: scored.length,
    practiceAvg: avg,
    recentScores: scored.slice(-TREND_N),
    cardTotal,
  };
}

function StatBox({ label, value, hint }: { label: string; value: string; hint?: string }) {
  return (
    <View style={styles.statBox}>
      <Text style={styles.statValue}>{value}</Text>
      <Text style={styles.statLabel}>{label}</Text>
      {hint ? <Text style={styles.statHint}>{hint}</Text> : null}
    </View>
  );
}

export default function PerformanceStatsScreen() {
  const navigation = useNavigation<Nav>();
  const [stats, setStats] = useState<StatsState>(EMPTY);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [error, setError] = useState('');

  const load = useCallback(async () => {
    setError('');
    try {
      // 三路独立拉取，单路失败整页报错可重试（数据要么全对要么明确失败，不拼半页）
      const [visitRes, practiceRes, cardRes] = await Promise.all([
        visitAPI.list({ page: 1, page_size: VISIT_WINDOW }),
        practiceAPI.list(),
        academicAPI.listMyCards(),
      ]);
      const visits = Array.isArray(visitRes?.items) ? visitRes.items : [];
      const practices = Array.isArray(practiceRes?.items) ? practiceRes.items : [];
      setStats(computeStats(visits, Number(visitRes?.total ?? visits.length), practices, Number(cardRes?.total ?? 0)));
    } catch (e: any) {
      setError(e?.message || '统计数据加载失败，请检查网络');
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { load(); }, [load]);

  const onRefresh = async () => {
    setRefreshing(true);
    await load();
    setRefreshing(false);
  };

  return (
    <View style={styles.container}>
      <View style={styles.header}>
        <TouchableOpacity onPress={() => navigation.goBack()}>
          <Icon name="chevron-left" size={22} color={Colors.textWhite} />
        </TouchableOpacity>
        <Text style={styles.headerTitle}>业绩统计</Text>
        <View style={{ width: 24 }} />
      </View>
      <ScrollView
        contentContainerStyle={styles.content}
        refreshControl={<RefreshControl refreshing={refreshing} onRefresh={onRefresh} />}
      >
        {error ? (
          <View style={[styles.card, Shadow.card]}>
            <Text style={styles.errorText}>{error}</Text>
            <TouchableOpacity style={styles.retryBtn} onPress={load}>
              <Text style={styles.retryText}>重试</Text>
            </TouchableOpacity>
          </View>
        ) : loading ? (
          <View style={[styles.card, Shadow.card, styles.loadingBox]}>
            <ActivityIndicator color={Colors.primary} />
          </View>
        ) : (
          <>
            <View style={[styles.card, Shadow.card]}>
              <Text style={styles.cardTitle}>我的拜访</Text>
              <View style={styles.statRow}>
                <StatBox label="累计拜访" value={String(stats.visitTotal)} />
                <StatBox label="本月" value={String(stats.visitMonth)} />
                <StatBox label="进行中" value={String(stats.visitInProgress)} />
              </View>
            </View>

            <View style={[styles.card, Shadow.card]}>
              <Text style={styles.cardTitle}>AI 陪练</Text>
              <View style={styles.statRow}>
                <StatBox label="陪练场次" value={String(stats.practiceTotal)} />
                <StatBox
                  label="平均分"
                  value={stats.practiceAvg != null ? stats.practiceAvg.toFixed(1) : '--'}
                  hint={stats.practiceScored ? `已评分 ${stats.practiceScored} 场` : '暂无已评分场次'}
                />
                <View style={styles.statBox}>
                  <View style={styles.trendRow}>
                    {stats.recentScores.length ? stats.recentScores.map((s, i) => (
                      <View
                        key={i}
                        style={[styles.trendBar, { height: Math.max(4, Math.round((s / SCORE_MAX) * 44)) }]}
                      />
                    )) : (
                      <Text style={styles.statHint}>暂无趋势</Text>
                    )}
                  </View>
                  <Text style={styles.statLabel}>最近 {TREND_N} 场</Text>
                </View>
              </View>
            </View>

            <View style={[styles.card, Shadow.card]}>
              <Text style={styles.cardTitle}>学术卡片</Text>
              <View style={styles.statRow}>
                <StatBox label="累计创建" value={String(stats.cardTotal)} />
              </View>
            </View>

            <Text style={styles.footnote}>
              口径说明：累计数为接口 total；本月/进行中按最近 {VISIT_WINDOW} 条拜访计算
              {stats.visitTruncated ? '（超出部分未计入）' : ''}；陪练评分为 0~1 分制，
              平均分仅统计已完成评分的场次。
            </Text>
          </>
        )}
      </ScrollView>
    </View>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1, backgroundColor: Colors.background },
  header: {
    flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between',
    paddingHorizontal: Spacing.md, paddingVertical: Spacing.sm,
    backgroundColor: Colors.primary,
  },
  headerTitle: { color: Colors.textWhite, fontSize: FontSize.lg, fontWeight: '700' },
  content: { padding: Spacing.md },
  card: {
    backgroundColor: Colors.backgroundAlt, borderRadius: BorderRadius.md,
    padding: Spacing.md, marginBottom: Spacing.md,
  },
  cardTitle: { fontSize: FontSize.md, fontWeight: '700', color: Colors.textPrimary, marginBottom: Spacing.md },
  statRow: { flexDirection: 'row' },
  statBox: { flex: 1, alignItems: 'center' },
  statValue: { fontSize: FontSize.xl, fontWeight: '700', color: Colors.primary },
  statLabel: { fontSize: FontSize.xs, color: Colors.textHint, marginTop: 2 },
  statHint: { fontSize: FontSize.xs, color: Colors.textHint, marginTop: 2, textAlign: 'center' },
  trendRow: { flexDirection: 'row', alignItems: 'flex-end', height: 44, gap: 4 },
  trendBar: { width: 10, borderRadius: 2, backgroundColor: Colors.accent },
  loadingBox: { alignItems: 'center', padding: Spacing.lg },
  errorText: { color: Colors.textPrimary, fontSize: FontSize.sm, textAlign: 'center', marginBottom: Spacing.md },
  retryBtn: {
    alignSelf: 'center', paddingVertical: Spacing.sm, paddingHorizontal: Spacing.lg,
    borderRadius: BorderRadius.md, backgroundColor: Colors.primary,
  },
  retryText: { color: Colors.textWhite, fontSize: FontSize.sm },
  footnote: { fontSize: FontSize.xs, color: Colors.textHint, lineHeight: 18 },
});
