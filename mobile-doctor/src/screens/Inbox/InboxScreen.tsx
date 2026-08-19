/**
 * 学术卡片收件箱（二期 G 医生端）：
 *   - listInbox 分页列表：卡片标题 / 代表 / 阅读状态徽标，点击进详情
 *   - 样式令牌照 theme.ts，列表卡片范式照 MyTwinsScreen
 */
import React, { useCallback, useState } from 'react';
import {
  View,
  Text,
  StyleSheet,
  FlatList,
  TouchableOpacity,
  RefreshControl,
  ActivityIndicator,
} from 'react-native';
import { useFocusEffect, useNavigation } from '@react-navigation/native';
import type { NativeStackNavigationProp } from '@react-navigation/native-stack';
import Icon, { FeatureIcons } from '../../components/Icon';
import { inboxAPI } from '../../api/inbox';
import { Colors, FontSize, Spacing, BorderRadius, Shadow } from '../../constants/theme';
import type { CardPushRecord, CardReadStatus } from '../../types';
import type { RootStackParamList } from '../../navigation/types';

type Nav = NativeStackNavigationProp<RootStackParamList>;

/** 阅读状态 → 展示文案/样式（后端枚举 unread/read/favorited/forwarded） */
const READ_STATUS_CONFIG: Record<CardReadStatus, { label: string; bg: string; color: string }> = {
  unread: { label: '未读', bg: Colors.warningLight, color: Colors.warning },
  read: { label: '已读', bg: Colors.backgroundAlt, color: Colors.textSecondary },
  favorited: { label: '已收藏', bg: Colors.primarySurface, color: Colors.primary },
  forwarded: { label: '已转发', bg: Colors.infoLight, color: Colors.info },
};
const READ_STATUS_FALLBACK = { label: '未读', bg: Colors.backgroundAlt, color: Colors.textHint };

export default function InboxScreen() {
  const navigation = useNavigation<Nav>();
  const [items, setItems] = useState<CardPushRecord[]>([]);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [error, setError] = useState('');

  const load = useCallback(async () => {
    setError('');
    try {
      const res = await inboxAPI.listInbox();
      setItems(Array.isArray(res?.items) ? res.items : []);
    } catch (e: any) {
      setError(e?.message || '收件箱加载失败，请检查网络');
      setItems([]);
    } finally {
      setLoading(false);
    }
  }, []);

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

  const renderItem = ({ item }: { item: CardPushRecord }) => {
    const title = item.card?.title || `学术卡片 #${item.id}`;
    const status = READ_STATUS_CONFIG[item.read_status] || READ_STATUS_FALLBACK;

    return (
      <TouchableOpacity
        style={[styles.card, Shadow.card]}
        onPress={() => navigation.navigate('CardDetail', { pushId: item.id })}
        activeOpacity={0.7}
      >
        <View style={styles.iconBox}>
          <Icon name={FeatureIcons.content} size={20} color={Colors.primary} />
        </View>
        <View style={styles.info}>
          <View style={styles.titleRow}>
            <Text style={styles.title} numberOfLines={2}>
              {title}
            </Text>
            <View style={[styles.statusBadge, { backgroundColor: status.bg }]}>
              <Text style={[styles.statusText, { color: status.color }]}>{status.label}</Text>
            </View>
          </View>
          <Text style={styles.meta}>医药代表 #{item.representative_id}</Text>
        </View>
        <Icon name="chevron-right" size={20} color={Colors.textHint} />
      </TouchableOpacity>
    );
  };

  if (loading) {
    return (
      <View style={styles.centered}>
        <ActivityIndicator size="large" color={Colors.primary} />
        <Text style={styles.loadingText}>加载学术卡片...</Text>
      </View>
    );
  }

  return (
    <View style={styles.container}>
      <View style={styles.header}>
        <Text style={styles.headerTitle}>学术卡片</Text>
        <Text style={styles.headerSubtitle}>医药代表推送的学术内容</Text>
      </View>

      <FlatList
        data={items}
        renderItem={renderItem}
        keyExtractor={(item) => item.id.toString()}
        contentContainerStyle={styles.list}
        refreshControl={
          <RefreshControl refreshing={refreshing} onRefresh={onRefresh} colors={[Colors.primary]} />
        }
        ListEmptyComponent={
          <View style={styles.empty}>
            <Icon name={FeatureIcons.content} size={48} color={Colors.textHint} />
            <Text style={styles.emptyTitle}>{error || '暂无学术卡片'}</Text>
            <Text style={styles.emptyDesc}>医药代表推送的学术内容会出现在这里</Text>
            {error ? (
              <TouchableOpacity style={styles.retryBtn} onPress={load} activeOpacity={0.8}>
                <Text style={styles.retryText}>重试</Text>
              </TouchableOpacity>
            ) : null}
          </View>
        }
      />
    </View>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1, backgroundColor: Colors.background },
  centered: { flex: 1, justifyContent: 'center', alignItems: 'center', backgroundColor: Colors.background },
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
    alignItems: 'center',
    gap: Spacing.md,
  },
  iconBox: {
    width: 40,
    height: 40,
    borderRadius: 10,
    backgroundColor: Colors.primarySurface,
    alignItems: 'center',
    justifyContent: 'center',
  },
  info: { flex: 1, gap: 4 },
  titleRow: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: Spacing.sm,
  },
  title: {
    flex: 1,
    fontSize: FontSize.md,
    fontWeight: '600',
    color: Colors.textPrimary,
  },
  statusBadge: {
    paddingHorizontal: 8,
    paddingVertical: 2,
    borderRadius: BorderRadius.full,
  },
  statusText: { fontSize: FontSize.xs, fontWeight: '600' },
  meta: { fontSize: FontSize.xs, color: Colors.textHint },
  empty: { alignItems: 'center', paddingTop: Spacing.huge },
  emptyTitle: {
    fontSize: FontSize.md,
    fontWeight: '600',
    color: Colors.textSecondary,
    marginTop: Spacing.md,
  },
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
});
