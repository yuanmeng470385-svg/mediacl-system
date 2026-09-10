/**
 * 分身管理（二期 H）：分身列表（风格设置表单 + 暂停/启用）+ 风格测试生成（5 题 → 建分身）。
 */
import React, { useCallback, useEffect, useState } from 'react';
import {
  Alert, ScrollView, StyleSheet, Text, TouchableOpacity, View,
} from 'react-native';
import { useNavigation } from '@react-navigation/native';
import type { NativeStackNavigationProp } from '@react-navigation/native-stack';
import Icon from '../../components/Icon';
import { specialistAPI } from '../../api/specialist';
import { twinAPI } from '../../api/practice';
import { useAuth } from '../../store/AuthContext';
import type { RootStackParamList } from '../../navigation/types';
import { BorderRadius, Colors, FontSize, Shadow, Spacing } from '../../constants/theme';

type Nav = NativeStackNavigationProp<RootStackParamList>;

interface TwinStyle {
  formal_level?: string;
  reply_length?: string;
  opening_mode?: string;
}

interface Twin {
  id: number;
  name?: string;
  status?: string;
  representative_id?: number;
  persona?: { style?: TwinStyle } | null;
}

const FORMAL_OPTIONS = ['非常严谨', '标准学术', '略带亲和力'];
const LENGTH_OPTIONS = ['简洁', '标准', '详尽'];
const OPENING_OPTIONS = ['直切主题', '先寒暄再进入'];

/** 风格测试 5 题（每题材 3 个选项，索引 0/1/2） */
const STYLE_QUESTIONS = [
  { q: '面对初次见面的医生，你更倾向如何开场？', options: ['直接介绍产品', '先寒暄再切入', '视场合而定'] },
  { q: '讲解临床数据时，你习惯的详细程度？', options: ['只讲结论', '结论+关键数据', '完整数据与出处'] },
  { q: '当医生提出质疑时，你的反应？', options: ['坚持原观点', '先认可再解释', '顺着对方调整'] },
  { q: '你的沟通语气更接近？', options: ['严谨克制', '平衡专业与亲和', '轻松亲和'] },
  { q: '你希望回复的篇幅？', options: ['简洁扼要', '适中', '详尽充分'] },
];

export default function TwinManageScreen() {
  const navigation = useNavigation<Nav>();
  const { user } = useAuth();
  const [twins, setTwins] = useState<Twin[]>([]);
  const [loaded, setLoaded] = useState(false);
  const [busyId, setBusyId] = useState<number | null>(null);
  const [answers, setAnswers] = useState<number[]>(STYLE_QUESTIONS.map(() => 0));
  const [generating, setGenerating] = useState(false);

  const loadTwins = useCallback(async () => {
    setLoaded(false);
    try {
      const all: any[] = await specialistAPI.list();
      const mine: Twin[] = all.filter((s) => s.representative_id === user?.id);
      setTwins(mine);
    } catch {
      // 保留空列表
    } finally {
      setLoaded(true);
    }
  }, [user?.id]);

  useEffect(() => {
    loadTwins();
  }, [loadTwins]);

  // 从「从历史记录生成分身」返回时刷新列表（生成成功后新分身要出现）
  useEffect(() => {
    const unsub = navigation.addListener('focus', loadTwins);
    return unsub;
  }, [navigation, loadTwins]);

  const togglePause = async (twin: Twin) => {
    setBusyId(twin.id);
    try {
      if (twin.status === 'paused') {
        await twinAPI.resume(twin.id);
      } else {
        await twinAPI.pause(twin.id);
      }
      await loadTwins();
    } catch (err: any) {
      Alert.alert('操作失败', err?.message || '请稍后重试');
    } finally {
      setBusyId(null);
    }
  };

  const saveStyle = async (twin: Twin, style: TwinStyle) => {
    if (!style.formal_level && !style.reply_length && !style.opening_mode) return;
    setBusyId(twin.id);
    try {
      await twinAPI.setStyle(twin.id, style as Record<string, string>);
      Alert.alert('已保存', '分身风格已更新');
      await loadTwins();
    } catch (err: any) {
      Alert.alert('保存失败', err?.message || '请稍后重试');
    } finally {
      setBusyId(null);
    }
  };

  const generate = async () => {
    setGenerating(true);
    try {
      const twin = await twinAPI.styleTest(answers);
      Alert.alert('生成成功', `已创建分身「${twin?.name || '我的分身'}」`);
      setAnswers(STYLE_QUESTIONS.map(() => 0));
      await loadTwins();
    } catch (err: any) {
      Alert.alert('生成失败', err?.message || '请稍后重试');
    } finally {
      setGenerating(false);
    }
  };

  return (
    <View style={styles.container}>
      <View style={styles.header}>
        <TouchableOpacity onPress={() => navigation.goBack()}>
          <Icon name="chevron-left" size={22} color={Colors.textWhite} />
        </TouchableOpacity>
        <Text style={styles.headerTitle}>分身管理</Text>
        <View style={{ width: 24 }} />
      </View>

      <ScrollView contentContainerStyle={styles.content}>
        {/* 分身列表 */}
        <View style={[styles.card, Shadow.card]}>
          <Text style={styles.cardTitle}>我的分身</Text>
          {!loaded ? (
            <Text style={styles.emptyText}>加载中…</Text>
          ) : twins.length === 0 ? (
            <Text style={styles.emptyText}>暂无分身，用下方风格测试生成一个吧</Text>
          ) : (
            twins.map((twin) => (
              <View key={twin.id} style={styles.twinCard}>
                <View style={styles.twinTop}>
                  <View style={styles.iconBox}>
                    <Icon name="robot-outline" size={18} color={Colors.primary} />
                  </View>
                  <Text style={styles.twinName} numberOfLines={1}>{twin.name || `分身 #${twin.id}`}</Text>
                  <View style={[styles.statusPill, twin.status === 'active' ? styles.pillActive : styles.pillPaused]}>
                    <Text style={[styles.statusText, twin.status === 'active' ? styles.statusTextActive : styles.statusTextPaused]}>
                      {twin.status === 'active' ? '工作中' : twin.status === 'paused' ? '已暂停' : twin.status || '草稿'}
                    </Text>
                  </View>
                </View>

                <StylePicker
                  label="正式程度"
                  options={FORMAL_OPTIONS}
                  value={twin.persona?.style?.formal_level}
                  onChange={(v) => saveStyle(twin, { formal_level: v })}
                />
                <StylePicker
                  label="回复长度"
                  options={LENGTH_OPTIONS}
                  value={twin.persona?.style?.reply_length}
                  onChange={(v) => saveStyle(twin, { reply_length: v })}
                />
                <StylePicker
                  label="开场方式"
                  options={OPENING_OPTIONS}
                  value={twin.persona?.style?.opening_mode}
                  onChange={(v) => saveStyle(twin, { opening_mode: v })}
                />

                <TouchableOpacity
                  style={[styles.toggleBtn, twin.status === 'paused' && styles.toggleBtnResume]}
                  disabled={busyId === twin.id}
                  onPress={() => togglePause(twin)}
                  activeOpacity={0.7}
                >
                  <Icon
                    name={twin.status === 'paused' ? 'play' : 'pause'}
                    size={16}
                    color={twin.status === 'paused' ? Colors.success : Colors.danger}
                  />
                  <Text style={[styles.toggleText, twin.status === 'paused' && { color: Colors.success }]}>
                    {busyId === twin.id ? '处理中…' : twin.status === 'paused' ? '启用' : '暂停'}
                  </Text>
                </TouchableOpacity>
              </View>
            ))
          )}
        </View>

        {/* 风格测试生成 */}
        <View style={[styles.card, Shadow.card]}>
          <Text style={styles.cardTitle}>风格测试生成分身</Text>
          <Text style={styles.hint}>回答 5 题，系统按你的风格画像创建专属分身</Text>
          {/* 2026-09-10 双入口：也可选历史对话记录，由 AI 从真实发言提炼风格 */}
          <TouchableOpacity
            style={styles.fromRecordsBtn}
            onPress={() => navigation.navigate('StyleSource')}
            activeOpacity={0.7}
          >
            <Icon name="history" size={16} color={Colors.primary} />
            <Text style={styles.fromRecordsText}>用我的真实对话记录生成（推荐）</Text>
            <Icon name="chevron-right" size={16} color={Colors.border} />
          </TouchableOpacity>
          {STYLE_QUESTIONS.map((item, qi) => (
            <View key={qi} style={styles.question}>
              <Text style={styles.questionText}>{qi + 1}. {item.q}</Text>
              <View style={styles.chipWrap}>
                {item.options.map((opt, oi) => {
                  const active = answers[qi] === oi;
                  return (
                    <TouchableOpacity
                      key={oi}
                      style={[styles.chip, active && styles.chipActive]}
                      onPress={() => setAnswers((prev) => prev.map((a, i) => (i === qi ? oi : a)))}
                      activeOpacity={0.7}
                    >
                      <Text style={[styles.chipText, active && styles.chipTextActive]}>{opt}</Text>
                    </TouchableOpacity>
                  );
                })}
              </View>
            </View>
          ))}
          <TouchableOpacity
            style={[styles.generateBtn, generating && { opacity: 0.6 }]}
            disabled={generating}
            onPress={generate}
            activeOpacity={0.7}
          >
            <Icon name="account-tie-outline" size={18} color={Colors.textWhite} />
            <Text style={styles.generateText}>{generating ? '生成中…' : '生成分身'}</Text>
          </TouchableOpacity>
        </View>
      </ScrollView>
    </View>
  );
}

function StylePicker({ label, options, value, onChange }: {
  label: string; options: string[]; value?: string; onChange: (v: string) => void;
}) {
  return (
    <View style={styles.picker}>
      <Text style={styles.pickerLabel}>{label}</Text>
      <View style={styles.chipWrap}>
        {options.map((opt) => {
          const active = value === opt;
          return (
            <TouchableOpacity
              key={opt}
              style={[styles.chip, active && styles.chipActive]}
              onPress={() => onChange(opt)}
              activeOpacity={0.7}
            >
              <Text style={[styles.chipText, active && styles.chipTextActive]}>{opt}</Text>
            </TouchableOpacity>
          );
        })}
      </View>
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
  content: { padding: Spacing.md },
  card: { backgroundColor: Colors.card, borderRadius: BorderRadius.md, padding: Spacing.lg, marginBottom: Spacing.md },
  cardTitle: { fontSize: FontSize.md, fontWeight: '600', color: Colors.textPrimary, marginBottom: Spacing.sm },
  hint: { fontSize: FontSize.xs, color: Colors.textHint, marginBottom: Spacing.md },
  emptyText: { fontSize: FontSize.sm, color: Colors.textHint, textAlign: 'center', paddingVertical: Spacing.lg },
  twinCard: { borderWidth: 1, borderColor: Colors.divider, borderRadius: BorderRadius.md, padding: Spacing.md, marginBottom: Spacing.md },
  twinTop: { flexDirection: 'row', alignItems: 'center', gap: Spacing.sm, marginBottom: Spacing.sm },
  iconBox: {
    width: 36, height: 36, borderRadius: 10,
    backgroundColor: Colors.primarySurface, alignItems: 'center', justifyContent: 'center',
  },
  twinName: { flex: 1, fontSize: FontSize.md, fontWeight: '600', color: Colors.textPrimary },
  statusPill: { borderRadius: BorderRadius.full, paddingHorizontal: Spacing.sm, paddingVertical: 2 },
  pillActive: { backgroundColor: Colors.successLight },
  pillPaused: { backgroundColor: Colors.warningLight },
  statusText: { fontSize: FontSize.xs, fontWeight: '600' },
  statusTextActive: { color: Colors.success },
  statusTextPaused: { color: Colors.warning },
  picker: { marginBottom: Spacing.sm },
  pickerLabel: { fontSize: FontSize.xs, color: Colors.textSecondary, marginBottom: Spacing.xs },
  chipWrap: { flexDirection: 'row', flexWrap: 'wrap', gap: Spacing.sm },
  chip: {
    paddingHorizontal: Spacing.md, paddingVertical: Spacing.xs,
    borderRadius: BorderRadius.full, borderWidth: 1, borderColor: Colors.border,
    backgroundColor: Colors.white,
  },
  chipActive: { backgroundColor: Colors.primarySurface, borderColor: Colors.primary },
  chipText: { fontSize: FontSize.sm, color: Colors.textSecondary },
  chipTextActive: { color: Colors.primary, fontWeight: '600' },
  toggleBtn: {
    marginTop: Spacing.sm, flexDirection: 'row', alignItems: 'center', justifyContent: 'center',
    gap: Spacing.sm, borderWidth: 1, borderColor: Colors.danger,
    borderRadius: BorderRadius.sm, padding: Spacing.sm,
  },
  toggleBtnResume: { borderColor: Colors.success },
  toggleText: { color: Colors.danger, fontSize: FontSize.sm, fontWeight: '600' },
  question: { marginBottom: Spacing.md },
  fromRecordsBtn: {
    flexDirection: 'row', alignItems: 'center', gap: Spacing.xs,
    borderWidth: 1, borderColor: Colors.primary, borderRadius: BorderRadius.sm,
    backgroundColor: Colors.primarySurface, padding: Spacing.sm, marginBottom: Spacing.md,
  },
  fromRecordsText: { flex: 1, fontSize: FontSize.sm, color: Colors.primary, fontWeight: '600' },
  questionText: { fontSize: FontSize.sm, color: Colors.textPrimary, marginBottom: Spacing.xs, lineHeight: 20 },
  generateBtn: {
    marginTop: Spacing.sm, backgroundColor: Colors.primary, borderRadius: BorderRadius.sm,
    padding: Spacing.md, alignItems: 'center', flexDirection: 'row',
    justifyContent: 'center', gap: Spacing.sm,
  },
  generateText: { color: Colors.textWhite, fontSize: FontSize.md, fontWeight: '600' },
});
