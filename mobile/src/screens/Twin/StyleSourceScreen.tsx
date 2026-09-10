/**
 * 从历史记录生成分身（2026-09-10）：
 * 多选本人三类对话记录（与专员对话 / 拜访医生转写 / 陪练会话）→
 * style-from-records 同步 LLM 提取真实说话风格 → 直接建分身（与 5 题问卷双入口）。
 * 门槛与后端对齐：记录最多选 10 条、代表发言合计 ≥10 条才能生成。
 */
import React, { useCallback, useEffect, useMemo, useState } from 'react';
import {
  ActivityIndicator, Alert, ScrollView, StyleSheet, Text, TouchableOpacity, View,
} from 'react-native';
import { useNavigation } from '@react-navigation/native';
import type { NativeStackNavigationProp } from '@react-navigation/native-stack';
import Icon from '../../components/Icon';
import { twinAPI } from '../../api/practice';
import { BorderRadius, Colors, FontSize, Shadow, Spacing } from '../../constants/theme';

type Nav = NativeStackNavigationProp<any>;

// 后端 style_from_records 门槛（specialist-service specialists.py）的前端镜像
const MIN_REP_UTTERANCES = 10;
const MAX_SOURCES = 10;

/** 与专员对话会话项（GET /style-sources chats 子集） */
interface ChatItem {
  session_id: string;
  specialist_id?: number;
  specialist_name?: string | null;
  turns: number;
  first_question?: string;
  created_at?: string;
}

/** 拜访记录项（visits 子集） */
interface VisitItem {
  visit_id: number;
  rep_lines: number;
  transcript_preview?: string;
  visit_time?: string;
}

/** 陪练会话项（practices 子集） */
interface PracticeItem {
  session_id: number;
  scenario?: string;
  turn_count?: number;
  created_at?: string;
}

/** 统一选材行：type + 展示字段 + 代表发言条数（素材量统计口径） */
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

/** created_at / visit_time（ISO）→ "MM-DD HH:mm"；解析失败返回空串 */
function formatTime(iso?: string): string {
  if (!iso) return '';
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return '';
  const p = (n: number) => String(n).padStart(2, '0');
  return `${p(d.getMonth() + 1)}-${p(d.getDate())} ${p(d.getHours())}:${p(d.getMinutes())}`;
}

export default function StyleSourceScreen() {
  const navigation = useNavigation<Nav>();
  const [rows, setRows] = useState<SourceRow[]>([]);
  const [loaded, setLoaded] = useState(false);
  const [loadFailed, setLoadFailed] = useState(false);
  const [selected, setSelected] = useState<string[]>([]);
  const [generating, setGenerating] = useState(false);

  const loadSources = useCallback(async () => {
    setLoaded(false);
    setLoadFailed(false);
    try {
      const res = await twinAPI.styleSources();
      const chats: ChatItem[] = Array.isArray(res?.chats) ? res.chats : [];
      const visits: VisitItem[] = Array.isArray(res?.visits) ? res.visits : [];
      const practices: PracticeItem[] = Array.isArray(res?.practices) ? res.practices : [];
      const mapped: SourceRow[] = [
        ...chats.map<SourceRow>((c) => ({
          key: `chat:${c.session_id}`,
          type: 'chat',
          id: c.session_id,
          title: c.first_question || c.specialist_name || '与专员的对话',
          meta: `${c.specialist_name || '专员'} · ${c.turns} 条${formatTime(c.created_at) ? ` · ${formatTime(c.created_at)}` : ''}`,
          count: c.turns,
        })),
        ...visits.map<SourceRow>((v) => ({
          key: `visit:${v.visit_id}`,
          type: 'visit',
          id: v.visit_id,
          title: v.transcript_preview || '拜访医生实录',
          meta: `代表发言 ${v.rep_lines} 条${formatTime(v.visit_time) ? ` · ${formatTime(v.visit_time)}` : ''}`,
          count: v.rep_lines,
        })),
        ...practices.map<SourceRow>((p) => ({
          key: `practice:${p.session_id}`,
          type: 'practice',
          id: p.session_id,
          title: p.scenario || `陪练 #${p.session_id}`,
          meta: `轮数 ${p.turn_count ?? 0}${formatTime(p.created_at) ? ` · ${formatTime(p.created_at)}` : ''}`,
          count: p.turn_count ?? 0,
        })),
      ];
      setRows(mapped);
    } catch {
      setLoadFailed(true);
    } finally {
      setLoaded(true);
    }
  }, []);

  useEffect(() => {
    loadSources();
  }, [loadSources]);

  // 按类型分组渲染（某类为空则整组不出现）
  const grouped = useMemo(() => {
    const order: SourceRow['type'][] = ['chat', 'visit', 'practice'];
    return order
      .map((type) => ({ type, items: rows.filter((r) => r.type === type) }))
      .filter((g) => g.items.length > 0);
  }, [rows]);

  const selectedRows = rows.filter((r) => selected.includes(r.key));
  const repTotal = selectedRows.reduce((sum, r) => sum + r.count, 0);
  const canGenerate = selected.length > 0 && repTotal >= MIN_REP_UTTERANCES && !generating;

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

  const generate = (keys: string[]) => {
    const payload = rows
      .filter((r) => keys.includes(r.key))
      .map((r) => ({ type: r.type, id: r.id }));
    setGenerating(true);
    twinAPI.styleFromRecords(payload)
      .then((twin: any) => {
        Alert.alert('生成成功', `已按你的真实说话风格创建分身「${twin?.name || '我的分身'}」`, [
          { text: '好', onPress: () => navigation.goBack() },
        ]);
      })
      .catch((err: any) => {
        // 4002 限额 / 4003 LLM 失败 / 4xx 素材不合格——后端 message 已是中文
        Alert.alert('生成失败', err?.message || '风格提取失败，请稍后重试', [
          { text: '重试', onPress: () => generate(keys) },
          { text: '取消', style: 'cancel' },
        ]);
      })
      .finally(() => setGenerating(false));
  };

  const hasAny = rows.length > 0;

  return (
    <View style={styles.container}>
      <View style={styles.header}>
        <TouchableOpacity onPress={() => navigation.goBack()}>
          <Icon name="chevron-left" size={22} color={Colors.textWhite} />
        </TouchableOpacity>
        <Text style={styles.headerTitle}>从历史记录生成分身</Text>
        <View style={{ width: 24 }} />
      </View>

      <View style={styles.body}>
        {!loaded ? (
          <View style={styles.centerWrap}>
            <ActivityIndicator size="large" color={Colors.primary} />
            <Text style={styles.emptyText}>加载中…</Text>
          </View>
        ) : loadFailed ? (
          <View style={styles.centerWrap}>
            <View style={[styles.card, Shadow.card]}>
              <Text style={styles.cardTitle}>记录列表加载失败</Text>
              <Text style={styles.emptyText}>网络异常，请重试</Text>
              <TouchableOpacity style={styles.fullBtn} onPress={loadSources} activeOpacity={0.7}>
                <Icon name="refresh" size={18} color={Colors.textWhite} />
                <Text style={styles.btnText}>重新加载</Text>
              </TouchableOpacity>
            </View>
          </View>
        ) : !hasAny ? (
          <View style={styles.centerWrap}>
            <View style={[styles.card, Shadow.card, styles.emptyCard]}>
              <View style={styles.emptyIconBox}>
                <Icon name="robot-outline" size={30} color={Colors.primary} />
              </View>
              <Text style={styles.emptyTitle}>还没有可用的对话记录</Text>
              <Text style={styles.emptyHint}>
                与专员对话、拜访医生、AI 陪练的记录都会自动留存；
                积累几轮后即可用你的真实发言生成分身
              </Text>
            </View>
          </View>
        ) : (
          <>
            <ScrollView contentContainerStyle={styles.content}>
              <View style={[styles.card, Shadow.card]}>
                <Text style={styles.cardTitle}>选择对话记录（最多 {MAX_SOURCES} 条）</Text>
                <Text style={styles.hint}>
                  三类记录可混选；本人发言合计 ≥{MIN_REP_UTTERANCES} 条才能生成
                </Text>
                {grouped.map((group) => (
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
                ))}
              </View>
            </ScrollView>

            {/* 底部：已选统计 + 生成入口（素材不足禁用） */}
            <View style={styles.footer}>
              <Text style={styles.footerCount}>
                已选 {selected.length} 条 · 本人发言 {repTotal} 条
                {repTotal < MIN_REP_UTTERANCES ? `（需 ≥${MIN_REP_UTTERANCES} 条）` : ''}
              </Text>
              <TouchableOpacity
                style={[styles.generateBtn, !canGenerate && { opacity: 0.5 }]}
                disabled={!canGenerate}
                onPress={() => generate(selected)}
                activeOpacity={0.7}
              >
                <Icon name="account-tie-outline" size={18} color={Colors.textWhite} />
                <Text style={styles.btnText}>生成分身</Text>
              </TouchableOpacity>
            </View>
          </>
        )}
      </View>

      {/* 生成中遮罩：同步 LLM 可能约 1 分钟，阻断误操作并给出预期 */}
      {generating && (
        <View style={styles.mask}>
          <View style={[styles.maskCard, Shadow.card]}>
            <ActivityIndicator size="large" color={Colors.primary} />
            <Text style={styles.maskTitle}>正在分析你的真实对话…</Text>
            <Text style={styles.maskHint}>由 AI 提取说话风格，可能耗时约 1 分钟，请勿退出</Text>
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
  headerTitle: { color: Colors.textWhite, fontSize: FontSize.lg, fontWeight: '600' },
  body: { flex: 1 },
  content: { padding: Spacing.md },
  card: { backgroundColor: Colors.card, borderRadius: BorderRadius.md, padding: Spacing.lg, marginBottom: Spacing.md },
  cardTitle: { fontSize: FontSize.md, fontWeight: '600', color: Colors.textPrimary, marginBottom: Spacing.sm },
  hint: { fontSize: FontSize.xs, color: Colors.textHint, marginBottom: Spacing.sm },
  groupWrap: { marginBottom: Spacing.md },
  groupLabel: {
    fontSize: FontSize.xs, color: Colors.textSecondary, fontWeight: '600',
    marginBottom: Spacing.xs, marginTop: Spacing.sm,
  },
  centerWrap: { flex: 1, alignItems: 'center', justifyContent: 'center', padding: Spacing.md },
  emptyCard: { alignItems: 'center', width: '100%' },
  emptyIconBox: {
    width: 56, height: 56, borderRadius: BorderRadius.lg,
    backgroundColor: Colors.primarySurface, alignItems: 'center', justifyContent: 'center',
    marginBottom: Spacing.md,
  },
  emptyTitle: { fontSize: FontSize.lg, fontWeight: '600', color: Colors.textPrimary, marginBottom: Spacing.xs },
  emptyHint: { fontSize: FontSize.sm, color: Colors.textSecondary, textAlign: 'center', lineHeight: 20 },
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
  btnText: { color: Colors.textWhite, fontSize: FontSize.md, fontWeight: '600' },
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
