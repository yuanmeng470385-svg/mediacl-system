/**
 * 创建分身三步向导（2026-09-15，原 TwinManage 内嵌问卷 + StyleSourceScreen 收编）：
 * 第 1 步 5 题问卷（映射风格三枚举，定大致方向）
 *   → 第 2 步选真实对话记录（可跳过=纯问卷；选了但发言 <10 条不能下一步）
 *   → 第 3 步起名 → style-from-records 一次建成（answers+sources+name）。
 * 后端契约见 twinAPI.styleFromRecords；纯问卷路径不调 LLM 秒建。
 */
import React, { useCallback, useEffect, useMemo, useState } from 'react';
import {
  ActivityIndicator, Alert, ScrollView, StyleSheet, Text, TextInput, TouchableOpacity, View,
} from 'react-native';
import { CommonActions, useNavigation } from '@react-navigation/native';
import Icon from '../../components/Icon';
import { twinAPI } from '../../api/practice';
import { BorderRadius, Colors, FontSize, Shadow, Spacing } from '../../constants/theme';

// 后端 style_from_records 门槛（specialist-service specialists.py）的前端镜像
const MIN_REP_UTTERANCES = 10;
const MAX_SOURCES = 10;

/** 风格问卷 5 题（每题材 3 个选项，索引 0/1/2）——与后端 answers 契约对齐 */
const STYLE_QUESTIONS = [
  { q: '面对初次见面的医生，你更倾向如何开场？', options: ['直接介绍产品', '先寒暄再切入', '视场合而定'] },
  { q: '讲解临床数据时，你习惯的详细程度？', options: ['只讲结论', '结论+关键数据', '完整数据与出处'] },
  { q: '当医生提出质疑时，你的反应？', options: ['坚持原观点', '先认可再解释', '顺着对方调整'] },
  { q: '你的沟通语气更接近？', options: ['严谨克制', '平衡专业与亲和', '轻松亲和'] },
  { q: '你希望回复的篇幅？', options: ['简洁扼要', '适中', '详尽充分'] },
];

/** 问卷答案 → 风格三枚举预览（与后端均值映射同式；后端为准，此处仅第 3 步展示） */
function quizStylePreview(answers: number[]) {
  const avg = answers.reduce((s, a) => s + Math.max(0, Math.min(2, a)), 0) / 5;
  return {
    formal_level: avg < 0.67 ? '非常严谨' : avg < 1.34 ? '标准学术' : '略带亲和力',
    reply_length: avg < 0.67 ? '简洁' : avg < 1.34 ? '标准' : '详尽',
    opening_mode: avg < 1.0 ? '直切主题' : '先寒暄再进入',
  };
}

interface SourceRow {
  key: string;
  type: 'chat' | 'visit' | 'practice';
  id: string | number;
  title: string;
  meta: string;
  count: number;
}

const TYPE_LABELS: Record<SourceRow['type'], string> = {
  chat: '与专员对话',
  visit: '拜访记录',
  practice: '陪练会话',
};

function formatTime(iso?: string): string {
  if (!iso) return '';
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return '';
  const p = (n: number) => String(n).padStart(2, '0');
  return `${p(d.getMonth() + 1)}-${p(d.getDate())} ${p(d.getHours())}:${p(d.getMinutes())}`;
}

const STEP_TITLES = ['风格问卷', '选择真实记录', '为分身起名'];

export default function CreateTwinWizardScreen() {
  const navigation = useNavigation();
  const [step, setStep] = useState(1);
  const [answers, setAnswers] = useState<number[]>(STYLE_QUESTIONS.map(() => 0));

  // 第 2 步素材
  const [rows, setRows] = useState<SourceRow[]>([]);
  const [sourcesLoaded, setSourcesLoaded] = useState(false);
  const [loadFailed, setLoadFailed] = useState(false);
  const [selected, setSelected] = useState<string[]>([]);

  // 第 3 步
  const [name, setName] = useState('');
  const [creating, setCreating] = useState(false);

  const loadSources = useCallback(async () => {
    setSourcesLoaded(false);
    setLoadFailed(false);
    try {
      const res = await twinAPI.styleSources();
      const chats: any[] = Array.isArray(res?.chats) ? res.chats : [];
      const visits: any[] = Array.isArray(res?.visits) ? res.visits : [];
      const practices: any[] = Array.isArray(res?.practices) ? res.practices : [];
      setRows([
        ...chats.map<SourceRow>((c) => ({
          key: `chat:${c.session_id}`, type: 'chat', id: c.session_id,
          title: c.first_question || c.specialist_name || '与专员的对话',
          meta: `${c.specialist_name || '专员'} · ${c.turns} 条${formatTime(c.created_at) ? ` · ${formatTime(c.created_at)}` : ''}`,
          count: c.turns,
        })),
        ...visits.map<SourceRow>((v) => ({
          key: `visit:${v.visit_id}`, type: 'visit', id: v.visit_id,
          title: v.transcript_preview || '拜访医生实录',
          meta: `代表发言 ${v.rep_lines} 条${formatTime(v.visit_time) ? ` · ${formatTime(v.visit_time)}` : ''}`,
          count: v.rep_lines,
        })),
        ...practices.map<SourceRow>((p) => ({
          key: `practice:${p.session_id}`, type: 'practice', id: p.session_id,
          title: p.scenario || `陪练 #${p.session_id}`,
          meta: `轮数 ${p.turn_count ?? 0}${formatTime(p.created_at) ? ` · ${formatTime(p.created_at)}` : ''}`,
          count: p.turn_count ?? 0,
        })),
      ]);
    } catch {
      setLoadFailed(true);
    } finally {
      setSourcesLoaded(true);
    }
  }, []);

  // 进入第 2 步时懒加载素材（第 1 步不浪费一次请求）
  useEffect(() => {
    if (step === 2 && !sourcesLoaded && !loadFailed) loadSources();
  }, [step, sourcesLoaded, loadFailed, loadSources]);

  const grouped = useMemo(() => {
    const order: SourceRow['type'][] = ['chat', 'visit', 'practice'];
    return order
      .map((type) => ({ type, items: rows.filter((r) => r.type === type) }))
      .filter((g) => g.items.length > 0);
  }, [rows]);

  const selectedRows = rows.filter((r) => selected.includes(r.key));
  const repTotal = selectedRows.reduce((sum, r) => sum + r.count, 0);
  // 选了素材但发言不足 → 不能下一步（与后端 ≥10 门槛一致）；一条没选 = 纯问卷路径合法
  const step2Blocked = selected.length > 0 && repTotal < MIN_REP_UTTERANCES;

  const toggle = (key: string) => {
    if (selected.includes(key)) {
      setSelected(selected.filter((x) => x !== key));
      return;
    }
    if (selected.length >= MAX_SOURCES) {
      Alert.alert('最多选择 10 条记录', '素材足够即可，再多不会提升生成质量');
      return;
    }
    setSelected([...selected, key]);
  };

  const create = () => {
    const sources = selectedRows.map((r) => ({ type: r.type, id: r.id }));
    const trimmed = name.trim();
    setCreating(true);
    twinAPI.styleFromRecords(sources, trimmed || undefined, answers)
      .then((twin: any) => {
        Alert.alert('创建成功', `分身「${twin?.name || '我的分身'}」已就绪`, [
          {
            text: '好',
            // 回到 我的分身 列表看新分身（栈：MainTabs → TwinManage → MyTwins）
            onPress: () => navigation.dispatch(CommonActions.reset({
              index: 2,
              routes: [
                { name: 'MainTabs' },
                { name: 'TwinManage' },
                { name: 'MyTwins' },
              ],
            })),
          },
        ]);
      })
      .catch((err: any) => {
        // 4002 限额 / 4003 LLM 失败 / 4xx 素材不合格——后端 message 已是中文
        Alert.alert('创建失败', err?.message || '生成失败，请稍后重试');
      })
      .finally(() => setCreating(false));
  };

  const goBackOne = () => {
    if (step === 1) {
      navigation.goBack();
      return;
    }
    setStep(step - 1);
  };

  const preview = quizStylePreview(answers);

  return (
    <View style={styles.container}>
      <View style={styles.header}>
        <TouchableOpacity onPress={goBackOne}>
          <Icon name="chevron-left" size={22} color={Colors.textWhite} />
        </TouchableOpacity>
        <Text style={styles.headerTitle}>创建分身 · 第 {step}/3 步 {STEP_TITLES[step - 1]}</Text>
        <View style={{ width: 24 }} />
      </View>

      <ScrollView contentContainerStyle={styles.content} keyboardShouldPersistTaps="handled">
        {/* 步骤条 */}
        <View style={styles.stepBar}>
          {[1, 2, 3].map((s) => (
            <View key={s} style={[styles.stepSeg, s <= step && styles.stepSegActive]} />
          ))}
        </View>

        {step === 1 && (
          <View style={[styles.card, Shadow.card]}>
            <Text style={styles.cardTitle}>先答 5 题，确定分身的大致风格方向</Text>
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
          </View>
        )}

        {step === 2 && (
          <View style={[styles.card, Shadow.card]}>
            <Text style={styles.cardTitle}>选择真实对话记录（可选，推荐）</Text>
            <Text style={styles.hint}>
              AI 从你的真实发言提炼说话风格画像，与问卷方向结合；不选则仅按问卷生成。
              三类可混选，本人发言合计 ≥{MIN_REP_UTTERANCES} 条。
            </Text>
            {!sourcesLoaded ? (
              <View style={styles.centerWrap}>
                <ActivityIndicator size="small" color={Colors.primary} />
                <Text style={styles.emptyText}>加载中…</Text>
              </View>
            ) : loadFailed ? (
              <View style={styles.centerWrap}>
                <Text style={styles.emptyText}>记录加载失败</Text>
                <TouchableOpacity style={styles.retryBtn} onPress={loadSources} activeOpacity={0.7}>
                  <Icon name="refresh" size={16} color={Colors.primary} />
                  <Text style={styles.retryText}>重新加载</Text>
                </TouchableOpacity>
              </View>
            ) : rows.length === 0 ? (
              <View style={styles.centerWrap}>
                <Text style={styles.emptyText}>
                  还没有可用的对话记录{'\n'}与专员对话、拜访医生、AI 陪练都会自动留存，{'\n'}积累后可让分身更像你
                </Text>
              </View>
            ) : (
              grouped.map((group) => (
                <View key={group.type} style={styles.groupWrap}>
                  <Text style={styles.groupLabel}>{TYPE_LABELS[group.type]}</Text>
                  {group.items.map((item) => {
                    const active = selected.includes(item.key);
                    return (
                      <TouchableOpacity
                        key={item.key}
                        style={[styles.sessionRow, active && styles.sessionRowActive]}
                        onPress={() => toggle(item.key)}
                        activeOpacity={0.7}
                      >
                        <View style={{ flex: 1 }}>
                          <Text style={styles.sessionScenario} numberOfLines={1}>{item.title}</Text>
                          <Text style={styles.sessionMeta} numberOfLines={1}>{item.meta}</Text>
                        </View>
                        <Icon
                          name={active ? 'check-circle' : 'circle-outline'}
                          size={22}
                          color={active ? Colors.primary : Colors.border}
                        />
                      </TouchableOpacity>
                    );
                  })}
                </View>
              ))
            )}
            <Text style={styles.countText}>
              已选 {selected.length} 条 · 本人发言 {repTotal} 条
              {selected.length > 0 && repTotal < MIN_REP_UTTERANCES
                ? `（需 ≥${MIN_REP_UTTERANCES} 条才能用于生成）` : ''}
            </Text>
          </View>
        )}

        {step === 3 && (
          <View style={[styles.card, Shadow.card]}>
            <Text style={styles.cardTitle}>为分身起个名字</Text>
            <TextInput
              style={styles.nameInput}
              value={name}
              onChangeText={setName}
              maxLength={100}
              placeholder="不填则自动起名"
              placeholderTextColor={Colors.textHint}
            />
            <Text style={styles.summaryTitle}>生成内容预览</Text>
            <View style={styles.summaryBox}>
              <View style={styles.summaryRow}>
                <Text style={styles.summaryLabel}>风格方向（问卷）</Text>
                <Text style={styles.summaryValue}>
                  {preview.formal_level} · {preview.reply_length} · {preview.opening_mode}
                </Text>
              </View>
              <View style={styles.summaryRow}>
                <Text style={styles.summaryLabel}>真实记录画像</Text>
                <Text style={styles.summaryValue}>
                  {selected.length > 0
                    ? `已选 ${selected.length} 条记录，AI 将提炼你的说话风格`
                    : '未选记录，仅按问卷方向生成'}
                </Text>
              </View>
            </View>
            <TouchableOpacity
              style={[styles.primaryBtn, creating && { opacity: 0.6 }]}
              disabled={creating}
              onPress={create}
              activeOpacity={0.7}
            >
              <Icon name="account-tie-outline" size={18} color={Colors.textWhite} />
              <Text style={styles.primaryText}>{creating ? '创建中…' : '创建分身'}</Text>
            </TouchableOpacity>
          </View>
        )}

        {/* 底部导航：上一步 + 下一步/创建 */}
        {step < 3 && (
          <View style={styles.navRow}>
            <TouchableOpacity style={styles.ghostBtn} onPress={goBackOne} activeOpacity={0.7}>
              <Text style={styles.ghostText}>上一步</Text>
            </TouchableOpacity>
            <TouchableOpacity
              style={[styles.primaryNavBtn, step2Blocked && { opacity: 0.5 }]}
              disabled={step2Blocked}
              onPress={() => setStep(step + 1)}
              activeOpacity={0.7}
            >
              <Text style={styles.primaryText}>
                {step === 2 && selected.length === 0 ? '暂不选用，下一步' : '下一步'}
              </Text>
            </TouchableOpacity>
          </View>
        )}
      </ScrollView>

      {/* 创建中遮罩：含素材路径同步 LLM 可能约 1 分钟 */}
      {creating && (
        <View style={styles.mask}>
          <View style={[styles.maskCard, Shadow.card]}>
            <ActivityIndicator size="large" color={Colors.primary} />
            <Text style={styles.maskTitle}>正在生成分身…</Text>
            <Text style={styles.maskHint}>结合问卷方向与真实记录提炼风格，可能耗时约 1 分钟，请勿退出</Text>
          </View>
        </View>
      )}
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
  headerTitle: { color: Colors.textWhite, fontSize: FontSize.md, fontWeight: '600' },
  content: { padding: Spacing.md },
  stepBar: { flexDirection: 'row', gap: Spacing.xs, marginBottom: Spacing.md },
  stepSeg: { flex: 1, height: 4, borderRadius: 2, backgroundColor: Colors.divider },
  stepSegActive: { backgroundColor: Colors.primary },
  card: { backgroundColor: Colors.card, borderRadius: BorderRadius.md, padding: Spacing.lg, marginBottom: Spacing.md },
  cardTitle: { fontSize: FontSize.md, fontWeight: '600', color: Colors.textPrimary, marginBottom: Spacing.sm },
  hint: { fontSize: FontSize.xs, color: Colors.textHint, marginBottom: Spacing.md, lineHeight: 18 },
  question: { marginBottom: Spacing.md },
  questionText: { fontSize: FontSize.sm, color: Colors.textPrimary, marginBottom: Spacing.xs, lineHeight: 20 },
  chipWrap: { flexDirection: 'row', flexWrap: 'wrap', gap: Spacing.sm },
  chip: {
    paddingHorizontal: Spacing.md, paddingVertical: Spacing.xs,
    borderRadius: BorderRadius.full, borderWidth: 1, borderColor: Colors.border,
    backgroundColor: Colors.white,
  },
  chipActive: { backgroundColor: Colors.primarySurface, borderColor: Colors.primary },
  chipText: { fontSize: FontSize.sm, color: Colors.textSecondary },
  chipTextActive: { color: Colors.primary, fontWeight: '600' },
  groupWrap: { marginBottom: Spacing.md },
  groupLabel: {
    fontSize: FontSize.xs, color: Colors.textSecondary, fontWeight: '600',
    marginBottom: Spacing.xs, marginTop: Spacing.sm,
  },
  sessionRow: {
    flexDirection: 'row', alignItems: 'center', gap: Spacing.md,
    paddingVertical: Spacing.md, paddingHorizontal: Spacing.sm,
    borderRadius: BorderRadius.sm, marginBottom: Spacing.xs,
  },
  sessionRowActive: { backgroundColor: Colors.primarySurface },
  sessionScenario: { fontSize: FontSize.md, color: Colors.textPrimary, fontWeight: '500' },
  sessionMeta: { fontSize: FontSize.xs, color: Colors.textSecondary, marginTop: 2 },
  countText: { fontSize: FontSize.xs, color: Colors.textSecondary, marginTop: Spacing.xs },
  centerWrap: { alignItems: 'center', paddingVertical: Spacing.lg, gap: Spacing.sm },
  emptyText: { fontSize: FontSize.sm, color: Colors.textHint, textAlign: 'center', lineHeight: 20 },
  retryBtn: {
    flexDirection: 'row', alignItems: 'center', gap: Spacing.xs,
    borderWidth: 1, borderColor: Colors.primary, borderRadius: BorderRadius.sm,
    paddingHorizontal: Spacing.md, paddingVertical: Spacing.xs,
  },
  retryText: { fontSize: FontSize.sm, color: Colors.primary, fontWeight: '600' },
  nameInput: {
    borderWidth: 1, borderColor: Colors.border, borderRadius: BorderRadius.sm,
    backgroundColor: Colors.white, paddingHorizontal: Spacing.md, paddingVertical: Spacing.sm,
    fontSize: FontSize.md, color: Colors.textPrimary, marginBottom: Spacing.md,
  },
  summaryTitle: { fontSize: FontSize.sm, fontWeight: '600', color: Colors.textPrimary, marginBottom: Spacing.xs },
  summaryBox: {
    backgroundColor: Colors.primarySurface, borderRadius: BorderRadius.sm,
    padding: Spacing.md, marginBottom: Spacing.md, gap: Spacing.sm,
  },
  summaryRow: { flexDirection: 'row', alignItems: 'flex-start', gap: Spacing.sm },
  summaryLabel: { width: 104, fontSize: FontSize.xs, color: Colors.textSecondary },
  summaryValue: { flex: 1, fontSize: FontSize.xs, color: Colors.textPrimary, lineHeight: 18 },
  navRow: { flexDirection: 'row', gap: Spacing.md, marginBottom: Spacing.lg },
  ghostBtn: {
    flex: 1, borderWidth: 1, borderColor: Colors.border, borderRadius: BorderRadius.sm,
    padding: Spacing.md, alignItems: 'center',
  },
  ghostText: { color: Colors.primary, fontSize: FontSize.md, fontWeight: '600' },
  primaryBtn: {
    backgroundColor: Colors.primary, borderRadius: BorderRadius.sm,
    padding: Spacing.md, alignItems: 'center', flexDirection: 'row',
    justifyContent: 'center', gap: Spacing.sm,
  },
  primaryNavBtn: {
    flex: 2, backgroundColor: Colors.primary, borderRadius: BorderRadius.sm,
    padding: Spacing.md, alignItems: 'center',
  },
  primaryText: { color: Colors.textWhite, fontSize: FontSize.md, fontWeight: '600' },
  mask: {
    ...StyleSheet.absoluteFillObject, backgroundColor: 'rgba(7,37,64,0.45)',
    alignItems: 'center', justifyContent: 'center', padding: Spacing.xl,
  },
  maskCard: {
    backgroundColor: Colors.card, borderRadius: BorderRadius.lg, padding: Spacing.xl,
    alignItems: 'center', width: '100%',
  },
  maskTitle: { fontSize: FontSize.md, fontWeight: '600', color: Colors.textPrimary, marginTop: Spacing.md },
  maskHint: { fontSize: FontSize.xs, color: Colors.textHint, marginTop: Spacing.xs, textAlign: 'center' },
});
