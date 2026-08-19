/**
 * 合规考试页（二期 F）：加载题目 → 逐题选择 → 提交 → 结果。
 * startExam 返回 {questions}，submitExam 返回 ExamRecord（request 已解包 data）。
 */
import React, { useCallback, useEffect, useState } from 'react';
import { Alert, ScrollView, StyleSheet, Text, TouchableOpacity, View } from 'react-native';
import { useNavigation } from '@react-navigation/native';
import { examAPI } from '../../api/exam';
import type { ExamQuestion } from '../../types';
import Icon from '../../components/Icon';
import { BorderRadius, Colors, FontSize, Shadow, Spacing } from '../../constants/theme';

const TYPE_TEXT: Record<string, string> = { single: '单选', multiple: '多选', judge: '判断' };

export default function ExamScreen() {
  const navigation = useNavigation();
  const [questions, setQuestions] = useState<ExamQuestion[]>([]);
  const [answers, setAnswers] = useState<Record<number, number[]>>({});
  const [submitting, setSubmitting] = useState(false);
  const [result, setResult] = useState<any | null>(null);

  const load = async () => {
    try {
      const res = await examAPI.startExam(10);
      setQuestions(res?.questions || []);
      const init: Record<number, number[]> = {};
      (res?.questions || []).forEach((q: ExamQuestion) => { init[q.id] = []; });
      setAnswers(init);
    } catch { Alert.alert('加载失败', '暂无可考试的题目或网络异常'); }
  };

  useEffect(() => { load(); }, []);

  const toggle = (qid: number, idx: number, multi: boolean) => {
    setAnswers(prev => {
      const cur = prev[qid] || [];
      if (multi) {
        const next = cur.includes(idx) ? cur.filter(i => i !== idx) : [...cur, idx];
        return { ...prev, [qid]: next };
      }
      return { ...prev, [qid]: cur.includes(idx) ? [] : [idx] };
    });
  };

  const submit = async () => {
    const payload = Object.entries(answers).map(([qid, selected]) => ({ question_id: Number(qid), selected }));
    if (payload.some(a => !a.selected.length)) { Alert.alert('提示', '请完成所有题目'); return; }
    setSubmitting(true);
    try {
      const res = await examAPI.submitExam(payload);
      setResult(res);
    } catch { Alert.alert('提交失败', '请稍后重试'); }
    finally { setSubmitting(false); }
  };

  if (result) {
    return (
      <View style={styles.container}>
        <View style={styles.header}><TouchableOpacity onPress={() => navigation.goBack()}><Icon name="chevron-left" size={22} color={Colors.textWhite} /></TouchableOpacity><Text style={styles.headerTitle}>考试结果</Text><View style={{ width: 24 }} /></View>
        <View style={[styles.card, Shadow.card]}>
          <Text style={[styles.score, { color: result.passed ? Colors.success : Colors.danger }]}>{result.score} 分</Text>
          <Text style={styles.desc}>{result.passed ? '已通过（≥80 分）' : '未通过，请重新学习后补考'}</Text>
          <Text style={styles.desc}>答对 {result.correct_count} / {result.question_count}</Text>
          <TouchableOpacity style={styles.submitBtn} onPress={() => navigation.goBack()}><Text style={styles.submitText}>返回</Text></TouchableOpacity>
        </View>
      </View>
    );
  }

  return (
    <View style={styles.container}>
      <View style={styles.header}><TouchableOpacity onPress={() => navigation.goBack()}><Icon name="chevron-left" size={22} color={Colors.textWhite} /></TouchableOpacity><Text style={styles.headerTitle}>合规考试</Text><View style={{ width: 24 }} /></View>
      <ScrollView contentContainerStyle={styles.content}>
        {questions.map((q, qi) => (
          <View key={q.id} style={[styles.card, Shadow.card]}>
            <Text style={styles.cardTitle}>{qi + 1}. {q.content} <Text style={styles.typeTag}>[{TYPE_TEXT[q.question_type] || q.question_type}]</Text></Text>
            {q.options.map((opt, oi) => {
              const sel = (answers[q.id] || []).includes(oi);
              return (
                <TouchableOpacity key={oi} style={[styles.option, sel && styles.optionSelected]} onPress={() => toggle(q.id, oi, q.question_type === 'multiple')}>
                  <Icon name={sel ? 'check-circle' : 'circle-outline'} size={18} color={sel ? Colors.primary : Colors.textHint} />
                  <Text style={styles.optionText}>{opt}</Text>
                </TouchableOpacity>
              );
            })}
          </View>
        ))}
        <TouchableOpacity style={[styles.submitBtn, submitting && { opacity: 0.6 }]} disabled={submitting} onPress={submit}>
          <Text style={styles.submitText}>{submitting ? '提交中…' : '提交试卷'}</Text>
        </TouchableOpacity>
      </ScrollView>
    </View>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1, backgroundColor: Colors.background },
  header: { backgroundColor: Colors.primary, paddingTop: 50, paddingBottom: 14, paddingHorizontal: Spacing.lg, flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', ...Shadow.header },
  headerTitle: { color: Colors.textWhite, fontSize: FontSize.lg, fontWeight: '600' },
  content: { padding: Spacing.md },
  card: { backgroundColor: Colors.card, borderRadius: BorderRadius.md, padding: Spacing.lg, marginBottom: Spacing.md },
  cardTitle: { fontSize: FontSize.md, fontWeight: '600', color: Colors.textPrimary, marginBottom: Spacing.sm },
  typeTag: { fontSize: FontSize.xs, color: Colors.textHint },
  option: { flexDirection: 'row', alignItems: 'center', gap: 8, borderWidth: 1, borderColor: Colors.border, borderRadius: BorderRadius.sm, padding: Spacing.sm, marginTop: Spacing.sm },
  optionSelected: { borderColor: Colors.primary, backgroundColor: 'rgba(22,119,255,0.08)' },
  optionText: { flex: 1, fontSize: FontSize.sm, color: Colors.textPrimary },
  score: { fontSize: 40, fontWeight: '700', textAlign: 'center', marginBottom: Spacing.sm },
  desc: { fontSize: FontSize.sm, color: Colors.textSecondary, textAlign: 'center', marginTop: 2 },
  submitBtn: { marginTop: Spacing.lg, backgroundColor: Colors.primary, borderRadius: BorderRadius.sm, padding: Spacing.md, alignItems: 'center' },
  submitText: { color: Colors.textWhite, fontSize: FontSize.md, fontWeight: '600' },
});
