/**
 * 分身对话页（2026-08-26 挂账收尾：REST → WS 流式，照 rep 端 ChatScreen 范式）：
 *   - WS 流式优先（openChatWs：start→delta*→done），8s 未收到 start 帧降级 REST
 *   - REST 兜底 twinAPI.chat（POST /api/v1/specialists/{id}/chat）
 *   - 顶部常驻"该分身由 AI 生成"标识条（合规要求，不可关闭）
 *   - blocked 态渲染后端安全话术 + 违规提示明细
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
import { useNavigation, useRoute } from '@react-navigation/native';
import type { RouteProp } from '@react-navigation/native';
import Icon, { ActionIcons } from '../../components/Icon';
import { twinAPI } from '../../api/twin';
import { apiClient } from '../../api/client';
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

  /**
   * WS 流式优先：8s 内未收到 start 帧即清理并返回 false → handleSend 降级 REST。
   * onDone 时把最终答案以普通 assistant 消息入列（带 citations/violations/blocked）。
   * 结果已定（done/error/8s 超时）后迟到的帧一律忽略，防止降级 REST 后重复入列。
   */
  const tryStream = async (text: string, token: string): Promise<boolean> => {
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
        ws.sendQuestion(text);
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
      const ok = await tryStream(text, token);
      if (ok) return;                                  // WS 完成（含 done），不走 REST

      // ---- REST 降级（WS 8s 超时/断开/服务端异常）----
      const response = await twinAPI.chat(twinId, text);
      const violationText = violationTextOf(response.violations);
      const aiMsg: Message = {
        id: response.request_id || `a_${Date.now()}`,
        role: 'assistant',
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
        <View style={{ width: 40 }} />
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
