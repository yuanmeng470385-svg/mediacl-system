/**
 * 学术卡片列表（二期 G）—— 展示本人已生成的学术卡片（标题/结论/要点/生成时间/合规状态）。
 * 样式参照 BriefingListScreen（临床精准风）。
 */
import React, { useCallback, useEffect, useState } from 'react';
import {
  ActivityIndicator, FlatList, RefreshControl, StyleSheet, Text, TouchableOpacity, View,
} from 'react-native';
import { useNavigation } from '@react-navigation/native';
import type { NativeStackNavigationProp } from '@react-navigation/native-stack';
import Icon from '../../components/Icon';
import EmptyState from '../../components/EmptyState';
import { academicAPI } from '../../api/academic';
import type { AcademicCard } from '../../types';
import { BorderRadius, Colors, FontSize, Shadow, Spacing } from '../../constants/theme';
import type { RootStackParamList } from '../../navigation/types';

type Nav = NativeStackNavigationProp<RootStackParamList>;

export default function CardListScreen() {
  const navigation = useNavigation<Nav>();
  const [items, setItems] = useState<AcademicCard[]>([]);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [error, setError] = useState('');

  const loadList = useCallback(async () => {
    try {
      const res = await academicAPI.listMyCards();
      setItems(Array.isArray(res?.items) ? res.items : []);
      setError('');
    } catch (e: any) {
      setError(e?.message || '卡片加载失败，请检查网络');
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

  const renderItem = ({ item }: { item: AcademicCard }) => {
    const passed = item.compliance_status === 'passed';
    return (
      <View style={[styles.card, Shadow.card]}>
        <View style={styles.cardHead}>
          <View style={styles.titleBox}>
            <Icon name="file-document-outline" size={16} color={Colors.primary} />
            <Text style={styles.titleText} numberOfLines={2}>{item.title}</Text>
          </View>
          <View style={[styles.statusBadge, { backgroundColor: passed ? Colors.successLight : Colors.warningLight }]}>
            <Text style={[styles.statusText, { color: passed ? Colors.success : Colors.warning }]}>
              {passed ? '已过审' : item.compliance_status || '待审'}
            </Text>
          </View>
        </View>
        {item.content?.conclusion ? (
          <Text style={styles.conclusion} numberOfLines={3}>{item.content.conclusion}</Text>
        ) : null}
        {item.content?.key_points?.length ? (
          <Text style={styles.points} numberOfLines={2}>
            {item.content.key_points.join('；')}
          </Text>
        ) : null}
        <View style={styles.cardFooter}>
          <Text style={styles.dateText}>{item.created_at ? item.created_at.slice(0, 10) : '时间未知'}</Text>
          <Text style={styles.tapHint}>AI 生成</Text>
        </View>
      </View>
    );
  };

  return (
    <View style={styles.container}>
      <View style={styles.header}>
        <TouchableOpacity onPress={() => navigation.goBack()} style={styles.headerBtn}>
          <Icon name="chevron-left" size={22} color={Colors.textWhite} />
        </TouchableOpacity>
        <Text style={styles.headerTitle}>我的学术卡片</Text>
        <TouchableOpacity onPress={() => navigation.navigate('AcademicCardCreate')} style={styles.headerBtn}>
          <Icon name="plus" size={24} color={Colors.textWhite} />
        </TouchableOpacity>
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
            <EmptyState
              icon="file-document-outline"
              title="暂无学术卡片"
              description="在「创建学术卡片」中输入主题即可 AI 生成并推送医生"
              actionLabel="去创建"
              onAction={() => navigation.navigate('AcademicCardCreate')}
            />
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
  cardHead: { flexDirection: 'row', justifyContent: 'space-between', alignItems: 'flex-start', marginBottom: Spacing.sm },
  titleBox: { flexDirection: 'row', alignItems: 'center', gap: 6, flex: 1, marginRight: Spacing.sm },
  titleText: { flex: 1, fontSize: FontSize.md, color: Colors.textPrimary, fontWeight: '600' },
  statusBadge: { paddingHorizontal: 10, paddingVertical: 3, borderRadius: BorderRadius.full },
  statusText: { fontSize: 10, fontWeight: '600' },
  conclusion: { fontSize: FontSize.sm, color: Colors.textPrimary, lineHeight: 20, marginBottom: Spacing.xs },
  points: { fontSize: FontSize.sm, color: Colors.textSecondary, lineHeight: 20 },
  cardFooter: {
    flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center',
    marginTop: Spacing.sm,
  },
  dateText: { fontSize: 11, color: Colors.textHint },
  tapHint: { fontSize: 10, color: Colors.primary },
});
