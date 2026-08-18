/**
 * 夜间简报列表页 —— 展示每晚生成的医生问答简报（twin_name / 日期 / status）。
 * 临床精准风
 */
import React, { useEffect, useState, useCallback } from 'react';
import {
  View, Text, StyleSheet, FlatList, TouchableOpacity,
  ActivityIndicator, RefreshControl,
} from 'react-native';
import { useNavigation } from '@react-navigation/native';
import type { NativeStackNavigationProp } from '@react-navigation/native-stack';
import Icon from '../../components/Icon';
import EmptyState from '../../components/EmptyState';
import { briefingAPI } from '../../api/briefing';
import type { NightlyBriefing } from '../../types';
import { Colors, FontSize, Spacing, BorderRadius, Shadow } from '../../constants/theme';
import type { RootStackParamList } from '../../navigation/types';

type Nav = NativeStackNavigationProp<RootStackParamList>;

/** 后端 NightlyBriefing.status 枚举（生成器只写 ready） */
const STATUS_LABELS: Record<string, { label: string; color: string; bg: string }> = {
  ready: { label: '已生成', color: Colors.success, bg: Colors.successLight },
  generating: { label: '生成中', color: Colors.warning, bg: Colors.warningLight },
  failed: { label: '生成失败', color: Colors.danger, bg: Colors.dangerLight },
};

export default function BriefingListScreen() {
  const navigation = useNavigation<Nav>();
  const [items, setItems] = useState<NightlyBriefing[]>([]);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [error, setError] = useState('');

  const loadList = useCallback(async () => {
    try {
      const res = await briefingAPI.list(1, 100);
      setItems(Array.isArray(res?.items) ? res.items : []);
      setError('');
    } catch (e: any) {
      setError(e?.message || '简报加载失败，请检查网络');
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { loadList(); }, [loadList]);

  const onRefresh = async () => {
    setRefreshing(true);
    await loadList();
    setRefreshing(false);
  };

  const renderItem = ({ item }: { item: NightlyBriefing }) => {
    const st = STATUS_LABELS[item.status] || { label: item.status || '未知', color: Colors.textHint, bg: Colors.border };
    return (
      <TouchableOpacity
        style={[styles.card, Shadow.card]}
        activeOpacity={0.7}
        onPress={() => navigation.navigate('BriefingDetail', { briefingId: item.id })}
      >
        <View style={styles.cardHead}>
          <View style={styles.twinBadge}>
            <Icon name="weather-night" size={14} color={Colors.primary} />
            <Text style={styles.twinText}>{item.twin_name || `分身 #${item.specialist_id}`}</Text>
          </View>
          <View style={[styles.statusBadge, { backgroundColor: st.bg }]}>
            <Text style={[styles.statusText, { color: st.color }]}>{st.label}</Text>
          </View>
        </View>
        <View style={styles.cardMeta}>
          <Icon name="calendar-outline" size={12} color={Colors.textHint} />
          <Text style={styles.metaText}>{item.briefing_date || '日期未知'}</Text>
        </View>
        <View style={styles.cardFooter}>
          <Text style={styles.tapHint}>点击查看详情</Text>
          <Icon name="chevron-right" size={16} color={Colors.textHint} />
        </View>
      </TouchableOpacity>
    );
  };

  return (
    <View style={styles.container}>
      <View style={styles.header}>
        <TouchableOpacity onPress={() => navigation.goBack()} style={styles.headerBtn}>
          <Icon name="chevron-left" size={22} color={Colors.textWhite} />
        </TouchableOpacity>
        <Text style={styles.headerTitle}>夜间简报</Text>
        <View style={{ width: 24 }} />
      </View>

      {loading ? (
        <View style={styles.centered}>
          <ActivityIndicator size="large" color={Colors.primary} />
        </View>
      ) : error && items.length === 0 ? (
        <View style={styles.centered}>
          <Text style={styles.errorText}>{error}</Text>
          <TouchableOpacity style={styles.retryBtn} onPress={loadList} activeOpacity={0.8}>
            <Text style={styles.retryText}>重试</Text>
          </TouchableOpacity>
        </View>
      ) : (
        <FlatList
          data={items}
          renderItem={renderItem}
          keyExtractor={(item) => String(item.id)}
          contentContainerStyle={[styles.list, items.length === 0 && styles.listEmpty]}
          showsVerticalScrollIndicator={false}
          refreshControl={
            <RefreshControl refreshing={refreshing} onRefresh={onRefresh} tintColor={Colors.primary} colors={[Colors.primary]} />
          }
          ListEmptyComponent={
            <EmptyState icon="weather-night" title="暂无简报" description="每日夜间生成的医生问答简报会出现在这里" />
          }
        />
      )}
    </View>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1, backgroundColor: Colors.background },
  centered: { flex: 1, justifyContent: 'center', alignItems: 'center' },
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
    backgroundColor: Colors.primary, paddingTop: 50, paddingBottom: 14,
    paddingHorizontal: Spacing.lg, flexDirection: 'row',
    alignItems: 'center', justifyContent: 'space-between', ...Shadow.header,
  },
  headerBtn: { padding: 4 },
  headerTitle: { color: Colors.textWhite, fontSize: FontSize.lg, fontWeight: '600' },
  list: { padding: Spacing.lg },
  listEmpty: { flexGrow: 1, justifyContent: 'center' },
  card: {
    backgroundColor: Colors.white, borderRadius: BorderRadius.xl,
    padding: Spacing.lg, marginBottom: Spacing.md,
  },
  cardHead: { flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center', marginBottom: Spacing.sm },
  twinBadge: { flexDirection: 'row', alignItems: 'center', gap: 6, flex: 1 },
  twinText: { fontSize: FontSize.md, color: Colors.textPrimary, fontWeight: '600' },
  statusBadge: { paddingHorizontal: 10, paddingVertical: 3, borderRadius: BorderRadius.full },
  statusText: { fontSize: 10, fontWeight: '600' },
  cardMeta: { flexDirection: 'row', alignItems: 'center', gap: 4, marginBottom: Spacing.sm },
  metaText: { fontSize: 11, color: Colors.textHint },
  cardFooter: {
    flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center',
    marginTop: Spacing.xs,
  },
  tapHint: { fontSize: 10, color: Colors.primary },
});
