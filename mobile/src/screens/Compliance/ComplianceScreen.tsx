/**
 * 合规手册页 - 查看合规规则
 */
import React, { useEffect, useState } from 'react';
import {
  View,
  Text,
  StyleSheet,
  FlatList,
  TouchableOpacity,
  ActivityIndicator,
  Alert,
  Platform,
} from 'react-native';
import { complianceAPI } from '../../api/compliance';
import { Colors, FontSize, Spacing, BorderRadius, Shadow } from '../../constants/theme';
import type { ComplianceRule } from '../../types';

const severityConfig: Record<string, { color: string; bg: string; label: string }> = {
  high: { color: Colors.danger, bg: '#fef2f2', label: '高' },
  medium: { color: Colors.warning, bg: '#fffbeb', label: '中' },
  low: { color: Colors.info, bg: '#ecfeff', label: '低' },
};

// 静态规则（后端不可用时的 fallback）
const FALLBACK_RULES: ComplianceRule[] = [
  {
    code: 'R001',
    description: '禁止使用"保证治好""根治""治愈"等绝对化疗效承诺用语',
    severity: 'high',
    type: 'keyword',
  },
  {
    code: 'R002',
    description: '禁止与竞品进行直接疗效对比',
    severity: 'high',
    type: 'keyword',
  },
  {
    code: 'R003',
    description: '学术推广中必须引用公开已发表的数据，不得使用未公开内部数据',
    severity: 'high',
    type: 'llm',
  },
  {
    code: 'R004',
    description: '禁止提及药品回扣、利益输送等敏感内容',
    severity: 'high',
    type: 'keyword',
  },
  {
    code: 'R005',
    description: '适应症外推必须基于循证医学证据且明确标注为"超说明书用药"',
    severity: 'medium',
    type: 'llm',
  },
  {
    code: 'R006',
    description: '推广内容必须有明确证据来源标注（文献+证据等级）',
    severity: 'medium',
    type: 'regex',
  },
  {
    code: 'R007',
    description: '禁止使用"最安全""最好""第一品牌"等极端表述',
    severity: 'medium',
    type: 'keyword',
  },
];

const filterTabs = ['全部', '高', '中', '低'];

export default function ComplianceScreen() {
  const [rules, setRules] = useState<ComplianceRule[]>([]);
  const [loading, setLoading] = useState(true);
  const [filter, setFilter] = useState('全部');

  useEffect(() => {
    loadRules();
  }, []);

  const loadRules = async () => {
    try {
      const result = await complianceAPI.listRules();
      setRules(result || FALLBACK_RULES);
    } catch {
      setRules(FALLBACK_RULES);
    } finally {
      setLoading(false);
    }
  };

  const filteredRules = rules.filter(
    (r) => filter === '全部' || severityConfig[r.severity]?.label === filter
  );

  const renderRule = ({ item }: { item: ComplianceRule }) => {
    const sev = severityConfig[item.severity] || severityConfig.medium;

    return (
      <TouchableOpacity
        style={[styles.ruleCard, Shadow.card]}
        activeOpacity={0.7}
        onPress={() => Alert.alert('规则详情', item.description)}
      >
        <View style={styles.ruleHeader}>
          <View style={styles.ruleCodeRow}>
            <Text style={styles.ruleCode}>{item.code}</Text>
            <View style={[styles.severityBadge, { backgroundColor: sev.bg }]}>
              <Text style={[styles.severityText, { color: sev.color }]}>
                {sev.label}
              </Text>
            </View>
          </View>
          <View style={styles.typeFlag}>
            <Text style={styles.typeText}>
              {item.type === 'keyword'
                ? '关键词'
                : item.type === 'regex'
                ? '正则'
                : 'AI语义'}
            </Text>
          </View>
        </View>
        <Text style={styles.ruleDesc}>{item.description}</Text>
      </TouchableOpacity>
    );
  };

  return (
    <View style={styles.container}>
      {/* 头部 */}
      <View style={styles.header}>
        <Text style={styles.headerTitle}>合规手册</Text>
        <Text style={styles.headerSub}>
          共 {rules.length} 条合规规则 · 拜访前务必阅读红线
        </Text>
      </View>

      {/* 筛选 */}
      <View style={styles.filterBar}>
        {filterTabs.map((tab) => (
          <TouchableOpacity
            key={tab}
            style={[
              styles.filterChip,
              filter === tab && styles.filterChipActive,
            ]}
            onPress={() => setFilter(tab)}
          >
            <Text
              style={[
                styles.filterText,
                filter === tab && styles.filterTextActive,
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
      ) : (
        <FlatList
          data={filteredRules}
          renderItem={renderRule}
          keyExtractor={(item) => item.code}
          contentContainerStyle={styles.list}
          showsVerticalScrollIndicator={false}
        />
      )}
    </View>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1, backgroundColor: Colors.background },
  centered: { flex: 1, justifyContent: 'center', alignItems: 'center' },
  header: {
    backgroundColor: Colors.primary,
    paddingTop: 52,
    paddingBottom: Spacing.xl,
    paddingHorizontal: Spacing.xl,
  },
  headerTitle: { color: Colors.textWhite, fontSize: FontSize.xl, fontWeight: '700' },
  headerSub: { color: 'rgba(255,255,255,0.7)', fontSize: FontSize.sm, marginTop: 4 },
  filterBar: {
    flexDirection: 'row',
    padding: Spacing.lg,
    gap: Spacing.sm,
    backgroundColor: Colors.white,
    borderBottomWidth: 1,
    borderBottomColor: Colors.divider,
  },
  filterChip: {
    paddingHorizontal: Spacing.lg,
    paddingVertical: Spacing.sm,
    borderRadius: BorderRadius.full,
    backgroundColor: Colors.background,
  },
  filterChipActive: { backgroundColor: Colors.primary },
  filterText: { fontSize: FontSize.sm, color: Colors.textSecondary },
  filterTextActive: { color: Colors.textWhite, fontWeight: '600' },
  list: { padding: Spacing.lg },
  ruleCard: {
    backgroundColor: Colors.white,
    borderRadius: BorderRadius.lg,
    padding: Spacing.lg,
    marginBottom: Spacing.md,
  },
  ruleHeader: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
    marginBottom: Spacing.sm,
  },
  ruleCodeRow: { flexDirection: 'row', alignItems: 'center', gap: Spacing.sm },
  ruleCode: {
    fontSize: FontSize.sm,
    fontWeight: '700',
    color: Colors.primary,
    fontFamily: Platform.OS === 'ios' ? 'Menlo' : 'monospace',
  },
  severityBadge: {
    paddingHorizontal: 8,
    paddingVertical: 2,
    borderRadius: BorderRadius.sm,
  },
  severityText: { fontSize: 10, fontWeight: '700' },
  typeFlag: {
    backgroundColor: Colors.background,
    paddingHorizontal: 8,
    paddingVertical: 2,
    borderRadius: BorderRadius.sm,
  },
  typeText: { fontSize: 10, color: Colors.textHint },
  ruleDesc: {
    fontSize: FontSize.md,
    color: Colors.textPrimary,
    lineHeight: 22,
  },
});
