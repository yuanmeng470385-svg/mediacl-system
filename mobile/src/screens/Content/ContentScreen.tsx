/**
 * 学术内容页 - 文献/指南/说明书浏览
 */
import React, { useCallback, useEffect, useState } from 'react';
import Icon from '../../components/Icon';
import { ActionIcons } from '../../components/Icon';
import {
  View,
  Text,
  StyleSheet,
  FlatList,
  TouchableOpacity,
  TextInput,
  RefreshControl,
  ActivityIndicator,
} from 'react-native';
import { useNavigation } from '@react-navigation/native';
import type { NativeStackNavigationProp } from '@react-navigation/native-stack';
import EmptyState from '../../components/EmptyState';
import { contentAPI } from '../../api/content';
import { Colors, FontSize, Spacing, BorderRadius, Shadow } from '../../constants/theme';
import type { ContentItem } from '../../types';
import type { RootStackParamList } from '../../navigation/types';

type Nav = NativeStackNavigationProp<RootStackParamList>;

const typeLabels: Record<string, { icon: string; label: string }> = {
  literature: { icon: 'file-document-outline', label: '文献' },
  guideline: { icon: 'clipboard-text-outline', label: '指南' },
  manual: { icon: 'book-open-page-variant-outline', label: '说明书' },
  news: { icon: 'newspaper-variant-outline', label: '资讯' },
};

const tabs = ['全部', '文献', '指南', '说明书'];

export default function ContentScreen() {
  const navigation = useNavigation<Nav>();
  const [searchText, setSearchText] = useState('');
  const [activeTab, setActiveTab] = useState('全部');
  const [items, setItems] = useState<ContentItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [refreshing, setRefreshing] = useState(false);

  const load = useCallback(async () => {
    try {
      const res = await contentAPI.getDocuments({ page: 1, page_size: 50 });
      setItems(res.items);
      setError('');
    } catch (e: any) {
      setError(e.message || '加载失败');
    } finally {
      setLoading(false);
      setRefreshing(false);
    }
  }, []);

  useEffect(() => { load(); }, [load]);

  const filteredContent = items.filter((item) => {
    const matchTab =
      activeTab === '全部' || typeLabels[item.type]?.label === activeTab;
    const matchSearch =
      !searchText ||
      (item.title || '').includes(searchText) ||
      (item.tags ?? []).some((t) => t.includes(searchText));
    return matchTab && matchSearch;
  });

  const renderItem = ({ item }: { item: ContentItem }) => {
    const type = typeLabels[item.type] || { icon: 'file-document-outline', label: item.type };

    return (
      <TouchableOpacity
        style={[styles.card, Shadow.card]}
        activeOpacity={0.7}
        onPress={() => navigation.navigate('ContentDetail', { contentId: item.id })}
      >
        <View style={styles.cardHeader}>
          <View style={styles.typeBadge}>
            <Text style={styles.typeIcon}>{type.icon}</Text>
            <Text style={styles.typeLabel}>{type.label}</Text>
          </View>
          {item.evidence_level ? (
            <Text style={styles.evidenceBadge}>
              {item.evidence_level}级证据
            </Text>
          ) : null}
        </View>
        <Text style={styles.cardTitle} numberOfLines={2}>
          {item.title}
        </Text>
        <Text style={styles.cardSummary} numberOfLines={3}>
          {item.summary ?? ''}
        </Text>
        <View style={styles.cardFooter}>
          <Text style={styles.cardSource}>{item.source ?? ''}</Text>
          <Text style={styles.cardDate}>{item.publish_date ?? ''}</Text>
        </View>
        <View style={styles.tagRow}>
          {(item.tags ?? []).map((tag, i) => (
            <View key={i} style={styles.tag}>
              <Text style={styles.tagText}>{tag}</Text>
            </View>
          ))}
        </View>
      </TouchableOpacity>
    );
  };

  const handleRetry = () => {
    setLoading(true);
    setError('');
    load();
  };

  return (
    <View style={styles.container}>
      {/* 头部 */}
      <View style={styles.header}>
        <Text style={styles.headerTitle}>学术内容</Text>
        <View style={styles.searchRow}>
          <Icon name={ActionIcons.search} size={18} color={Colors.textHint} />
          <TextInput
            style={styles.searchInput}
            placeholder="搜索学术内容..."
            placeholderTextColor={Colors.textHint}
            value={searchText}
            onChangeText={setSearchText}
          />
        </View>
      </View>

      {/* Tab */}
      <View style={styles.tabBar}>
        {tabs.map((tab) => (
          <TouchableOpacity
            key={tab}
            style={[styles.tab, activeTab === tab && styles.tabActive]}
            onPress={() => setActiveTab(tab)}
          >
            <Text
              style={[
                styles.tabText,
                activeTab === tab && styles.tabTextActive,
              ]}
            >
              {tab}
            </Text>
          </TouchableOpacity>
        ))}
      </View>

      {loading ? (
        <View style={styles.centered}>
          <ActivityIndicator size="large" color={Colors.primary} />
        </View>
      ) : error ? (
        <View style={styles.centered}>
          <Text style={styles.errorText}>{error}</Text>
          <TouchableOpacity style={styles.retryBtn} onPress={handleRetry}>
            <Text style={styles.retryText}>重试</Text>
          </TouchableOpacity>
        </View>
      ) : (
        <FlatList
          data={filteredContent}
          renderItem={renderItem}
          keyExtractor={(item) => item.id.toString()}
          contentContainerStyle={styles.list}
          refreshControl={
            <RefreshControl
              refreshing={refreshing}
              onRefresh={() => { setRefreshing(true); load(); }}
            />
          }
          ListEmptyComponent={
            <EmptyState
              icon="book-open-page-variant-outline"
              title="暂无学术内容"
              description="知识库上线后将展示医学文献和指南"
            />
          }
        />
      )}
    </View>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1, backgroundColor: Colors.background },
  centered: { flex: 1, justifyContent: 'center', alignItems: 'center', backgroundColor: Colors.background },
  header: {
    backgroundColor: Colors.primary,
    paddingTop: 52,
    paddingBottom: Spacing.md,
    paddingHorizontal: Spacing.lg,
  },
  headerTitle: {
    color: Colors.textWhite,
    fontSize: FontSize.xl,
    fontWeight: '700',
    marginBottom: Spacing.md,
  },
  searchRow: {
    flexDirection: 'row',
    alignItems: 'center',
    backgroundColor: 'rgba(255,255,255,0.2)',
    borderRadius: BorderRadius.full,
    paddingHorizontal: Spacing.md,
    gap: Spacing.sm,
  },
  searchIcon: { fontSize: 16 },
  searchInput: {
    flex: 1,
    fontSize: FontSize.md,
    color: Colors.textWhite,
    paddingVertical: 8,
  },
  tabBar: {
    flexDirection: 'row',
    backgroundColor: Colors.white,
    paddingHorizontal: Spacing.lg,
    borderBottomWidth: 1,
    borderBottomColor: Colors.divider,
  },
  tab: {
    paddingVertical: Spacing.md,
    marginRight: Spacing.xxl,
    borderBottomWidth: 2,
    borderBottomColor: 'transparent',
  },
  tabActive: { borderBottomColor: Colors.primary },
  tabText: { fontSize: FontSize.md, color: Colors.textSecondary },
  tabTextActive: { color: Colors.primary, fontWeight: '600' },
  list: { padding: Spacing.lg },
  card: {
    backgroundColor: Colors.white,
    borderRadius: BorderRadius.lg,
    padding: Spacing.lg,
    marginBottom: Spacing.md,
  },
  cardHeader: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
    marginBottom: Spacing.sm,
  },
  typeBadge: { flexDirection: 'row', alignItems: 'center', gap: 4 },
  typeIcon: { fontSize: 16 },
  typeLabel: { fontSize: FontSize.xs, color: Colors.textSecondary, fontWeight: '500' },
  evidenceBadge: {
    fontSize: 10,
    color: Colors.primary,
    backgroundColor: '#dbeafe',
    paddingHorizontal: 8,
    paddingVertical: 2,
    borderRadius: BorderRadius.sm,
    fontWeight: '600',
  },
  cardTitle: {
    fontSize: FontSize.lg,
    fontWeight: '600',
    color: Colors.textPrimary,
    marginBottom: Spacing.sm,
    lineHeight: 24,
  },
  cardSummary: {
    fontSize: FontSize.sm,
    color: Colors.textSecondary,
    lineHeight: 20,
    marginBottom: Spacing.md,
  },
  cardFooter: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    marginBottom: Spacing.sm,
  },
  cardSource: { fontSize: FontSize.xs, color: Colors.textHint },
  cardDate: { fontSize: FontSize.xs, color: Colors.textHint },
  tagRow: { flexDirection: 'row', gap: Spacing.xs, flexWrap: 'wrap' },
  tag: {
    backgroundColor: Colors.background,
    paddingHorizontal: 8,
    paddingVertical: 2,
    borderRadius: BorderRadius.sm,
  },
  tagText: { fontSize: 10, color: Colors.textSecondary },
  errorText: {
    fontSize: FontSize.md, color: Colors.danger,
    marginBottom: Spacing.lg, paddingHorizontal: Spacing.xl, textAlign: 'center',
  },
  retryBtn: {
    backgroundColor: Colors.primary, borderRadius: BorderRadius.md,
    paddingHorizontal: Spacing.xl, paddingVertical: Spacing.sm,
  },
  retryText: { color: Colors.textWhite, fontSize: FontSize.md, fontWeight: '600' },
});
