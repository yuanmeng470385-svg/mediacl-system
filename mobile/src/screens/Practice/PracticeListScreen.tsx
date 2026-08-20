/**
 * AI 陪练 - 场景选择 + 历史列表（二期 H）
 * 预置科室/性格场景 → 创建陪练会话 → 进入对话；历史列表展示评分/轮数。
 */
import React, { useCallback, useEffect, useState } from 'react';
import {
  Alert, ScrollView, StyleSheet, Text, TouchableOpacity, View,
} from 'react-native';
import { useNavigation } from '@react-navigation/native';
import type { NativeStackNavigationProp } from '@react-navigation/native-stack';
import Icon from '../../components/Icon';
import { practiceAPI } from '../../api/practice';
import type { RootStackParamList } from '../../navigation/types';
import { BorderRadius, Colors, FontSize, Shadow, Spacing } from '../../constants/theme';

type Nav = NativeStackNavigationProp<RootStackParamList>;

/** 预置场景（科室 × 性格组合成可选项） */
const SCENARIOS = [
  '心内科推广',
  '肿瘤科推广',
  '内分泌科推广',
  '呼吸科推广',
  '神内科推广',
];

/** 预置医生性格（拼接进场景文案） */
const PERSONAS = ['严谨型', '挑剔型', '温和型'];

interface HistoryItem {
  id: number;
  scenario?: string;
  status?: string;
  turn_count?: number;
  scores?: { overall?: number } | null;
}

export default function PracticeListScreen() {
  const navigation = useNavigation<Nav>();
  const [scenario, setScenario] = useState(SCENARIOS[0]);
  const [persona, setPersona] = useState(PERSONAS[0]);
  const [history, setHistory] = useState<HistoryItem[]>([]);
  const [loaded, setLoaded] = useState(false);
  const [starting, setStarting] = useState(false);

  const loadHistory = useCallback(async () => {
    setLoaded(false);
    try {
      const res = await practiceAPI.list();
      setHistory(Array.isArray(res?.items) ? res.items : []);
    } catch {
      // 历史列表拉取失败不阻塞场景选择，保留空列表
    } finally {
      setLoaded(true);
    }
  }, []);

  useEffect(() => {
    loadHistory();
  }, [loadHistory]);

  const startPractice = async () => {
    setStarting(true);
    try {
      const fullScenario = `${scenario}·${persona}医生`;
      const session = await practiceAPI.create({ scenario: fullScenario });
      navigation.navigate('PracticeChat', { sessionId: session.id });
    } catch (err: any) {
      Alert.alert('创建失败', err?.message || '无法创建陪练会话，请稍后重试');
    } finally {
      setStarting(false);
    }
  };

  return (
    <View style={styles.container}>
      <View style={styles.header}>
        <TouchableOpacity onPress={() => navigation.goBack()}>
          <Icon name="chevron-left" size={22} color={Colors.textWhite} />
        </TouchableOpacity>
        <Text style={styles.headerTitle}>AI 陪练</Text>
        <View style={{ width: 24 }} />
      </View>

      <ScrollView contentContainerStyle={styles.content}>
        {/* 场景选择 */}
        <View style={[styles.card, Shadow.card]}>
          <Text style={styles.cardTitle}>选择场景（科室）</Text>
          <View style={styles.chipWrap}>
            {SCENARIOS.map((s) => {
              const active = s === scenario;
              return (
                <TouchableOpacity
                  key={s}
                  style={[styles.chip, active && styles.chipActive]}
                  onPress={() => setScenario(s)}
                  activeOpacity={0.7}
                >
                  <Text style={[styles.chipText, active && styles.chipTextActive]}>{s}</Text>
                </TouchableOpacity>
              );
            })}
          </View>

          <Text style={styles.cardTitle}>医生性格</Text>
          <View style={styles.chipWrap}>
            {PERSONAS.map((p) => {
              const active = p === persona;
              return (
                <TouchableOpacity
                  key={p}
                  style={[styles.chip, active && styles.chipActive]}
                  onPress={() => setPersona(p)}
                  activeOpacity={0.7}
                >
                  <Text style={[styles.chipText, active && styles.chipTextActive]}>{p}</Text>
                </TouchableOpacity>
              );
            })}
          </View>

          <TouchableOpacity
            style={[styles.startBtn, starting && { opacity: 0.6 }]}
            disabled={starting}
            onPress={startPractice}
            activeOpacity={0.7}
          >
            <Icon name="play" size={18} color={Colors.textWhite} />
            <Text style={styles.startText}>{starting ? '创建中…' : '开始陪练'}</Text>
          </TouchableOpacity>
        </View>

        {/* 历史列表 */}
        <View style={[styles.card, Shadow.card]}>
          <Text style={styles.cardTitle}>历史陪练</Text>
          {!loaded ? (
            <Text style={styles.emptyText}>加载中…</Text>
          ) : history.length === 0 ? (
            <Text style={styles.emptyText}>暂无陪练记录，去开启第一场吧</Text>
          ) : (
            history.map((item, index) => (
              <View key={item.id} style={[styles.historyRow, index > 0 && styles.rowBorder]}>
                <View style={styles.historyIconBox}>
                  <Icon name="robot-outline" size={18} color={Colors.primary} />
                </View>
                <View style={{ flex: 1 }}>
                  <Text style={styles.historyScenario} numberOfLines={1}>
                    {item.scenario || `陪练 #${item.id}`}
                  </Text>
                  <Text style={styles.historyMeta}>轮数 {item.turn_count ?? 0}</Text>
                </View>
                <View style={styles.scoreBox}>
                  <Text style={styles.scoreLabel}>评分</Text>
                  <Text style={styles.scoreValue}>
                    {item.scores?.overall != null ? item.scores.overall : '--'}
                  </Text>
                </View>
              </View>
            ))
          )}
        </View>
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
  headerTitle: { color: Colors.textWhite, fontSize: FontSize.lg, fontWeight: '600' },
  content: { padding: Spacing.md },
  card: { backgroundColor: Colors.card, borderRadius: BorderRadius.md, padding: Spacing.lg, marginBottom: Spacing.md },
  cardTitle: { fontSize: FontSize.md, fontWeight: '600', color: Colors.textPrimary, marginBottom: Spacing.sm, marginTop: Spacing.xs },
  chipWrap: { flexDirection: 'row', flexWrap: 'wrap', gap: Spacing.sm, marginBottom: Spacing.xs },
  chip: {
    paddingHorizontal: Spacing.lg, paddingVertical: Spacing.sm,
    borderRadius: BorderRadius.full, borderWidth: 1, borderColor: Colors.border,
    backgroundColor: Colors.white,
  },
  chipActive: { backgroundColor: Colors.primarySurface, borderColor: Colors.primary },
  chipText: { fontSize: FontSize.sm, color: Colors.textSecondary },
  chipTextActive: { color: Colors.primary, fontWeight: '600' },
  startBtn: {
    marginTop: Spacing.lg, backgroundColor: Colors.primary, borderRadius: BorderRadius.sm,
    padding: Spacing.md, alignItems: 'center', flexDirection: 'row',
    justifyContent: 'center', gap: Spacing.sm,
  },
  startText: { color: Colors.textWhite, fontSize: FontSize.md, fontWeight: '600' },
  emptyText: { fontSize: FontSize.sm, color: Colors.textHint, textAlign: 'center', paddingVertical: Spacing.lg },
  historyRow: { flexDirection: 'row', alignItems: 'center', paddingVertical: Spacing.md, gap: Spacing.md },
  rowBorder: { borderTopWidth: StyleSheet.hairlineWidth, borderTopColor: Colors.divider },
  historyIconBox: {
    width: 36, height: 36, borderRadius: 10,
    backgroundColor: Colors.primarySurface, alignItems: 'center', justifyContent: 'center',
  },
  historyScenario: { fontSize: FontSize.md, color: Colors.textPrimary, fontWeight: '500' },
  historyMeta: { fontSize: FontSize.xs, color: Colors.textSecondary, marginTop: 2 },
  scoreBox: { alignItems: 'center', minWidth: 48 },
  scoreLabel: { fontSize: FontSize.xs, color: Colors.textHint },
  scoreValue: { fontSize: FontSize.lg, fontWeight: '700', color: Colors.accent },
});
