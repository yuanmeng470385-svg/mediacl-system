/**
 * AI 陪练 - 多轮对话（二期 H）
 * 输入代表话术 → 显示 AI 医生回应；结束按钮 → complete 展示评分。
 */
import React, { useState } from 'react';
import {
  ActivityIndicator, Alert, KeyboardAvoidingView, Platform, ScrollView,
  StyleSheet, Text, TextInput, TouchableOpacity, View,
} from 'react-native';
import { RouteProp, useNavigation, useRoute } from '@react-navigation/native';
import type { NativeStackNavigationProp } from '@react-navigation/native-stack';
import Icon from '../../components/Icon';
import { practiceAPI } from '../../api/practice';
import type { RootStackParamList } from '../../navigation/types';
import { BorderRadius, Colors, FontSize, Shadow, Spacing } from '../../constants/theme';

type Nav = NativeStackNavigationProp<RootStackParamList>;
type Route = RouteProp<RootStackParamList, 'PracticeChat'>;

interface Msg {
  role: 'rep' | 'doctor';
  content: string;
}

interface PerTurnScore {
  turn?: number;
  feedback?: string;
}

interface Scores {
  evidence_accuracy?: number;
  objection_handling?: number;
  communication_logic?: number;
  overall?: number;
  summary?: string;
  per_turn?: PerTurnScore[];
}

export default function PracticeChatScreen() {
  const navigation = useNavigation<Nav>();
  const route = useRoute<Route>();
  const { sessionId } = route.params;

  const [messages, setMessages] = useState<Msg[]>([]);
  const [input, setInput] = useState('');
  const [sending, setSending] = useState(false);
  const [scores, setScores] = useState<Scores | null>(null);
  const [completing, setCompleting] = useState(false);

  const send = async () => {
    const text = input.trim();
    if (!text || sending || scores) return;
    setInput('');
    setMessages((prev) => [...prev, { role: 'rep', content: text }]);
    setSending(true);
    try {
      const res = await practiceAPI.turn(sessionId, text);
      const reply = res?.ai_message || '（医生没有回应）';
      setMessages((prev) => [...prev, { role: 'doctor', content: reply }]);
    } catch (err: any) {
      Alert.alert('发送失败', err?.message || '请稍后重试');
    } finally {
      setSending(false);
    }
  };

  const complete = async () => {
    if (completing || scores) return;
    setCompleting(true);
    try {
      const session = await practiceAPI.complete(sessionId);
      setScores(session?.scores ?? null);
    } catch (err: any) {
      Alert.alert('结束失败', err?.message || '请稍后重试');
    } finally {
      setCompleting(false);
    }
  };

  return (
    <View style={styles.container}>
      <View style={styles.header}>
        <TouchableOpacity onPress={() => navigation.goBack()}>
          <Icon name="chevron-left" size={22} color={Colors.textWhite} />
        </TouchableOpacity>
        <Text style={styles.headerTitle}>陪练对话</Text>
        <TouchableOpacity onPress={complete} disabled={completing || !!scores}>
          {completing ? (
            <ActivityIndicator size="small" color={Colors.textWhite} />
          ) : (
            <Text style={styles.endText}>结束</Text>
          )}
        </TouchableOpacity>
      </View>

      <KeyboardAvoidingView
        style={{ flex: 1 }}
        behavior={Platform.OS === 'ios' ? 'padding' : undefined}
      >
        <ScrollView style={styles.chatArea} contentContainerStyle={styles.chatContent}>
          {messages.length === 0 && !scores && (
            <Text style={styles.emptyText}>开始你的第一句学术推广话术吧</Text>
          )}

          {messages.map((m, i) => (
            <View
              key={i}
              style={[
                styles.bubbleRow,
                m.role === 'rep' ? styles.rowRight : styles.rowLeft,
              ]}
            >
              <View style={[styles.bubble, m.role === 'rep' ? styles.bubbleRep : styles.bubbleDoctor]}>
                <Text style={styles.bubbleLabel}>{m.role === 'rep' ? '我' : 'AI 医生'}</Text>
                <Text style={[styles.bubbleText, m.role === 'rep' && { color: Colors.textWhite }]}>
                  {m.content}
                </Text>
              </View>
            </View>
          ))}

          {/* 评分面板 */}
          {scores && (
            <View style={[styles.scoreCard, Shadow.card]}>
              <View style={styles.scoreHeader}>
                <Icon name="check-circle" size={20} color={Colors.success} />
                <Text style={styles.scoreTitle}>陪练评分</Text>
              </View>
              <View style={styles.scoreGrid}>
                <ScoreCell label="证据准确" value={scores.evidence_accuracy} />
                <ScoreCell label="异议处理" value={scores.objection_handling} />
                <ScoreCell label="沟通逻辑" value={scores.communication_logic} />
                <ScoreCell label="综合评分" value={scores.overall} highlight />
              </View>

              {scores.summary ? (
                <View style={styles.summaryBlock}>
                  <Text style={styles.summaryLabel}>改进建议</Text>
                  <Text style={styles.summaryText}>{scores.summary}</Text>
                </View>
              ) : null}

              {(scores.per_turn && scores.per_turn.length > 0) ? (
                <View style={styles.turnBlock}>
                  <Text style={styles.turnTitle}>逐句反馈</Text>
                  {scores.per_turn.map((pt, i) => (
                    <View key={i} style={styles.turnItem}>
                      <Text style={styles.turnLabel}>第 {pt.turn ?? i + 1} 轮</Text>
                      <Text style={styles.turnFeedback}>{pt.feedback || '—'}</Text>
                    </View>
                  ))}
                </View>
              ) : null}

              <TouchableOpacity
                style={styles.backBtn}
                onPress={() => navigation.goBack()}
                activeOpacity={0.7}
              >
                <Text style={styles.backText}>返回陪练列表</Text>
              </TouchableOpacity>
            </View>
          )}
        </ScrollView>

        {!scores && (
          <View style={styles.inputBar}>
            <TextInput
              style={styles.input}
              value={input}
              onChangeText={setInput}
              placeholder="输入你的推广话术…"
              placeholderTextColor={Colors.textHint}
              multiline
            />
            <TouchableOpacity
              style={[styles.sendBtn, (!input.trim() || sending) && { opacity: 0.5 }]}
              disabled={!input.trim() || sending}
              onPress={send}
              activeOpacity={0.7}
            >
              <Icon name="send" size={18} color={Colors.textWhite} />
            </TouchableOpacity>
          </View>
        )}
      </KeyboardAvoidingView>
    </View>
  );
}

function ScoreCell({ label, value, highlight }: { label: string; value?: number; highlight?: boolean }) {
  return (
    <View style={[styles.scoreCell, highlight && styles.scoreCellHighlight]}>
      <Text style={[styles.scoreCellLabel, highlight && { color: Colors.textWhite }]}>
        {label}
      </Text>
      <Text style={[styles.scoreCellValue, highlight && { color: Colors.textWhite }]}>
        {value != null ? value : '--'}
      </Text>
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
  endText: { color: Colors.textWhite, fontSize: FontSize.md, fontWeight: '600' },
  chatArea: { flex: 1 },
  chatContent: { padding: Spacing.md },
  emptyText: { fontSize: FontSize.sm, color: Colors.textHint, textAlign: 'center', marginTop: Spacing.xxl },
  bubbleRow: { marginBottom: Spacing.md },
  rowRight: { alignItems: 'flex-end' },
  rowLeft: { alignItems: 'flex-start' },
  bubble: { maxWidth: '82%', borderRadius: BorderRadius.lg, padding: Spacing.md },
  bubbleRep: { backgroundColor: Colors.primary },
  bubbleDoctor: { backgroundColor: Colors.white, ...Shadow.card },
  bubbleLabel: { fontSize: FontSize.xs, color: Colors.accent, marginBottom: 2 },
  bubbleText: { fontSize: FontSize.md, color: Colors.textPrimary, lineHeight: 22 },
  scoreCard: {
    backgroundColor: Colors.white, borderRadius: BorderRadius.lg,
    padding: Spacing.lg, marginTop: Spacing.md,
  },
  scoreHeader: { flexDirection: 'row', alignItems: 'center', gap: Spacing.sm, marginBottom: Spacing.md },
  scoreTitle: { fontSize: FontSize.md, fontWeight: '600', color: Colors.textPrimary },
  scoreGrid: { flexDirection: 'row', flexWrap: 'wrap', gap: Spacing.sm },
  scoreCell: {
    width: '48%', backgroundColor: Colors.backgroundAlt, borderRadius: BorderRadius.md,
    padding: Spacing.md, alignItems: 'center',
  },
  scoreCellHighlight: { backgroundColor: Colors.accent },
  scoreCellLabel: { fontSize: FontSize.xs, color: Colors.textSecondary },
  scoreCellValue: { fontSize: FontSize.xl, fontWeight: '700', color: Colors.textPrimary, marginTop: 2 },
  backBtn: {
    marginTop: Spacing.lg, borderRadius: BorderRadius.sm, padding: Spacing.md,
    alignItems: 'center', borderWidth: 1, borderColor: Colors.primary,
  },
  backText: { color: Colors.primary, fontSize: FontSize.md, fontWeight: '600' },
  summaryBlock: { marginTop: Spacing.md, padding: Spacing.md, backgroundColor: Colors.warningLight, borderRadius: BorderRadius.md },
  summaryLabel: { fontSize: FontSize.xs, fontWeight: '600', color: Colors.warning, marginBottom: 4 },
  summaryText: { fontSize: FontSize.sm, color: Colors.textPrimary, lineHeight: 20 },
  turnBlock: { marginTop: Spacing.md },
  turnTitle: { fontSize: FontSize.md, fontWeight: '600', color: Colors.textPrimary, marginBottom: Spacing.sm },
  turnItem: { backgroundColor: Colors.backgroundAlt, borderRadius: BorderRadius.md, padding: Spacing.md, marginBottom: Spacing.sm },
  turnLabel: { fontSize: FontSize.xs, fontWeight: '600', color: Colors.textSecondary, marginBottom: 2 },
  turnFeedback: { fontSize: FontSize.sm, color: Colors.textPrimary, lineHeight: 20 },
  inputBar: {
    flexDirection: 'row', alignItems: 'flex-end', padding: Spacing.md, gap: Spacing.sm,
    backgroundColor: Colors.white, ...Shadow.header,
  },
  input: {
    flex: 1, borderWidth: 1, borderColor: Colors.border, borderRadius: BorderRadius.lg,
    paddingHorizontal: Spacing.md, paddingVertical: Spacing.sm,
    fontSize: FontSize.md, color: Colors.textPrimary, maxHeight: 100,
  },
  sendBtn: {
    width: 44, height: 44, borderRadius: 22, backgroundColor: Colors.primary,
    alignItems: 'center', justifyContent: 'center',
  },
});
