/**
 * 患教工具（二期 I 医生端）：
 *   - 患教模板选择（医生端仅 approved）→ 生成 → 展示卡片（正文/注意事项/就医指征）
 *   - 转发给患者：RN Share 唤起系统分享 + 后端留痕（028 迁移，2026-09-03 业务
 *     审查批——此前是假 Alert，无真实分享无留痕）
 *
 * 样式令牌照 theme.ts，列表/卡片范式照 MyTwinsScreen + MedicalQAScreen。
 */
import React, { useCallback, useState } from 'react';
import {
  ActivityIndicator,
  Alert,
  ScrollView,
  Share,
  StyleSheet,
  Text,
  TouchableOpacity,
  View,
} from 'react-native';
import { useFocusEffect, useNavigation } from '@react-navigation/native';
import type { NativeStackNavigationProp } from '@react-navigation/native-stack';
import Icon, { FeatureIcons } from '../../components/Icon';
import { doctorExpAPI } from '../../api/doctorExp';
import type { PatientEduTemplate, EduCard } from '../../types';
import type { RootStackParamList } from '../../navigation/types';
import { BorderRadius, Colors, FontSize, Shadow, Spacing } from '../../constants/theme';

type Nav = NativeStackNavigationProp<RootStackParamList>;

/** 疾病领域徽标色 */
const AREA_BADGE: Record<string, { bg: string; color: string }> = {
  心血管: { bg: Colors.dangerLight, color: Colors.danger },
  肿瘤: { bg: Colors.primarySurface, color: Colors.primary },
  内分泌: { bg: Colors.warningLight, color: Colors.warning },
  呼吸: { bg: Colors.infoLight, color: Colors.info },
  神经: { bg: Colors.accentLight, color: Colors.info },
};
const AREA_BADGE_FALLBACK = { bg: Colors.backgroundAlt, color: Colors.textSecondary };

/** 患教审核状态徽标（我的患教列表） */
function auditStatusBadge(status: string | null | undefined) {
  switch (status) {
    case 'pending':
      return { label: '审核中', bg: Colors.warningLight, color: Colors.warning };
    case 'approved':
      return { label: '已上架专区', bg: Colors.successLight, color: Colors.success };
    case 'rejected':
      return { label: '未通过审核', bg: Colors.dangerLight, color: Colors.danger };
    default:
      return { label: '未分享', bg: Colors.backgroundAlt, color: Colors.textSecondary };
  }
}

export default function PatientEduScreen() {
  const navigation = useNavigation<Nav>();
  const [templates, setTemplates] = useState<PatientEduTemplate[]>([]);
  const [card, setCard] = useState<EduCard | null>(null);
  const [myEdu, setMyEdu] = useState<EduCard[]>([]);
  const [loading, setLoading] = useState(true);
  const [generatingId, setGeneratingId] = useState<number | null>(null);
  const [publishing, setPublishing] = useState(false);
  const [withdrawingId, setWithdrawingId] = useState<number | null>(null);
  const [error, setError] = useState('');

  const load = useCallback(async () => {
    setError('');
    try {
      const [tplRes, mineRes] = await Promise.all([
        doctorExpAPI.listTemplates(),
        doctorExpAPI.myEdu(),
      ]);
      setTemplates(Array.isArray(tplRes?.items) ? tplRes.items : []);
      setMyEdu(Array.isArray(mineRes?.items) ? mineRes.items : []);
    } catch (e: any) {
      setError(e?.message || '加载失败，请检查网络');
      setTemplates([]);
      setMyEdu([]);
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

  const handleForward = async () => {
    if (!card) return;
    // 真实转发：唤起系统分享面板（微信/短信等），用户真正发出后回写留痕
    try {
      const res = await Share.share({
        title: card.content.title,
        message: `【${card.content.title}】

${card.content.body}

注意事项：${card.content.notes}
如出现：${card.content.seek_care}，请及时就医。

（内容由 AI 辅助生成，仅供患者教育参考，不构成诊疗建议）`,
      });
      if (res.action === Share.dismissedAction) return; // 用户取消，不留痕
      const updated = await doctorExpAPI.forwardEdu(card.id);
      setCard(updated);
      Alert.alert('已转发', `患教卡片已转发（累计 ${updated.forward_count ?? 1} 次）`);
    } catch (e: any) {
      Alert.alert('转发失败', e?.message || '请稍后重试');
    }
  };

  const handlePublish = async () => {
    if (!card || publishing) return;
    setPublishing(true);
    try {
      const updated = await doctorExpAPI.publishEdu(card.id);
      setCard(updated);
      Alert.alert('分享成功', '已提交审核，通过后专区可见');
    } catch (e: any) {
      Alert.alert('分享失败', e?.message || '请稍后重试');
    } finally {
      setPublishing(false);
    }
  };

  const handleUnpublish = async () => {
    if (!card || publishing) return;
    setPublishing(true);
    try {
      const updated = await doctorExpAPI.unpublishEdu(card.id);
      setCard(updated);
      Alert.alert('已撤回', '已撤回分享');
    } catch (e: any) {
      Alert.alert('撤回失败', e?.message || '请稍后重试');
    } finally {
      setPublishing(false);
    }
  };

  const handleWithdraw = async (record: EduCard) => {
    if (withdrawingId !== null) return;
    setWithdrawingId(record.id);
    try {
      await doctorExpAPI.unpublishEdu(record.id);
      Alert.alert('已撤回', '该患教内容已从专区撤回');
      await load();
    } catch (e: any) {
      Alert.alert('撤回失败', e?.message || '请稍后重试');
    } finally {
      setWithdrawingId(null);
    }
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
  const canWithdraw =
    card?.audit_status === 'pending' ||
    card?.audit_status === 'rejected' ||
    card?.audit_status === 'approved';

  return (
    <View style={styles.container}>
      <View style={styles.header}>
        <View style={styles.headerTopRow}>
          <Text style={styles.headerTitle}>患教工具</Text>
          <TouchableOpacity
            style={styles.zoneEntry}
            onPress={() => navigation.navigate('PatientEduZone')}
            activeOpacity={0.7}
          >
            <Text style={styles.zoneEntryText}>患教专区</Text>
            <Icon name="chevron-right" size={16} color={Colors.textWhite} />
          </TouchableOpacity>
        </View>
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
              {card.audit_status === 'pending' && (
                <View style={[styles.auditBadge, { backgroundColor: Colors.warningLight }]}>
                  <Text style={[styles.auditBadgeText, { color: Colors.warning }]}>审核中</Text>
                </View>
              )}
              {card.audit_status === 'approved' && (
                <View style={[styles.auditBadge, { backgroundColor: Colors.successLight }]}>
                  <Text style={[styles.auditBadgeText, { color: Colors.success }]}>已上架专区</Text>
                </View>
              )}
              {card.audit_status === 'rejected' && (
                <View style={[styles.auditBadge, { backgroundColor: Colors.dangerLight }]}>
                  <Text style={[styles.auditBadgeText, { color: Colors.danger }]}>未通过审核</Text>
                </View>
              )}
              <Text style={styles.eduMetaText}>仅供患者教育参考</Text>
            </View>

            <TouchableOpacity style={styles.forwardBtn} onPress={handleForward} activeOpacity={0.7}>
              <Icon name="send" size={18} color={Colors.textWhite} />
              <Text style={styles.forwardBtnText}>转发给患者</Text>
            </TouchableOpacity>

            {card.audit_status == null && (
              <TouchableOpacity
                style={[styles.publishBtn, publishing && styles.btnDisabled]}
                onPress={handlePublish}
                disabled={publishing}
                activeOpacity={0.7}
              >
                {publishing ? (
                  <ActivityIndicator size="small" color={Colors.textWhite} />
                ) : (
                  <Icon name="send" size={18} color={Colors.textWhite} />
                )}
                <Text style={styles.publishBtnText}>分享到患教专区</Text>
              </TouchableOpacity>
            )}

            {canWithdraw && (
              <TouchableOpacity
                style={[styles.unpublishBtn, publishing && styles.btnDisabled]}
                onPress={handleUnpublish}
                disabled={publishing}
                activeOpacity={0.7}
              >
                {publishing ? (
                  <ActivityIndicator size="small" color={Colors.textSecondary} />
                ) : (
                  <Icon name="undo" size={18} color={Colors.textSecondary} />
                )}
                <Text style={styles.unpublishBtnText}>
                  {card.audit_status === 'pending' ? '撤回分享' : '撤回'}
                </Text>
              </TouchableOpacity>
            )}
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

        {/* 我的患教 */}
        <Text style={styles.listTitle}>我的患教</Text>
        {myEdu.length === 0 ? (
          <View style={styles.empty}>
            <Text style={styles.emptyDesc}>暂无患教记录</Text>
          </View>
        ) : (
          myEdu.map((r) => {
            const badge = auditStatusBadge(r.audit_status);
            const withdrawing = withdrawingId === r.id;
            const canWithdraw = r.audit_status != null;
            return (
              <View key={r.id} style={[styles.myEduRow, Shadow.card]}>
                <View style={styles.myEduInfo}>
                  <Text style={styles.myEduTitle} numberOfLines={1}>
                    {r.content?.title || '患教卡片'}
                  </Text>
                  <View style={[styles.auditBadge, { backgroundColor: badge.bg }]}>
                    <Text style={[styles.auditBadgeText, { color: badge.color }]}>{badge.label}</Text>
                  </View>
                </View>
                {canWithdraw && (
                  <TouchableOpacity
                    style={[styles.withdrawBtn, withdrawing && styles.btnDisabled]}
                    onPress={() => handleWithdraw(r)}
                    disabled={withdrawingId !== null}
                    activeOpacity={0.7}
                  >
                    {withdrawing ? (
                      <ActivityIndicator size="small" color={Colors.textSecondary} />
                    ) : (
                      <Text style={styles.withdrawText}>撤回</Text>
                    )}
                  </TouchableOpacity>
                )}
              </View>
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
  headerTopRow: { flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between' },
  headerTitle: { color: Colors.textWhite, fontSize: FontSize.xl, fontWeight: '700' },
  zoneEntry: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 2,
    paddingVertical: 6,
    paddingLeft: Spacing.md,
    paddingRight: Spacing.xs,
    borderRadius: BorderRadius.full,
    backgroundColor: 'rgba(255,255,255,0.16)',
  },
  zoneEntryText: { color: Colors.textWhite, fontSize: FontSize.sm, fontWeight: '600' },
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
  auditBadge: {
    borderRadius: BorderRadius.sm,
    paddingHorizontal: 6,
    paddingVertical: 2,
  },
  auditBadgeText: { fontSize: FontSize.xs, fontWeight: '600' },
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
  publishBtn: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'center',
    gap: Spacing.sm,
    marginTop: Spacing.sm,
    paddingVertical: Spacing.md,
    borderRadius: BorderRadius.md,
    backgroundColor: Colors.primary,
  },
  publishBtnText: { color: Colors.textWhite, fontSize: FontSize.md, fontWeight: '600' },
  unpublishBtn: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'center',
    gap: Spacing.sm,
    marginTop: Spacing.sm,
    paddingVertical: Spacing.md,
    borderRadius: BorderRadius.md,
    borderWidth: 1,
    borderColor: Colors.border,
    backgroundColor: Colors.white,
  },
  unpublishBtnText: { color: Colors.textSecondary, fontSize: FontSize.md, fontWeight: '600' },
  btnDisabled: { opacity: 0.6 },
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
  myEduRow: {
    backgroundColor: Colors.white,
    borderRadius: BorderRadius.lg,
    padding: Spacing.md,
    marginBottom: Spacing.sm,
    flexDirection: 'row',
    alignItems: 'center',
    gap: Spacing.md,
  },
  myEduInfo: { flex: 1, flexDirection: 'row', alignItems: 'center', gap: Spacing.sm },
  myEduTitle: { flex: 1, fontSize: FontSize.md, fontWeight: '600', color: Colors.textPrimary },
  withdrawBtn: {
    paddingHorizontal: Spacing.md,
    paddingVertical: Spacing.xs,
    borderRadius: BorderRadius.full,
    borderWidth: 1,
    borderColor: Colors.border,
    backgroundColor: Colors.white,
  },
  withdrawText: { fontSize: FontSize.sm, color: Colors.textSecondary, fontWeight: '600' },
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
