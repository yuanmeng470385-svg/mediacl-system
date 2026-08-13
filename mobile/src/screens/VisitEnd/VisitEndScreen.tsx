/**
 * 拜访结束页 - AI 摘要 + 关键发现 + 下次建议 + 跟进
 *
 * 摘要来源：优先用 VisitInProgress 在导航前已调 endVisit 的结果（navigation params.summary），
 * 没有才自己调一次 endVisit —— 避免同一拜访被 end 两次触发后端"已结束"锁。
 * 真实失败显示错误态 + 重试，绝不展示伪造数据。
 */
import React, { useEffect, useState } from 'react';
import {
  View,
  Text,
  ScrollView,
  StyleSheet,
  TouchableOpacity,
  ActivityIndicator,
  Alert,
  Share,
} from 'react-native';
import { useRoute, useNavigation } from '@react-navigation/native';
import type { RouteProp } from '@react-navigation/native';
import type { NativeStackNavigationProp } from '@react-navigation/native-stack';
import { visitAPI } from '../../api/visit';
import { Colors, FontSize, Spacing, BorderRadius, Shadow } from '../../constants/theme';
import type { RootStackParamList, VisitEndParams } from '../../navigation/types';
import type { VisitSummary } from '../../types';

type RouteType = RouteProp<{ VisitEnd: VisitEndParams }, 'VisitEnd'>;
type Nav = NativeStackNavigationProp<RootStackParamList>;

export default function VisitEndScreen() {
  const route = useRoute<RouteType>();
  const navigation = useNavigation<Nav>();
  const { visitId, summary: initialSummary } = route.params;

  const [summary, setSummary] = useState<VisitSummary | null>(initialSummary ?? null);
  const [loading, setLoading] = useState(!initialSummary);
  const [error, setError] = useState('');
  const [followUp, setFollowUp] = useState<{
    follow_up_plan: string;
    suggested_date: string;
  } | null>(null);

  useEffect(() => {
    if (!initialSummary) loadSummary();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const loadSummary = async () => {
    try {
      // getById fallback：拜访已在别处结束（重复进入本页 / 断线后重进）→ 直接展示已有总结，
      // 不再调 endVisit —— 后端对已结束拜访拒绝重复 end（证据保护），重复调用只会报错
      const detail = await visitAPI.getById(visitId);
      if (detail?.ai_summary) {
        setSummary(detail.ai_summary);
        return;
      }
      const result = await visitAPI.endVisit(visitId);
      setSummary(result);
    } catch (e: any) {
      setError(e?.message || '生成拜访总结失败，请重试');
    } finally {
      setLoading(false);
    }
  };

  const retry = () => {
    setError('');
    setLoading(true);
    loadSummary();
  };

  const handleFollowUp = async () => {
    try {
      const result = await visitAPI.followUp(visitId);
      if (!result.follow_up_plan) {
        // api 层解析失败给了空结构 → 提示并保留按钮可重试
        Alert.alert('生成失败', '未能生成跟进计划，请重试');
        return;
      }
      setFollowUp(result);
    } catch (e: any) {
      // 失败保留生成按钮，用户可重试
      Alert.alert('生成失败', e?.message || '请稍后重试');
    }
  };

  // 分享 AI 摘要 + 关键点（需求 3.1.6：拜访总结可分享给上级）
  const handleShare = async () => {
    if (!summary) return;
    const points = (summary.key_points || [])
      .map((p, i) => `${i + 1}. ${p}`)
      .join('\n');
    const text = [
      '【MedAgent 拜访总结】',
      '',
      `摘要：${summary.summary || '暂无摘要'}`,
      points ? `\n关键点：\n${points}` : '',
      summary.interests?.length ? `\n兴趣点：${summary.interests.join('、')}` : '',
      summary.next_visit_recommendation ? `\n下次拜访推荐：${summary.next_visit_recommendation}` : '',
    ].filter(Boolean).join('\n');
    try {
      await Share.share({ title: '拜访总结', message: text });
    } catch {
      // 用户取消分享无需提示；系统失败给个兜底
      Alert.alert('提示', '分享失败，请稍后重试');
    }
  };

  // 确认完成：纯前端完成语义 —— 后端无对应状态端点（visit 状态由 endVisit 置为
  // completed），此处仅弹确认 → 提示成功 → 返回工作台
  const handleDone = () => {
    Alert.alert('确认完成', '确认本次拜访已全部完成？', [
      { text: '取消', style: 'cancel' },
      {
        text: '确认完成',
        onPress: () => {
          Alert.alert('完成', '本次拜访已完成，感谢使用', [
            { text: '知道了', onPress: () => navigation.popToTop() },
          ]);
        },
      },
    ]);
  };

  if (loading) {
    return (
      <View style={styles.centered}>
        <ActivityIndicator size="large" color={Colors.primary} />
        <Text style={styles.loadingText}>AI 正在生成拜访总结...</Text>
      </View>
    );
  }

  if (error || !summary) {
    return (
      <View style={styles.centered}>
        <Text style={styles.errorText}>{error || '拜访总结生成失败'}</Text>
        <TouchableOpacity style={styles.retryBtn} onPress={retry} activeOpacity={0.8}>
          <Text style={styles.retryText}>重试</Text>
        </TouchableOpacity>
      </View>
    );
  }

  const sentimentColor =
    summary.sentiment === 'positive' ? Colors.success
      : summary.sentiment === 'negative' ? Colors.danger
      : Colors.textSecondary;
  const sentimentLabel =
    summary.sentiment === 'positive' ? '积极'
      : summary.sentiment === 'negative' ? '消极'
      : '中性';

  return (
    <View style={styles.container}>
      {/* 头部 */}
      <View style={styles.header}>
        <Text style={styles.headerTitle}>拜访总结</Text>
        <Text style={styles.headerSub}>AI 自动生成</Text>
      </View>

      <ScrollView
        style={styles.content}
        showsVerticalScrollIndicator={false}
      >
        {/* 情感判断 */}
        <View style={[styles.card, Shadow.card]}>
          <View style={styles.sentimentRow}>
            <View style={[styles.sentimentDot, { backgroundColor: sentimentColor }]} />
            <View>
              <Text style={styles.sentimentLabel}>
                整体氛围：{sentimentLabel}
              </Text>
              <Text style={styles.sentimentHint}>
                基于对话内容的AI情感分析
              </Text>
            </View>
          </View>
        </View>

        {/* AI 摘要 */}
        <View style={[styles.card, Shadow.card]}>
          <Text style={styles.sectionTitle}>📋 摘要</Text>
          <Text style={styles.summaryText}>{summary.summary || '暂无摘要'}</Text>
        </View>

        {/* 关键点 */}
        <View style={[styles.card, Shadow.card]}>
          <Text style={styles.sectionTitle}>🔑 关键点</Text>
          {summary.key_points?.map((point, i) => (
            <View key={i} style={styles.keyPoint}>
              <Text style={styles.keyPointNum}>{i + 1}.</Text>
              <Text style={styles.keyPointText}>{point}</Text>
            </View>
          ))}
        </View>

        {/* 兴趣点 */}
        {summary.interests && summary.interests.length > 0 && (
          <View style={[styles.card, Shadow.card]}>
            <Text style={styles.sectionTitle}>💡 兴趣点</Text>
            <View style={styles.tagRow}>
              {summary.interests.map((item, i) => (
                <View key={i} style={styles.tag}>
                  <Text style={styles.tagText}>{item}</Text>
                </View>
              ))}
            </View>
          </View>
        )}

        {/* 异议 */}
        {summary.objections && summary.objections.length > 0 && (
          <View style={[styles.card, styles.warningCard]}>
            <Text style={styles.sectionTitle}>⚠️ 异议</Text>
            {summary.objections.map((obj, i) => (
              <View key={i} style={styles.objectionItem}>
                <Text style={styles.objectionText}>{obj}</Text>
              </View>
            ))}
          </View>
        )}

        {/* 下次推荐 */}
        <View style={[styles.card, Shadow.card]}>
          <Text style={styles.sectionTitle}>📅 下次拜访推荐</Text>
          <Text style={styles.nextVisitText}>
            {summary.next_visit_recommendation || '暂无推荐'}
          </Text>
        </View>

        {/* 跟进计划 */}
        {followUp ? (
          <View style={[styles.card, styles.followCard]}>
            <Text style={styles.sectionTitle}>✅ 跟进计划</Text>
            <Text style={styles.followText}>{followUp.follow_up_plan}</Text>
            <Text style={styles.followDate}>
              建议日期：{followUp.suggested_date}
            </Text>
          </View>
        ) : (
          <TouchableOpacity
            style={styles.followBtn}
            onPress={handleFollowUp}
            activeOpacity={0.7}
          >
            <Text style={styles.followBtnText}>📝 生成跟进计划</Text>
          </TouchableOpacity>
        )}

        <View style={{ height: 120 }} />
      </ScrollView>

      {/* 底部按钮 */}
      <View style={styles.bottomBar}>
        <TouchableOpacity
          style={styles.shareBtn}
          onPress={handleShare}
          activeOpacity={0.7}
        >
          <Text style={styles.shareBtnText}>分享</Text>
        </TouchableOpacity>
        <TouchableOpacity
          style={styles.doneBtn}
          onPress={handleDone}
          activeOpacity={0.8}
        >
          <Text style={styles.doneBtnText}>确认完成</Text>
        </TouchableOpacity>
      </View>
    </View>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1, backgroundColor: Colors.background },
  centered: { flex: 1, justifyContent: 'center', alignItems: 'center', backgroundColor: Colors.background },
  loadingText: { marginTop: Spacing.md, color: Colors.textHint, fontSize: FontSize.sm },
  errorText: {
    fontSize: FontSize.md, color: Colors.danger,
    marginBottom: Spacing.lg, paddingHorizontal: Spacing.xl, textAlign: 'center',
  },
  retryBtn: {
    backgroundColor: Colors.primary, borderRadius: BorderRadius.md,
    paddingHorizontal: Spacing.xl, paddingVertical: Spacing.sm,
  },
  retryText: { color: Colors.textWhite, fontSize: FontSize.md, fontWeight: '600' },
  header: {
    backgroundColor: Colors.success,
    paddingTop: 52,
    paddingBottom: Spacing.xl,
    alignItems: 'center',
  },
  headerTitle: { color: Colors.textWhite, fontSize: FontSize.xxl, fontWeight: '700' },
  headerSub: { color: 'rgba(255,255,255,0.8)', fontSize: FontSize.sm, marginTop: 4 },
  content: { flex: 1, padding: Spacing.lg },
  card: {
    backgroundColor: Colors.white,
    borderRadius: BorderRadius.lg,
    padding: Spacing.lg,
    marginBottom: Spacing.md,
  },
  sectionTitle: {
    fontSize: FontSize.lg,
    fontWeight: '700',
    color: Colors.textPrimary,
    marginBottom: Spacing.md,
  },
  // 情感
  sentimentRow: { flexDirection: 'row', alignItems: 'center', gap: Spacing.lg },
  sentimentDot: { width: 32, height: 32, borderRadius: 16 },
  sentimentLabel: { fontSize: FontSize.lg, fontWeight: '600', color: Colors.textPrimary },
  sentimentHint: { fontSize: FontSize.xs, color: Colors.textHint, marginTop: 2 },
  // 摘要
  summaryText: { fontSize: FontSize.md, color: Colors.textPrimary, lineHeight: 24 },
  // 关键点
  keyPoint: { flexDirection: 'row', marginBottom: Spacing.sm, gap: Spacing.sm },
  keyPointNum: { fontSize: FontSize.md, fontWeight: '700', color: Colors.primary, width: 20 },
  keyPointText: { fontSize: FontSize.md, color: Colors.textPrimary, flex: 1, lineHeight: 22 },
  // 标签
  tagRow: { flexDirection: 'row', flexWrap: 'wrap', gap: Spacing.sm },
  tag: {
    backgroundColor: Colors.background,
    paddingHorizontal: Spacing.md,
    paddingVertical: Spacing.xs,
    borderRadius: BorderRadius.full,
  },
  tagText: { fontSize: FontSize.sm, color: Colors.textPrimary },
  // 异议
  warningCard: { backgroundColor: '#fffbeb', borderWidth: 1, borderColor: '#fde68a' },
  objectionItem: {
    backgroundColor: '#fef3c7',
    padding: Spacing.md,
    borderRadius: BorderRadius.md,
    marginBottom: Spacing.xs,
  },
  objectionText: { fontSize: FontSize.sm, color: Colors.textPrimary },
  // 下次推荐
  nextVisitText: { fontSize: FontSize.md, color: Colors.textPrimary, lineHeight: 24 },
  // 跟进
  followCard: {
    backgroundColor: '#f0fdf4',
    borderWidth: 1,
    borderColor: '#bbf7d0',
  },
  followText: { fontSize: FontSize.md, color: Colors.textPrimary, lineHeight: 24, marginBottom: Spacing.sm },
  followDate: { fontSize: FontSize.sm, color: Colors.success, fontWeight: '600' },
  followBtn: {
    backgroundColor: Colors.white,
    borderRadius: BorderRadius.lg,
    padding: Spacing.xl,
    alignItems: 'center',
    borderWidth: 1.5,
    borderColor: Colors.primary,
    borderStyle: 'dashed',
    marginBottom: Spacing.md,
  },
  followBtnText: { color: Colors.primary, fontSize: FontSize.md, fontWeight: '600' },
  // 底部
  bottomBar: {
    flexDirection: 'row',
    padding: Spacing.lg,
    paddingBottom: 34,
    backgroundColor: Colors.white,
    borderTopWidth: 1,
    borderTopColor: Colors.divider,
    gap: Spacing.md,
  },
  shareBtn: {
    flex: 1,
    borderRadius: BorderRadius.lg,
    paddingVertical: 16,
    alignItems: 'center',
    borderWidth: 1,
    borderColor: Colors.border,
  },
  shareBtnText: { color: Colors.textPrimary, fontSize: FontSize.md, fontWeight: '600' },
  doneBtn: {
    flex: 2,
    backgroundColor: Colors.success,
    borderRadius: BorderRadius.lg,
    paddingVertical: 16,
    alignItems: 'center',
  },
  doneBtnText: { color: Colors.textWhite, fontSize: FontSize.lg, fontWeight: '700' },
});
