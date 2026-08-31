/**
 * 我的 Skill（三期 J）：展示本人发布的 Skill 列表。
 * 每条：名称 + 审核状态徽标 + 热度(heat) + 好评率(approval_rate)，
 * 下架（off_shelf_status === 'off_shelved'）时红字提示下架原因。
 * 后端 mine 接口不返回 content/skill_weights，本屏仅展示元数据。
 */
import React, { useCallback, useEffect, useState } from 'react';
import {
  FlatList, RefreshControl, StyleSheet, Text, TouchableOpacity, View,
} from 'react-native';
import { useNavigation } from '@react-navigation/native';
import type { NativeStackNavigationProp } from '@react-navigation/native-stack';
import Icon from '../../components/Icon';
import EmptyState from '../../components/EmptyState';
import { plazaAPI } from '../../api/practice';
import type { RootStackParamList } from '../../navigation/types';
import { BorderRadius, Colors, FontSize, Shadow, Spacing } from '../../constants/theme';

type Nav = NativeStackNavigationProp<RootStackParamList>;

interface MySkillItem {
  id: number;
  name?: string;
  audit_status?: string;
  heat?: number;
  approval_rate?: number | null;
  off_shelf_status?: string;
  off_shelf_reason?: string;
}

const AUDIT_BADGE: Record<string, { label: string; color: string; bg: string }> = {
  pending: { label: '审核中', color: Colors.warning, bg: Colors.warningLight },
  approved: { label: '已通过', color: Colors.success, bg: Colors.successLight },
  rejected: { label: '已驳回', color: Colors.danger, bg: Colors.dangerLight },
};

export default function MySkillListScreen() {
  const navigation = useNavigation<Nav>();
  const [items, setItems] = useState<MySkillItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [error, setError] = useState('');

  const load = useCallback(async () => {
    try {
      const res = await plazaAPI.mySkills();
      setItems(Array.isArray(res?.items) ? res.items : []);
      setError('');
    } catch (err: any) {
      setError(err?.message || '加载失败，请检查网络');
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  const onRefresh = async () => {
    setRefreshing(true);
    await load();
    setRefreshing(false);
  };

  const formatRate = (rate?: number | null) => {
    if (rate == null) return '--';
    return `${Math.round(rate * 100)}%`;
  };

  const renderItem = ({ item }: { item: MySkillItem }) => {
    const badge = AUDIT_BADGE[item.audit_status || ''] || {
      label: item.audit_status || '未知',
      color: Colors.textHint,
      bg: Colors.border,
    };
    const offShelved = item.off_shelf_status === 'off_shelved';
    return (
      <View style={[styles.card, Shadow.card]}>
        <View style={styles.cardHead}>
          <View style={styles.iconBox}>
            <Icon name="creation" size={18} color={Colors.primary} />
          </View>
          <Text style={styles.name} numberOfLines={1}>{item.name || `Skill #${item.id}`}</Text>
          <View style={[styles.statusBadge, { backgroundColor: badge.bg }]}>
            <Text style={[styles.statusText, { color: badge.color }]}>{badge.label}</Text>
          </View>
        </View>

        <View style={styles.metaRow}>
          <View style={styles.metaItem}>
            <Icon name="fire" size={14} color={Colors.warning} />
            <Text style={styles.metaText}>热度 {item.heat ?? 0}</Text>
          </View>
          <View style={styles.metaItem}>
            <Icon name="thumb-up-outline" size={14} color={Colors.accent} />
            <Text style={styles.metaText}>好评率 {formatRate(item.approval_rate)}</Text>
          </View>
        </View>

        {offShelved && (
          <View style={styles.offShelfBox}>
            <Icon name="alert-circle-outline" size={14} color={Colors.danger} />
            <Text style={styles.offShelfText}>
              已下架{item.off_shelf_reason ? `：${item.off_shelf_reason}` : ''}
            </Text>
          </View>
        )}
      </View>
    );
  };

  return (
    <View style={styles.container}>
      <View style={styles.header}>
        <TouchableOpacity onPress={() => navigation.goBack()} style={styles.headerBtn}>
          <Icon name="chevron-left" size={22} color={Colors.textWhite} />
        </TouchableOpacity>
        <Text style={styles.headerTitle}>我的 Skill</Text>
        <TouchableOpacity onPress={load} style={styles.headerBtn}>
          <Icon name="refresh" size={22} color={Colors.textWhite} />
        </TouchableOpacity>
      </View>

      {loading ? (
        <View style={styles.centered}>
          <Text style={styles.loadingText}>加载中…</Text>
        </View>
      ) : error && items.length === 0 ? (
        <View style={styles.centered}>
          <Text style={styles.errorText}>{error}</Text>
          <TouchableOpacity style={styles.retryBtn} onPress={load} activeOpacity={0.8}>
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
            <EmptyState
              icon="creation"
              title="暂无 Skill"
              description="发布 Skill 后，审核通过即可上架广场"
              actionLabel="从陪练对话生成"
              onAction={() => navigation.navigate('SkillExtract')}
            />
          }
        />
      )}
    </View>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1, backgroundColor: Colors.background },
  header: {
    backgroundColor: Colors.primary, paddingTop: 50, paddingBottom: 14,
    paddingHorizontal: Spacing.lg, flexDirection: 'row',
    alignItems: 'center', justifyContent: 'space-between', ...Shadow.header,
  },
  headerBtn: { padding: 4 },
  headerTitle: { color: Colors.textWhite, fontSize: FontSize.lg, fontWeight: '600' },
  centered: { flex: 1, justifyContent: 'center', alignItems: 'center' },
  loadingText: { fontSize: FontSize.sm, color: Colors.textHint },
  errorText: {
    fontSize: FontSize.md, color: Colors.danger,
    marginBottom: Spacing.lg, paddingHorizontal: Spacing.xl, textAlign: 'center',
  },
  retryBtn: {
    backgroundColor: Colors.primary, borderRadius: BorderRadius.md,
    paddingHorizontal: Spacing.xl, paddingVertical: Spacing.sm,
  },
  retryText: { color: Colors.textWhite, fontSize: FontSize.md, fontWeight: '600' },
  list: { padding: Spacing.md },
  listEmpty: { flexGrow: 1, justifyContent: 'center' },
  card: {
    backgroundColor: Colors.white, borderRadius: BorderRadius.md,
    padding: Spacing.lg, marginBottom: Spacing.md,
  },
  cardHead: { flexDirection: 'row', alignItems: 'center', gap: Spacing.sm },
  iconBox: {
    width: 36, height: 36, borderRadius: 10,
    backgroundColor: Colors.primarySurface, alignItems: 'center', justifyContent: 'center',
  },
  name: { flex: 1, fontSize: FontSize.md, fontWeight: '600', color: Colors.textPrimary },
  statusBadge: { paddingHorizontal: 10, paddingVertical: 3, borderRadius: BorderRadius.full },
  statusText: { fontSize: 10, fontWeight: '600' },
  metaRow: { flexDirection: 'row', alignItems: 'center', gap: Spacing.xl, marginTop: Spacing.md },
  metaItem: { flexDirection: 'row', alignItems: 'center', gap: 4 },
  metaText: { fontSize: FontSize.xs, color: Colors.textSecondary },
  offShelfBox: {
    flexDirection: 'row', alignItems: 'center', gap: 4,
    backgroundColor: Colors.dangerLight, borderRadius: BorderRadius.sm,
    paddingHorizontal: Spacing.sm, paddingVertical: Spacing.xs, marginTop: Spacing.sm,
  },
  offShelfText: { fontSize: FontSize.xs, color: Colors.danger, flex: 1 },
});
