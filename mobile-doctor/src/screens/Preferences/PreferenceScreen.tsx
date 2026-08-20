/**
 * 偏好 + 个性化学术简报（二期 I 医生端）：
 *   - 兴趣领域多选 / 文献类型单选 / 回复长度单选（本地编辑态）
 *   - 关闭个性化开关（closed）
 *   - 「重新学习」按钮：从本人问答历史自动学习偏好（learnProfile）
 *   - 「保存偏好」：updateProfile 全量提交
 *   - 学术简报展示：getBriefing（无画像/关闭个性化时为空态）
 *
 * 样式令牌照 theme.ts，表单/卡片范式照 mobile SettingsScreen。
 */
import React, { useCallback, useState } from 'react';
import {
  ActivityIndicator,
  Alert,
  ScrollView,
  StyleSheet,
  Switch,
  Text,
  TouchableOpacity,
  View,
} from 'react-native';
import { useFocusEffect } from '@react-navigation/native';
import Icon, { FeatureIcons } from '../../components/Icon';
import { doctorExpAPI } from '../../api/doctorExp';
import type { DoctorProfile, DoctorBriefing } from '../../types';
import { BorderRadius, Colors, FontSize, Shadow, Spacing } from '../../constants/theme';

/** 兴趣领域候选（对齐后端 _AREA_KEYWORDS / patient_edu VALID_AREA） */
const INTEREST_AREAS = ['心血管', '肿瘤', '内分泌', '呼吸', '神经'];

/** 文献类型（对齐后端 VALID_DOC_TYPES） */
const DOC_TYPES: { value: string; label: string }[] = [
  { value: 'guideline', label: '临床指南' },
  { value: 'rct', label: '临床试验' },
  { value: 'real_world', label: '真实世界研究' },
  { value: 'case_report', label: '病例报告' },
];

/** 回复长度（对齐后端 VALID_STYLES） */
const STYLES = ['简洁', '标准', '详尽'];

export default function PreferenceScreen() {
  const [profile, setProfile] = useState<DoctorProfile | null>(null);
  const [interestAreas, setInterestAreas] = useState<string[]>([]);
  const [docType, setDocType] = useState<string | null>(null);
  const [replyStyle, setReplyStyle] = useState<string | null>(null);
  const [closed, setClosed] = useState(false);

  const [briefing, setBriefing] = useState<DoctorBriefing | null>(null);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [learning, setLearning] = useState(false);

  const applyProfile = useCallback((p: DoctorProfile | null) => {
    setProfile(p);
    setInterestAreas(Array.isArray(p?.interest_areas) ? (p!.interest_areas as string[]) : []);
    setDocType(p?.preferred_doc_type ?? null);
    setReplyStyle(p?.preferred_style ?? null);
    setClosed(!!p?.closed);
  }, []);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const [p, b] = await Promise.all([
        doctorExpAPI.getProfile(),
        doctorExpAPI.getBriefing(),
      ]);
      applyProfile(p);
      setBriefing(b);
    } catch {
      // 静默失败：保留空态，下方简报区展示空态
      setBriefing({ items: [], personalized: false });
    } finally {
      setLoading(false);
    }
  }, [applyProfile]);

  useFocusEffect(
    useCallback(() => {
      load();
    }, [load])
  );

  const toggleArea = (area: string) => {
    setInterestAreas((prev) =>
      prev.includes(area) ? prev.filter((a) => a !== area) : [...prev, area]
    );
  };

  const handleSave = async () => {
    if (saving) return;
    setSaving(true);
    try {
      const updated = await doctorExpAPI.updateProfile({
        interest_areas: interestAreas,
        preferred_doc_type: docType,
        preferred_style: replyStyle,
        closed,
      });
      applyProfile(updated);
      // 保存后同步刷新简报（兴趣领域/关闭态变化会影响简报）
      const b = await doctorExpAPI.getBriefing();
      setBriefing(b);
      Alert.alert('已保存', '偏好设置已更新');
    } catch (e: any) {
      Alert.alert('保存失败', e?.message || '请稍后重试');
    } finally {
      setSaving(false);
    }
  };

  const handleLearn = async () => {
    if (learning) return;
    setLearning(true);
    try {
      const updated = await doctorExpAPI.learnProfile();
      applyProfile(updated);
      const b = await doctorExpAPI.getBriefing();
      setBriefing(b);
      Alert.alert('学习完成', '已根据你的问答历史更新偏好');
    } catch (e: any) {
      Alert.alert('学习失败', e?.message || '请稍后重试');
    } finally {
      setLearning(false);
    }
  };

  if (loading) {
    return (
      <View style={styles.centered}>
        <ActivityIndicator size="large" color={Colors.primary} />
        <Text style={styles.loadingText}>加载偏好...</Text>
      </View>
    );
  }

  return (
    <View style={styles.container}>
      <View style={styles.header}>
        <Text style={styles.headerTitle}>学术偏好</Text>
        <Text style={styles.headerSubtitle}>个性化简报与文献推送依据</Text>
      </View>

      <ScrollView contentContainerStyle={styles.content}>
        {/* 关闭个性化 */}
        <View style={[styles.card, Shadow.card]}>
          <View style={styles.switchRow}>
            <View style={styles.rowText}>
              <Text style={styles.sectionTitle}>个性化推荐</Text>
              <Text style={styles.sectionDesc}>关闭后不再基于偏好生成学术简报</Text>
            </View>
            <Switch
              value={!closed}
              onValueChange={(v) => setClosed(!v)}
              trackColor={{ false: Colors.border, true: Colors.primaryLight }}
              thumbColor={Colors.white}
            />
          </View>
        </View>

        {/* 兴趣领域多选 */}
        <View style={[styles.card, Shadow.card]}>
          <Text style={styles.sectionTitle}>兴趣领域（可多选）</Text>
          <View style={styles.chipWrap}>
            {INTEREST_AREAS.map((area) => {
              const active = interestAreas.includes(area);
              return (
                <TouchableOpacity
                  key={area}
                  style={[styles.chip, active && styles.chipActive]}
                  onPress={() => toggleArea(area)}
                  activeOpacity={0.7}
                >
                  <Text style={[styles.chipText, active && styles.chipTextActive]}>{area}</Text>
                </TouchableOpacity>
              );
            })}
          </View>
        </View>

        {/* 文献类型 */}
        <View style={[styles.card, Shadow.card]}>
          <Text style={styles.sectionTitle}>文献类型偏好</Text>
          <View style={styles.chipWrap}>
            {DOC_TYPES.map((t) => {
              const active = docType === t.value;
              return (
                <TouchableOpacity
                  key={t.value}
                  style={[styles.chip, active && styles.chipActive]}
                  onPress={() => setDocType(t.value)}
                  activeOpacity={0.7}
                >
                  <Text style={[styles.chipText, active && styles.chipTextActive]}>{t.label}</Text>
                </TouchableOpacity>
              );
            })}
          </View>
        </View>

        {/* 回复长度 */}
        <View style={[styles.card, Shadow.card]}>
          <Text style={styles.sectionTitle}>回复长度偏好</Text>
          <View style={styles.chipWrap}>
            {STYLES.map((s) => {
              const active = replyStyle === s;
              return (
                <TouchableOpacity
                  key={s}
                  style={[styles.chip, active && styles.chipActive]}
                  onPress={() => setReplyStyle(s)}
                  activeOpacity={0.7}
                >
                  <Text style={[styles.chipText, active && styles.chipTextActive]}>{s}</Text>
                </TouchableOpacity>
              );
            })}
          </View>
        </View>

        {/* 操作按钮 */}
        <View style={styles.actionsRow}>
          <TouchableOpacity
            style={[styles.outlineBtn, learning && { opacity: 0.6 }]}
            onPress={handleLearn}
            disabled={learning}
            activeOpacity={0.7}
          >
            {learning ? (
              <ActivityIndicator size="small" color={Colors.primary} />
            ) : (
              <Icon name="refresh" size={18} color={Colors.primary} />
            )}
            <Text style={styles.outlineBtnText}>重新学习</Text>
          </TouchableOpacity>
          <TouchableOpacity
            style={[styles.primaryBtn, saving && { opacity: 0.6 }]}
            onPress={handleSave}
            disabled={saving}
            activeOpacity={0.7}
          >
            {saving ? (
              <ActivityIndicator size="small" color={Colors.textWhite} />
            ) : (
              <Text style={styles.primaryBtnText}>保存偏好</Text>
            )}
          </TouchableOpacity>
        </View>

        {/* 学术简报 */}
        <View style={[styles.card, Shadow.card]}>
          <View style={styles.briefHeader}>
            <Icon name={FeatureIcons.knowledge} size={20} color={Colors.primary} />
            <Text style={styles.sectionTitle}>个性化学术简报</Text>
          </View>
          {briefing?.personalized && briefing.items.length > 0 ? (
            briefing.items.map((item, i) => (
              <View key={i} style={[styles.briefItem, i > 0 && styles.rowBorder]}>
                <Text style={styles.briefArea}>{item.area}</Text>
                <Text style={styles.briefSuggestion}>{item.suggestion}</Text>
              </View>
            ))
          ) : (
            <Text style={styles.emptyText}>
              {closed ? '已关闭个性化推荐' : '暂无简报，保存偏好或「重新学习」后生成'}
            </Text>
          )}
        </View>
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
  switchRow: { flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between' },
  rowText: { flex: 1, paddingRight: Spacing.md },
  sectionTitle: { fontSize: FontSize.md, fontWeight: '600', color: Colors.textPrimary },
  sectionDesc: { fontSize: FontSize.xs, color: Colors.textHint, marginTop: 2 },
  chipWrap: { flexDirection: 'row', flexWrap: 'wrap', gap: Spacing.sm, marginTop: Spacing.md },
  chip: {
    paddingHorizontal: Spacing.lg,
    paddingVertical: Spacing.sm,
    borderRadius: BorderRadius.full,
    backgroundColor: Colors.background,
    borderWidth: 1,
    borderColor: Colors.border,
  },
  chipActive: { backgroundColor: Colors.primarySurface, borderColor: Colors.primary },
  chipText: { fontSize: FontSize.sm, color: Colors.textSecondary },
  chipTextActive: { color: Colors.primary, fontWeight: '600' },
  actionsRow: { flexDirection: 'row', gap: Spacing.md, marginBottom: Spacing.md },
  outlineBtn: {
    flex: 1,
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'center',
    gap: Spacing.xs,
    paddingVertical: Spacing.md,
    borderRadius: BorderRadius.md,
    borderWidth: 1,
    borderColor: Colors.primary,
    backgroundColor: Colors.white,
  },
  outlineBtnText: { color: Colors.primary, fontSize: FontSize.md, fontWeight: '600' },
  primaryBtn: {
    flex: 1,
    alignItems: 'center',
    justifyContent: 'center',
    paddingVertical: Spacing.md,
    borderRadius: BorderRadius.md,
    backgroundColor: Colors.primary,
    minHeight: 46,
  },
  primaryBtnText: { color: Colors.textWhite, fontSize: FontSize.md, fontWeight: '600' },
  briefHeader: { flexDirection: 'row', alignItems: 'center', gap: Spacing.sm },
  briefItem: { paddingVertical: Spacing.md },
  briefArea: { fontSize: FontSize.md, fontWeight: '600', color: Colors.primary },
  briefSuggestion: { fontSize: FontSize.sm, color: Colors.textSecondary, marginTop: 2 },
  rowBorder: { borderTopWidth: StyleSheet.hairlineWidth, borderTopColor: Colors.divider },
  emptyText: { fontSize: FontSize.sm, color: Colors.textHint, marginTop: Spacing.md },
});
