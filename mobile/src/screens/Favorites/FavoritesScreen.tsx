/**
 * 我的收藏页 - 收藏的数字专员问答（后端 /api/v1/favorites 真实列表）
 * 临床精准风
 */
import React, { useEffect, useState, useCallback } from 'react';
import {
  View, Text, StyleSheet, FlatList, TouchableOpacity,
  ActivityIndicator, RefreshControl, Alert,
} from 'react-native';
import { useNavigation } from '@react-navigation/native';
import Icon from '../../components/Icon';
import EmptyState from '../../components/EmptyState';
import { specialistAPI } from '../../api/specialist';
import type { FavoriteItem } from '../../api/specialist';
import { Colors, FontSize, Spacing, BorderRadius, Shadow } from '../../constants/theme';

export default function FavoritesScreen() {
  const navigation = useNavigation();
  const [favorites, setFavorites] = useState<FavoriteItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [error, setError] = useState('');

  const loadFavorites = useCallback(async () => {
    try {
      const result = await specialistAPI.listFavorites({ page: 1, page_size: 100 });
      setFavorites(result.items || []);
      setError('');
    } catch (e: any) {
      setError(e?.message || '收藏加载失败，请检查网络');
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { loadFavorites(); }, [loadFavorites]);

  const onRefresh = async () => {
    setRefreshing(true);
    await loadFavorites();
    setRefreshing(false);
  };

  /** 取消收藏：确认后删除并刷新 */
  const handleRemove = (item: FavoriteItem) => {
    Alert.alert('取消收藏', `确认取消收藏「${item.question || '这条问答'}」？`, [
      { text: '再想想', style: 'cancel' },
      {
        text: '取消收藏',
        style: 'destructive',
        onPress: async () => {
          try {
            await specialistAPI.removeFavorite(item.id);
            setFavorites((prev) => prev.filter((f) => f.id !== item.id));
          } catch (e: any) {
            Alert.alert('操作失败', e?.message || '请稍后重试');
          }
        },
      },
    ]);
  };

  /** 查看完整问答 */
  const handleView = (item: FavoriteItem) => {
    Alert.alert(item.question || '收藏问答', item.answer || '（无回答内容）', [{ text: '关闭' }]);
  };

  const renderItem = ({ item }: { item: FavoriteItem }) => (
    <TouchableOpacity
      style={[styles.card, Shadow.card]}
      activeOpacity={0.7}
      onPress={() => handleView(item)}
    >
      <View style={styles.cardHead}>
        <View style={styles.specialistBadge}>
          <Icon name="account-tie" size={12} color={Colors.primary} />
          <Text style={styles.specialistText}>专员 #{item.specialist_id}</Text>
        </View>
        <TouchableOpacity
          style={styles.removeBtn}
          hitSlop={{ top: 8, bottom: 8, left: 8, right: 8 }}
          onPress={() => handleRemove(item)}
        >
          <Icon name="star" size={16} color={Colors.warning} />
        </TouchableOpacity>
      </View>
      <Text style={styles.question} numberOfLines={2}>{item.question || '（无问题）'}</Text>
      <Text style={styles.answer} numberOfLines={3}>{item.answer || '（无回答）'}</Text>
      <View style={styles.footer}>
        {item.created_at ? (
          <Text style={styles.dateText}>收藏于 {String(item.created_at).slice(0, 10)}</Text>
        ) : null}
        <Text style={styles.tapHint}>点击查看完整回答</Text>
      </View>
    </TouchableOpacity>
  );

  return (
    <View style={styles.container}>
      <View style={styles.header}>
        <TouchableOpacity onPress={() => navigation.goBack()} style={styles.headerBtn}>
          <Icon name="chevron-left" size={22} color={Colors.textWhite} />
        </TouchableOpacity>
        <Text style={styles.headerTitle}>我的收藏</Text>
        <View style={{ width: 24 }} />
      </View>

      {loading ? (
        <View style={styles.centered}>
          <ActivityIndicator size="large" color={Colors.primary} />
        </View>
      ) : error && favorites.length === 0 ? (
        <View style={styles.centered}>
          <Text style={styles.errorText}>{error}</Text>
          <TouchableOpacity style={styles.retryBtn} onPress={loadFavorites} activeOpacity={0.8}>
            <Text style={styles.retryText}>重试</Text>
          </TouchableOpacity>
        </View>
      ) : (
        <FlatList
          data={favorites}
          renderItem={renderItem}
          keyExtractor={(item) => String(item.id)}
          contentContainerStyle={[styles.list, favorites.length === 0 && styles.listEmpty]}
          showsVerticalScrollIndicator={false}
          refreshControl={
            <RefreshControl refreshing={refreshing} onRefresh={onRefresh} tintColor={Colors.primary} colors={[Colors.primary]} />
          }
          ListEmptyComponent={
            <EmptyState icon="star-outline" title="暂无收藏" description="在数字专员对话中点 ★ 收藏重要问答" />
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
  specialistBadge: { flexDirection: 'row', alignItems: 'center', gap: 4 },
  specialistText: { fontSize: 11, color: Colors.primary, fontWeight: '600' },
  removeBtn: { padding: 4 },
  question: { fontSize: FontSize.md, color: Colors.textPrimary, fontWeight: '600', lineHeight: 22 },
  answer: { fontSize: FontSize.sm, color: Colors.textSecondary, marginTop: 6, lineHeight: 20 },
  footer: {
    flexDirection: 'row', justifyContent: 'space-between',
    marginTop: Spacing.md, alignItems: 'center',
  },
  dateText: { fontSize: 10, color: Colors.textHint },
  tapHint: { fontSize: 10, color: Colors.primary },
});
