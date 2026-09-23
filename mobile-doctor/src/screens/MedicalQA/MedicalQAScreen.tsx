/**
 * 医学问答 Tab（照 mobile ChatScreen 气泡+加载态范式）：
 *   - v1.1（2026-09-23）：WS 流式优先（openMedicalQaWs 打字机），REST 兜底；
 *     对话记录常驻 AsyncStorage（重进恢复），「新建对话」按钮另起窗口（豆包式）
 *   - 每条 AI 回答强制渲染 disclaimer 与"AI 生成"标识
 *   - blocked 态：渲染后端安全话术 + 违规提示明细
 */
import React, { useEffect, useRef, useState } from 'react';
import {
  View,
  Text,
  TextInput,
  TouchableOpacity,
  FlatList,
  StyleSheet,
  KeyboardAvoidingView,
  Platform,
  ActivityIndicator,
} from 'react-native';
import AsyncStorage from '@react-native-async-storage/async-storage';
import Icon, { ActionIcons } from '../../components/Icon';
import { medicalAPI } from '../../api/medical';
import { apiClient } from '../../api/client';
import { openMedicalQaWs, type MedicalQaWsSession } from '../../services/medicalQaWs';
import { Colors, FontSize, Spacing, BorderRadius, Shadow } from '../../constants/theme';
import type { ChatViolation } from '../../types';
import { BRAND } from '../../brandConfig';

interface Message {
  id: string;
  role: 'user' | 'assistant';
  content: string;
  citations?: { title: string; url?: string; doc_id?: string }[];
  disclaimer?: string;
  blocked?: boolean;
  violations?: ChatViolation[];
}

/** 违规明细文本：优先 matched_text，其次 reason，最后 rule_name（同 mobile ChatScreen 口径） */
function violationTextOf(violations: ChatViolation[] | undefined): string {
  const list = Array.isArray(violations) ? violations : [];
  return list
    .map((v) => String(v.matched_text || v.reason || v.rule_name || ''))
    .filter(Boolean)
    .join('；');
}

export default function MedicalQAScreen() {
  const [messages, setMessages] = useState<Message[]>([
    {
      id: 'welcome',
      role: 'assistant',
      content: '你好！我是医学信息助手，请描述你的医学问题。',
    },
  ]);
  const [input, setInput] = useState('');
  const [loading, setLoading] = useState(false);
  const flatListRef = useRef<FlatList>(null);

  // ---- v1.1：流式态 + 对话记录常驻（AsyncStorage）+ 新建对话 ----
  const [streaming, setStreaming] = useState(false);
  const [streamText, setStreamText] = useState('');
  const wsRef = useRef<MedicalQaWsSession | null>(null);
  const loadedRef = useRef(false);
  const HIST_KEY = 'medical_qa_history';

  const persist = (list: Message[]) => {
    AsyncStorage.setItem(HIST_KEY, JSON.stringify(list)).catch(() => {});
  };

  // 重进/重启恢复历史；损坏或为空 → 保持欢迎语（读取完成前不回写，防欢迎语覆盖历史）
  useEffect(() => {
    (async () => {
      try {
        const raw = await AsyncStorage.getItem(HIST_KEY);
        if (raw) {
          const list = JSON.parse(raw);
          if (Array.isArray(list) && list.length) setMessages(list);
        }
      } catch { /* 损坏忽略 */ }
      loadedRef.current = true;
    })();
    return () => { wsRef.current?.close(); wsRef.current = null; };
  }, []);

  useEffect(() => {
    if (loadedRef.current) persist(messages);
  }, [messages]);

  /** 新建对话：清空记录另起窗口（生成中禁用，防半截状态） */
  const handleNewChat = () => {
    if (loading || streaming) return;
    setMessages([
      { id: 'welcome', role: 'assistant', content: '你好！我是医学信息助手，请描述你的医学问题。' },
    ]);
  };

  /** AI 消息统一组装（WS done 与 REST 共用；blocked 拼违规明细，口径同旧版） */
  const pushAi = (d: {
    answer: string;
    citations?: Message['citations'];
    disclaimer?: string;
    blocked?: boolean;
    violations?: ChatViolation[];
  }) => {
    const violationText = violationTextOf(d.violations);
    setMessages((prev) => [
      ...prev,
      {
        id: `a_${Date.now()}`,
        role: 'assistant',
        content: d.blocked
          ? [d.answer, violationText && `（${violationText}）`].filter(Boolean).join('')
          : d.answer,
        citations: d.citations ?? [],
        disclaimer: d.disclaimer,
        blocked: d.blocked,
        violations: d.violations,
      },
    ]);
  };

  /**
   * WS 流式优先：8s 未收到 start 帧降级 REST（与 TwinChat/rep Chat 同款兜底节奏）。
   * onDelta 收到的是累积全文（与分身对话同口径），直接整段覆盖流式气泡。
   */
  const tryStream = (text: string, token: string): Promise<boolean> => {
    return new Promise((resolve) => {
      let settled = false;
      let started = false;
      const timer = setTimeout(() => {
        if (!started) { cleanup(); resolve(false); }
      }, 8000);
      const cleanup = () => {
        settled = true;
        clearTimeout(timer);
        wsRef.current?.close();
        wsRef.current = null;
      };
      const ws = openMedicalQaWs(token, {
        onStart: () => {
          if (settled) return;
          started = true;
          clearTimeout(timer);
          setStreaming(true);
          setStreamText('');
        },
        onDelta: (t) => { if (!settled) setStreamText(t); },
        onDone: (d) => {
          if (settled) return;
          settled = true;
          started = true;
          clearTimeout(timer);
          setStreaming(false);
          setStreamText('');
          pushAi({
            answer: d.answer ?? '',
            citations: d.citations,
            disclaimer: d.disclaimer,
            blocked: d.blocked,
            violations: (d.violations ?? []) as ChatViolation[],
          });
          wsRef.current = null;
          resolve(true);
        },
        onError: () => {
          if (settled) return;
          settled = true;
          started = true;
          clearTimeout(timer);
          setStreaming(false);
          setStreamText('');
          wsRef.current = null;
          resolve(false);
        },
      });
      wsRef.current = ws;
      ws.sendQuestion(text);
    });
  };

  const handleSend = async () => {
    const text = input.trim();
    if (!text || loading || streaming) return;

    const userMsg: Message = { id: `u_${Date.now()}`, role: 'user', content: text };
    setMessages((prev) => [...prev, userMsg]);
    setInput('');
    setLoading(true);

    try {
      // v1.1：WS 流式优先；未 start/断开/异常 → REST 兜底（medicalAPI.qa）
      const token = (await apiClient.getToken()) || '';
      const ok = await tryStream(text, token);
      if (!ok) {
        const response = await medicalAPI.qa(text);
        pushAi(response);
      }
    } catch (e: any) {
      // catch 闭包内先取字符串（Hermes 坑防御，同 TwinChat）
      const errMsg = `抱歉，出错了：${e?.message || '请稍后重试'}`;
      setMessages((prev) => [
        ...prev,
        { id: `err_${Date.now()}`, role: 'assistant', content: errMsg },
      ]);
    } finally {
      setLoading(false);
    }
  };

  const renderMessage = ({ item }: { item: Message }) => {
    const isUser = item.role === 'user';
    const violationText = violationTextOf(item.violations);

    return (
      <View style={styles.msgWrapper}>
        <View style={[styles.bubble, isUser ? styles.userBubble : styles.aiBubble]}>
          <Text style={[styles.bubbleText, isUser ? styles.userText : styles.aiText]} selectable>
            {item.content}
          </Text>

          {!isUser && item.citations && item.citations.length > 0 && (
            <View style={styles.citations}>
              <Text style={styles.citationTitle}>引用来源</Text>
              {item.citations.map((c, i) => (
                <View key={i} style={styles.citationItem}>
                  <View style={styles.citationBadge}>
                    <Text style={styles.citationIndex}>{i + 1}</Text>
                  </View>
                  <Text style={styles.citationContent} numberOfLines={2}>
                    {c.title}
                  </Text>
                </View>
              ))}
            </View>
          )}

          {/* 强制合规标识：每条 AI 回答（含 blocked）都渲染 disclaimer + AI 生成标识 */}
          {!isUser && (
            <View style={styles.disclaimerRow}>
              <View style={styles.aiBadge}>
                <Text style={styles.aiBadgeText}>AI 生成</Text>
              </View>
              {item.disclaimer ? (
                <Text style={styles.disclaimerText}>{item.disclaimer}</Text>
              ) : null}
            </View>
          )}

          {/* blocked 态违规提示（除正文拼接外单独渲染明细） */}
          {!isUser && item.blocked && violationText ? (
            <View style={styles.violationBox}>
              <Icon name={ActionIcons.close} size={14} color={Colors.danger} />
              <Text style={styles.violationText}>违规提示：{violationText}</Text>
            </View>
          ) : null}
        </View>
      </View>
    );
  };

  return (
    <KeyboardAvoidingView
      style={styles.container}
      behavior={Platform.OS === 'ios' ? 'padding' : undefined}
    >
      
      <FlatList
        ref={flatListRef}
        data={streaming || streamText
          ? [...messages, { id: 'streaming', role: 'assistant' as const, content: streamText || '正在思考...' }]
          : messages}
        ListHeaderComponent={
          <>
            {BRAND && (
        <View style={{ flexDirection: 'row', alignItems: 'center', paddingHorizontal: 16, paddingVertical: 7, backgroundColor: BRAND.primary }}>
          <View style={{ width: 18, height: 18, borderRadius: 5, backgroundColor: 'rgba(255,255,255,0.25)', alignItems: 'center', justifyContent: 'center', marginRight: 8 }}>
            <Text style={{ color: '#FFFFFF', fontSize: 11, fontWeight: '700' }}>{BRAND.char}</Text>
          </View>
          <Text style={{ color: '#FFFFFF', fontSize: 12, fontWeight: '600' }}>{BRAND.name}</Text>
          <Text numberOfLines={1} style={{ color: 'rgba(255,255,255,0.8)', fontSize: 11, marginLeft: 10, flexShrink: 1 }}>{BRAND.tagline}</Text>
        </View>
      )}
            <View style={styles.header}>
              <View style={{ flex: 1 }}>
                <Text style={styles.headerTitle}>医学问答</Text>
                <Text style={styles.headerSubtitle}>基于知识库的医学信息检索</Text>
              </View>
              <TouchableOpacity
                onPress={handleNewChat}
                disabled={loading || streaming}
                activeOpacity={0.7}
                style={{
                  paddingHorizontal: 12, paddingVertical: 6, borderRadius: 14,
                  backgroundColor: 'rgba(255,255,255,0.18)',
                  opacity: loading || streaming ? 0.5 : 1,
                }}
              >
                <Text style={{ color: Colors.textWhite, fontSize: 12, fontWeight: '600' }}>＋ 新对话</Text>
              </TouchableOpacity>
            </View>
          </>
        }
        renderItem={renderMessage}
        keyExtractor={(item) => item.id}
        contentContainerStyle={styles.list}
        onContentSizeChange={() => setTimeout(() => flatListRef.current?.scrollToEnd(), 100)}
        showsVerticalScrollIndicator={false}
      />

      <View style={styles.inputBar}>
        <TextInput
          style={styles.input}
          value={input}
          onChangeText={setInput}
          placeholder="输入医学问题..."
          placeholderTextColor={Colors.textHint}
          multiline
          maxLength={2000}
          returnKeyType="send"
          onSubmitEditing={handleSend}
          blurOnSubmit={false}
        />
        <TouchableOpacity
          style={[styles.sendBtn, (!input.trim() || loading || streaming) && styles.sendBtnDisabled]}
          onPress={handleSend}
          disabled={!input.trim() || loading || streaming}
          activeOpacity={0.7}
        >
          {loading || streaming ? (
            <ActivityIndicator color={Colors.textWhite} size="small" />
          ) : (
            <Icon name={ActionIcons.send} size={18} color={Colors.textWhite} />
          )}
        </TouchableOpacity>
      </View>
    </KeyboardAvoidingView>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1, backgroundColor: Colors.background },
  header: {
    backgroundColor: Colors.primary,
    paddingTop: 52,
    paddingBottom: Spacing.lg,
    paddingHorizontal: Spacing.xl,
    flexDirection: 'row',
    alignItems: 'flex-end',
  },
  headerTitle: { color: Colors.textWhite, fontSize: FontSize.xl, fontWeight: '700' },
  headerSubtitle: {
    color: 'rgba(255,255,255,0.7)',
    fontSize: FontSize.sm,
    marginTop: 4,
  },
  list: { padding: Spacing.lg, paddingBottom: Spacing.sm },
  msgWrapper: { marginBottom: Spacing.lg },
  bubble: { padding: Spacing.md, borderRadius: BorderRadius.lg, maxWidth: '88%' },
  userBubble: {
    alignSelf: 'flex-end',
    backgroundColor: Colors.primary,
    borderBottomRightRadius: 4,
  },
  aiBubble: {
    alignSelf: 'flex-start',
    backgroundColor: Colors.white,
    borderBottomLeftRadius: 4,
    ...Shadow.card,
  },
  bubbleText: { fontSize: FontSize.md, lineHeight: 22 },
  userText: { color: Colors.textWhite },
  aiText: { color: Colors.textPrimary },
  citations: {
    marginTop: Spacing.md,
    paddingTop: Spacing.md,
    borderTopWidth: 1,
    borderTopColor: Colors.divider,
  },
  citationTitle: {
    fontSize: FontSize.xs,
    fontWeight: '600',
    color: Colors.textSecondary,
    marginBottom: Spacing.sm,
  },
  citationItem: {
    flexDirection: 'row',
    marginBottom: 4,
    gap: Spacing.sm,
    alignItems: 'center',
  },
  citationBadge: {
    width: 20,
    height: 20,
    borderRadius: 10,
    backgroundColor: Colors.primarySurface,
    alignItems: 'center',
    justifyContent: 'center',
  },
  citationIndex: { fontSize: FontSize.xs, color: Colors.primary, fontWeight: '700' },
  citationContent: { fontSize: FontSize.xs, color: Colors.textSecondary, flex: 1 },
  disclaimerRow: {
    marginTop: Spacing.md,
    paddingTop: Spacing.sm,
    borderTopWidth: 1,
    borderTopColor: Colors.divider,
    gap: Spacing.xs,
  },
  aiBadge: {
    alignSelf: 'flex-start',
    backgroundColor: Colors.accentLight,
    borderRadius: BorderRadius.sm,
    paddingHorizontal: 6,
    paddingVertical: 2,
  },
  aiBadgeText: { fontSize: FontSize.xs, color: Colors.info, fontWeight: '600' },
  disclaimerText: { fontSize: FontSize.xs, color: Colors.textHint, lineHeight: 16 },
  violationBox: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: Spacing.xs,
    marginTop: Spacing.sm,
    padding: Spacing.sm,
    borderRadius: BorderRadius.sm,
    backgroundColor: Colors.dangerLight,
  },
  violationText: { flex: 1, fontSize: FontSize.xs, color: Colors.danger },
  inputBar: {
    flexDirection: 'row',
    alignItems: 'flex-end',
    padding: Spacing.sm,
    backgroundColor: Colors.white,
    borderTopWidth: 1,
    borderTopColor: Colors.divider,
    gap: Spacing.sm,
  },
  input: {
    flex: 1,
    paddingHorizontal: Spacing.md,
    paddingVertical: Spacing.sm,
    fontSize: FontSize.md,
    maxHeight: 100,
    backgroundColor: Colors.background,
    borderRadius: BorderRadius.xl,
    color: Colors.textPrimary,
  },
  sendBtn: {
    backgroundColor: Colors.primary,
    paddingHorizontal: Spacing.lg,
    paddingVertical: 10,
    borderRadius: BorderRadius.xl,
    justifyContent: 'center',
    minWidth: 44,
    alignItems: 'center',
  },
  sendBtnDisabled: { backgroundColor: Colors.border },
});
