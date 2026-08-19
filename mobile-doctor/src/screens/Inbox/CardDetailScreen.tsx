/**
 * 学术卡片详情页（二期 G 医生端）：
 *   - 展示卡片正文（结论/要点/一句话总结/引用来源）+ AI 生成标识
 *   - 离开时上报阅读（read + 停留秒数，走 trackRead）
 *   - 反馈：有用 / 无用 / 追问文本（走 submitFeedback）
 *
 * 后端无单卡详情端点，卡片正文随收件箱 listInbox 每条携带（card 对象），
 * 故本页用 listInbox 按 pushId 定位（与导航参数 { pushId } 对齐）。
 */
import React, { useCallback, useEffect, useRef, useState } from 'react';
import {
  ActivityIndicator,
  Alert,
  ScrollView,
  StyleSheet,
  Text,
  TextInput,
  TouchableOpacity,
  View,
} from 'react-native';
import { useNavigation, useRoute } from '@react-navigation/native';
import type { RouteProp } from '@react-navigation/native';
import Icon, { ActionIcons } from '../../components/Icon';
import { inboxAPI } from '../../api/inbox';
import { Colors, FontSize, Spacing, BorderRadius, Shadow } from '../../constants/theme';
import type { RootStackParamList } from '../../navigation/types';
import type { CardPushRecord } from '../../types';

type RouteType = RouteProp<RootStackParamList, 'CardDetail'>;

type FeedbackKind = 'useful' | 'useless';

export default function CardDetailScreen() {
  const route = useRoute<RouteType>();
  const navigation = useNavigation();
  const { pushId } = route.params;

  const [record, setRecord] = useState<CardPushRecord | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');

  const [feedbackKind, setFeedbackKind] = useState<FeedbackKind | null>(null);
  const [submittingKind, setSubmittingKind] = useState<FeedbackKind | null>(null);
  const [question, setQuestion] = useState('');
  const [submittingQuestion, setSubmittingQuestion] = useState(false);

  const startTimeRef = useRef<number>(Date.now());
  const reportedRef = useRef(false);

  const load = useCallback(async () => {
    setLoading(true);
    setError('');
    try {
      const res = await inboxAPI.listInbox();
      const items = Array.isArray(res?.items) ? res.items : [];
      setRecord(items.find((it) => it.id === pushId) ?? null);
      if (!items.some((it) => it.id === pushId)) {
        setError('未找到该卡片');
      }
    } catch (e: any) {
      setError(e?.message || '卡片加载失败，请检查网络');
    } finally {
      setLoading(false);
    }
  }, [pushId]);

  useEffect(() => {
    load();
  }, [load]);

  // 离开页面时上报阅读：read + 停留秒数（fire-and-forget，只报一次）
  useEffect(() => {
    return () => {
      if (reportedRef.current) return;
      reportedRef.current = true;
      const seconds = Math.floor((Date.now() - startTimeRef.current) / 1000);
      inboxAPI.trackRead(pushId, 'read', seconds).catch(() => {
        // 静默失败：阅读上报不阻塞离开
      });
    };
  }, [pushId]);

  const handleFeedback = async (kind: FeedbackKind) => {
    if (submittingKind) return;
    setSubmittingKind(kind);
    try {
      await inboxAPI.submitFeedback(pushId, kind);
      setFeedbackKind(kind);
    } catch (e: any) {
      Alert.alert('提交失败', e?.message || '请稍后重试');
    } finally {
      setSubmittingKind(null);
    }
  };

  const handleQuestion = async () => {
    const text = question.trim();
    if (!text || submittingQuestion) return;
    setSubmittingQuestion(true);
    try {
      await inboxAPI.submitFeedback(pushId, text);
      setQuestion('');
      Alert.alert('已提交', '追问已发送给医药代表');
    } catch (e: any) {
      Alert.alert('提交失败', e?.message || '请稍后重试');
    } finally {
      setSubmittingQuestion(false);
    }
  };

  const content = record?.card?.content;
  const citations = Array.isArray(content?.citations) ? content.citations : [];
  const keyPoints = Array.isArray(content?.key_points) ? content.key_points : [];

  return (
    <View style={styles.container}>
      <View style={styles.header}>
        <TouchableOpacity onPress={() => navigation.goBack()} style={styles.headerBtn}>
          <Icon name={ActionIcons.back} size={22} color={Colors.textWhite} />
        </TouchableOpacity>
        <View style={styles.headerCenter}>
          <Text style={styles.headerTitle} numberOfLines={1}>
            {record?.card?.title || '学术卡片'}
          </Text>
          <Text style={styles.headerSub}>学术卡片详情</Text>
        </View>
        <View style={{ width: 40 }} />
      </View>

      {loading ? (
        <View style={styles.centered}>
          <ActivityIndicator size="large" color={Colors.primary} />
          <Text style={styles.loadingText}>加载卡片内容...</Text>
        </View>
      ) : error || !content ? (
        <View style={styles.centered}>
          <Icon name="file-document-outline" size={48} color={Colors.textHint} />
          <Text style={styles.errorText}>{error || '暂无内容'}</Text>
          <TouchableOpacity style={styles.retryBtn} onPress={load} activeOpacity={0.8}>
            <Text style={styles.retryText}>重试</Text>
          </TouchableOpacity>
        </View>
      ) : (
        <ScrollView contentContainerStyle={styles.content} showsVerticalScrollIndicator={false}>
          {record?.card?.is_ai_generated ? (
            <View style={styles.aiBanner}>
              <Icon name="robot-outline" size={14} color={Colors.info} />
              <Text style={styles.aiBannerText}>
                该卡片由 AI 生成，内容仅供学术参考，不构成诊疗建议
              </Text>
            </View>
          ) : null}

          {content.summary ? (
            <View style={[styles.section, Shadow.card]}>
              <Text style={styles.sectionTitle}>一句话总结</Text>
              <Text style={styles.summaryText}>{content.summary}</Text>
            </View>
          ) : null}

          {content.conclusion ? (
            <View style={[styles.section, Shadow.card]}>
              <Text style={styles.sectionTitle}>核心结论</Text>
              <Text style={styles.bodyText}>{content.conclusion}</Text>
            </View>
          ) : null}

          {keyPoints.length > 0 ? (
            <View style={[styles.section, Shadow.card]}>
              <Text style={styles.sectionTitle}>要点</Text>
              {keyPoints.map((kp, i) => (
                <View key={i} style={styles.pointRow}>
                  <View style={styles.pointBadge}>
                    <Text style={styles.pointIndex}>{i + 1}</Text>
                  </View>
                  <Text style={styles.pointText}>{kp}</Text>
                </View>
              ))}
            </View>
          ) : null}

          {citations.length > 0 ? (
            <View style={[styles.section, Shadow.card]}>
              <Text style={styles.sectionTitle}>引用来源</Text>
              {citations.map((c, i) => (
                <View key={i} style={styles.citationItem}>
                  <Text style={styles.citationIndex}>{i + 1}.</Text>
                  <View style={styles.citationBody}>
                    <Text style={styles.citationName}>{c.doc_name || '未命名文献'}</Text>
                    {c.version || c.section ? (
                      <Text style={styles.citationMeta}>
                        {[c.version, c.section].filter(Boolean).join(' · ')}
                      </Text>
                    ) : null}
                  </View>
                </View>
              ))}
            </View>
          ) : null}

          {/* 反馈区 */}
          <View style={[styles.section, Shadow.card, styles.feedbackSection]}>
            <Text style={styles.sectionTitle}>反馈</Text>
            <View style={styles.feedbackRow}>
              <TouchableOpacity
                style={[
                  styles.feedbackBtn,
                  feedbackKind === 'useful' && styles.feedbackBtnActive,
                ]}
                onPress={() => handleFeedback('useful')}
                disabled={submittingKind !== null}
                activeOpacity={0.7}
              >
                {submittingKind === 'useful' ? (
                  <ActivityIndicator size="small" color={Colors.primary} />
                ) : (
                  <Icon
                    name={ActionIcons.thumbUp}
                    size={16}
                    color={feedbackKind === 'useful' ? Colors.textWhite : Colors.primary}
                  />
                )}
                <Text
                  style={[
                    styles.feedbackBtnText,
                    feedbackKind === 'useful' && styles.feedbackBtnTextActive,
                  ]}
                >
                  有用
                </Text>
              </TouchableOpacity>

              <TouchableOpacity
                style={[
                  styles.feedbackBtn,
                  feedbackKind === 'useless' && styles.feedbackBtnActive,
                ]}
                onPress={() => handleFeedback('useless')}
                disabled={submittingKind !== null}
                activeOpacity={0.7}
              >
                {submittingKind === 'useless' ? (
                  <ActivityIndicator size="small" color={Colors.primary} />
                ) : (
                  <Icon
                    name={ActionIcons.thumbDown}
                    size={16}
                    color={feedbackKind === 'useless' ? Colors.textWhite : Colors.primary}
                  />
                )}
                <Text
                  style={[
                    styles.feedbackBtnText,
                    feedbackKind === 'useless' && styles.feedbackBtnTextActive,
                  ]}
                >
                  无用
                </Text>
              </TouchableOpacity>
            </View>

            <TextInput
              style={styles.questionInput}
              value={question}
              onChangeText={setQuestion}
              placeholder="对卡片内容有疑问？向医药代表提问..."
              placeholderTextColor={Colors.textHint}
              multiline
              maxLength={500}
            />
            <TouchableOpacity
              style={[styles.questionBtn, (!question.trim() || submittingQuestion) && styles.questionBtnDisabled]}
              onPress={handleQuestion}
              disabled={!question.trim() || submittingQuestion}
              activeOpacity={0.7}
            >
              {submittingQuestion ? (
                <ActivityIndicator size="small" color={Colors.textWhite} />
              ) : (
                <Text style={styles.questionBtnText}>提交追问</Text>
              )}
            </TouchableOpacity>
          </View>
        </ScrollView>
      )}
    </View>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1, backgroundColor: Colors.background },
  centered: { flex: 1, justifyContent: 'center', alignItems: 'center', padding: Spacing.xl },
  loadingText: { marginTop: Spacing.md, color: Colors.textHint, fontSize: FontSize.sm },
  errorText: {
    fontSize: FontSize.md,
    color: Colors.textSecondary,
    marginTop: Spacing.md,
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
  header: {
    backgroundColor: Colors.primary,
    paddingTop: 50,
    paddingBottom: 14,
    paddingHorizontal: Spacing.lg,
    flexDirection: 'row',
    alignItems: 'center',
    ...Shadow.header,
  },
  headerBtn: { padding: 4 },
  headerCenter: { flex: 1, alignItems: 'center', paddingHorizontal: Spacing.sm },
  headerTitle: { color: Colors.textWhite, fontSize: FontSize.lg, fontWeight: '600' },
  headerSub: { color: 'rgba(255,255,255,0.6)', fontSize: FontSize.xs, marginTop: 2 },
  content: { padding: Spacing.lg, paddingBottom: Spacing.xxxl },
  aiBanner: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: Spacing.xs,
    backgroundColor: Colors.infoLight,
    borderRadius: BorderRadius.md,
    paddingHorizontal: Spacing.md,
    paddingVertical: Spacing.sm,
    marginBottom: Spacing.md,
  },
  aiBannerText: { flex: 1, fontSize: FontSize.xs, color: Colors.info, lineHeight: 16 },
  section: {
    backgroundColor: Colors.white,
    borderRadius: BorderRadius.lg,
    padding: Spacing.lg,
    marginBottom: Spacing.md,
  },
  sectionTitle: {
    fontSize: FontSize.sm,
    fontWeight: '700',
    color: Colors.textSecondary,
    marginBottom: Spacing.sm,
  },
  summaryText: { fontSize: FontSize.md, color: Colors.textPrimary, lineHeight: 22 },
  bodyText: { fontSize: FontSize.md, color: Colors.textPrimary, lineHeight: 22 },
  pointRow: { flexDirection: 'row', gap: Spacing.sm, marginBottom: Spacing.sm },
  pointBadge: {
    width: 20,
    height: 20,
    borderRadius: 10,
    backgroundColor: Colors.primarySurface,
    alignItems: 'center',
    justifyContent: 'center',
    marginTop: 2,
  },
  pointIndex: { fontSize: FontSize.xs, color: Colors.primary, fontWeight: '700' },
  pointText: { flex: 1, fontSize: FontSize.md, color: Colors.textPrimary, lineHeight: 22 },
  citationItem: { flexDirection: 'row', gap: Spacing.sm, marginBottom: Spacing.sm },
  citationIndex: { fontSize: FontSize.sm, color: Colors.textSecondary, fontWeight: '600' },
  citationBody: { flex: 1 },
  citationName: { fontSize: FontSize.sm, color: Colors.textPrimary, fontWeight: '500' },
  citationMeta: { fontSize: FontSize.xs, color: Colors.textHint, marginTop: 2 },
  feedbackSection: { marginTop: Spacing.sm },
  feedbackRow: { flexDirection: 'row', gap: Spacing.sm, marginBottom: Spacing.md },
  feedbackBtn: {
    flex: 1,
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'center',
    gap: Spacing.xs,
    paddingVertical: 10,
    borderRadius: BorderRadius.md,
    borderWidth: 1,
    borderColor: Colors.primary,
    backgroundColor: Colors.white,
  },
  feedbackBtnActive: { backgroundColor: Colors.primary },
  feedbackBtnText: { fontSize: FontSize.md, fontWeight: '600', color: Colors.primary },
  feedbackBtnTextActive: { color: Colors.textWhite },
  questionInput: {
    minHeight: 80,
    paddingHorizontal: Spacing.md,
    paddingVertical: Spacing.sm,
    fontSize: FontSize.md,
    backgroundColor: Colors.background,
    borderRadius: BorderRadius.md,
    color: Colors.textPrimary,
    textAlignVertical: 'top',
  },
  questionBtn: {
    backgroundColor: Colors.primary,
    borderRadius: BorderRadius.md,
    paddingVertical: 10,
    alignItems: 'center',
    marginTop: Spacing.sm,
  },
  questionBtnDisabled: { backgroundColor: Colors.border },
  questionBtnText: { color: Colors.textWhite, fontSize: FontSize.md, fontWeight: '600' },
});
