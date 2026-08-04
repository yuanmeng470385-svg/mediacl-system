/**
 * 帮助中心页
 */
import React from 'react';
import { View, Text, ScrollView, StyleSheet, TouchableOpacity } from 'react-native';
import { useNavigation } from '@react-navigation/native';
import Icon from '../../components/Icon';
import { Colors, FontSize, Spacing, BorderRadius, Shadow } from '../../constants/theme';

const faqs = [
  { q: '如何使用数字专员？', a: '在"对话"Tab中选择对应产品的数字专员，输入医学问题，3秒内即可获得带文献引用的答案。' },
  { q: '拜访记录如何生成？', a: '拜访中实时转写对话，拜访结束后AI自动生成结构化记录，1分钟即可完成确认。' },
  { q: '合规红线是什么？', a: '系统会自动检测话术中的违规内容（如疗效保证、竞品对比等），实时弹窗提醒代表修改。' },
  { q: '数据是否安全？', a: '所有对话和操作均加密存储，审计日志不可篡改，符合NMPA监管要求。' },
];

export default function HelpCenterScreen() {
  const navigation = useNavigation();
  const [expanded, setExpanded] = React.useState<number | null>(null);

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
  faqItem: { paddingVertical: Spacing.md },
  faqBorder: { borderBottomWidth: StyleSheet.hairlineWidth, borderBottomColor: Colors.divider },
  faqHeader: { flexDirection: 'row', alignItems: 'center', gap: Spacing.sm },
  faqQ: { flex: 1, fontSize: FontSize.md, color: Colors.textPrimary, fontWeight: '500' },
  faqA: {
    fontSize: FontSize.sm, color: Colors.textSecondary, lineHeight: 22,
    marginTop: Spacing.sm, paddingLeft: 26,
  },
  contactCard: {
    backgroundColor: Colors.primarySurface, borderRadius: BorderRadius.xl,
    padding: Spacing.xl, marginTop: Spacing.lg, alignItems: 'center', gap: Spacing.sm,
  },
  contactTitle: { fontSize: FontSize.lg, fontWeight: '600', color: Colors.primary },
  contactDesc: { fontSize: FontSize.sm, color: Colors.textSecondary, textAlign: 'center' },
  contactPhone: { fontSize: FontSize.lg, fontWeight: '700', color: Colors.primary, marginTop: Spacing.xs },
});
