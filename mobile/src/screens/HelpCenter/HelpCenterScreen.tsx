/**
 * 帮助中心页
 *
 * "红线清单"区块接真实合规规则接口（reject 类规则即红线），失败显示错误态 + 重试，
 * 不用写死规则兜底；"错误 vs 正确对比"与"联系方式"保持静态内容。
 */
import React, { useEffect, useState } from 'react';
import {
  View, Text, ScrollView, StyleSheet, TouchableOpacity,
  ActivityIndicator, Alert,
} from 'react-native';
import { useNavigation } from '@react-navigation/native';
import Icon from '../../components/Icon';
import { complianceAPI } from '../../api/compliance';
import { Colors, FontSize, Spacing, BorderRadius, Shadow } from '../../constants/theme';
import type { ComplianceRule } from '../../types';

const faqs = [
  { q: '如何使用数字专员？', a: '在"对话"Tab中选择对应产品的数字专员，输入医学问题，3秒内即可获得带文献引用的答案。' },
  { q: '拜访记录如何生成？', a: '拜访中实时转写对话，拜访结束后AI自动生成结构化记录，1分钟即可完成确认。' },
  { q: '合规红线是什么？', a: '系统会自动检测话术中的违规内容（如疗效保证、竞品对比等），实时弹窗提醒代表修改。' },
  { q: '数据是否安全？', a: '所有对话和操作均加密存储，审计日志不可篡改，符合NMPA监管要求。' },
];

/** 静态示例（需求 3.1.13 的错误 vs 正确对比；无对应后端接口，保持静态） */
const examplePairs = [
  {
    wrong: '我们这个药能保证治愈，效果绝对好。',
    right: '根据 III 期临床研究数据，本品在 XX 适应症的缓解率为 XX%，具体疗效因人而异。',
  },
  {
    wrong: '比 XX 竞品疗效好得多，选我们没错。',
    right: '本品不在推广中与其他产品直接对比，建议关注本品自身的循证数据。',
  },
  {
    wrong: '这是内部数据，还没公开，但确实有效。',
    right: '以下证据来自已公开发表的文献与指南：……',
  },
];

export default function HelpCenterScreen() {
  const navigation = useNavigation();
  const [expanded, setExpanded] = useState<number | null>(null);
  const [redLines, setRedLines] = useState<ComplianceRule[]>([]);
  const [loadingRules, setLoadingRules] = useState(true);
  const [rulesError, setRulesError] = useState('');

  // 红线清单 = 合规规则中 action=reject 的规则（GET /api/v1/compliance/rules）
  const loadRedLines = async () => {
    setLoadingRules(true);
    setRulesError('');
    try {
      const rules = await complianceAPI.listRules();
      const rejects = (rules || []).filter((r) => r.action === 'reject' && r.enabled !== false);
      setRedLines(rejects);
    } catch (e: any) {
      setRulesError(e?.message || '红线规则加载失败，请检查网络');
      setRedLines([]);
    } finally {
      setLoadingRules(false);
    }
  };

  useEffect(() => { loadRedLines(); }, []);

  return (
    <View style={styles.container}>
      <View style={styles.header}>
        <TouchableOpacity onPress={() => navigation.goBack()}>
          <Icon name="chevron-left" size={22} color={Colors.textWhite} />
        </TouchableOpacity>
        <Text style={styles.headerTitle}>帮助中心</Text>
        <View style={{ width: 24 }} />
      </View>
      <ScrollView contentContainerStyle={styles.content}>
        <View style={[styles.card, Shadow.card]}>
          <Text style={styles.cardTitle}>常见问题</Text>
          {faqs.map((faq, i) => (
            <TouchableOpacity
              key={i}
              style={[styles.faqItem, i < faqs.length - 1 && styles.faqBorder]}
              onPress={() => setExpanded(expanded === i ? null : i)}
              activeOpacity={0.7}
            >
              <View style={styles.faqHeader}>
                <Icon name="help-circle" size={18} color={Colors.primary} />
                <Text style={styles.faqQ}>{faq.q}</Text>
                <Icon name={expanded === i ? 'chevron-up' : 'chevron-down'} size={20} color={Colors.textHint} />
              </View>
              {expanded === i && (
                <Text style={styles.faqA}>{faq.a}</Text>
              )}
            </TouchableOpacity>
          ))}
        </View>

        {/* 合规红线清单（真实数据） */}
        <View style={[styles.card, Shadow.card, styles.redCard]}>
          <View style={styles.cardTitleRow}>
            <Icon name="alert-octagon-outline" size={18} color={Colors.danger} />
            <Text style={[styles.cardTitle, styles.redCardTitle]}>合规红线清单</Text>
          </View>
          {loadingRules ? (
            <View style={styles.rulesLoading}>
              <ActivityIndicator size="small" color={Colors.primary} />
              <Text style={styles.rulesLoadingText}>加载红线规则...</Text>
            </View>
          ) : rulesError ? (
            <View style={styles.rulesErrorBox}>
              <Text style={styles.rulesErrorText}>{rulesError}</Text>
              <TouchableOpacity style={styles.retryBtn} onPress={loadRedLines} activeOpacity={0.8}>
                <Text style={styles.retryText}>重试</Text>
              </TouchableOpacity>
            </View>
          ) : redLines.length === 0 ? (
            <Text style={styles.rulesEmpty}>暂无红线规则</Text>
          ) : (
            redLines.map((rule) => (
              <TouchableOpacity
                key={rule.rule_code}
                style={styles.ruleItem}
                onPress={() => Alert.alert(`红线 ${rule.rule_code}`, rule.description)}
                activeOpacity={0.7}
              >
                <Text style={styles.ruleCode}>{rule.rule_code}</Text>
                <View style={styles.ruleBody}>
                  <Text style={styles.ruleName}>{rule.rule_name}</Text>
                  <Text style={styles.ruleDesc}>{rule.description}</Text>
                </View>
              </TouchableOpacity>
            ))
          )}
        </View>

        {/* 错误 vs 正确对比（静态示例） */}
        <View style={[styles.card, Shadow.card]}>
          <Text style={styles.cardTitle}>错误 vs 正确对比</Text>
          {examplePairs.map((pair, i) => (
            <View key={i} style={[styles.pairItem, i < examplePairs.length - 1 && styles.faqBorder]}>
              <View style={styles.pairRow}>
                <View style={[styles.pairTag, styles.pairWrongTag]}>
                  <Text style={styles.pairWrongText}>错误</Text>
                </View>
                <Text style={styles.pairWrong}>{pair.wrong}</Text>
              </View>
              <View style={styles.pairRow}>
                <View style={[styles.pairTag, styles.pairRightTag]}>
                  <Text style={styles.pairRightText}>正确</Text>
                </View>
                <Text style={styles.pairRight}>{pair.right}</Text>
              </View>
            </View>
          ))}
        </View>

        <View style={[styles.contactCard, Shadow.card]}>
          <Icon name="headset" size={24} color={Colors.primary} />
          <Text style={styles.contactTitle}>联系支持</Text>
          <Text style={styles.contactDesc}>如有疑问，请联系系统管理员或拨打技术支持热线</Text>
          <Text style={styles.contactPhone}>400-xxx-xxxx</Text>
        </View>

        <View style={{ height: 40 }} />
      </ScrollView>
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
  headerTitle: { color: Colors.textWhite, fontSize: FontSize.lg, fontWeight: '600' },
  content: { padding: Spacing.lg },
  card: { backgroundColor: Colors.white, borderRadius: BorderRadius.xl, padding: Spacing.lg },
  cardTitle: { fontSize: FontSize.lg, fontWeight: '700', color: Colors.textPrimary, marginBottom: Spacing.md },
  cardTitleRow: { flexDirection: 'row', alignItems: 'center', gap: Spacing.sm, marginBottom: Spacing.md },
  faqItem: { paddingVertical: Spacing.md },
  faqBorder: { borderBottomWidth: StyleSheet.hairlineWidth, borderBottomColor: Colors.divider },
  faqHeader: { flexDirection: 'row', alignItems: 'center', gap: Spacing.sm },
  faqQ: { flex: 1, fontSize: FontSize.md, color: Colors.textPrimary, fontWeight: '500' },
  faqA: {
    fontSize: FontSize.sm, color: Colors.textSecondary, lineHeight: 22,
    marginTop: Spacing.sm, paddingLeft: 26,
  },
  // 红线清单
  redCard: { marginTop: Spacing.lg, borderWidth: 1, borderColor: '#fecaca' },
  redCardTitle: { color: Colors.danger, marginBottom: 0 },
  rulesLoading: { flexDirection: 'row', alignItems: 'center', gap: Spacing.sm, paddingVertical: Spacing.md },
  rulesLoadingText: { fontSize: FontSize.sm, color: Colors.textHint },
  rulesErrorBox: { alignItems: 'center', paddingVertical: Spacing.md, gap: Spacing.md },
  rulesErrorText: { fontSize: FontSize.sm, color: Colors.danger, textAlign: 'center' },
  retryBtn: {
    backgroundColor: Colors.primary, borderRadius: BorderRadius.md,
    paddingHorizontal: Spacing.xl, paddingVertical: Spacing.sm,
  },
  retryText: { color: Colors.textWhite, fontSize: FontSize.sm, fontWeight: '600' },
  rulesEmpty: { fontSize: FontSize.sm, color: Colors.textHint, paddingVertical: Spacing.md },
  ruleItem: {
    flexDirection: 'row', gap: Spacing.md, paddingVertical: Spacing.md,
    borderBottomWidth: StyleSheet.hairlineWidth, borderBottomColor: Colors.divider,
  },
  ruleCode: {
    fontSize: FontSize.xs, fontWeight: '700', color: Colors.danger,
    fontFamily: 'monospace', marginTop: 2,
  },
  ruleBody: { flex: 1 },
  ruleName: { fontSize: FontSize.md, color: Colors.textPrimary, fontWeight: '600' },
  ruleDesc: { fontSize: FontSize.xs, color: Colors.textSecondary, marginTop: 4, lineHeight: 18 },
  // 错误 vs 正确对比
  pairItem: { paddingVertical: Spacing.md },
  pairRow: { flexDirection: 'row', gap: Spacing.sm, marginBottom: Spacing.sm, alignItems: 'flex-start' },
  pairTag: {
    paddingHorizontal: 8, paddingVertical: 2, borderRadius: BorderRadius.sm,
    marginTop: 2,
  },
  pairWrongTag: { backgroundColor: Colors.dangerLight },
  pairWrongText: { fontSize: 10, fontWeight: '700', color: Colors.danger },
  pairRightTag: { backgroundColor: '#dcfce7' },
  pairRightText: { fontSize: 10, fontWeight: '700', color: Colors.success },
  pairWrong: { flex: 1, fontSize: FontSize.sm, color: Colors.danger, lineHeight: 20 },
  pairRight: { flex: 1, fontSize: FontSize.sm, color: Colors.textPrimary, lineHeight: 20 },
  // 联系支持
  contactCard: {
    backgroundColor: Colors.primarySurface, borderRadius: BorderRadius.xl,
    padding: Spacing.xl, marginTop: Spacing.lg, alignItems: 'center', gap: Spacing.sm,
  },
  contactTitle: { fontSize: FontSize.lg, fontWeight: '600', color: Colors.primary },
  contactDesc: { fontSize: FontSize.sm, color: Colors.textSecondary, textAlign: 'center' },
  contactPhone: { fontSize: FontSize.lg, fontWeight: '700', color: Colors.primary, marginTop: Spacing.xs },
});
