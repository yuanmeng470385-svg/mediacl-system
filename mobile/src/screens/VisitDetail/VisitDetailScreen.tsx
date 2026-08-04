/**
 * 拜访详情页 - 查看已完成的拜访记录
 */
import React, { useEffect, useState } from 'react';
import { View, Text, ScrollView, StyleSheet, TouchableOpacity, ActivityIndicator } from 'react-native';
import { useRoute, useNavigation } from '@react-navigation/native';
import type { RouteProp } from '@react-navigation/native';
import Icon from '../../components/Icon';
import { Colors, FontSize, Spacing, BorderRadius, Shadow } from '../../constants/theme';
import type { RootStackParamList } from '../../navigation/types';

type RouteType = RouteProp<RootStackParamList, 'VisitDetail'>;

export default function VisitDetailScreen() {
  const route = useRoute<RouteType>();
  const navigation = useNavigation();
  const { visitId } = route.params;
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    const timer = setTimeout(() => setLoading(false), 800);
    return () => clearTimeout(timer);
  }, []);

  if (loading) {
    return (
      <View style={styles.centered}>
        <ActivityIndicator size="large" color={Colors.primary} />
      </View>
    );
  }

  return (
    <View style={styles.container}>
      <View style={styles.header}>
        <TouchableOpacity onPress={() => navigation.goBack()}>
          <Icon name="chevron-left" size={22} color={Colors.textWhite} />
        </TouchableOpacity>
        <Text style={styles.headerTitle}>拜访详情</Text>
        <View style={{ width: 24 }} />
      </View>

      <ScrollView contentContainerStyle={styles.content}>
        {/* 基本信息 */}
        <View style={[styles.card, Shadow.card]}>
          <Text style={styles.cardTitle}>基本信息</Text>
          <View style={styles.infoRow}>
            <Icon name="doctor" size={18} color={Colors.textSecondary} />
            <Text style={styles.infoText}>医生：李主任</Text>
          </View>
          <View style={styles.infoRow}>
            <Icon name="calendar" size={18} color={Colors.textSecondary} />
            <Text style={styles.infoText}>日期：2026-08-04</Text>
          </View>
          <View style={styles.infoRow}>
            <Icon name="clock-outline" size={18} color={Colors.textSecondary} />
            <Text style={styles.infoText}>时长：25 分钟</Text>
          </View>
          <View style={styles.infoRow}>
            <Icon name="hospital-building" size={18} color={Colors.textSecondary} />
            <Text style={styles.infoText}>地点：肿瘤科门诊</Text>
          </View>
        </View>

        {/* AI 总结 */}
        <View style={[styles.card, Shadow.card]}>
          <Text style={styles.cardTitle}>AI 拜访总结</Text>
          <View style={styles.summaryBox}>
            <Text style={styles.summaryText}>
              本次拜访围绕产品最新临床数据展开讨论。医生对疗效数据表示认可，但提出了安全性方面的顾虑。建议下次拜访准备更详细的安全性数据对比。
            </Text>
          </View>
        </View>

        {/* 关键发现 */}
        <View style={[styles.card, Shadow.card]}>
          <Text style={styles.cardTitle}>关键发现</Text>
          {[
            '医生对III期临床数据非常感兴趣',
            '安全性是主要顾虑点',
            '价格敏感度较高',
          ].map((point, i) => (
            <View key={i} style={styles.bulletRow}>
              <View style={styles.bullet} />
              <Text style={styles.bulletText}>{point}</Text>
            </View>
          ))}
        </View>

        <View style={{ height: 40 }} />
      </ScrollView>
    </View>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1, backgroundColor: Colors.background },
  centered: { flex: 1, justifyContent: 'center', alignItems: 'center', backgroundColor: Colors.background },
  header: {
    backgroundColor: Colors.primary, paddingTop: 50, paddingBottom: 14,
    paddingHorizontal: Spacing.lg, flexDirection: 'row',
    alignItems: 'center', justifyContent: 'space-between', ...Shadow.header,
  },
  headerTitle: { color: Colors.textWhite, fontSize: FontSize.lg, fontWeight: '600' },
  content: { padding: Spacing.lg },
  card: {
    backgroundColor: Colors.white, borderRadius: BorderRadius.xl,
    padding: Spacing.lg, marginBottom: Spacing.md,
  },
  cardTitle: {
    fontSize: FontSize.lg, fontWeight: '700', color: Colors.textPrimary,
    marginBottom: Spacing.md,
  },
  infoRow: {
    flexDirection: 'row', alignItems: 'center', gap: Spacing.sm,
    paddingVertical: Spacing.xs,
  },
  infoText: { fontSize: FontSize.md, color: Colors.textPrimary },
  summaryBox: {
    backgroundColor: Colors.primarySurface, padding: Spacing.lg,
    borderRadius: BorderRadius.md, borderLeftWidth: 4, borderLeftColor: Colors.primary,
  },
  summaryText: { fontSize: FontSize.md, color: Colors.textPrimary, lineHeight: 24, fontStyle: 'italic' },
  bulletRow: {
    flexDirection: 'row', alignItems: 'flex-start',
    gap: Spacing.sm, paddingVertical: Spacing.xs,
  },
  bullet: {
    width: 6, height: 6, borderRadius: 3, backgroundColor: Colors.accent,
    marginTop: 8,
  },
  bulletText: { fontSize: FontSize.md, color: Colors.textPrimary, lineHeight: 22, flex: 1 },
});
