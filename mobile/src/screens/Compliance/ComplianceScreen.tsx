/**
 * 合规手册页 - 查看合规规则
 * 临床精准风
 */
import React, { useEffect, useState } from 'react';
import {
  View, Text, StyleSheet, FlatList, TouchableOpacity,
  ActivityIndicator, Alert,
} from 'react-native';
import Icon from '../../components/Icon';
import { complianceAPI } from '../../api/compliance';
import { Colors, FontSize, Spacing, BorderRadius, Shadow } from '../../constants/theme';
import type { ComplianceRule } from '../../types';

const severityConfig: Record<string, { color: string; bg: string; icon: string }> = {
  high: { color: Colors.danger, bg: Colors.dangerLight, icon: 'alert-octagon' },
  medium: { color: Colors.warning, bg: Colors.warningLight, icon: 'alert' },
  low: { color: Colors.info, bg: Colors.infoLight, icon: 'information' },
};

const FALLBACK_RULES: ComplianceRule[] = [
  { id: 1, rule_code: 'R001', rule_name: '绝对化疗效承诺', description: '禁止使用"保证治好""根治""治愈"等绝对化疗效承诺用语', severity: 'high', rule_type: 'keyword', action: 'reject', enabled: true, version: 1 },
  { id: 2, rule_code: 'R002', rule_name: '竞品对比', description: '禁止与竞品进行直接疗效对比', severity: 'high', rule_type: 'keyword', action: 'reject', enabled: true, version: 1 },
  { id: 3, rule_code: 'R003', rule_name: '未公开数据引用', description: '学术推广中必须引用公开已发表的数据，不得使用未公开内部数据', severity: 'high', rule_type: 'semantic', action: 'reject', enabled: true, version: 1 },
  { id: 4, rule_code: 'R004', rule_name: '利益输送', description: '禁止提及药品回扣、利益输送等敏感内容', severity: 'high', rule_type: 'keyword', action: 'reject', enabled: true, version: 1 },
  { id: 5, rule_code: 'R005', rule_name: '超说明书用药标注', description: '适应症外推必须基于循证医学证据且明确标注为"超说明书用药"', severity: 'medium', rule_type: 'semantic', action: 'warn', enabled: true, version: 1 },
  { id: 6, rule_code: 'R006', rule_name: '证据来源标注', description: '推广内容必须有明确证据来源标注（文献+证据等级）', severity: 'medium', rule_type: 'regex', action: 'warn', enabled: true, version: 1 },
  { id: 7, rule_code: 'R007', rule_name: '极端表述', description: '禁止使用"最安全""最好""第一品牌"等极端表述', severity: 'medium', rule_type: 'keyword', action: 'warn', enabled: true, version: 1 },
];

const filterTabs = ['全部', '高', '中', '低'];
const TYPE_LABELS: Record<string, string> = { keyword: '关键词', regex: '正则', semantic: 'AI语义' };

export default function ComplianceScreen() {
  const [rules, setRules] = useState<ComplianceRule[]>([]);
  const [loading, setLoading] = useState(true);
  const [filter, setFilter] = useState('全部');

  useEffect(() => { loadRules(); }, []);

  const loadRules = async () => {
    try {
      const result = await complianceAPI.listRules();
      setRules(result || FALLBACK_RULES);
    } catch { setRules(FALLBACK_RULES); }
    finally { setLoading(false); }
  };

  const filteredRules = rules.filter(
    (r) => filter === '全部' || severityConfig[r.severity]?.color === (filter === '高' ? Colors.danger : filter === '中' ? Colors.warning : Colors.info)
  );

  const renderRule = ({ item }: { item: ComplianceRule }) => {
    const sev = severityConfig[item.severity] || severityConfig.medium;

    return (
      <TouchableOpacity
        style={[styles.ruleCard, Shadow.card]}
        activeOpacity={0.7}
        onPress={() => Alert.alert(`规则 ${item.rule_code}`, item.description)}
      >
        <View style={styles.ruleHeader}>
          <View style={styles.ruleLeft}>
            <Text style={styles.ruleCode}>{item.rule_code}</Text>
            <View style={[styles.severityBadge, { backgroundColor: sev.bg }]}>
              <Icon name={sev.icon} size={12} color={sev.color} />
              <Text style={[styles.severityText, { color: sev.color }]}>
                {filterTabs.find(t => t !== '全部' && severityConfig[item.severity]?.color === (t === '高' ? Colors.danger : Colors.warning) ) || ''}
              </Text>
            </View>
          </View>
          <View style={styles.typeBadge}>
            <Text style={styles.typeText}>{TYPE_LABELS[item.rule_type] || item.rule_type}</Text>
          </View>
        </View>
        <Text style={styles.ruleDesc}>{item.description}</Text>
      </TouchableOpacity>
    );
  };

  return (
    <View style={styles.container}>
      <View style={styles.header}>
        <Text style={styles.headerTitle}>合规手册</Text>
        <Text style={styles.headerSub}>共 {rules.length} 条合规规则 · 拜访前务必阅读红线</Text>
      </View>

      <View style={styles.filterBar}>
        {filterTabs.map((tab) => (
          <TouchableOpacity
            key={tab}
            style={[styles.filterChip, filter === tab && styles.filterChipActive]}
            onPress={() => setFilter(tab)}
          >
            <Text style={[styles.filterText, filter === tab && styles.filterTextActive]}>{tab}</Text>
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
          keyExtractor={(item) => item.rule_code}
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
    backgroundColor: Colors.primary, paddingTop: 52, paddingBottom: Spacing.xl,
    paddingHorizontal: Spacing.xxl, ...Shadow.header,
  },
  headerTitle: { color: Colors.textWhite, fontSize: FontSize.xxl, fontWeight: '700' },
  headerSub: { color: 'rgba(255,255,255,0.7)', fontSize: FontSize.sm, marginTop: 4 },
  filterBar: {
    flexDirection: 'row', padding: Spacing.lg, gap: Spacing.sm,
    backgroundColor: Colors.white, borderBottomWidth: 1, borderBottomColor: Colors.divider,
  },
  filterChip: {
    paddingHorizontal: Spacing.lg, paddingVertical: Spacing.sm,
    borderRadius: BorderRadius.full, backgroundColor: Colors.background,
  },
  filterChipActive: { backgroundColor: Colors.primary },
  filterText: { fontSize: FontSize.sm, color: Colors.textSecondary },
  filterTextActive: { color: Colors.textWhite, fontWeight: '600' },
  list: { padding: Spacing.lg },
  ruleCard: {
    backgroundColor: Colors.white, borderRadius: BorderRadius.xl,
    padding: Spacing.lg, marginBottom: Spacing.md,
    borderLeftWidth: 3, borderLeftColor: Colors.primary,
  },
  ruleHeader: {
    flexDirection: 'row', justifyContent: 'space-between',
    alignItems: 'center', marginBottom: Spacing.sm,
  },
  ruleLeft: { flexDirection: 'row', alignItems: 'center', gap: Spacing.sm },
  ruleCode: {
    fontSize: FontSize.sm, fontWeight: '700', color: Colors.primary,
    fontFamily: 'monospace',
  },
  severityBadge: {
    flexDirection: 'row', alignItems: 'center', gap: 2,
    paddingHorizontal: 8, paddingVertical: 2, borderRadius: BorderRadius.sm,
  },
  severityText: { fontSize: 10, fontWeight: '700' },
  typeBadge: {
    backgroundColor: Colors.background, paddingHorizontal: 8,
    paddingVertical: 2, borderRadius: BorderRadius.sm,
  },
  typeText: { fontSize: 10, color: Colors.textHint },
  ruleDesc: { fontSize: FontSize.md, color: Colors.textPrimary, lineHeight: 22 },
});
