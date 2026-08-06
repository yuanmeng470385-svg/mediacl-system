/**
 * 拜访前准备页 - 快速了解医生、准备话题、避免踩雷
 * 临床精准风
 */
import React, { useEffect, useState } from 'react';
import {
  View, Text, ScrollView, StyleSheet, TouchableOpacity,
  ActivityIndicator, Alert,
} from 'react-native';
import { useRoute, useNavigation } from '@react-navigation/native';
import type { RouteProp } from '@react-navigation/native';
import type { NativeStackNavigationProp } from '@react-navigation/native-stack';
import { visitAPI } from '../../api/visit';
import { formatLocalDate } from '../../utils/date';
import Icon from '../../components/Icon';
import { ActionIcons, VisitIcons } from '../../components/Icon';
import { Colors, FontSize, Spacing, BorderRadius, Shadow } from '../../constants/theme';
import type { VisitPrepareParams, RootStackParamList } from '../../navigation/types';
import type { VisitPrepareData } from '../../types';

type RouteType = RouteProp<{ VisitPrepare: VisitPrepareParams }, 'VisitPrepare'>;
type Nav = NativeStackNavigationProp<RootStackParamList>;

export default function VisitPrepareScreen() {
  const route = useRoute<RouteType>();
  const navigation = useNavigation<Nav>();
  const { hcpId, hcpName, productId } = route.params;

  const [data, setData] = useState<VisitPrepareData | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [selectedTopics, setSelectedTopics] = useState<Set<string>>(new Set());

  useEffect(() => { loadPrepareData(); }, []);

  // 真实失败显示错误态 + 重试，不用假数据兜底
  const loadPrepareData = async () => {
    try {
      const result = await visitAPI.prepareVisit({ hcpId, productId: productId || 1 });
      setData(result);
      if (result.recommendations?.suggested_topics) {
        setSelectedTopics(new Set(result.recommendations.suggested_topics));
      }
    } catch (e: any) {
      setError(e?.message || '无法获取拜访准备数据');
    } finally {
      setLoading(false);
    }
  };

  const retry = () => {
    setError('');
    setLoading(true);
    loadPrepareData();
  };

  const toggleTopic = (topic: string) => {
    setSelectedTopics((prev) => {
      const next = new Set(prev);
      next.has(topic) ? next.delete(topic) : next.add(topic);
      return next;
    });
  };

  const handleStartVisit = async () => {
    try {
      const result = await visitAPI.startVisit({
        hcp_id: hcpId, product_id: productId || 1,
        // 本地日期（toISOString 是 UTC，东八区凌晨会取成昨天）
        planned_date: formatLocalDate(),
        notes: `推荐话题：${[...selectedTopics].join('、')}`,
      });
      navigation.replace('VisitInProgress', { visitId: result.visit_id, hcpName });
    } catch (e: any) {
      Alert.alert('开始拜访失败', e.message || '请稍后重试');
    }
  };

  if (loading) {
    return (
      <View style={styles.centered}>
        <ActivityIndicator size="large" color={Colors.primary} />
        <Text style={styles.loadingText}>准备拜访资料...</Text>
      </View>
    );
  }

  if (error || !data) {
    return (
      <View style={styles.centered}>
        <Text style={styles.errorText}>{error || '加载失败'}</Text>
        <TouchableOpacity style={styles.retryBtn} onPress={retry} activeOpacity={0.8}>
          <Text style={styles.retryText}>重试</Text>
        </TouchableOpacity>
      </View>
    );
  }

  return (
    <View style={styles.container}>
      <View style={styles.header}>
        <TouchableOpacity onPress={() => navigation.goBack()}>
          <Icon name={ActionIcons.back} size={22} color={Colors.textWhite} />
        </TouchableOpacity>
        <Text style={styles.headerTitle}>拜访前准备</Text>
        <View style={{ width: 24 }} />
      </View>

      <ScrollView style={styles.content} showsVerticalScrollIndicator={false}>
        {/* 医生信息卡片 */}
        <View style={[styles.card, Shadow.card]}>
          <View style={styles.cardHeader}>
            <Icon name={VisitIcons.doctor} size={22} color={Colors.primary} />
            <Text style={styles.sectionTitle}>医生信息</Text>
          </View>
          <Text style={styles.hcpName}>{data?.hcp_profile?.basic_info?.name || hcpName}</Text>
          <Text style={styles.hcpInfo}>
            {data?.hcp_profile?.basic_info?.hospital} · {data?.hcp_profile?.basic_info?.department} · {data?.hcp_profile?.basic_info?.title}
          </Text>
          {data?.hcp_profile?.communication_advice && (
            <View style={styles.tipBox}>
              <Icon name="lightbulb-outline" size={16} color={Colors.accent} />
              <View style={{ flex: 1 }}>
                <Text style={styles.tipTitle}>沟通建议</Text>
                <Text style={styles.tipText}>最佳时间：{data.hcp_profile.communication_advice.best_time}</Text>
                <Text style={styles.tipText}>偏好方式：{(data.hcp_profile.communication_advice.preferred_channels || []).join('、')}</Text>
              </View>
            </View>
          )}
        </View>

        {/* 推荐话题 */}
        <View style={[styles.card, Shadow.card]}>
          <View style={styles.cardHeader}>
            <Icon name="lightbulb-on-outline" size={22} color={Colors.warning} />
            <Text style={styles.sectionTitle}>推荐话题</Text>
          </View>
          <Text style={styles.hintText}>勾选本次拜访准备讨论的话题</Text>
          {data?.recommendations?.suggested_topics?.map((topic, i) => (
            <TouchableOpacity key={i} style={styles.topicItem} onPress={() => toggleTopic(topic)} activeOpacity={0.7}>
              <View style={[styles.checkbox, selectedTopics.has(topic) && styles.checkboxChecked]}>
                {selectedTopics.has(topic) && <Icon name="check" size={14} color={Colors.textWhite} />}
              </View>
              <Text style={styles.topicText}>{topic}</Text>
            </TouchableOpacity>
          ))}
        </View>

        {/* 红线提醒 */}
        <View style={[styles.card, styles.redCard]}>
          <View style={styles.cardHeader}>
            <Icon name="alert-octagon-outline" size={22} color={Colors.danger} />
            <Text style={styles.redTitle}>合规红线</Text>
          </View>
          {data?.recommendations?.red_lines?.map((line, i) => (
            <View key={i} style={styles.redItem}>
              <View style={styles.redDot} />
              <Text style={styles.redText}>{line}</Text>
            </View>
          ))}
        </View>

        {/* 开场白 */}
        {data?.recommendations?.opening_remarks && (
          <View style={[styles.card, Shadow.card]}>
            <View style={styles.cardHeader}>
              <Icon name="message-text-outline" size={22} color={Colors.primary} />
              <Text style={styles.sectionTitle}>开场白建议</Text>
            </View>
            <View style={styles.openingBox}>
              <Text style={styles.openingText}>{data.recommendations.opening_remarks}</Text>
            </View>
          </View>
        )}

        {/* 参考资料（materials 有就渲染，没有就不渲染该板块） */}
        {data.recommendations?.materials && data.recommendations.materials.length > 0 && (
          <View style={[styles.card, Shadow.card]}>
            <View style={styles.cardHeader}>
              <Icon name="file-document-outline" size={22} color={Colors.accent} />
              <Text style={styles.sectionTitle}>参考资料</Text>
            </View>
            {data.recommendations.materials.map((m, i) => (
              <View key={i} style={styles.materialItem}>
                <View style={styles.materialDot} />
                <View style={{ flex: 1 }}>
                  <Text style={styles.materialTitle}>{m.title}</Text>
                  {!!m.url && <Text style={styles.materialUrl} numberOfLines={1}>{m.url}</Text>}
                </View>
              </View>
            ))}
          </View>
        )}

        {/* 上次跟进 */}
        {data?.recommendations?.last_follow_up && (
          <View style={[styles.card, Shadow.card]}>
            <View style={styles.cardHeader}>
              <Icon name="history" size={22} color={Colors.textSecondary} />
              <Text style={styles.sectionTitle}>上次跟进</Text>
            </View>
            <Text style={styles.followText}>{data.recommendations.last_follow_up}</Text>
          </View>
        )}

        <View style={{ height: 100 }} />
      </ScrollView>

      <View style={styles.bottomBar}>
        <TouchableOpacity style={styles.startBtn} onPress={handleStartVisit} activeOpacity={0.8}>
          <Icon name="play-circle-outline" size={22} color={Colors.textWhite} />
          <Text style={styles.startBtnText}>开始拜访</Text>
        </TouchableOpacity>
      </View>
    </View>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1, backgroundColor: Colors.background },
  centered: { flex: 1, justifyContent: 'center', alignItems: 'center' },
  loadingText: { marginTop: Spacing.md, color: Colors.textHint, fontSize: FontSize.sm },
  header: {
    backgroundColor: Colors.primary, paddingTop: 50, paddingBottom: 14,
    paddingHorizontal: Spacing.lg, flexDirection: 'row',
    alignItems: 'center', justifyContent: 'space-between',
    ...Shadow.header,
  },
  headerTitle: { color: Colors.textWhite, fontSize: FontSize.lg, fontWeight: '600' },
  content: { flex: 1, padding: Spacing.lg },
  card: {
    backgroundColor: Colors.white, borderRadius: BorderRadius.xl,
    padding: Spacing.lg, marginBottom: Spacing.md,
  },
  cardHeader: { flexDirection: 'row', alignItems: 'center', gap: Spacing.sm, marginBottom: Spacing.md },
  sectionTitle: { fontSize: FontSize.lg, fontWeight: '700', color: Colors.textPrimary },
  hintText: { fontSize: FontSize.xs, color: Colors.textHint, marginBottom: Spacing.sm },
  hcpName: { fontSize: FontSize.xl, fontWeight: '700', color: Colors.textPrimary, marginBottom: 4 },
  hcpInfo: { fontSize: FontSize.sm, color: Colors.textSecondary },
  tipBox: {
    marginTop: Spacing.md, backgroundColor: Colors.accentLight,
    padding: Spacing.md, borderRadius: BorderRadius.md,
    flexDirection: 'row', gap: Spacing.sm, alignItems: 'flex-start',
  },
  tipTitle: { fontSize: FontSize.sm, fontWeight: '600', color: Colors.textPrimary, marginBottom: 4 },
  tipText: { fontSize: FontSize.sm, color: Colors.textSecondary, marginTop: 2 },
  topicItem: {
    flexDirection: 'row', alignItems: 'center',
    paddingVertical: Spacing.sm, gap: Spacing.md,
  },
  checkbox: {
    width: 22, height: 22, borderRadius: 6, borderWidth: 2,
    borderColor: Colors.border, alignItems: 'center', justifyContent: 'center',
  },
  checkboxChecked: { backgroundColor: Colors.primary, borderColor: Colors.primary },
  topicText: { fontSize: FontSize.md, color: Colors.textPrimary, flex: 1 },
  redCard: { backgroundColor: Colors.dangerLight, borderWidth: 1, borderColor: '#fecaca' },
  redTitle: { fontSize: FontSize.lg, fontWeight: '700', color: Colors.danger },
  redItem: { flexDirection: 'row', marginBottom: Spacing.sm, gap: Spacing.sm, alignItems: 'center' },
  redDot: { width: 6, height: 6, borderRadius: 3, backgroundColor: Colors.danger },
  redText: { fontSize: FontSize.sm, color: Colors.danger, flex: 1, lineHeight: 20 },
  openingBox: {
    backgroundColor: Colors.primarySurface, padding: Spacing.lg,
    borderRadius: BorderRadius.md, borderLeftWidth: 4, borderLeftColor: Colors.primary,
  },
  openingText: { fontSize: FontSize.md, color: Colors.textPrimary, lineHeight: 24, fontStyle: 'italic' },
  materialItem: {
    flexDirection: 'row', gap: Spacing.sm, alignItems: 'flex-start',
    paddingVertical: Spacing.xs,
  },
  materialDot: {
    width: 6, height: 6, borderRadius: 3, backgroundColor: Colors.accent,
    marginTop: 8,
  },
  materialTitle: { fontSize: FontSize.md, color: Colors.textPrimary, lineHeight: 22 },
  materialUrl: { fontSize: FontSize.xs, color: Colors.textHint, marginTop: 2 },
  errorText: {
    fontSize: FontSize.md, color: Colors.danger,
    marginBottom: Spacing.lg, paddingHorizontal: Spacing.xl, textAlign: 'center',
  },
  retryBtn: {
    backgroundColor: Colors.primary, borderRadius: BorderRadius.md,
    paddingHorizontal: Spacing.xl, paddingVertical: Spacing.sm,
  },
  retryText: { color: Colors.textWhite, fontSize: FontSize.md, fontWeight: '600' },
  followText: { fontSize: FontSize.md, color: Colors.textSecondary, lineHeight: 22 },
  bottomBar: {
    padding: Spacing.lg, paddingBottom: 34, backgroundColor: Colors.white,
    borderTopWidth: 1, borderTopColor: Colors.divider,
  },
  startBtn: {
    backgroundColor: Colors.primary, borderRadius: BorderRadius.lg,
    paddingVertical: 16, flexDirection: 'row',
    alignItems: 'center', justifyContent: 'center', gap: Spacing.sm,
  },
  startBtnText: { color: Colors.textWhite, fontSize: FontSize.lg, fontWeight: '700' },
});
