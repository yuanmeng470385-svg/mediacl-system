/**
 * 数字专员对话页 - 核心交互页面
 * 功能：气泡对话 / 引用来源卡片 / 证据等级 / 反馈收藏 / 语音输入 / 多轮对话
 */
import React, { useState, useRef, useCallback, useEffect } from 'react';
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
import AsyncStorage from '@react-native-async-storage/async-storage';
import EvidenceBadge from '../../components/EvidenceBadge';
import Icon from '../../components/Icon';
import { ActionIcons } from '../../components/Icon';
import { specialistAPI } from '../../api/specialist';
import { apiClient } from '../../api/client';
import { openChatWs } from '../../services/wsChat';
import { Colors, FontSize, Spacing, BorderRadius, Shadow } from '../../constants/theme';
import type { ChatScreenParams } from '../../navigation/types';

type RouteType = RouteProp<{ Chat: ChatScreenParams }, 'Chat'>;

// 会话持久化：App 重启/重进聊天页后恢复历史（后端 GET /specialists/conversations/{session_id}，
// 归属校验不过（换账号）→ 忽略并全新会话）
const SESSION_KEY = (specialistId: number) => `chat_session_${specialistId}`;

interface Message {
  id: string;
  role: 'user' | 'assistant' | 'system';
  content: string;
  citations?: { title: string; url?: string }[];
  evidenceLevel?: string | null;
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
  const [streaming, setStreaming] = useState(false);   // 流式生成中
  const [streamText, setStreamText] = useState('');    // 当前增量累积
  const wsRef = useRef<ReturnType<typeof openChatWs> | null>(null);
  const flatListRef = useRef<FlatList>(null);

  // 会话 ID 持久化（每次多轮续传都更新存储）
  const persistSession = useCallback((sid: string) => {
    setSessionId(sid);
    AsyncStorage.setItem(SESSION_KEY(specialistId), sid).catch(() => {});
  }, [specialistId]);

  // 重进聊天页恢复历史：上次会话的消息 + 继续用同一 session 多轮对话。
  // 归属校验不过（换账号）/网络失败 → 静默全新会话（历史读取失败不阻塞聊天）
  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const saved = await AsyncStorage.getItem(SESSION_KEY(specialistId));
        if (!saved || cancelled) return;
        const history = await specialistAPI.getConversationHistory(saved);
        if (!cancelled && Array.isArray(history) && history.length) {
          setSessionId(saved);
          setMessages((prev) => [
            ...prev,
            ...history.map((h) => ({
              id: h.id,
              role: h.role === 'user' ? ('user' as const) : ('assistant' as const),
              content: h.content,
              citations: h.citations,
              evidenceLevel: h.evidence_level,
              // 历史行只有快照（无会话内主键）→ 反馈/收藏按钮不显示
              conversationId: null,
            })),
          ]);
        }
      } catch {
        // 会话失效（如已换账号）或网络失败 → 全新会话
      }
    })();
    return () => { cancelled = true; };
  }, [specialistId]);

  // 流式生成中卸载页面（返回/切走）→ 关闭 WS，避免孤儿会话与连接泄漏
  useEffect(() => () => {
    wsRef.current?.close();
    wsRef.current = null;
  }, []);

  /**
   * WS 流式优先：8s 内未收到 start 帧即清理并返回 false → handleSend 降级 REST。
   * onDone 时把最终答案以普通 assistant 消息入列（带 citations/conversationId）。
   */
  const tryStream = async (
    text: string,
    session: string | null,
    token: string
  ): Promise<boolean> => {
    return new Promise((resolve) => {
      let started = false;
      // 结果已定（done/error/8s 超时降级）后，迟到的帧一律忽略：
      // 防止降级 REST 后 onStart 重建“正在思考...”气泡、onDone 重复入列
      let settled = false;
      let retried = false;                               // 已重连一次（未开始断线仅重试一次）
      const timer = setTimeout(() => {                   // 8s 未收到 start → 降级
        if (!started) { cleanup(); resolve(false); }
      }, 8000);
      const cleanup = () => {
        settled = true;
        clearTimeout(timer);
        if (wsRef.current) { wsRef.current.close(); wsRef.current = null; }
      };
      const open = () => {
        const ws = openChatWs(specialistId, token, {
          onStart: () => {
            if (settled) return;
            started = true; setStreaming(true); setStreamText('');
          },
          onDelta: (t) => {
            if (settled) return;
            setStreamText(t);
          },
          onDone: (d) => {
            if (settled) return;
            settled = true;
            started = true;
            clearTimeout(timer);
            setStreamText('');
            setStreaming(false);
            // 与 REST 路径一致的 blocked 拼装：正文 +（违规明细），blocked/evidenceLevel 一并透传
            const violationText = ((d.violations ?? []) as { description?: string }[])
              .map((v) => v.description)
              .filter(Boolean)
              .join('；');
            const content = d.blocked
              ? [d.text, violationText && `（${violationText}）`]
                  .filter(Boolean)
                  .join('')
              : d.text;
            const aiMsg: Message = {
              id: `a_${Date.now()}`,
              role: 'assistant',
              content,
              citations: (d.citations ?? []) as Message['citations'],
              blocked: d.blocked ?? false,
              evidenceLevel: d.evidenceLevel ?? null,
              conversationId: d.conversationId ?? null,
            };
            setMessages((prev) => [...prev, aiMsg]);
            if (d.sessionId) persistSession(d.sessionId);
            wsRef.current = null;
            resolve(true);
          },
          onError: (m) => {
            if (settled) return;
            // 尚未收到 start 帧就断开（网络瞬断/服务端拒连前的链路失败）→ 重连一次再试。
            // 已开始生成后断开 → 直接 REST 降级（避免生成一半的数据错乱）
            if (!started && !retried) {
              retried = true;
              wsRef.current = null;
              open();
              return;
            }
            settled = true;
            started = true;
            clearTimeout(timer);
            setStreaming(false);
            setStreamText('');
            wsRef.current = null;
            resolve(false);                              // 降级 REST
          },
        });
        wsRef.current = ws;
        ws.sendQuestion(text, session ?? undefined);
      };
      open();
    });
  };

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
      const token = (await apiClient.getToken()) || '';
      const ok = await tryStream(text, sessionId, token);
      if (ok) return;                                    // WS 完成（含 done），不走 REST

      // ---- REST fallback（既有逻辑）----
      const response = await specialistAPI.sendMessage(specialistId, {
        question: text,
        session_id: sessionId || undefined,
      });

      if (response.session_id) persistSession(response.session_id);

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
  }, [input, loading, specialistId, sessionId, tryStream]);

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

  // 流式渲染：WS 增量进行中，在消息尾部并入临时气泡
  // （conversationId 为空 → 反馈/收藏按钮天然不显示，与既有条件一致）
  const streamMsg: Message | null = streaming || streamText
    ? { id: 'streaming', role: 'assistant', content: streamText || '正在思考...' }
    : null;
  const listData = streamMsg ? [...messages, streamMsg] : messages;

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
        data={listData}
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
