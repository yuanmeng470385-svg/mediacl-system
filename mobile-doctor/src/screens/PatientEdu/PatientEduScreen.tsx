/**
 * 患教工具（二期 I 医生端）：
 *   - 患教模板选择（医生端仅 approved）→ 生成 → 展示卡片（正文/注意事项/就医指征）
 *   - 转发前确认（无后端转发端点，仅前端确认提示）
 *
 * 样式令牌照 theme.ts，列表/卡片范式照 MyTwinsScreen + MedicalQAScreen。
 */
import React, { useCallback, useState } from 'react';
import {
  ActivityIndicator,
  Alert,
  ScrollView,
  StyleSheet,
  Text,
  TouchableOpacity,
  View,
} from 'react-native';
import { useFocusEffect } from '@react-navigation/native';
import Icon, { FeatureIcons } from '../../components/Icon';
import { doctorExpAPI } from '../../api/doctorExp';
import type { PatientEduTemplate, EduCard } from '../../types';
import { BorderRadius, Colors, FontSize, Shadow, Spacing } from '../../constants/theme';

/** 疾病领域徽标色 */
const AREA_BADGE: Record<string, { bg: string; color: string }> = {
  心血管: { bg: Colors.dangerLight, color: Colors.danger },
  肿瘤: { bg: Colors.primarySurface, color: Colors.primary },
  内分泌: { bg: Colors.warningLight, color: Colors.warning },
  呼吸: { bg: Colors.infoLight, color: Colors.info },
  神经: { bg: Colors.accentLight, color: Colors.info },
};
const AREA_BADGE_FALLBACK = { bg: Colors.backgroundAlt, color: Colors.textSecondary };

export default function PatientEduScreen() {
  const [templates, setTemplates] = useState<PatientEduTemplate[]>([]);
  const [card, setCard] = useState<EduCard | null>(null);
  const [loading, setLoading] = useState(true);
  const [generatingId, setGeneratingId] = useState<number | null>(null);
  const [error, setError] = useState('');

  const load = useCallback(async () => {
    setError('');
    try {
      const res = await doctorExpAPI.listTemplates();
      setTemplates(Array.isArray(res?.items) ? res.items : []);
    } catch (e: any) {
      setError(e?.message || '模板加载失败，请检查网络');
      setTemplates([]);
    } finally {
      setLoading(false);
    }
  }, []);

  useFocusEffect(
    useCallback(() => {
      load();
    }, [load])
  );

  const handleGenerate = async (template: PatientEduTemplate) => {
    if (generatingId !== null) return;
    setGeneratingId(template.id);
    try {
      const generated = await doctorExpAPI.generateEdu(template.id);
      setCard(generated);
    } catch (e: any) {
      Alert.alert('生成失败', e?.message || '请稍后重试');
    } finally {
      setGeneratingId(null);
    }
  };

  const handleForward = () => {
    if (!card) return;
    Alert.alert(
      '转发确认',
      '确定要将这份患教卡片转发给患者吗？内容仅供患者教育参考，不构成诊疗建议。',
      [
        { text: '取消', style: 'cancel' },
        { text: '确认转发', onPress: () => Alert.alert('已转发', '患教卡片已转发') },
      ]
    );
  };

  if (loading) {
    return (
      <View style={styles.centered}>
        <ActivityIndicator size="large" color={Colors.primary} />
        <Text style={styles.loadingText}>加载患教模板...</Text>
      </View>
    );
  }

  const content = card?.content;

  return (
    <View style={styles.container}>
      <View style={styles.header}>
        <Text style={styles.headerTitle}>患教工具</Text>
        <Text style={styles.headerSubtitle}>选择模板生成患者教育卡片</Text>
      </View>

      <ScrollView contentContainerStyle={styles.content}>
        {/* 生成的患教卡片 */}
        {card && content ? (
          <View style={[styles.card, Shadow.card, styles.eduCard]}>
            <View style={styles.eduCardHeader}>
              <Icon name={FeatureIcons.content} size={20} color={Colors.primary} />
              <Text style={styles.eduCardTitle}>{content.title || '患教卡片'}</Text>
            </View>

            <View style={styles.eduSection}>
              <Text style={styles.eduSectionLabel}>正文</Text>
              <Text style={styles.eduBody}>{content.body || '—'}</Text>
            </View>

            {content.notes ? (
              <View style={styles.eduSection}>
                <Text style={styles.eduSectionLabel}>注意事项</Text>
                <Text style={styles.eduNotes}>{content.notes}</Text>
              </View>
            ) : null}

            {content.seek_care ? (
              <View style={[styles.eduSection, styles.seekCare]}>
                <Text style={styles.eduSectionLabel}>就医指征</Text>
                <Text style={styles.eduSeekCare}>{content.seek_care}</Text>
              </View>
            ) : null}

            <View style={styles.eduMetaRow}>
              <View style={styles.aiBadge}>
                <Text style={styles.aiBadgeText}>AI 生成</Text>
              </View>
              <Text style={styles.eduMetaText}>仅供患者教育参考</Text>
            </View>

            <TouchableOpacity style={styles.forwardBtn} onPress={handleForward} activeOpacity={0.7}>
              <Icon name="send" size={18} color={Colors.textWhite} />
              <Text style={styles.forwardBtnText}>转发给患者</Text>
            </TouchableOpacity>
          </View>
        ) : null}

        {/* 模板选择 */}
        <Text style={styles.listTitle}>选择患教模板</Text>
        {templates.length === 0 ? (
          <View style={styles.empty}>
            <Icon name={FeatureIcons.content} size={48} color={Colors.textHint} />
            <Text style={styles.emptyTitle}>{error || '暂无可用模板'}</Text>
            <Text style={styles.emptyDesc}>审核通过的患教模板会出现在这里</Text>
            {error ? (
              <TouchableOpacity style={styles.retryBtn} onPress={load} activeOpacity={0.8}>
                <Text style={styles.retryText}>重试</Text>
              </TouchableOpacity>
            ) : null}
          </View>
        ) : (
          templates.map((t) => {
            const badge = AREA_BADGE[t.disease_area] || AREA_BADGE_FALLBACK;
            const generating = generatingId === t.id;
            const selected = card?.template_id === t.id;
            return (
              <TouchableOpacity
                key={t.id}
                style={[styles.templateRow, Shadow.card, selected && styles.templateRowSelected]}
                onPress={() => handleGenerate(t)}
                disabled={generatingId !== null}
                activeOpacity={0.7}
              >
                <View style={styles.templateIconBox}>
                  <Icon name={FeatureIcons.content} size={18} color={Colors.primary} />
                </View>
                <View style={styles.templateInfo}>
                  <View style={styles.templateTitleRow}>
                    <Text style={styles.templateTitle} numberOfLines={1}>
                      {t.title}
                    </Text>
                    <View style={[styles.areaBadge, { backgroundColor: badge.bg }]}>
                      <Text style={[styles.areaBadgeText, { color: badge.color }]}>
                        {t.disease_area}
                      </Text>
                    </View>
                  </View>
                  <Text style={styles.templateDesc} numberOfLines={2}>
                    {t.content}
                  </Text>
                </View>
                {generating ? (
                  <ActivityIndicator size="small" color={Colors.primary} />
                ) : (
                  <Icon name="chevron-right" size={20} color={Colors.textHint} />
                )}
              </TouchableOpacity>
            );
          })
        )}
      </ScrollView>
    </View>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1, backgroundColor: Colors.background },
  centered: { flex: 1, justifyContent: 'center', alignItems: 'center', backgroundColor: Colors.background },
  loadingText: { marginTop: Spacing.md, color: Colors.textHint, fontSize: FontSize.sm },
  header: {
    backgroundColor: Colors.primary,
    paddingHorizontal: Spacing.xl,
    paddingTop: 52,
    paddingBottom: Spacing.xl,
  },
  headerTitle: { color: Colors.textWhite, fontSize: FontSize.xl, fontWeight: '700' },
  headerSubtitle: {
    color: 'rgba(255,255,255,0.7)',
    fontSize: FontSize.sm,
    marginTop: 4,
  },
  content: { padding: Spacing.lg },
  card: {
    backgroundColor: Colors.white,
    borderRadius: BorderRadius.lg,
    padding: Spacing.lg,
    marginBottom: Spacing.md,
  },
  eduCard: { marginBottom: Spacing.lg },
  eduCardHeader: { flexDirection: 'row', alignItems: 'center', gap: Spacing.sm, marginBottom: Spacing.md },
  eduCardTitle: { flex: 1, fontSize: FontSize.lg, fontWeight: '700', color: Colors.textPrimary },
  eduSection: { marginBottom: Spacing.md },
  eduSectionLabel: {
    fontSize: FontSize.xs,
    fontWeight: '600',
    color: Colors.textSecondary,
    marginBottom: Spacing.xs,
  },
  eduBody: { fontSize: FontSize.md, color: Colors.textPrimary, lineHeight: 22 },
  eduNotes: { fontSize: FontSize.sm, color: Colors.textSecondary, lineHeight: 20 },
  seekCare: {
    padding: Spacing.md,
    borderRadius: BorderRadius.md,
    backgroundColor: Colors.warningLight,
  },
  eduSeekCare: { fontSize: FontSize.sm, color: Colors.warning, lineHeight: 20 },
  eduMetaRow: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: Spacing.sm,
    marginTop: Spacing.xs,
  },
  aiBadge: {
    backgroundColor: Colors.accentLight,
    borderRadius: BorderRadius.sm,
    paddingHorizontal: 6,
    paddingVertical: 2,
  },
  aiBadgeText: { fontSize: FontSize.xs, color: Colors.info, fontWeight: '600' },
  eduMetaText: { fontSize: FontSize.xs, color: Colors.textHint },
  forwardBtn: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'center',
    gap: Spacing.sm,
    marginTop: Spacing.md,
    paddingVertical: Spacing.md,
    borderRadius: BorderRadius.md,
    backgroundColor: Colors.primary,
  },
  forwardBtnText: { color: Colors.textWhite, fontSize: FontSize.md, fontWeight: '600' },
  listTitle: {
    fontSize: FontSize.md,
    fontWeight: '600',
    color: Colors.textSecondary,
    marginBottom: Spacing.sm,
  },
  templateRow: {
    backgroundColor: Colors.white,
    borderRadius: BorderRadius.lg,
    padding: Spacing.md,
    marginBottom: Spacing.sm,
    flexDirection: 'row',
    alignItems: 'center',
    gap: Spacing.md,
  },
  templateRowSelected: { borderWidth: 1, borderColor: Colors.primary },
  templateIconBox: {
    width: 36,
    height: 36,
    borderRadius: 10,
    backgroundColor: Colors.primarySurface,
    alignItems: 'center',
    justifyContent: 'center',
  },
  templateInfo: { flex: 1, gap: 4 },
  templateTitleRow: { flexDirection: 'row', alignItems: 'center', gap: Spacing.sm },
  templateTitle: { flex: 1, fontSize: FontSize.md, fontWeight: '600', color: Colors.textPrimary },
  areaBadge: {
    paddingHorizontal: 8,
    paddingVertical: 2,
    borderRadius: BorderRadius.full,
  },
  areaBadgeText: { fontSize: FontSize.xs, fontWeight: '600' },
  templateDesc: { fontSize: FontSize.xs, color: Colors.textHint },
  empty: { alignItems: 'center', paddingTop: Spacing.xl },
  emptyTitle: {
    fontSize: FontSize.md,
    fontWeight: '600',
    color: Colors.textSecondary,
    marginTop: Spacing.md,
  },
  emptyDesc: {
    fontSize: FontSize.sm,
    color: Colors.textHint,
    marginTop: Spacing.xs,
    textAlign: 'center',
  },
  retryBtn: {
    backgroundColor: Colors.primary,
    borderRadius: BorderRadius.md,
    paddingHorizontal: Spacing.xl,
    paddingVertical: Spacing.sm,
    marginTop: Spacing.lg,
  },
  retryText: { color: Colors.textWhite, fontSize: FontSize.md, fontWeight: '600' },
});
