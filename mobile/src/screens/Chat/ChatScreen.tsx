/**
 * 数字专员对话页 - 核心交互页面
 * 功能：气泡对话 / 引用来源卡片 / 证据等级 / 反馈收藏 / 语音输入 / 多轮对话
 */
import React, { useState, useRef, useCallback } from 'react';
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
  Alert,
} from 'react-native';
import { useRoute, useNavigation } from '@react-navigation/native';
import type { RouteProp } from '@react-navigation/native';
import EvidenceBadge from '../../components/EvidenceBadge';
import Icon from '../../components/Icon';
import { ActionIcons } from '../../components/Icon';
import { specialistAPI } from '../../api/specialist';
import { Colors, FontSize, Spacing, BorderRadius, Shadow } from '../../constants/theme';
import type { ChatScreenParams } from '../../navigation/types';

type RouteType = RouteProp<{ Chat: ChatScreenParams }, 'Chat'>;

interface Message {
  id: string;
  role: 'user' | 'assistant' | 'system';
  content: string;
  citations?: { title: string; url?: string }[];
  evidenceLevel?: string;
  blocked?: boolean;
  /** 反馈/收藏主键（assistant 行 id）。为空则禁用这两个动作 */
  conversationId?: number | null;
}

export default function ChatScreen() {
  const route = useRoute<RouteType>();
  const navigation = useNavigation();
  const { specialistId, specialistName } = route.params;

  const [messages, setMessages] = useState<Message[]>([
    {
      id: 'welcome',
      role: 'assistant',
      content: `你好！我是${specialistName}。有什么可以帮助你的？`,
    },
  ]);
  const [input, setInput] = useState('');
  const [loading, setLoading] = useState(false);
  const [sessionId, setSessionId] = useState<string | null>(null);
  const flatListRef = useRef<FlatList>(null);

  const handleSend = useCallback(async () => {
    const text = input.trim();
    if (!text || loading) return;

    // 不做客户端合规预检：/compliance/check 需 X-Internal-Key（恒 403），
    // 且服务端 answer_generator 已在 chat 流程内完成问题预检。
    const userMsg: Message = { id: `u_${Date.now()}`, role: 'user', content: text };
    setMessages((prev) => [...prev, userMsg]);
    setInput('');
    setLoading(true);

    try {
      const response = await specialistAPI.sendMessage(specialistId, {
        question: text,
        session_id: sessionId || undefined,
      });

      if (!sessionId && response.session_id) setSessionId(response.session_id);

      // blocked 时展示后端给出的真实原因与违规明细，不再写死话术
      const violationText = (response.violations ?? [])
        .map((v) => v.description)
        .filter(Boolean)
        .join('；');
      const content = response.blocked
        ? [response.answer, violationText && `（${violationText}）`]
            .filter(Boolean)
            .join('')
        : response.answer;

      const aiMsg: Message = {
        id: response.request_id || `a_${Date.now()}`,
        role: 'assistant',
        content,
        citations: response.citations,
        evidenceLevel: response.evidence_level,
        blocked: response.blocked,
        conversationId: response.conversation_id ?? null,
      };
      setMessages((prev) => [...prev, aiMsg]);
    } catch (e: any) {
      setMessages((prev) => [...prev, {
        id: `err_${Date.now()}`, role: 'assistant',
        content: `抱歉，出错了：${e.message || '请稍后重试'}`,
      }]);
    } finally {
      setLoading(false);
    }
  }, [input, loading, specialistId, sessionId]);

  const handleFeedback = (msg: Message, rating: 1 | -1) => {
    if (!msg.conversationId) return;
    specialistAPI.sendFeedback(msg.conversationId, rating)
      .then(() => Alert.alert('提示', rating === 1 ? '感谢反馈！' : '我们会持续改进'))
      .catch((e) => Alert.alert('提示', e.message || '操作失败'));
  };

  const handleFavorite = (msg: Message) => {
    if (!msg.conversationId) return;
    specialistAPI.toggleFavorite(msg.conversationId)
      .then((r) => Alert.alert('提示', r.is_favorite ? '已收藏' : '已取消收藏'))
      .catch((e) => Alert.alert('提示', e.message || '操作失败'));
  };

  const renderMessage = ({ item }: { item: Message }) => {
    const isUser = item.role === 'user';
    const isSystem = item.role === 'system';

    if (isSystem) {
      return (
        <View style={styles.systemBubble}>
          <Icon name={ActionIcons.close} size={14} color={Colors.danger} />
          <Text style={styles.systemText}>{item.content}</Text>
        </View>
      );
    }

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
                  <Text style={styles.citationContent} numberOfLines={2}>{c.title}</Text>
                </View>
              ))}
            </View>
          )}

          {!isUser && item.evidenceLevel && (
            <View style={styles.evidenceRow}>
              <EvidenceBadge level={item.evidenceLevel} />
            </View>
          )}
        </View>

        {!isUser && !item.blocked && item.conversationId && (
          <View style={styles.actions}>
            <TouchableOpacity style={styles.actionBtn} onPress={() => handleFeedback(item, 1)}>
              <Icon name={ActionIcons.thumbUp} size={16} color={Colors.textHint} />
            </TouchableOpacity>
            <TouchableOpacity style={styles.actionBtn} onPress={() => handleFeedback(item, -1)}>
              <Icon name={ActionIcons.thumbDown} size={16} color={Colors.textHint} />
            </TouchableOpacity>
            <TouchableOpacity style={styles.actionBtn} onPress={() => handleFavorite(item)}>
              <Icon name={ActionIcons.star} size={16} color={Colors.textHint} />
            </TouchableOpacity>
          </View>
        )}
      </View>
    );
  };

  return (
    <KeyboardAvoidingView
      style={styles.container}
      behavior={Platform.OS === 'ios' ? 'padding' : undefined}
      keyboardVerticalOffset={0}
    >
      <View style={styles.header}>
        <TouchableOpacity onPress={() => navigation.goBack()} style={styles.headerBtn}>
          <Icon name={ActionIcons.back} size={22} color={Colors.textWhite} />
        </TouchableOpacity>
        <View style={styles.headerCenter}>
          <Text style={styles.headerTitle}>{specialistName}</Text>
          <Text style={styles.headerSub}>数字学术专员 · 在线</Text>
        </View>
        <View style={{ width: 40 }} />
      </View>

      <FlatList
        ref={flatListRef}
        data={messages}
        renderItem={renderMessage}
        keyExtractor={(item) => item.id}
        contentContainerStyle={styles.list}
        onContentSizeChange={() => setTimeout(() => flatListRef.current?.scrollToEnd(), 100)}
        showsVerticalScrollIndicator={false}
      />

      <View style={styles.inputBar}>
        <TouchableOpacity style={styles.voiceBtn}>
          <Icon name={ActionIcons.mic} size={22} color={Colors.textSecondary} />
        </TouchableOpacity>
        <TextInput
          style={styles.input}
          value={input}
          onChangeText={setInput}
          placeholder="输入问题..."
          placeholderTextColor={Colors.textHint}
          multiline
          maxLength={2000}
          returnKeyType="send"
          onSubmitEditing={handleSend}
          blurOnSubmit={false}
        />
        <TouchableOpacity
          style={[styles.sendBtn, (!input.trim() || loading) && styles.sendBtnDisabled]}
          onPress={handleSend}
          disabled={!input.trim() || loading}
          activeOpacity={0.7}
        >
          {loading ? (
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
    paddingTop: 50, paddingBottom: 14,
    paddingHorizontal: Spacing.lg,
    flexDirection: 'row', alignItems: 'center',
    ...Shadow.header,
  },
  headerBtn: { padding: 4 },
  headerCenter: { flex: 1, alignItems: 'center' },
  headerTitle: { color: Colors.textWhite, fontSize: FontSize.lg, fontWeight: '600' },
  headerSub: { color: 'rgba(255,255,255,0.6)', fontSize: FontSize.xs, marginTop: 2 },
  list: { padding: Spacing.lg, paddingBottom: Spacing.sm },
  msgWrapper: { marginBottom: Spacing.lg },
  bubble: { padding: Spacing.md, borderRadius: BorderRadius.lg, maxWidth: '82%' },
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
  systemBubble: {
    alignSelf: 'center',
    backgroundColor: Colors.dangerLight,
    paddingHorizontal: Spacing.lg, paddingVertical: Spacing.sm,
    borderRadius: BorderRadius.full, marginBottom: Spacing.md,
    flexDirection: 'row', alignItems: 'center', gap: Spacing.sm,
    borderWidth: 1, borderColor: '#fecaca',
  },
  systemText: { color: Colors.danger, fontSize: FontSize.sm },
  citations: {
    marginTop: Spacing.md, paddingTop: Spacing.md,
    borderTopWidth: 1, borderTopColor: Colors.divider,
  },
  citationTitle: {
    fontSize: FontSize.xs, fontWeight: '600',
    color: Colors.textSecondary, marginBottom: Spacing.sm,
  },
  citationItem: {
    flexDirection: 'row', marginBottom: 4, gap: Spacing.sm, alignItems: 'center',
  },
  citationBadge: {
    width: 20, height: 20, borderRadius: 10,
    backgroundColor: Colors.primarySurface,
    alignItems: 'center', justifyContent: 'center',
  },
  citationIndex: { fontSize: FontSize.xs, color: Colors.primary, fontWeight: '700' },
  citationContent: { fontSize: FontSize.xs, color: Colors.textSecondary, flex: 1 },
  evidenceRow: { marginTop: Spacing.sm },
  actions: {
    flexDirection: 'row', gap: Spacing.sm,
    marginTop: Spacing.xs, marginLeft: Spacing.sm,
  },
  actionBtn: {
    padding: 8, borderRadius: BorderRadius.full,
    backgroundColor: Colors.white, ...Shadow.card,
  },
  inputBar: {
    flexDirection: 'row', alignItems: 'flex-end',
    padding: Spacing.sm, backgroundColor: Colors.white,
    borderTopWidth: 1, borderTopColor: Colors.divider, gap: Spacing.sm,
  },
  voiceBtn: {
    width: 40, height: 40, borderRadius: 20,
    backgroundColor: Colors.background,
    alignItems: 'center', justifyContent: 'center',
  },
  input: {
    flex: 1, paddingHorizontal: Spacing.md, paddingVertical: Spacing.sm,
    fontSize: FontSize.md, maxHeight: 100,
    backgroundColor: Colors.background, borderRadius: BorderRadius.xl,
    color: Colors.textPrimary,
  },
  sendBtn: {
    backgroundColor: Colors.primary, paddingHorizontal: Spacing.lg,
    paddingVertical: 10, borderRadius: BorderRadius.xl,
    justifyContent: 'center', minWidth: 44, alignItems: 'center',
  },
  sendBtnDisabled: { backgroundColor: Colors.border },
});
