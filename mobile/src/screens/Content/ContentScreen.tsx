/**
 * 学术内容页 - 文献/指南/说明书浏览
 */
import React, { useState } from 'react';
import {
  View,
  Text,
  StyleSheet,
  FlatList,
  TouchableOpacity,
  TextInput,
} from 'react-native';
import EmptyState from '../../components/EmptyState';
import { Colors, FontSize, Spacing, BorderRadius, Shadow } from '../../constants/theme';
import type { ContentItem } from '../../types';

const MOCK_CONTENT: ContentItem[] = [
  {
    id: 1,
    title: '2026 NCCN 非小细胞肺癌指南更新解读',
    type: 'guideline',
    summary: '最新的NCCN指南针对非小细胞肺癌的靶向治疗和免疫治疗方案进行了重大更新...',
    source: 'NCCN Guidelines',
    publish_date: '2026-06-15',
    evidence_level: 'A',
    tags: ['肺癌', '指南', '靶向治疗'],
  },
  {
    id: 2,
    title: 'PD-1抑制剂在晚期黑色素瘤中的III期临床研究',
    type: 'literature',
    summary: '一项多中心、随机、双盲III期临床研究，比较PD-1抑制剂与标准化疗的疗效和安全性...',
    source: 'The Lancet Oncology',
    publish_date: '2026-04-20',
    evidence_level: 'A',
    tags: ['黑色素瘤', 'III期', '免疫治疗'],
  },
  {
    id: 3,
    title: 'XX产品说明书（2026年修订版）',
    type: 'manual',
    summary: '适应症、用法用量、不良反应、禁忌症等完整处方信息...',
    source: '内部资料',
    publish_date: '2026-07-01',
    evidence_level: 'B',
    tags: ['说明书', '产品信息'],
  },
];

const typeLabels: Record<string, { icon: string; label: string }> = {
  literature: { icon: '📄', label: '文献' },
  guideline: { icon: '📋', label: '指南' },
  manual: { icon: '📘', label: '说明书' },
  news: { icon: '📰', label: '资讯' },
};

const tabs = ['全部', '文献', '指南', '说明书'];

export default function ContentScreen() {
  const [searchText, setSearchText] = useState('');
  const [activeTab, setActiveTab] = useState('全部');

  const filteredContent = MOCK_CONTENT.filter((item) => {
    const matchTab =
      activeTab === '全部' || typeLabels[item.type]?.label === activeTab;
    const matchSearch =
      !searchText ||
      item.title.includes(searchText) ||
      item.tags.some((t) => t.includes(searchText));
    return matchTab && matchSearch;
  });

  const renderItem = ({ item }: { item: ContentItem }) => {
    const type = typeLabels[item.type] || { icon: '📄', label: item.type };

    return (
      <TouchableOpacity style={[styles.card, Shadow.card]} activeOpacity={0.7}>
        <View style={styles.cardHeader}>
          <View style={styles.typeBadge}>
            <Text style={styles.typeIcon}>{type.icon}</Text>
            <Text style={styles.typeLabel}>{type.label}</Text>
          </View>
          <Text style={styles.evidenceBadge}>
            {item.evidence_level}级证据
          </Text>
        </View>
        <Text style={styles.cardTitle} numberOfLines={2}>
          {item.title}
        </Text>
        <Text style={styles.cardSummary} numberOfLines={3}>
          {item.summary}
        </Text>
        <View style={styles.cardFooter}>
          <Text style={styles.cardSource}>{item.source}</Text>
          <Text style={styles.cardDate}>{item.publish_date}</Text>
        </View>
        <View style={styles.tagRow}>
          {item.tags.map((tag, i) => (
            <View key={i} style={styles.tag}>
              <Text style={styles.tagText}>{tag}</Text>
            </View>
          ))}
        </View>
      </TouchableOpacity>
    );
  };

  return (
    <View style={styles.container}>
      {/* 头部 */}
      <View style={styles.header}>
        <Text style={styles.headerTitle}>学术内容</Text>
        <View style={styles.searchRow}>
          <Text style={styles.searchIcon}>🔍</Text>
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

      <FlatList
        data={filteredContent}
        renderItem={renderItem}
        keyExtractor={(item) => item.id.toString()}
        contentContainerStyle={styles.list}
        ListEmptyComponent={
          <EmptyState
            icon="📚"
            title="暂无学术内容"
            description="知识库上线后将展示医学文献和指南"
          />
        }
      />
    </View>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1, backgroundColor: Colors.background },
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
});
