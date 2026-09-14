/**
 * 收藏历史（二期 I 医生端，复用 /api/v1/favorites 既有端点）：
 *   - 展示本人收藏的问答快照（问题/回答）
 *   - 支持取消收藏（DELETE /api/v1/favorites/{id}）
 *
 * 样式令牌照 theme.ts，列表卡片范式照 MyTwinsScreen。
 */
import React, { useCallback, useState } from 'react';
import {
  ActivityIndicator,
  Alert,
  FlatList,
  RefreshControl,
  StyleSheet,
  Text,
  TouchableOpacity,
  View,
} from 'react-native';
import { useFocusEffect } from '@react-navigation/native';
import Icon, { ActionIcons } from '../../components/Icon';
import { favoritesAPI } from '../../api/favorites';
import type { FavoriteItem } from '../../types';
import { BorderRadius, Colors, FontSize, Shadow, Spacing } from '../../constants/theme';

export default function FavoritesScreen() {
  const [items, setItems] = useState<FavoriteItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [error, setError] = useState('');
  const [removingId, setRemovingId] = useState<number | null>(null);

  const load = useCallback(async () => {
    setError('');
    try {
      const res = await favoritesAPI.listFavorites();
      setItems(Array.isArray(res?.items) ? res.items : []);
    } catch (e: any) {
      setError(e?.message || '收藏加载失败，请检查网络');
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

  const handleRemove = (item: FavoriteItem) => {
    Alert.alert('取消收藏', '确定取消收藏这条问答吗？', [
      { text: '取消', style: 'cancel' },
      {
        text: '取消收藏',
        style: 'destructive',
        onPress: async () => {
          if (removingId !== null) return;
          setRemovingId(item.id);
          try {
            await favoritesAPI.removeFavorite(item.id);
            setItems((prev) => prev.filter((it) => it.id !== item.id));
          } catch (e: any) {
            Alert.alert('操作失败', e?.message || '请稍后重试');
          } finally {
            setRemovingId(null);
          }
        },
      },
    ]);
  };

  const renderItem = ({ item }: { item: FavoriteItem }) => {
    const busy = removingId === item.id;
    return (
      <View style={[styles.card, Shadow.card]}>
        <View style={styles.qRow}>
          <Icon name={ActionIcons.help} size={16} color={Colors.primary} />
          <Text style={styles.question} numberOfLines={3}>
            {item.question || '（无问题）'}
          </Text>
        </View>
        <Text style={styles.answer} numberOfLines={4}>
          {item.answer || '（无回答）'}
        </Text>
        <View style={styles.footer}>
          <Text style={styles.meta}>收藏于 {item.created_at ? item.created_at.slice(0, 10) : '—'}</Text>
          <TouchableOpacity
            style={[styles.removeBtn, busy && { opacity: 0.6 }]}
            onPress={() => handleRemove(item)}
            disabled={busy}
            activeOpacity={0.7}
          >
            {busy ? (
              <ActivityIndicator size="small" color={Colors.danger} />
            ) : (
              <Text style={styles.removeText}>取消收藏</Text>
            )}
          </TouchableOpacity>
        </View>
      </View>
    );
  };

  if (loading) {
    return (
      <View style={styles.centered}>
        <ActivityIndicator size="large" color={Colors.primary} />
        <Text style={styles.loadingText}>加载收藏...</Text>
      </View>
    );
  }

  return (
    <View style={styles.container}>
      <View style={styles.header}>
        <Text style={styles.headerTitle}>收藏历史</Text>
        <Text style={styles.headerSubtitle}>本人收藏的问答</Text>
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
            <Icon name={ActionIcons.star} size={48} color={Colors.textHint} />
            <Text style={styles.emptyTitle}>{error || '暂无收藏'}</Text>
            <Text style={styles.emptyDesc}>在分身对话中，点击回答下方的「收藏」即可保存有价值的问答</Text>
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
  },
  qRow: { flexDirection: 'row', alignItems: 'flex-start', gap: Spacing.sm },
  question: { flex: 1, fontSize: FontSize.md, fontWeight: '600', color: Colors.textPrimary },
  answer: {
    fontSize: FontSize.sm,
    color: Colors.textSecondary,
    lineHeight: 20,
    marginTop: Spacing.sm,
  },
  footer: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    marginTop: Spacing.md,
    paddingTop: Spacing.sm,
    borderTopWidth: StyleSheet.hairlineWidth,
    borderTopColor: Colors.divider,
  },
  meta: { fontSize: FontSize.xs, color: Colors.textHint },
  removeBtn: { paddingHorizontal: Spacing.sm, paddingVertical: Spacing.xs },
  removeText: { fontSize: FontSize.xs, color: Colors.danger, fontWeight: '600' },
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
