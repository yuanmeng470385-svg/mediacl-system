/**
 * 产品使用 AI 助手（2026-09-15）：功能不熟/找不到入口时直接问。
 * 纯本地会话（消息不出本屏 state），后端无状态不落库；
 * 只答产品使用问题，医学问题会被引导去数字专员/医学问答。
 */
import React, { useEffect, useRef, useState } from 'react';
import {
  ActivityIndicator, KeyboardAvoidingView, Platform, ScrollView, StyleSheet, Text, TextInput,
  TouchableOpacity, View,
} from 'react-native';
import { useNavigation } from '@react-navigation/native';
import Icon from '../../components/Icon';
import { assistantAPI } from '../../api/assistant';
import { BorderRadius, Colors, FontSize, Shadow, Spacing } from '../../constants/theme';

interface Bubble {
  role: 'user' | 'assistant';
  content: string;
}

const GREETING: Bubble = {
  role: 'assistant',
  content: '你好，我是产品使用助手。不知道某个功能在哪、或者怎么用，直接问我，比如「在哪里管理我的分身？」「夜间简报在哪看？」',
};

const SUGGESTIONS = [
  '在哪里管理我的数字分身？',
  '夜间简报在哪看？',
  '怎么发起一次拜访？',
  'AI 陪练怎么选 Skill？',
];

export default function AssistantScreen() {
  const navigation = useNavigation();
  const [messages, setMessages] = useState<Bubble[]>([GREETING]);
  const [input, setInput] = useState('');
  const [asking, setAsking] = useState(false);
  const scrollRef = useRef<any>(null);

  useEffect(() => {
    // 新消息后贴底（稍延迟等布局完成）
    const timer = setTimeout(() => scrollRef.current?.scrollToEnd?.({ animated: true }), 80);
    return () => clearTimeout(timer);
  }, [messages, asking]);

  const ask = (text: string) => {
    const question = text.trim();
    if (!question || asking) return;
    setMessages((prev) => [...prev, { role: 'user', content: question }]);
    setInput('');
    setAsking(true);
    assistantAPI.ask(question)
      .then((res) => {
        setMessages((prev) => [...prev, {
          role: 'assistant',
          content: res?.answer || '抱歉，没能生成回答，请换个问法试试。',
        }]);
      })
      .catch((err: any) => {
        setMessages((prev) => [...prev, {
          role: 'assistant',
          content: err?.message || '网络异常，请稍后重试。',
        }]);
      })
      .finally(() => setAsking(false));
  };

  return (
    <View style={styles.container}>
      <View style={styles.header}>
        <TouchableOpacity onPress={() => navigation.goBack()}>
          <Icon name="chevron-left" size={22} color={Colors.textWhite} />
        </TouchableOpacity>
        <View style={styles.headerCenter}>
          <Icon name="robot-excited-outline" size={18} color={Colors.textWhite} />
          <Text style={styles.headerTitle}>AI 助手</Text>
        </View>
        <View style={{ width: 24 }} />
      </View>

      <KeyboardAvoidingView
        style={{ flex: 1 }}
        behavior={Platform.OS === 'ios' ? 'padding' : undefined}
        keyboardVerticalOffset={0}
      >
        <View style={styles.chatArea}>
          <ScrollView ref={scrollRef} contentContainerStyle={styles.chatContent}>
            {messages.map((m, i) => (
              <View
                key={i}
                style={[styles.bubbleRow, m.role === 'user' && styles.bubbleRowUser]}
              >
                <View style={[styles.bubble, m.role === 'user' ? styles.bubbleUser : styles.bubbleAi]}>
                  <Text style={m.role === 'user' ? styles.bubbleUserText : styles.bubbleAiText}>
                    {m.content}
                  </Text>
                </View>
              </View>
            ))}
            {asking && (
              <View style={styles.bubbleRow}>
                <View style={[styles.bubble, styles.bubbleAi, styles.thinking]}>
                  <ActivityIndicator size="small" color={Colors.primary} />
                  <Text style={styles.thinkingText}>思考中…</Text>
                </View>
              </View>
            )}
          </ScrollView>
        </View>

        {/* 常问快捷入口：仅首轮展示 */}
        {messages.length === 1 && !asking && (
          <View style={styles.suggestWrap}>
            {SUGGESTIONS.map((s) => (
              <TouchableOpacity key={s} style={styles.suggestChip} onPress={() => ask(s)} activeOpacity={0.7}>
                <Text style={styles.suggestText}>{s}</Text>
              </TouchableOpacity>
            ))}
          </View>
        )}

        <View style={styles.inputBar}>
          <TextInput
            style={styles.input}
            value={input}
            onChangeText={setInput}
            placeholder="问问功能在哪、怎么用…"
            placeholderTextColor={Colors.textHint}
            multiline
            maxLength={500}
          />
          <TouchableOpacity
            style={[styles.sendBtn, (!input.trim() || asking) && { opacity: 0.5 }]}
            disabled={!input.trim() || asking}
            onPress={() => ask(input)}
            activeOpacity={0.7}
          >
            <Icon name="send" size={18} color={Colors.textWhite} />
          </TouchableOpacity>
        </View>
      </KeyboardAvoidingView>
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
  headerCenter: { flexDirection: 'row', alignItems: 'center', gap: Spacing.xs },
  headerTitle: { color: Colors.textWhite, fontSize: FontSize.lg, fontWeight: '600' },
  chatArea: { flex: 1 },
  chatContent: { padding: Spacing.md, paddingBottom: Spacing.sm },
  bubbleRow: { flexDirection: 'row', marginBottom: Spacing.md },
  bubbleRowUser: { justifyContent: 'flex-end' },
  bubble: {
    maxWidth: '82%', borderRadius: BorderRadius.lg, padding: Spacing.md,
  },
  bubbleAi: { backgroundColor: Colors.card, ...Shadow.card },
  bubbleUser: { backgroundColor: Colors.primary },
  bubbleAiText: { fontSize: FontSize.sm, color: Colors.textPrimary, lineHeight: 21 },
  bubbleUserText: { fontSize: FontSize.sm, color: Colors.textWhite, lineHeight: 21 },
  thinking: { flexDirection: 'row', alignItems: 'center', gap: Spacing.sm },
  thinkingText: { fontSize: FontSize.sm, color: Colors.textHint },
  suggestWrap: {
    flexDirection: 'row', flexWrap: 'wrap', gap: Spacing.sm,
    paddingHorizontal: Spacing.md, paddingBottom: Spacing.sm,
  },
  suggestChip: {
    borderWidth: 1, borderColor: Colors.primary, borderRadius: BorderRadius.full,
    backgroundColor: Colors.primarySurface, paddingHorizontal: Spacing.md, paddingVertical: Spacing.xs,
  },
  suggestText: { fontSize: FontSize.xs, color: Colors.primary },
  inputBar: {
    flexDirection: 'row', alignItems: 'flex-end', gap: Spacing.sm,
    padding: Spacing.md, borderTopWidth: StyleSheet.hairlineWidth,
    borderTopColor: Colors.divider, backgroundColor: Colors.card,
  },
  input: {
    flex: 1, minHeight: 40, maxHeight: 120, borderWidth: 1, borderColor: Colors.border,
    borderRadius: BorderRadius.lg, backgroundColor: Colors.white,
    paddingHorizontal: Spacing.md, paddingVertical: Spacing.sm,
    fontSize: FontSize.sm, color: Colors.textPrimary, textAlignVertical: 'center',
  },
  sendBtn: {
    width: 40, height: 40, borderRadius: BorderRadius.full, backgroundColor: Colors.primary,
    alignItems: 'center', justifyContent: 'center',
  },
});
