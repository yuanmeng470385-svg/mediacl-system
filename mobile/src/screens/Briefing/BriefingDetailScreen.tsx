/**
 * 夜间简报详情页 —— 渲染 content.summary + content.doctors（医生问答明细）。
 * 临床精准风
 */
import React, { useEffect, useState } from 'react';
import {
  View, Text, ScrollView, StyleSheet, TouchableOpacity, ActivityIndicator,
} from 'react-native';
import { useRoute, useNavigation } from '@react-navigation/native';
import type { RouteProp } from '@react-navigation/native';
import Icon from '../../components/Icon';
import { briefingAPI } from '../../api/briefing';
import type { NightlyBriefing } from '../../types';
import { Colors, FontSize, Spacing, BorderRadius, Shadow } from '../../constants/theme';
import type { RootStackParamList } from '../../navigation/types';

type RouteType = RouteProp<RootStackParamList, 'BriefingDetail'>;

export default function BriefingDetailScreen() {
  const route = useRoute<RouteType>();
  const navigation = useNavigation();
  const { briefingId } = route.params;
  const [briefing, setBriefing] = useState<NightlyBriefing | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');

  useEffect(() => {
    let cancelled = false;
    briefingAPI.getDetail(briefingId)
      .then((b) => { if (!cancelled) setBriefing(b); })
      .catch((e: any) => { if (!cancelled) setError(e.message || '加载失败'); })
      .finally(() => { if (!cancelled) setLoading(false); });
    return () => { cancelled = true; };
  }, [briefingId]);

  if (loading) {
    return (
      <View style={styles.centered}>
        <ActivityIndicator size="large" color={Colors.primary} />
      </View>
    );
  }
  if (error || !briefing) {
    return (
      <View style={styles.centered}>
        <Text style={styles.errorText}>{error || '简报不存在'}</Text>
      </View>
    );
  }

  const doctors = briefing.content?.doctors ?? [];

  return (
    <View style={styles.container}>
      <View style={styles.header}>
        <TouchableOpacity onPress={() => navigation.goBack()} style={styles.headerBtn}>
          <Icon name="chevron-left" size={22} color={Colors.textWhite} />
        </TouchableOpacity>
        <Text style={styles.headerTitle}>简报详情</Text>
        <View style={{ width: 24 }} />
      </View>

      <ScrollView contentContainerStyle={styles.content} showsVerticalScrollIndicator={false}>
        <View style={styles.headRow}>
          <View style={styles.twinBadge}>
            <Icon name="weather-night" size={14} color={Colors.primary} />
            <Text style={styles.twinText}>{briefing.twin_name || `分身 #${briefing.specialist_id}`}</Text>
          </View>
          <Text style={styles.dateText}>{briefing.briefing_date || ''}</Text>
        </View>

        <Text style={styles.sectionTitle}>简报摘要</Text>
        <View style={[styles.card, Shadow.card]}>
          <Text style={styles.summary}>{briefing.content?.summary || '暂无摘要'}</Text>
        </View>

        <Text style={styles.sectionTitle}>医生问答（{doctors.length}）</Text>
        {doctors.length === 0 ? (
          <View style={[styles.card, Shadow.card]}>
            <Text style={styles.emptyText}>暂无医生问答明细</Text>
          </View>
        ) : (
          doctors.map((d, i) => (
            <View key={`${d.doctor_name}-${i}`} style={[styles.card, Shadow.card]}>
              <View style={styles.doctorHead}>
                <Icon name="doctor" size={14} color={Colors.info} />
                <Text style={styles.doctorName}>{d.doctor_name || '医生'}</Text>
              </View>

              {Array.isArray(d.questions) && d.questions.length > 0 && (
                <View style={styles.block}>
                  <Text style={styles.blockLabel}>提问</Text>
                  {d.questions.map((q, qi) => (
                    <Text key={qi} style={styles.question}>· {q}</Text>
                  ))}
                </View>
              )}

              {d.concern ? (
                <View style={styles.block}>
                  <Text style={styles.blockLabel}>关注点</Text>
                  <Text style={styles.bodyText}>{d.concern}</Text>
                </View>
              ) : null}

              {d.follow_up ? (
                <View style={styles.block}>
                  <Text style={styles.blockLabel}>跟进建议</Text>
                  <Text style={styles.bodyText}>{d.follow_up}</Text>
                </View>
              ) : null}
            </View>
          ))
        )}

        <View style={{ height: 40 }} />
      </ScrollView>
    </View>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1, backgroundColor: Colors.background },
  centered: { flex: 1, justifyContent: 'center', alignItems: 'center', backgroundColor: Colors.background },
  errorText: { color: Colors.textSecondary, fontSize: FontSize.md, paddingHorizontal: Spacing.xl, textAlign: 'center' },
  header: {
    backgroundColor: Colors.primary, paddingTop: 50, paddingBottom: 14,
    paddingHorizontal: Spacing.lg, flexDirection: 'row',
    alignItems: 'center', justifyContent: 'space-between', ...Shadow.header,
  },
  headerBtn: { padding: 4 },
  headerTitle: { color: Colors.textWhite, fontSize: FontSize.lg, fontWeight: '600' },
  content: { padding: Spacing.lg },
  headRow: {
    flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center',
    marginBottom: Spacing.lg,
  },
  twinBadge: { flexDirection: 'row', alignItems: 'center', gap: 6, flex: 1 },
  twinText: { fontSize: FontSize.lg, color: Colors.textPrimary, fontWeight: '700' },
  dateText: { fontSize: FontSize.sm, color: Colors.textHint },
  sectionTitle: {
    fontSize: FontSize.md, color: Colors.textPrimary, fontWeight: '600',
    marginBottom: Spacing.md, marginTop: Spacing.sm,
  },
  card: { backgroundColor: Colors.white, borderRadius: BorderRadius.xl, padding: Spacing.lg, marginBottom: Spacing.md },
  summary: { fontSize: FontSize.md, color: Colors.textPrimary, lineHeight: 24 },
  emptyText: { fontSize: FontSize.sm, color: Colors.textHint },
  doctorHead: { flexDirection: 'row', alignItems: 'center', gap: 6, marginBottom: Spacing.md },
  doctorName: { fontSize: FontSize.md, color: Colors.textPrimary, fontWeight: '600' },
  block: { marginTop: Spacing.sm },
  blockLabel: { fontSize: FontSize.xs, color: Colors.textHint, marginBottom: 4 },
  question: { fontSize: FontSize.sm, color: Colors.textSecondary, lineHeight: 20, marginBottom: 2 },
  bodyText: { fontSize: FontSize.sm, color: Colors.textSecondary, lineHeight: 20 },
});
