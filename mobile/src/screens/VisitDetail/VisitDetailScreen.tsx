/**
 * 拜访详情页 - 查看已完成的拜访记录
 */
import React, { useEffect, useState } from 'react';
import { View, Text, ScrollView, StyleSheet, TouchableOpacity, ActivityIndicator, Alert } from 'react-native';
import { useRoute, useNavigation } from '@react-navigation/native';
import type { RouteProp } from '@react-navigation/native';
import type { NativeStackNavigationProp } from '@react-navigation/native-stack';
import Icon from '../../components/Icon';
import { Colors, FontSize, Spacing, BorderRadius, Shadow } from '../../constants/theme';
import { visitAPI } from '../../api/visit';
import type { VisitRecord } from '../../types';
import type { RootStackParamList } from '../../navigation/types';

type RouteType = RouteProp<RootStackParamList, 'VisitDetail'>;
type Nav = NativeStackNavigationProp<RootStackParamList>;

/** 拜访时长：两时间都在则算分钟数；只有开始时间则视为进行中/已结束；都缺显示 -- */
function formatDuration(start?: string, end?: string): string {
  if (start && end) {
    // 后端可能是 'YYYY-MM-DD HH:mm:ss' 空格格式，转 T 以便 Date.parse 兼容
    const s = Date.parse(start.replace(' ', 'T'));
    const e = Date.parse(end.replace(' ', 'T'));
    if (!Number.isNaN(s) && !Number.isNaN(e) && e >= s) {
      return `${Math.round((e - s) / 60000)} 分钟`;
    }
  }
  return start ? '进行中/已结束' : '--';
}

export default function VisitDetailScreen() {
  const route = useRoute<RouteType>();
  const navigation = useNavigation<Nav>();
  const { visitId } = route.params;
  const [record, setRecord] = useState<VisitRecord | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [reloadKey, setReloadKey] = useState(0);

  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const r = await visitAPI.getById(visitId);
        if (!cancelled) setRecord(r);
      } catch (e: any) {
        if (!cancelled) setError(e?.message || '加载失败');
      } finally {
        if (!cancelled) setLoading(false);
      }
    })();
    return () => { cancelled = true; };
  }, [visitId, reloadKey]);

  if (loading) {
    return (
      <View style={styles.centered}>
        <ActivityIndicator size="large" color={Colors.primary} />
      </View>
    );
  }

  if (error) {
    return (
      <View style={styles.centered}>
        <Text style={styles.errorText}>{error}</Text>
        <TouchableOpacity
          style={styles.retryBtn}
          onPress={() => {
            setLoading(true);
            setError('');
            setReloadKey((k) => k + 1);
          }}
        >
          <Text style={styles.retryText}>重试</Text>
        </TouchableOpacity>
      </View>
    );
  }

  const summary = record?.ai_summary;
  const keyPoints = summary?.key_points ?? [];
  const interests = summary?.interests ?? [];
  const objections = summary?.objections ?? [];

  // 进行中的拜访：恢复继续（回拜访中页，转写/录音继续追加）+ 显式取消（后端 POST /cancel，
  // 已结束/已取消会被拒绝）
  const handleResume = () => {
    navigation.navigate('VisitInProgress', { visitId, hcpName: record?.hcp_name || '' });
  };
  const handleCancel = () => {
    Alert.alert('取消拜访', '确认取消本次拜访？取消后转写将停止接收，无法恢复。', [
      { text: '再想想', style: 'cancel' },
      {
        text: '确认取消',
        style: 'destructive',
        onPress: async () => {
          try {
            await visitAPI.cancelVisit(visitId);
            Alert.alert('已取消', '本次拜访已取消');
            setReloadKey((k) => k + 1);
          } catch (e: any) {
            Alert.alert('取消失败', e?.message || '请稍后重试');
          }
        },
      },
    ]);
  };

  const statusLabel =
    record?.status === 'completed' ? '拜访已完成'
      : record?.status === 'cancelled' ? '已取消'
      : '进行中';

  return (
    <View style={styles.container}>
      <View style={styles.header}>
        <TouchableOpacity onPress={() => navigation.goBack()}>
          <Icon name="chevron-left" size={22} color={Colors.textWhite} />
        </TouchableOpacity>
        <Text style={styles.headerTitle}>拜访详情</Text>
        <View style={{ width: 24 }} />
      </View>

      <ScrollView contentContainerStyle={styles.content}>
        {/* 基本信息 */}
        <View style={[styles.card, Shadow.card]}>
          <Text style={styles.cardTitle}>基本信息</Text>
          <View style={styles.infoRow}>
            <Icon name="doctor" size={18} color={Colors.textSecondary} />
            <Text style={styles.infoText}>医生：{record?.hcp_name || '未知医生'}</Text>
          </View>
          <View style={styles.infoRow}>
            <Icon name="calendar" size={18} color={Colors.textSecondary} />
            <Text style={styles.infoText}>日期：{record?.planned_date || '--'}</Text>
          </View>
          <View style={styles.infoRow}>
            <Icon name="clock-outline" size={18} color={Colors.textSecondary} />
            <Text style={styles.infoText}>
              时长：{formatDuration(record?.actual_start_time, record?.actual_end_time)}
            </Text>
          </View>
          <View style={styles.infoRow}>
            <Icon name="hospital-building" size={18} color={Colors.textSecondary} />
            <Text style={styles.infoText}>
              状态：{statusLabel}
            </Text>
          </View>
        </View>

        {/* 进行中操作：恢复拜访 / 取消拜访 */}
        {record?.status === 'in_progress' && (
          <View style={styles.actionsRow}>
            <TouchableOpacity style={[styles.actionBtn, styles.resumeBtn]} onPress={handleResume} activeOpacity={0.8}>
              <Icon name="play-circle" size={18} color={Colors.textWhite} />
              <Text style={styles.resumeText}>继续拜访</Text>
            </TouchableOpacity>
            <TouchableOpacity style={[styles.actionBtn, styles.cancelBtn]} onPress={handleCancel} activeOpacity={0.8}>
              <Icon name="close-circle" size={18} color={Colors.danger} />
              <Text style={styles.cancelText}>取消拜访</Text>
            </TouchableOpacity>
          </View>
        )}

        {/* AI 总结 */}
        <View style={[styles.card, Shadow.card]}>
          <Text style={styles.cardTitle}>AI 拜访总结</Text>
          <View style={styles.summaryBox}>
            <Text style={styles.summaryText}>{summary?.summary || '暂无 AI 总结'}</Text>
          </View>
          {summary?.next_visit_recommendation ? (
            <Text style={styles.nextRecommend}>
              下次拜访建议：{summary.next_visit_recommendation}
            </Text>
          ) : null}
        </View>

        {/* 关键发现 */}
        {keyPoints.length > 0 && (
          <View style={[styles.card, Shadow.card]}>
            <Text style={styles.cardTitle}>关键发现</Text>
            {keyPoints.map((point, i) => (
              <View key={i} style={styles.bulletRow}>
                <View style={styles.bullet} />
                <Text style={styles.bulletText}>{point}</Text>
              </View>
            ))}
          </View>
        )}

        {/* 兴趣点 */}
        {interests.length > 0 && (
          <View style={[styles.card, Shadow.card]}>
            <Text style={styles.cardTitle}>兴趣点</Text>
            {interests.map((point, i) => (
              <View key={i} style={styles.bulletRow}>
                <View style={styles.bullet} />
                <Text style={styles.bulletText}>{point}</Text>
              </View>
            ))}
          </View>
        )}

        {/* 异议 */}
        {objections.length > 0 && (
          <View style={[styles.card, Shadow.card]}>
            <Text style={styles.cardTitle}>异议</Text>
            {objections.map((point, i) => (
              <View key={i} style={styles.bulletRow}>
                <View style={styles.bullet} />
                <Text style={styles.bulletText}>{point}</Text>
              </View>
            ))}
          </View>
        )}

        <View style={{ height: 40 }} />
      </ScrollView>
    </View>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1, backgroundColor: Colors.background },
  centered: { flex: 1, justifyContent: 'center', alignItems: 'center', backgroundColor: Colors.background },
  header: {
    backgroundColor: Colors.primary, paddingTop: 50, paddingBottom: 14,
    paddingHorizontal: Spacing.lg, flexDirection: 'row',
    alignItems: 'center', justifyContent: 'space-between', ...Shadow.header,
  },
  headerTitle: { color: Colors.textWhite, fontSize: FontSize.lg, fontWeight: '600' },
  content: { padding: Spacing.lg },
  card: {
    backgroundColor: Colors.white, borderRadius: BorderRadius.xl,
    padding: Spacing.lg, marginBottom: Spacing.md,
  },
  cardTitle: {
    fontSize: FontSize.lg, fontWeight: '700', color: Colors.textPrimary,
    marginBottom: Spacing.md,
  },
  infoRow: {
    flexDirection: 'row', alignItems: 'center', gap: Spacing.sm,
    paddingVertical: Spacing.xs,
  },
  infoText: { fontSize: FontSize.md, color: Colors.textPrimary },
  summaryBox: {
    backgroundColor: Colors.primarySurface, padding: Spacing.lg,
    borderRadius: BorderRadius.md, borderLeftWidth: 4, borderLeftColor: Colors.primary,
  },
  summaryText: { fontSize: FontSize.md, color: Colors.textPrimary, lineHeight: 24, fontStyle: 'italic' },
  nextRecommend: {
    marginTop: Spacing.md, fontSize: FontSize.md, color: Colors.textSecondary, lineHeight: 22,
  },
  bulletRow: {
    flexDirection: 'row', alignItems: 'flex-start',
    gap: Spacing.sm, paddingVertical: Spacing.xs,
  },
  bullet: {
    width: 6, height: 6, borderRadius: 3, backgroundColor: Colors.accent,
    marginTop: 8,
  },
  bulletText: { fontSize: FontSize.md, color: Colors.textPrimary, lineHeight: 22, flex: 1 },
  errorText: {
    fontSize: FontSize.md, color: Colors.danger,
    marginBottom: Spacing.lg, paddingHorizontal: Spacing.xl, textAlign: 'center',
  },
  retryBtn: {
    backgroundColor: Colors.primary, borderRadius: BorderRadius.md,
    paddingHorizontal: Spacing.xl, paddingVertical: Spacing.sm,
  },
  retryText: { color: Colors.textWhite, fontSize: FontSize.md, fontWeight: '600' },
  actionsRow: {
    flexDirection: 'row', gap: Spacing.md, marginBottom: Spacing.md,
  },
  actionBtn: {
    flex: 1, flexDirection: 'row', alignItems: 'center', justifyContent: 'center',
    gap: Spacing.sm, paddingVertical: 14, borderRadius: BorderRadius.xl,
  },
  resumeBtn: { backgroundColor: Colors.primary },
  cancelBtn: { backgroundColor: Colors.white, borderWidth: 1, borderColor: Colors.danger },
  resumeText: { color: Colors.textWhite, fontSize: FontSize.md, fontWeight: '600' },
  cancelText: { color: Colors.danger, fontSize: FontSize.md, fontWeight: '600' },
});
