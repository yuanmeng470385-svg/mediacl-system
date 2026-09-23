/**
 * 分身对话页（2026-08-26 挂账收尾：REST → WS 流式，照 rep 端 ChatScreen 范式）：
 *   - WS 流式优先（openChatWs：start→delta*→done），8s 未收到 start 帧降级 REST
 *   - REST 兜底 twinAPI.chat（POST /api/v1/specialists/{id}/chat）
 *   - 顶部常驻"该分身由 AI 生成"标识条（合规要求，不可关闭）
 *   - blocked 态渲染后端安全话术 + 违规提示明细
 *   - 收藏星标（2026-09-11 死页清理批）：回答气泡下 toggle 收藏，激活既有收藏历史页
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
  Alert,
} from 'react-native';
import { useNavigation, useRoute } from '@react-navigation/native';
import type { RouteProp } from '@react-navigation/native';
import Icon, { ActionIcons } from '../../components/Icon';
import { twinAPI } from '../../api/twin';
import { favoritesAPI } from '../../api/favorites';
import { apiClient } from '../../api/client';
import AsyncStorage from '@react-native-async-storage/async-storage';
import { openChatWs } from '../../services/wsChat';
import { Colors, FontSize, Spacing, BorderRadius, Shadow } from '../../constants/theme';
import type { RootStackParamList } from '../../navigation/types';
import type { ChatViolation } from '../../types';

type RouteType = RouteProp<RootStackParamList, 'TwinChat'>;

interface Message {
  id: string;
  role: 'user' | 'assistant';
  content: string;
  citations?: { title: string; url?: string }[];
  blocked?: boolean;
  violations?: ChatViolation[];
  /** 收藏主键（assistant 行 id）；入库失败/欢迎语为空 → 星标不显示（rep 端同款条件） */
  conversationId?: number | null;
  /** 收藏态（toggle 成功后回写，本地乐观不持久化——以列表页为准） */
  favorite?: boolean;
}

function violationTextOf(violations: ChatViolation[] | undefined): string {
  const list = Array.isArray(violations) ? violations : [];
  return list
    .map((v) => String(v.matched_text || v.reason || v.rule_name || ''))
    .filter(Boolean)
    .join('；');
}

export default function TwinChatScreen() {
  const route = useRoute<RouteType>();
  const navigation = useNavigation();
  const { twinId, twinName } = route.params;

  const [messages, setMessages] = useState<Message[]>([
    {
      id: 'welcome',
      role: 'assistant',
      content: `你好！我是${twinName}。有什么可以帮助你的？`,
    },
  ]);
  const [input, setInput] = useState('');
  const [loading, setLoading] = useState(false);
  const [streaming, setStreaming] = useState(false);   // WS 流式生成中
  const [streamText, setStreamText] = useState('');    // 当前增量累积
  const wsRef = useRef<ReturnType<typeof openChatWs> | null>(null);
  const flatListRef = useRef<FlatList>(null);

  // ---- v1.1（2026-09-23）：会话常驻（豆包式）——重进恢复历史，继续同一 session；
  // 「新建对话」清 session 另起窗口。照 rep ChatScreen 的 SESSION_KEY 范式。
  const SESSION_KEY = `twin_chat_session_${twinId}`;
  const [sessionId, setSessionId] = useState<string | null>(null);

  const persistSession = (sid: string) => {
    setSessionId(sid);
    AsyncStorage.setItem(SESSION_KEY, sid).catch(() => {});
  };

  // 重进恢复：上次 session 的消息（归属不过/失效 → 静默全新会话）
  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const saved = await AsyncStorage.getItem(SESSION_KEY);
        if (!saved || cancelled) return;
        const history = await apiClient.request<any[]>(
          'GET', `/api/v1/specialists/conversations/${saved}`
        );
        if (!cancelled && Array.isArray(history) && history.length) {
          setSessionId(saved);
          setMessages((prev) => [
            ...prev,
            ...history.map((h) => ({
              id: String(h.id),
              role: h.role === 'user' ? ('user' as const) : ('assistant' as const),
              content: String(h.content ?? ''),
              citations: h.citations,
              conversationId: null, // 历史行无会话内主键 → 收藏星标不显示（rep 端同口径）
            })),
          ]);
        }
      } catch { /* 失效/网络失败 → 全新会话 */ }
    })();
    return () => { cancelled = true; };
  }, [twinId]);

  /** 新建对话：清 session（下一条消息后端会开新 session）+ 清消息 */
  const handleNewChat = () => {
    if (loading || streaming) return;
    AsyncStorage.removeItem(SESSION_KEY).catch(() => {});
    setSessionId(null);
    setMessages([
      { id: 'welcome', role: 'assistant', content: `你好！我是${twinName}。有什么可以帮助你的？` },
    ]);
  };

  /**
   * WS 流式优先：8s 内未收到 start 帧即清理并返回 false → handleSend 降级 REST。
   * onDone 时把最终答案以普通 assistant 消息入列（带 citations/violations/blocked）。
   * 结果已定（done/error/8s 超时）后迟到的帧一律忽略，防止降级 REST 后重复入列。
   */
  const tryStream = async (text: string, sid: string | null, token: string): Promise<boolean> => {
    return new Promise((resolve) => {
      let started = false;
      let settled = false;
      let retried = false;                             // 未开始断线仅重试一次
      const timer = setTimeout(() => {
        if (!started) { cleanup(); resolve(false); }
      }, 8000);
      const cleanup = () => {
        settled = true;
        clearTimeout(timer);
        if (wsRef.current) { wsRef.current.close(); wsRef.current = null; }
      };
      const open = () => {
        const ws = openChatWs(twinId, token, {
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
            if (d.sessionId) persistSession(d.sessionId); // v1.1：会话常驻，下次进来续聊
            // 与 REST 路径一致的 blocked 拼装：正文 +（违规明细）
            const violationText = violationTextOf(d.violations);
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
              violations: d.violations,
              conversationId: d.conversationId ?? null,
            };
            setMessages((prev) => [...prev, aiMsg]);
            wsRef.current = null;
            resolve(true);
          },
          onError: (m) => {
            if (settled) return;
            // 未收到 start 帧就断开（网络瞬断/链路失败）→ 重连一次再试；
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
            resolve(false);
          },
        });
        wsRef.current = ws;
        ws.sendQuestion(text, sid ?? undefined);
      };
      open();
    });
  };

  // 卸载时关闭未完成的 WS，避免内存泄漏/迟到回调 setState
  useEffect(() => {
    return () => {
      if (wsRef.current) wsRef.current.close();
    };
  }, []);

  const handleSend = async () => {
    const text = input.trim();
    if (!text || loading) return;

    const userMsg: Message = { id: `u_${Date.now()}`, role: 'user', content: text };
    setMessages((prev) => [...prev, userMsg]);
    setInput('');
    setLoading(true);

    try {
      const token = (await apiClient.getToken()) || '';
      const ok = await tryStream(text, sessionId, token);
      if (ok) return;                                  // WS 完成（含 done），不走 REST

      // ---- REST 降级（WS 8s 超时/断开/服务端异常）----
      const response = await twinAPI.chat(twinId, text, sessionId ?? undefined);
      if (response.session_id) persistSession(response.session_id); // v1.1：REST 路径同样续会话
      const violationText = violationTextOf(response.violations);
      const aiMsg: Message = {
        id: response.request_id || `a_${Date.now()}`,
        role: 'assistant',
        conversationId: response.conversation_id ?? null,
        content: response.blocked
          ? [response.answer, violationText && `（${violationText}）`]
              .filter(Boolean)
              .join('')
          : response.answer,
        citations: response.citations ?? [],
        blocked: response.blocked,
        violations: response.violations,
      };
      setMessages((prev) => [...prev, aiMsg]);
    } catch (e: any) {
      // Hermes 实测：在 setMessages updater 闭包里直接读 e.message 会抛
      // "Property 'e' doesn't exist"（catch 绑定未随闭包存活）→ 红屏。
      // 先在 catch 块内取好字符串，updater 只用纯值
      const errMsg = `抱歉，出错了：${e?.message || '请稍后重试'}`;
      setMessages((prev) => [
        ...prev,
        {
          id: `err_${Date.now()}`,
          role: 'assistant',
          content: errMsg,
        },
      ]);
    } finally {
      setLoading(false);
    }
  };

  /** 收藏/取消收藏（conversationId 为空的消息天然无按钮，与 rep 端一致） */
  const handleFavorite = async (msg: Message) => {
    if (!msg.conversationId) return;
    try {
      const res = await favoritesAPI.toggleFavorite(msg.conversationId);
      setMessages((prev) =>
        prev.map((m) => (m.id === msg.id ? { ...m, favorite: !!res?.is_favorite } : m))
      );
    } catch (e: any) {
      // catch 闭包内先取字符串（同 Hermes 坑防御）
      const errMsg = e?.message || '请稍后重试';
      Alert.alert('收藏失败', errMsg);
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

          {!isUser && item.blocked && violationText ? (
            <View style={styles.violationBox}>
              <Icon name={ActionIcons.close} size={14} color={Colors.danger} />
              <Text style={styles.violationText}>违规提示：{violationText}</Text>
            </View>
          ) : null}

          {!isUser && !item.blocked && item.conversationId ? (
            <TouchableOpacity
              style={styles.favoriteRow}
              onPress={() => handleFavorite(item)}
              activeOpacity={0.7}
              hitSlop={{ top: 6, bottom: 6, left: 6, right: 6 }}
            >
              <Icon
                name={item.favorite ? ActionIcons.starFilled : ActionIcons.star}
                size={16}
                color={item.favorite ? Colors.warning : Colors.textHint}
              />
              <Text style={[styles.favoriteText, item.favorite && styles.favoriteTextOn]}>
                {item.favorite ? '已收藏' : '收藏'}
              </Text>
            </TouchableOpacity>
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
      <View style={styles.header}>
        <TouchableOpacity onPress={() => navigation.goBack()} style={styles.headerBtn}>
          <Icon name={ActionIcons.back} size={22} color={Colors.textWhite} />
        </TouchableOpacity>
        <View style={styles.headerCenter}>
          <Text style={styles.headerTitle}>{twinName}</Text>
          <Text style={styles.headerSub}>数字员工 · 在线</Text>
        </View>
        <TouchableOpacity
          onPress={handleNewChat}
          disabled={loading || streaming}
          activeOpacity={0.7}
          style={{
            paddingHorizontal: 10, paddingVertical: 5, borderRadius: 13,
            backgroundColor: 'rgba(255,255,255,0.18)',
            opacity: loading || streaming ? 0.5 : 1,
          }}
        >
          <Text style={{ color: Colors.textWhite, fontSize: 12, fontWeight: '600' }}>＋ 新对话</Text>
        </TouchableOpacity>
      </View>

      {/* 常驻 AI 生成标识条（合规要求，不可关闭） */}
      <View style={styles.aiBanner}>
        <Icon name="robot-outline" size={14} color={Colors.info} />
        <Text style={styles.aiBannerText}>
          该分身由 AI 生成，其回答不构成诊疗建议
        </Text>
      </View>

      <FlatList
        ref={flatListRef}
        data={streaming || streamText ? [...messages, {
          id: 'streaming',
          role: 'assistant',
          content: streamText || '正在思考...',
        }] : messages}
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
    paddingTop: 50,
    paddingBottom: 14,
    paddingHorizontal: Spacing.lg,
    flexDirection: 'row',
    alignItems: 'center',
    ...Shadow.header,
  },
  headerBtn: { padding: 4 },
  headerCenter: { flex: 1, alignItems: 'center' },
  headerTitle: { color: Colors.textWhite, fontSize: FontSize.lg, fontWeight: '600' },
  headerSub: { color: 'rgba(255,255,255,0.6)', fontSize: FontSize.xs, marginTop: 2 },
  aiBanner: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'center',
    gap: 6,
    backgroundColor: Colors.infoLight,
    paddingVertical: 6,
    paddingHorizontal: Spacing.md,
  },
  aiBannerText: { fontSize: FontSize.xs, color: Colors.info },
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
  favoriteRow: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 4,
    alignSelf: 'flex-end',
    marginTop: Spacing.sm,
    paddingTop: Spacing.xs,
    borderTopWidth: 1,
    borderTopColor: Colors.divider,
  },
  favoriteText: { fontSize: FontSize.xs, color: Colors.textHint },
  favoriteTextOn: { color: Colors.warning },
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
