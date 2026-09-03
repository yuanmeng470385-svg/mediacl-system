/**
 * 我的分身 Tab（照 mobile SpecialistListScreen 列表卡片范式）：
 *   订阅列表卡片（名称/专员状态/订阅状态）+ 进入对话 + 屏蔽切换 + 添加分身入口
 */
import React, { useCallback, useEffect, useState } from 'react';
import {
  View,
  Text,
  StyleSheet,
  FlatList,
  TouchableOpacity,
  RefreshControl,
  ActivityIndicator,
  Alert,
} from 'react-native';
import { useNavigation, useFocusEffect } from '@react-navigation/native';
import type { NativeStackNavigationProp } from '@react-navigation/native-stack';
import Icon, { ActionIcons, FeatureIcons } from '../../components/Icon';
import { twinAPI } from '../../api/twin';
import { Colors, FontSize, Spacing, BorderRadius, Shadow } from '../../constants/theme';
import type { TwinSubscriptionItem } from '../../types';
import type { RootStackParamList } from '../../navigation/types';

type Nav = NativeStackNavigationProp<RootStackParamList>;

const avatarColors = ['#0D3B66', '#1565C0', '#00ACC1', '#2E7D32', '#C62828'];

/** 专员状态 → 展示文案/样式（后端枚举 draft/active/disabled/paused/frozen） */
const TWIN_STATUS_CONFIG: Record<string, { label: string; bg: string; color: string }> = {
  active: { label: '正常', bg: '#dcfce7', color: Colors.success },
  draft: { label: '草稿', bg: '#fef3c7', color: Colors.warning },
  disabled: { label: '已停用', bg: '#f3f4f6', color: Colors.textHint },
  paused: { label: '代表已暂停', bg: '#fef3c7', color: Colors.warning },
  frozen: { label: '合规冻结中', bg: Colors.dangerLight, color: Colors.danger },
};
const TWIN_STATUS_FALLBACK = { label: '暂不可用', bg: '#f3f4f6', color: Colors.textHint };

export default function MyTwinsScreen() {
  const navigation = useNavigation<Nav>();
  const [items, setItems] = useState<TwinSubscriptionItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [error, setError] = useState('');
  const [togglingId, setTogglingId] = useState<number | null>(null);

  const load = useCallback(async () => {
    setError('');
    try {
      const list = await twinAPI.list();
      setItems(Array.isArray(list) ? list : []);
    } catch (e: any) {
      setError(e?.message || '分身列表加载失败，请检查网络');
      setItems([]);
    } finally {
      setLoading(false);
    }
  }, []);

  // 每次回到本 Tab 都刷新：屏蔽/激活状态在别的页面会变
  useFocusEffect(
    useCallback(() => {
      load();
    }, [load])
  );

  const onRefresh = async () => {
    setRefreshing(true);
    await load();
    setRefreshing(false);
  };

  const handleToggle = async (item: TwinSubscriptionItem) => {
    if (togglingId !== null) return;
    const next: 'subscribed' | 'blocked' = item.status === 'blocked' ? 'subscribed' : 'blocked';
    setTogglingId(item.twin_id);
    try {
      await twinAPI.toggle(item.twin_id, next);
      setItems((prev) =>
        prev.map((it) => (it.twin_id === item.twin_id ? { ...it, status: next } : it))
      );
    } catch (e: any) {
      Alert.alert('操作失败', e?.message || '请稍后重试');
    } finally {
      setTogglingId(null);
    }
  };

  const getAvatarColor = (id: number) => avatarColors[id % avatarColors.length];

  const renderItem = ({ item }: { item: TwinSubscriptionItem }) => {
    const name = item.twin_name || `数字员工 #${item.twin_id}`;
    const initials = name.slice(0, 2);
    const twinStatus =
      TWIN_STATUS_CONFIG[item.twin_status || ''] || TWIN_STATUS_FALLBACK;
    const blocked = item.status === 'blocked';
    const twinActive = item.twin_status === 'active';
    const busy = togglingId === item.twin_id;

    return (
      <View style={[styles.card, Shadow.card, blocked && styles.cardBlocked]}>
        <View style={[styles.avatar, { backgroundColor: getAvatarColor(item.twin_id) }]}>
          <Text style={styles.avatarText}>{initials}</Text>
          {twinActive && !blocked && <View style={styles.onlineDot} />}
        </View>

        <View style={styles.info}>
          <View style={styles.nameRow}>
            <Text style={styles.name}>{name}</Text>
            <View style={[styles.statusBadge, { backgroundColor: twinStatus.bg }]}>
              <Text style={[styles.statusText, { color: twinStatus.color }]}>
                {twinStatus.label}
              </Text>
            </View>
          </View>
          <Text style={styles.subStatus}>{blocked ? '已屏蔽' : '已订阅'}</Text>

          <View style={styles.actions}>
            <TouchableOpacity
              style={[styles.chatBtn, (!twinActive || blocked) && styles.chatBtnDisabled]}
              onPress={() =>
                twinActive &&
                !blocked &&
                navigation.navigate('TwinChat', { twinId: item.twin_id, twinName: name })
              }
              disabled={!twinActive || blocked}
              activeOpacity={0.7}
            >
              <Text style={styles.chatBtnText}>{blocked ? '已屏蔽' : '进入对话'}</Text>
            </TouchableOpacity>

            <TouchableOpacity
              style={[styles.toggleBtn, busy && { opacity: 0.6 }]}
              onPress={() => handleToggle(item)}
              disabled={busy}
              activeOpacity={0.7}
            >
              {busy ? (
                <ActivityIndicator size="small" color={Colors.primary} />
              ) : (
                <Text style={styles.toggleBtnText}>
                  {blocked ? '取消屏蔽' : '屏蔽'}
                </Text>
              )}
            </TouchableOpacity>
          </View>
        </View>
      </View>
    );
  };

  if (loading) {
    return (
      <View style={styles.centered}>
        <ActivityIndicator size="large" color={Colors.primary} />
        <Text style={styles.loadingText}>加载分身列表...</Text>
      </View>
    );
  }

  return (
    <View style={styles.container}>
      <View style={styles.header}>
        <Text style={styles.headerTitle}>我的分身</Text>
        <Text style={styles.headerSubtitle}>已订阅的数字员工列表</Text>
      </View>

      <FlatList
        data={items}
        renderItem={renderItem}
        keyExtractor={(item) => item.twin_id.toString()}
        contentContainerStyle={styles.list}
        refreshControl={
          <RefreshControl refreshing={refreshing} onRefresh={onRefresh} colors={[Colors.primary]} />
        }
        ListEmptyComponent={
          <View style={styles.empty}>
            <Icon name={FeatureIcons.specialist} size={48} color={Colors.textHint} />
            <Text style={styles.emptyTitle}>{error || '暂无分身'}</Text>
            <Text style={styles.emptyDesc}>通过医药代表分享的链接添加数字员工分身</Text>
            {error ? (
              <TouchableOpacity style={styles.retryBtn} onPress={load} activeOpacity={0.8}>
                <Text style={styles.retryText}>重试</Text>
              </TouchableOpacity>
            ) : (
              <TouchableOpacity
                style={styles.retryBtn}
                onPress={() => navigation.navigate('TwinActivate')}
                activeOpacity={0.8}
              >
                <Text style={styles.retryText}>添加分身</Text>
              </TouchableOpacity>
            )}
          </View>
        }
        ListFooterComponent={
          items.length > 0 ? (
            <TouchableOpacity
              style={styles.addRow}
              onPress={() => navigation.navigate('TwinActivate')}
              activeOpacity={0.7}
            >
              <Icon name={ActionIcons.add} size={18} color={Colors.primary} />
              <Text style={styles.addRowText}>添加分身</Text>
            </TouchableOpacity>
          ) : null
        }
      />
    </View>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1, backgroundColor: Colors.background },
  centered: { flex: 1, justifyContent: 'center', alignItems: 'center' },
  loadingText: { marginTop: Spacing.md, color: Colors.textHint, fontSize: FontSize.sm },
  header: {
    backgroundColor: Colors.primary,
    paddingHorizontal: Spacing.xl,
    paddingTop: 52,
    paddingBottom: Spacing.xl,
  },
  headerTitle: { color: Colors.textWhite, fontSize: FontSize.xl, fontWeight: '700' },
  headerSubtitle: {
    color: 'rgba(255,255,255,0.7)',
    fontSize: FontSize.sm,
    marginTop: 4,
  },
  list: { padding: Spacing.lg },
  card: {
    backgroundColor: Colors.white,
    borderRadius: BorderRadius.lg,
    padding: Spacing.lg,
    marginBottom: Spacing.md,
    flexDirection: 'row',
    gap: Spacing.lg,
  },
  cardBlocked: { opacity: 0.55 },
  avatar: {
    width: 56,
    height: 56,
    borderRadius: 28,
    alignItems: 'center',
    justifyContent: 'center',
  },
  avatarText: { color: Colors.textWhite, fontSize: FontSize.lg, fontWeight: '700' },
  onlineDot: {
    position: 'absolute',
    bottom: 2,
    right: 2,
    width: 12,
    height: 12,
    borderRadius: 6,
    backgroundColor: Colors.success,
    borderWidth: 2,
    borderColor: Colors.white,
  },
  info: { flex: 1, gap: 4 },
  nameRow: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
  },
  name: { fontSize: FontSize.lg, fontWeight: '600', color: Colors.textPrimary },
  statusBadge: {
    paddingHorizontal: 8,
    paddingVertical: 2,
    borderRadius: BorderRadius.full,
  },
  statusText: { fontSize: FontSize.xs, fontWeight: '600' },
  subStatus: { fontSize: FontSize.sm, color: Colors.textSecondary },
  actions: { flexDirection: 'row', gap: Spacing.sm, marginTop: Spacing.sm },
  chatBtn: {
    backgroundColor: Colors.primary,
    borderRadius: BorderRadius.full,
    paddingVertical: 8,
    paddingHorizontal: Spacing.xl,
  },
  chatBtnDisabled: { backgroundColor: Colors.border },
  chatBtnText: { color: Colors.textWhite, fontSize: FontSize.sm, fontWeight: '600' },
  toggleBtn: {
    borderWidth: 1,
    borderColor: Colors.primary,
    borderRadius: BorderRadius.full,
    paddingVertical: 8,
    paddingHorizontal: Spacing.lg,
    justifyContent: 'center',
    minWidth: 76,
    alignItems: 'center',
  },
  toggleBtnText: { color: Colors.primary, fontSize: FontSize.sm, fontWeight: '600' },
  empty: { alignItems: 'center', paddingTop: Spacing.huge },
  emptyTitle: { fontSize: FontSize.md, fontWeight: '600', color: Colors.textSecondary, marginTop: Spacing.md },
  emptyDesc: {
    fontSize: FontSize.sm,
    color: Colors.textHint,
    marginTop: Spacing.xs,
    textAlign: 'center',
  },
  retryBtn: {
    backgroundColor: Colors.primary,
    borderRadius: BorderRadius.md,
    paddingHorizontal: Spacing.xl,
    paddingVertical: Spacing.sm,
    marginTop: Spacing.lg,
  },
  retryText: { color: Colors.textWhite, fontSize: FontSize.md, fontWeight: '600' },
  addRow: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'center',
    gap: Spacing.xs,
    paddingVertical: Spacing.md,
  },
  addRowText: { color: Colors.primary, fontSize: FontSize.sm, fontWeight: '600' },
});
