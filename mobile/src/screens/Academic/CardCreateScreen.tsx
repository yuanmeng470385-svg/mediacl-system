/**
 * 学术卡片创建（二期 G，需求 4.6(1)(3)）：
 *   标题/主题输入 → createCard 生成（结论/要点/引用）→ 订阅医生多选推送。
 * 2026-09-03 业务审查批：推送对象从"手输数字 doctor_id"改为订阅医生勾选列表。
 * 样式参照 ComplianceCenterScreen（临床精准风）。
 */
import React, { useEffect, useState } from 'react';
import {
  Alert, ScrollView, StyleSheet, Text, TextInput, TouchableOpacity, View,
} from 'react-native';
import { useNavigation } from '@react-navigation/native';
import type { NativeStackNavigationProp } from '@react-navigation/native-stack';
import Icon from '../../components/Icon';
import { academicAPI, PushTarget } from '../../api/academic';
import type { AcademicCard } from '../../types';
import type { RootStackParamList } from '../../navigation/types';
import { BorderRadius, Colors, FontSize, Shadow, Spacing } from '../../constants/theme';

type Nav = NativeStackNavigationProp<RootStackParamList>;

export default function CardCreateScreen() {
  const navigation = useNavigation<Nav>();
  const [title, setTitle] = useState('');
  const [topic, setTopic] = useState('');
  const [card, setCard] = useState<AcademicCard | null>(null);
  const [generating, setGenerating] = useState(false);

  const [targets, setTargets] = useState<PushTarget[]>([]);
  const [targetsLoading, setTargetsLoading] = useState(false);
  const [selected, setSelected] = useState<Set<number>>(new Set());
  const [pushing, setPushing] = useState(false);
  const [pushResult, setPushResult] = useState<string>('');

  // 生成卡片成功后拉取可推送的订阅医生（本人分身的订阅者）
  useEffect(() => {
    if (!card) return;
    let cancelled = false;
    setTargetsLoading(true);
    academicAPI.pushTargets()
      .then((res) => { if (!cancelled) setTargets(res?.items || []); })
      .catch(() => { /* 拉取失败保留空列表，推送时报错提示 */ })
      .finally(() => { if (!cancelled) setTargetsLoading(false); });
    return () => { cancelled = true; };
  }, [card?.id]);

  const toggleDoctor = (id: number) => {
    setSelected((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id); else next.add(id);
      return next;
    });
  };

  const generate = async () => {
    if (!title.trim()) {
      Alert.alert('提示', '请先输入卡片标题');
      return;
    }
    if (!topic.trim()) {
      Alert.alert('提示', '请先输入主题');
      return;
    }
    setGenerating(true);
    setPushResult('');
    try {
      const created = await academicAPI.createCard({ title: title.trim(), topic: topic.trim() });
      setCard(created);
    } catch (err: any) {
      Alert.alert('生成失败', err?.message || '请稍后重试');
    } finally {
      setGenerating(false);
    }
  };

  const push = async () => {
    if (!card) return;
    const ids = Array.from(selected);
    if (ids.length === 0) {
      Alert.alert('提示', '请至少勾选一位订阅医生');
      return;
    }
    if (ids.length > 50) {
      Alert.alert('提示', '一次最多推送 50 位医生');
      return;
    }
    setPushing(true);
    try {
      const res = await academicAPI.pushCard(card.id, ids);
      setPushResult(`推送成功 ${res.pushed} 位，跳过 ${res.skipped} 位（未订阅或已推送）`);
      Alert.alert('已推送', `成功 ${res.pushed} 位，跳过 ${res.skipped} 位`);
    } catch (err: any) {
      Alert.alert('推送失败', err?.message || '请稍后重试');
    } finally {
      setPushing(false);
    }
  };

  const citations = card?.content?.citations || [];

  return (
    <View style={styles.container}>
      <View style={styles.header}>
        <TouchableOpacity onPress={() => navigation.goBack()} style={styles.headerBtn}>
          <Icon name="chevron-left" size={22} color={Colors.textWhite} />
        </TouchableOpacity>
        <Text style={styles.headerTitle}>创建学术卡片</Text>
        <TouchableOpacity onPress={() => navigation.navigate('AcademicCardList')} style={styles.headerBtn}>
          <Text style={styles.headerAction}>我的卡片</Text>
        </TouchableOpacity>
      </View>

      <ScrollView contentContainerStyle={styles.content} keyboardShouldPersistTaps="handled">
        {/* 生成表单卡 */}
        <View style={[styles.card, Shadow.card]}>
          <Text style={styles.cardTitle}>生成学术卡片</Text>
          <Text style={styles.label}>标题</Text>
          <TextInput
            style={styles.input}
            value={title}
            onChangeText={setTitle}
            placeholder="如 高血压诊疗指南要点"
            placeholderTextColor={Colors.textHint}
            maxLength={200}
          />
          <Text style={styles.label}>主题</Text>
          <TextInput
            style={styles.input}
            value={topic}
            onChangeText={setTopic}
            placeholder="如 高血压"
            placeholderTextColor={Colors.textHint}
          />
          <TouchableOpacity
            style={[styles.submitBtn, generating && { opacity: 0.6 }]}
            disabled={generating}
            onPress={generate}
            activeOpacity={0.7}
          >
            <Text style={styles.submitText}>{generating ? '生成中…' : '生成卡片'}</Text>
          </TouchableOpacity>
          <Text style={styles.footnote}>内容由 AI 基于知识库引用生成，并经合规预检后落库</Text>
        </View>

        {/* 生成结果卡 */}
        {card && (
          <View style={[styles.card, Shadow.card]}>
            <Text style={styles.cardTitle}>{card.title}</Text>
            <View style={[styles.statusBadge, { backgroundColor: Colors.successLight }]}>
              <Icon name="check-circle" size={14} color={Colors.success} />
              <Text style={[styles.statusText, { color: Colors.success }]}>已过审</Text>
            </View>
            {card.content?.conclusion ? (
              <Text style={styles.conclusion}>{card.content.conclusion}</Text>
            ) : null}
            {card.content?.key_points?.length ? (
              <View style={styles.section}>
                <Text style={styles.sectionTitle}>要点</Text>
                {card.content.key_points.map((p, i) => (
                  <View key={i} style={styles.pointRow}>
                    <Icon name="check" size={14} color={Colors.primary} />
                    <Text style={styles.pointText}>{p}</Text>
                  </View>
                ))}
              </View>
            ) : null}
            {card.content?.summary ? (
              <View style={styles.section}>
                <Text style={styles.sectionTitle}>一句话总结</Text>
                <Text style={styles.summaryText}>{card.content.summary}</Text>
              </View>
            ) : null}
            {citations.length > 0 && (
              <View style={styles.section}>
                <Text style={styles.sectionTitle}>引用来源</Text>
                {citations.map((c, i) => (
                  <View key={i} style={styles.citeRow}>
                    <Icon name="file-document-outline" size={14} color={Colors.textHint} />
                    <Text style={styles.citeText} numberOfLines={2}>
                      {c.doc_name || '未命名文献'}
                      {c.version ? ` · ${c.version}` : ''}
                    </Text>
                  </View>
                ))}
              </View>
            )}
          </View>
        )}

        {/* 推送医生卡（订阅医生多选，2026-09-03 业务审查批） */}
        {card && (
          <View style={[styles.card, Shadow.card]}>
            <View style={styles.pushHeader}>
              <Text style={styles.cardTitle}>推送医生</Text>
              {targets.length > 0 && (
                <TouchableOpacity
                  onPress={() => setSelected(
                    selected.size === targets.length ? new Set() : new Set(targets.map((t) => t.doctorId))
                  )}
                >
                  <Text style={styles.selectAll}>
                    {selected.size === targets.length ? '取消全选' : '全选'}
                  </Text>
                </TouchableOpacity>
              )}
            </View>
            {targetsLoading ? (
              <Text style={styles.footnote}>订阅医生加载中…</Text>
            ) : targets.length === 0 ? (
              <Text style={styles.footnote}>
                暂无订阅医生——医生添加你的分身后才能收到卡片（分享入口见「分身分享」）
              </Text>
            ) : (
              targets.map((t) => {
                const on = selected.has(t.doctorId);
                return (
                  <TouchableOpacity
                    key={t.doctorId}
                    style={[styles.doctorRow, on && styles.doctorRowActive]}
                    onPress={() => toggleDoctor(t.doctorId)}
                    activeOpacity={0.7}
                  >
                    <Icon
                      name={on ? 'checkbox-marked-circle' : 'checkbox-blank-circle-outline'}
                      size={22}
                      color={on ? Colors.primary : Colors.textHint}
                    />
                    <View style={styles.doctorInfo}>
                      <Text style={styles.doctorName}>{t.doctorName}</Text>
                      <Text style={styles.doctorSub} numberOfLines={1}>
                        订阅分身：{t.twinNames.join('、')}
                      </Text>
                    </View>
                  </TouchableOpacity>
                );
              })
            )}
            <TouchableOpacity
              style={[styles.submitBtn, (pushing || selected.size === 0) && { opacity: 0.6 }]}
              disabled={pushing || selected.size === 0}
              onPress={push}
              activeOpacity={0.7}
            >
              <Text style={styles.submitText}>
                {pushing ? '推送中…' : selected.size > 0 ? `推送医生（已选 ${selected.size}）` : '推送医生'}
              </Text>
            </TouchableOpacity>
            {pushResult ? <Text style={styles.pushResult}>{pushResult}</Text> : null}
            <Text style={styles.footnote}>仅可推送给订阅了本人分身的医生；已收到过本卡的自动跳过</Text>
          </View>
        )}
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
  headerBtn: { padding: 4, minWidth: 60 },
  headerTitle: { color: Colors.textWhite, fontSize: FontSize.lg, fontWeight: '600' },
  headerAction: { color: Colors.textWhite, fontSize: FontSize.sm, textAlign: 'right' },
  content: { padding: Spacing.md },
  card: {
    backgroundColor: Colors.card, borderRadius: BorderRadius.md,
    padding: Spacing.lg, marginBottom: Spacing.md,
  },
  cardTitle: { fontSize: FontSize.md, fontWeight: '600', color: Colors.textPrimary, marginBottom: Spacing.sm },
  label: { fontSize: FontSize.sm, color: Colors.textSecondary, marginTop: Spacing.sm },
  input: {
    borderWidth: 1, borderColor: Colors.border, borderRadius: BorderRadius.sm,
    padding: Spacing.sm, marginTop: Spacing.xs, color: Colors.textPrimary, fontSize: FontSize.md,
  },
  submitBtn: {
    marginTop: Spacing.lg, backgroundColor: Colors.primary, borderRadius: BorderRadius.sm,
    padding: Spacing.md, alignItems: 'center',
  },
  submitText: { color: Colors.textWhite, fontSize: FontSize.md, fontWeight: '600' },
  footnote: { marginTop: Spacing.sm, fontSize: FontSize.xs, color: Colors.textHint, textAlign: 'center' },
  statusBadge: {
    flexDirection: 'row', alignItems: 'center', alignSelf: 'flex-start',
    gap: 4, paddingHorizontal: 10, paddingVertical: 3, borderRadius: BorderRadius.full,
    marginBottom: Spacing.sm,
  },
  statusText: { fontSize: 12, fontWeight: '600' },
  conclusion: { fontSize: FontSize.md, color: Colors.textPrimary, lineHeight: 22, marginTop: Spacing.xs },
  section: { marginTop: Spacing.md },
  sectionTitle: { fontSize: FontSize.sm, fontWeight: '600', color: Colors.textSecondary, marginBottom: Spacing.xs },
  pointRow: { flexDirection: 'row', alignItems: 'flex-start', gap: 6, marginTop: 4 },
  pointText: { flex: 1, fontSize: FontSize.sm, color: Colors.textPrimary, lineHeight: 20 },
  summaryText: { fontSize: FontSize.sm, color: Colors.textPrimary, lineHeight: 20 },
  citeRow: { flexDirection: 'row', alignItems: 'flex-start', gap: 6, marginTop: 4 },
  citeText: { flex: 1, fontSize: FontSize.sm, color: Colors.textSecondary },
  pushResult: { marginTop: Spacing.sm, fontSize: FontSize.sm, color: Colors.success },
  pushHeader: { flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center' },
  selectAll: { fontSize: FontSize.sm, color: Colors.primary },
  doctorRow: {
    flexDirection: 'row', alignItems: 'center', paddingVertical: Spacing.sm,
    paddingHorizontal: Spacing.sm, borderRadius: BorderRadius.sm, marginBottom: 4,
    backgroundColor: Colors.backgroundAlt,
  },
  doctorRowActive: { backgroundColor: Colors.primarySurface },
  doctorInfo: { flex: 1, marginLeft: Spacing.sm },
  doctorName: { fontSize: FontSize.md, color: Colors.textPrimary },
  doctorSub: { fontSize: FontSize.xs, color: Colors.textHint, marginTop: 2 },
});
