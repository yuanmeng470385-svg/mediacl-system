/**
 * 从陪练对话提取风格 Skill 草稿（三期 P 第三环）：
 * 多选本人已完成会话（completed + turn_count≥3）→ extract-draft 同步 LLM 提取 →
 * 草稿确认卡（name/description/标签/三维度/话术摘录）→ replace 到 SkillRelease 预填发布。
 * 门槛与后端对齐：代表发言合计 ≥10 条才能生成、会话最多选 10 个。
 */
import React, { useCallback, useEffect, useState } from 'react';
import {
  ActivityIndicator, Alert, ScrollView, StyleSheet, Text, TouchableOpacity, View,
} from 'react-native';
import { useNavigation } from '@react-navigation/native';
import type { NativeStackNavigationProp } from '@react-navigation/native-stack';
import Icon from '../../components/Icon';
import { plazaAPI, practiceAPI } from '../../api/practice';
import type { RootStackParamList, SkillDraft } from '../../navigation/types';
import { BorderRadius, Colors, FontSize, Shadow, Spacing } from '../../constants/theme';

type Nav = NativeStackNavigationProp<RootStackParamList>;

// 后端 extract_draft 门槛（specialist-service skill_packages.py）的前端镜像
const MIN_REP_TURNS = 10;
const MAX_SESSIONS = 10;

/** 会话列表项（GET /api/v1/practices 的 item 子集；transcript 不在前端展示） */
interface SessionItem {
  id: number;
  scenario?: string;
  turn_count?: number;
  status?: string;
  created_at?: string;
}

/** 提取草稿：正式类型 SkillDraft 已在 navigation/types.ts 导出（与后端 extract-draft 返回同构） */
type ExtractDraft = SkillDraft;

/** created_at（ISO）→ "MM-DD HH:mm"；解析失败返回空串 */
function formatTime(iso?: string): string {
  if (!iso) return '';
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return '';
  const p = (n: number) => String(n).padStart(2, '0');
  return `${p(d.getMonth() + 1)}-${p(d.getDate())} ${p(d.getHours())}:${p(d.getMinutes())}`;
}

export default function SkillExtractScreen() {
  const navigation = useNavigation<Nav>();
  const [sessions, setSessions] = useState<SessionItem[]>([]);
  const [loaded, setLoaded] = useState(false);
  const [loadFailed, setLoadFailed] = useState(false);
  const [selected, setSelected] = useState<number[]>([]);
  const [extracting, setExtracting] = useState(false);
  const [draft, setDraft] = useState<ExtractDraft | null>(null);

  const loadSessions = useCallback(async () => {
    setLoaded(false);
    setLoadFailed(false);
    try {
      const res = await practiceAPI.list();
      const items: SessionItem[] = Array.isArray(res?.items) ? res.items : [];
      // 仅展示可提取会话：已完成且单会话 ≥3 轮（后端门槛同款）
      setSessions(items.filter((s) => s.status === 'completed' && (s.turn_count ?? 0) >= 3));
    } catch {
      setLoadFailed(true);
    } finally {
      setLoaded(true);
    }
  }, []);

  useEffect(() => {
    loadSessions();
  }, [loadSessions]);

  const toggle = (id: number) => {
    if (selected.includes(id)) {
      setSelected(selected.filter((x) => x !== id));
      return;
    }
    if (selected.length >= MAX_SESSIONS) {
      Alert.alert('最多选择 10 个会话', '素材足够即可，再多不会提升提取质量');
      return;
    }
    setSelected([...selected, id]);
  };

  // turn_count 即代表发言数（后端每轮 = 代表 1 条 + AI 回复 1 条，turn_count 只累计代表轮次）
  const repTurns = sessions
    .filter((s) => selected.includes(s.id))
    .reduce((sum, s) => sum + (s.turn_count ?? 0), 0);
  const canGenerate = selected.length > 0 && repTurns >= MIN_REP_TURNS && !extracting;

  const runExtract = async (ids: number[]) => {
    setExtracting(true);
    try {
      const res = await plazaAPI.extractDraft(ids);
      setDraft(res ?? null);
    } catch (err: any) {
      // 4002 限额 / 4003 LLM 失败 / 4xx 会话不合格——后端 message 已是中文，直接展示
      Alert.alert('生成失败', err?.message || '风格提取失败，请稍后重试', [
        { text: '重试', onPress: () => runExtract(ids) },
        { text: '取消', style: 'cancel' },
      ]);
    } finally {
      setExtracting(false);
    }
  };

  const goPractice = () => navigation.navigate('PracticeList');
  const goPublish = () => {
    if (!draft) return;
    // SkillRelease 读 route.params.draft 预填各字段（replace 避免返回时回到本屏）。
    // 来源会话 ID 由本地补齐（后端 extract 不回传自己已校验过的 session_ids），
    // release 提交时原样回传做审核溯源留档（2026-09-01）
    navigation.replace('SkillRelease', {
      draft: { ...draft, source_session_ids: selected },
    });
  };

  return (
    <View style={styles.container}>
      <View style={styles.header}>
        <TouchableOpacity onPress={() => navigation.goBack()}>
          <Icon name="chevron-left" size={22} color={Colors.textWhite} />
        </TouchableOpacity>
        <Text style={styles.headerTitle}>从陪练提取风格</Text>
        <View style={{ width: 24 }} />
      </View>

      <View style={styles.body}>
        {!loaded ? (
          <View style={styles.centerWrap}>
            <ActivityIndicator size="large" color={Colors.primary} />
            <Text style={styles.emptyText}>加载中…</Text>
          </View>
        ) : draft ? (
          <DraftCard
            draft={draft}
            regenerating={extracting}
            onRegenerate={() => runExtract(selected)}
            onPublish={goPublish}
          />
        ) : loadFailed ? (
          <View style={styles.centerWrap}>
            <View style={[styles.card, Shadow.card]}>
              <Text style={styles.cardTitle}>会话列表加载失败</Text>
              <Text style={styles.emptyText}>网络异常，请重试</Text>
              <TouchableOpacity style={styles.fullBtn} onPress={loadSessions} activeOpacity={0.7}>
                <Icon name="refresh" size={18} color={Colors.textWhite} />
                <Text style={styles.btnText}>重新加载</Text>
              </TouchableOpacity>
            </View>
          </View>
        ) : sessions.length === 0 ? (
          <View style={styles.centerWrap}>
            <View style={[styles.card, Shadow.card, styles.emptyCard]}>
              <View style={styles.emptyIconBox}>
                <Icon name="robot-outline" size={30} color={Colors.primary} />
              </View>
              <Text style={styles.emptyTitle}>先去陪练几轮再来</Text>
              <Text style={styles.emptyHint}>
                完成至少一场陪练（每场 ≥3 轮、各场代表发言合计 ≥10 条）后，
                即可从你的真实发言中提取说话风格
              </Text>
              <TouchableOpacity style={styles.fullBtn} onPress={goPractice} activeOpacity={0.7}>
                <Icon name="play" size={18} color={Colors.textWhite} />
                <Text style={styles.btnText}>去陪练</Text>
              </TouchableOpacity>
            </View>
          </View>
        ) : (
          <>
            <ScrollView contentContainerStyle={styles.content}>
              <View style={[styles.card, Shadow.card]}>
                <Text style={styles.cardTitle}>选择陪练会话（1~{MAX_SESSIONS} 个）</Text>
                <Text style={styles.hint}>
                  仅显示已结束且 ≥3 轮的会话；代表发言合计 ≥{MIN_REP_TURNS} 条才能生成
                </Text>
                {sessions.map((item) => {
                  const active = selected.includes(item.id);
                  return (
                    <TouchableOpacity
                      key={item.id}
                      style={[styles.sessionRow, active && styles.sessionRowActive]}
                      onPress={() => toggle(item.id)}
                      activeOpacity={0.7}
                    >
                      <View style={{ flex: 1 }}>
                        <Text style={styles.sessionScenario} numberOfLines={1}>
                          {item.scenario || `陪练 #${item.id}`}
                        </Text>
                        <Text style={styles.sessionMeta}>
                          轮数 {item.turn_count ?? 0}
                          {formatTime(item.created_at) ? ` · ${formatTime(item.created_at)}` : ''}
                        </Text>
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
            </ScrollView>

            {/* 底部：已选统计 + 生成入口（<10 条代表发言禁用） */}
            <View style={styles.footer}>
              <Text style={styles.footerCount}>
                已选 {selected.length} 个 · 代表发言 {repTurns} 条
                {repTurns < MIN_REP_TURNS ? `（需 ≥${MIN_REP_TURNS} 条）` : ''}
              </Text>
              <TouchableOpacity
                style={[styles.generateBtn, !canGenerate && { opacity: 0.5 }]}
                disabled={!canGenerate}
                onPress={() => runExtract(selected)}
                activeOpacity={0.7}
              >
                <Icon name="creation" size={18} color={Colors.textWhite} />
                <Text style={styles.btnText}>生成风格草稿</Text>
              </TouchableOpacity>
            </View>
          </>
        )}
      </View>

      {/* 生成中遮罩：同步 LLM 可能约 1 分钟，阻断误操作并给出预期 */}
      {extracting && (
        <View style={styles.mask}>
          <View style={[styles.maskCard, Shadow.card]}>
            <ActivityIndicator size="large" color={Colors.primary} />
            <Text style={styles.maskTitle}>正在分析你的陪练对话…</Text>
            <Text style={styles.maskHint}>由 AI 提取说话风格，可能耗时约 1 分钟，请勿退出</Text>
          </View>
        </View>
      )}
    </View>
  );
}

/** 草稿确认卡：name/description/标签/三维度/话术摘录 + 重新生成/去发布 */
function DraftCard({ draft, regenerating, onRegenerate, onPublish }: {
  draft: ExtractDraft;
  regenerating: boolean;
  onRegenerate: () => void;
  onPublish: () => void;
}) {
  const weights = draft.skill_weights ?? {};
  return (
    <ScrollView contentContainerStyle={styles.content}>
      <View style={[styles.card, Shadow.card]}>
        <Text style={styles.cardTitle}>提取结果（确认后进入发布）</Text>
        <Text style={styles.draftName}>{draft.name}</Text>
        <Text style={styles.draftDesc}>{draft.description}</Text>
        {Array.isArray(draft.style_tags) && draft.style_tags.length > 0 && (
          <View style={styles.chipWrap}>
            {draft.style_tags.map((tag) => (
              <View key={tag} style={styles.tagChip}>
                <Text style={styles.tagChipText}>{tag}</Text>
              </View>
            ))}
          </View>
        )}
        <WeightRow label="正式程度" value={weights.formal_level} />
        <WeightRow label="回复长度" value={weights.reply_length} />
        <WeightRow label="开场方式" value={weights.opening_mode} />
        <Text style={styles.label}>话术摘录（摘自本人陪练对话）</Text>
        <Text style={styles.contentBox}>{draft.content}</Text>
        <View style={styles.btnRow}>
          <TouchableOpacity
            style={[styles.secondaryBtn, regenerating && { opacity: 0.5 }]}
            disabled={regenerating}
            onPress={onRegenerate}
            activeOpacity={0.7}
          >
            <Icon name="refresh" size={16} color={Colors.primary} />
            <Text style={styles.secondaryBtnText}>重新生成</Text>
          </TouchableOpacity>
          <TouchableOpacity style={styles.primaryBtn} onPress={onPublish} activeOpacity={0.7}>
            <Icon name="send" size={16} color={Colors.textWhite} />
            <Text style={styles.btnText}>去发布</Text>
          </TouchableOpacity>
        </View>
      </View>
    </ScrollView>
  );
}

function WeightRow({ label, value }: { label: string; value?: string }) {
  return (
    <View style={styles.weightRow}>
      <Text style={styles.weightLabel}>{label}</Text>
      <Text style={styles.weightValue}>{value || '—'}</Text>
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
  body: { flex: 1 },
  content: { padding: Spacing.md },
  card: { backgroundColor: Colors.card, borderRadius: BorderRadius.md, padding: Spacing.lg, marginBottom: Spacing.md },
  cardTitle: { fontSize: FontSize.md, fontWeight: '600', color: Colors.textPrimary, marginBottom: Spacing.sm },
  hint: { fontSize: FontSize.xs, color: Colors.textHint, marginBottom: Spacing.sm },
  label: { fontSize: FontSize.xs, color: Colors.textSecondary, marginBottom: Spacing.xs, marginTop: Spacing.sm },
  centerWrap: { flex: 1, alignItems: 'center', justifyContent: 'center', padding: Spacing.md },
  emptyCard: { alignItems: 'center', width: '100%' },
  emptyIconBox: {
    width: 56, height: 56, borderRadius: BorderRadius.lg,
    backgroundColor: Colors.primarySurface, alignItems: 'center', justifyContent: 'center',
    marginBottom: Spacing.md,
  },
  emptyTitle: { fontSize: FontSize.lg, fontWeight: '600', color: Colors.textPrimary, marginBottom: Spacing.xs },
  emptyHint: { fontSize: FontSize.sm, color: Colors.textSecondary, textAlign: 'center', lineHeight: 20, marginBottom: Spacing.lg },
  emptyText: { fontSize: FontSize.sm, color: Colors.textHint, textAlign: 'center', paddingVertical: Spacing.lg },
  sessionRow: {
    flexDirection: 'row', alignItems: 'center', gap: Spacing.md,
    paddingVertical: Spacing.md, paddingHorizontal: Spacing.sm,
    borderRadius: BorderRadius.sm, marginBottom: Spacing.xs,
  },
  sessionRowActive: { backgroundColor: Colors.primarySurface },
  sessionScenario: { fontSize: FontSize.md, color: Colors.textPrimary, fontWeight: '500' },
  sessionMeta: { fontSize: FontSize.xs, color: Colors.textSecondary, marginTop: 2 },
  footer: {
    paddingHorizontal: Spacing.md, paddingVertical: Spacing.sm,
    borderTopWidth: StyleSheet.hairlineWidth, borderTopColor: Colors.divider,
    backgroundColor: Colors.card, flexDirection: 'row', alignItems: 'center', gap: Spacing.md,
  },
  footerCount: { flex: 1, fontSize: FontSize.xs, color: Colors.textSecondary },
  generateBtn: {
    backgroundColor: Colors.primary, borderRadius: BorderRadius.sm,
    paddingHorizontal: Spacing.lg, paddingVertical: Spacing.sm,
    alignItems: 'center', flexDirection: 'row', justifyContent: 'center', gap: Spacing.sm,
  },
  fullBtn: {
    marginTop: Spacing.md, backgroundColor: Colors.primary, borderRadius: BorderRadius.sm,
    padding: Spacing.md, alignItems: 'center', flexDirection: 'row',
    justifyContent: 'center', gap: Spacing.sm, alignSelf: 'stretch',
  },
  primaryBtn: {
    flex: 1, backgroundColor: Colors.primary, borderRadius: BorderRadius.sm,
    padding: Spacing.sm, alignItems: 'center', flexDirection: 'row',
    justifyContent: 'center', gap: Spacing.xs,
  },
  secondaryBtn: {
    flex: 1, borderRadius: BorderRadius.sm, borderWidth: 1, borderColor: Colors.primary,
    padding: Spacing.sm, alignItems: 'center', flexDirection: 'row',
    justifyContent: 'center', gap: Spacing.xs, backgroundColor: Colors.white,
  },
  secondaryBtnText: { color: Colors.primary, fontSize: FontSize.sm, fontWeight: '600' },
  btnText: { color: Colors.textWhite, fontSize: FontSize.md, fontWeight: '600' },
  btnRow: { flexDirection: 'row', gap: Spacing.md, marginTop: Spacing.lg },
  draftName: { fontSize: FontSize.xl, fontWeight: '700', color: Colors.textPrimary, marginBottom: Spacing.xs },
  draftDesc: { fontSize: FontSize.sm, color: Colors.textSecondary, marginBottom: Spacing.sm },
  chipWrap: { flexDirection: 'row', flexWrap: 'wrap', gap: Spacing.sm, marginBottom: Spacing.sm },
  tagChip: {
    paddingHorizontal: Spacing.md, paddingVertical: Spacing.xs,
    borderRadius: BorderRadius.full, backgroundColor: Colors.primarySurface,
  },
  tagChipText: { fontSize: FontSize.sm, color: Colors.primary, fontWeight: '600' },
  weightRow: {
    flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between',
    paddingVertical: Spacing.xs, borderBottomWidth: StyleSheet.hairlineWidth,
    borderBottomColor: Colors.divider,
  },
  weightLabel: { fontSize: FontSize.sm, color: Colors.textSecondary },
  weightValue: { fontSize: FontSize.sm, color: Colors.textPrimary, fontWeight: '600' },
  contentBox: {
    borderWidth: 1, borderColor: Colors.border, borderRadius: BorderRadius.sm,
    backgroundColor: Colors.white, padding: Spacing.md,
    fontSize: FontSize.sm, color: Colors.textPrimary, lineHeight: 22,
  },
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
