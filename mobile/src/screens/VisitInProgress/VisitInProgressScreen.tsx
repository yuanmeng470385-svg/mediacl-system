/**
 * 拜访中页面 - 实时转写 + 异议警告 + 话术提示 + 红线拦截
 * 临床精准风
 */
import React, { useState, useRef, useEffect, useCallback } from 'react';
import {
  View, Text, ScrollView, StyleSheet, TouchableOpacity,
  Alert, ActivityIndicator,
} from 'react-native';
import { useRoute, useNavigation } from '@react-navigation/native';
import type { RouteProp } from '@react-navigation/native';
import type { NativeStackNavigationProp } from '@react-navigation/native-stack';
import { visitAPI, mapComplianceViolations } from '../../api/visit';
import type { KeyNode, AiSuggestion } from '../../api/visit';
import { apiClient } from '../../api/client';
import { connectAsrStreaming } from '../../services/asr';
import { startRecording, stopRecording, recordingPath } from '../../services/recorder';
import { speak } from '../../services/tts';
import Icon from '../../components/Icon';
import { ActionIcons, StatusIcons } from '../../components/Icon';
import { Colors, FontSize, Spacing, BorderRadius, Shadow } from '../../constants/theme';
import type { RootStackParamList, VisitInProgressParams } from '../../navigation/types';
import type { ObjectionAlert, ComplianceAlert, VisitSummary } from '../../types';

type RouteType = RouteProp<{ VisitInProgress: VisitInProgressParams }, 'VisitInProgress'>;
type Nav = NativeStackNavigationProp<RootStackParamList>;

interface TranscriptSegment {
  id: string; speaker: 'rep' | 'hcp'; text: string; time: string;
}

export default function VisitInProgressScreen() {
  const route = useRoute<RouteType>();
  const navigation = useNavigation<Nav>();
  const { visitId, hcpName } = route.params;

  const [transcript, setTranscript] = useState<TranscriptSegment[]>([]);
  const [objections, setObjections] = useState<ObjectionAlert[]>([]);
  const [complianceAlerts, setComplianceAlerts] = useState<ComplianceAlert[]>([]);
  const [keyNodes, setKeyNodes] = useState<KeyNode[]>([]);
  const [aiSuggestion, setAiSuggestion] = useState<AiSuggestion | null>(null);
  const [elapsed, setElapsed] = useState(0);
  const [sending, setSending] = useState(false);
  const [showRedLine, setShowRedLine] = useState<string | null>(null);
  const [recording, setRecording] = useState(false);
  const [transcribing, setTranscribing] = useState(false);
  const [liveText, setLiveText] = useState('');           // 转写增量文本（onSentence 更新）
  // ASR 帧的说话人标签（visit-service 新字段 'rep'/'doctor'，缺省 undefined → 按代表处理）
  const [liveSpeaker, setLiveSpeaker] = useState<string | undefined>(undefined);
  const asrSessionRef = useRef<ReturnType<typeof connectAsrStreaming> | null>(null);
  const recordingRef = useRef(false); // recording 状态的 ref 镜像，供卸载清理读取
  const timerRef = useRef<ReturnType<typeof setInterval>>();
  const scrollRef = useRef<ScrollView>(null);

  useEffect(() => {
    timerRef.current = setInterval(() => setElapsed((prev) => prev + 1), 1000);
    return () => { if (timerRef.current) clearInterval(timerRef.current); };
  }, []);

  // 卸载清理：停止录音（释放麦克风）、关闭 ASR WS，避免原生层持续录音与孤儿会话
  useEffect(() => () => {
    if (recordingRef.current) stopRecording().catch(() => {});
    asrSessionRef.current?.close();
    asrSessionRef.current = null;
  }, []);

  const formatTime = (seconds: number) => {
    const m = Math.floor(seconds / 60);
    const s = seconds % 60;
    return `${m.toString().padStart(2, '0')}:${s.toString().padStart(2, '0')}`;
  };

  const addTranscript = useCallback(async (text: string, speaker: 'rep' | 'hcp') => {
    const seg: TranscriptSegment = { id: `ts_${Date.now()}`, speaker, text, time: formatTime(elapsed) };
    setTranscript((prev) => [...prev, seg]);
    setSending(true);
    try {
      const result = await visitAPI.sendTranscript(visitId, { text });
      if (result.objections?.length) setObjections((prev) => [...prev, ...result.objections]);
      if (result.compliance_alerts?.length) {
        setComplianceAlerts((prev) => [...prev, ...result.compliance_alerts]);
        const critical = result.compliance_alerts.find((a) => a.critical);
        if (critical) setShowRedLine(critical.description);
      }
      // LLM 实时推荐：关键节点累加、话术建议取最新一轮（后端每轮 transcript 都带）
      if (result.key_nodes?.length) setKeyNodes((prev) => [...prev, ...result.key_nodes]);
      if (result.ai_suggestion) setAiSuggestion(result.ai_suggestion);
    } catch {} finally { setSending(false); }
  }, [visitId, elapsed]);

  // 朗读话术（TTS 失败只 Alert 提示，不阻塞转写流程）
  const speakTts = useCallback(async (text: string) => {
    try {
      await speak(text);
    } catch (e: any) {
      Alert.alert('语音合成', e?.message || '合成失败，请检查 NLS 配置');
    }
  }, []);

  // 只调一次 end：结果放进 navigation params 传给 VisitEndScreen，避免第二次 end 触发后端"已结束"锁
  const handleEndVisit = () => {
    Alert.alert('结束拜访', '确认结束本次拜访并生成总结？', [
      { text: '取消', style: 'cancel' },
      { text: '确认结束', onPress: async () => {
        let summary: VisitSummary | undefined;
        try { summary = await visitAPI.endVisit(visitId); } catch {}
        navigation.replace('VisitEnd', { visitId, summary });
      }},
    ]);
  };

  const simulateInput = (speaker: 'rep' | 'hcp') => {
    const samples: Record<string, string[]> = {
      rep: ['主任，关于这个产品最新的临床数据您关注过吗？', '我们的产品在这一适应症上有很好的疗效数据支持。', '您觉得患者对这类治疗方案接受度怎么样？'],
      hcp: ['这个数据和国际指南一致吗？', '我对这个方案的安全性还有些顾虑。', '价格方面对患者来说还是比较大的负担。'],
    };
    addTranscript(samples[speaker][Math.floor(Math.random() * 3)], speaker);
  };

  // 真实录音 → 流式推流 ASR 转写（录音 start 即建立会话，asr.ts 轮询读 WAV 增量持续推流；
  // 结果走 addTranscript → 异议/合规检测 → 落库。不能录完再连：connectAsrStreaming 内部接管
  // onReady，且 sendAudioChunk/stop 在 WS OPEN 前调用会被静默丢弃。
  // 快按快放竞态：release 早于会话建立时，press 分支 resume 后按 recordingRef 判定弃建会话）
  const handleVoice = useCallback(async () => {
    if (transcribing) return;
    if (!recording) {
      try {
        await startRecording();
      } catch (e: any) {
        Alert.alert('提示', '无法开始录音：' + (e.message || '麦克风不可用'));
        return;
      }
      setRecording(true);
      recordingRef.current = true;
      try {
        const token = (await apiClient.getToken()) || '';
        // 快按快放：等待 token 期间用户已松键（release 分支已同步把 recordingRef 置 false）→
        // 会话已无意义。绝不能再补建会话：release 的 stop() 只会落到非 null 的 ref 上，而
        // WS OPEN 前发的 stop 帧会被 asr.ts 静默丢弃、服务端收不到 stop 就一直挂接收循环
        // （asr_ws.py 无空闲超时）→ onCompleted 永不触发 → transcribing 卡死、WS 孤儿到卸载
        if (!recordingRef.current) {
          setTranscribing(false); // 复位 release 分支挂起的转写态（无会话 → 不会有 completed 帧）
          return;
        }
        const session = connectAsrStreaming(visitId, token, recordingPath(), {
          // onReady 由 connectAsrStreaming 内部接管（影子回调，屏侧无需也收不到）；
          // 空实现仅满足 AsrCallbacks 类型约束，实际从不触发
          onReady: () => {},
          // 增量句：转写进行中在底部栏上方显示一行"转写中：<当前文本>"，带说话人标签
          onSentence: (text, _final, speaker) => {
            setLiveText(text);
            if (speaker) setLiveSpeaker(speaker);
          },
          // ASR WS compliance 帧：与 transcript 的 compliance_alerts 同一套映射与展示状态
          onCompliance: (blocked, violations) => {
            const alerts = mapComplianceViolations(violations);
            if (alerts.length) {
              setComplianceAlerts((prev) => [...prev, ...alerts]);
              const critical = alerts.find((a) => a.critical);
              if (critical) setShowRedLine(critical.description);
            }
          },
          onError: (msg) => {
            setLiveText('');
            setTranscribing(false); // 服务端 error 帧后即断开（无 completed 帧），必须复位防按钮卡死
            Alert.alert('语音转写', msg.includes('NLS') ? 'NLS 识别通道未配置，暂不可用' : msg);
          },
          // speaker：visit-service 帧的说话人标签（'doctor' → 医生，其余按代表）
          onCompleted: async (fullText, speaker) => {
            asrSessionRef.current = null;
            setTranscribing(false);
            setLiveText('');
            setLiveSpeaker(undefined);
            if (fullText && fullText.trim()) {
              await addTranscript(fullText.trim(), speaker === 'doctor' ? 'hcp' : 'rep'); // 走异议/合规检测 + 落库
            }
          },
        });
        asrSessionRef.current = session;
      } catch (e: any) {
        // 会话建立失败（token 通道异常等）：回滚录音态，避免"停止录音"按钮但无会话可 stop 的悬空态；
        // 若 release 已先行（快按快放），此处同样复位转写态（无会话 → 不会有 completed 帧）
        setTranscribing(false);
        setRecording(false);
        recordingRef.current = false;
        stopRecording().catch(() => {});
        Alert.alert('提示', '转写通道启动失败：' + (e.message || '请重试'));
      }
      return;
    }
    // 停止录音 → 流式会话收尾：stop() 推完剩余 PCM 再发 stop 帧（asr.ts M19 契约），
    // 服务端据此 finalize 并回 completed 帧 → onCompleted → addTranscript
    setRecording(false);
    recordingRef.current = false;
    setTranscribing(true);
    try { await stopRecording(); } catch {}
    if (asrSessionRef.current) {
      asrSessionRef.current.stop();
    }
    // else：会话尚未建立（press 分支仍在 getToken/建连途中）→ 不补 stop。
    // press 分支 resume 时发现 recordingRef=false 将直接弃建会话（快按快放 → 本次录音作废）。
    // 两种顺序均安全：release 的 stop 若落在 press 同步建会话块之后 → ref 非 null 正常收尾；
    // 落在之前 → press 弃建，transcribing 由 press 复位
  }, [recording, transcribing, visitId, addTranscript]);

  return (
    <View style={styles.container}>
      {/* 头部 */}
      <View style={styles.header}>
        <TouchableOpacity onPress={() => navigation.goBack()}>
          <Icon name={ActionIcons.back} size={22} color={Colors.textWhite} />
        </TouchableOpacity>
        <View style={styles.headerCenter}>
          <Text style={styles.headerTitle}>拜访中</Text>
          <Text style={styles.headerSub}>{hcpName}</Text>
        </View>
        <View style={styles.timerBox}>
          <View style={styles.recDot} />
          <Text style={styles.timerText}>{formatTime(elapsed)}</Text>
        </View>
      </View>

      <View style={styles.body}>
        {/* 转写区 */}
        <ScrollView
          ref={scrollRef}
          style={styles.transcriptArea}
          contentContainerStyle={styles.transcriptContent}
          onContentSizeChange={() => scrollRef.current?.scrollToEnd()}
          showsVerticalScrollIndicator={false}
        >
          {transcript.length === 0 && (
            <View style={styles.placeholder}>
              <View style={styles.placeholderCircle}>
                <Icon name="microphone" size={36} color={Colors.textHint} />
              </View>
              <Text style={styles.placeholderText}>
                点击底部按钮录音，实时转写对话内容
              </Text>
            </View>
          )}
          {transcript.map((seg) => (
            <View key={seg.id} style={[styles.tsItem, seg.speaker === 'rep' ? styles.tsRep : styles.tsHcp]}>
              <View style={styles.tsHead}>
                <Text style={styles.tsSpeaker}>{seg.speaker === 'rep' ? '代表' : hcpName}</Text>
                <Text style={styles.tsTime}>{seg.time}</Text>
              </View>
              <Text style={styles.tsText}>{seg.text}</Text>
            </View>
          ))}
          {sending && (
            <View style={styles.analyzing}>
              <ActivityIndicator size="small" color={Colors.primary} />
              <Text style={styles.analyzingText}>分析中...</Text>
            </View>
          )}
        </ScrollView>

        {/* 右侧面板 */}
        <View style={styles.sidePanel}>
          {objections.length > 0 && (
            <View style={styles.sideSection}>
              <View style={styles.sideTitleRow}>
                <Icon name="alert-outline" size={14} color={Colors.warning} />
                <Text style={styles.sideTitle}>异议</Text>
              </View>
              {objections.slice(-3).map((obj, i) => (
                <TouchableOpacity
                  key={obj.id || i}
                  style={styles.objectionCard}
                  onPress={() => Alert.alert('应对话术', obj.suggested_response || '暂无建议话术')}
                >
                  <Text style={styles.objectionText} numberOfLines={2}>{obj.description}</Text>
                  {obj.suggested_response && <Text style={styles.tipLabel}>点击查看话术</Text>}
                  {obj.suggested_response && (
                    <TouchableOpacity
                      style={styles.speakBtn}
                      hitSlop={{ top: 8, bottom: 8, left: 8, right: 8 }}
                      onPress={() => speakTts(obj.suggested_response!)}>
                      <Icon name="volume-high" size={12} color={Colors.primary} />
                      <Text style={styles.speakText}>朗读</Text>
                    </TouchableOpacity>
                  )}
                </TouchableOpacity>
              ))}
            </View>
          )}

          {/* AI 实时推荐：关键节点 + 话术建议（后端 transcript 响应 key_nodes/ai_suggestion） */}
          {(keyNodes.length > 0 || aiSuggestion) && (
            <View style={styles.sideSection}>
              <View style={styles.sideTitleRow}>
                <Icon name="bulb-outline" size={14} color={Colors.primary} />
                <Text style={styles.sideTitle}>AI 实时推荐</Text>
              </View>
              {keyNodes.slice(-5).map((n, i) => (
                <View key={`kn_${i}`} style={styles.keyNodeRow}>
                  <Text style={[styles.keyNodeBadge, n.type === 'decision_point' ? styles.keyNodeDecision : styles.keyNodeInterest]}>
                    {n.type === 'decision_point' ? '决策点' : '兴趣点'}
                  </Text>
                  <Text style={styles.keyNodeLabel} numberOfLines={2}>{n.label}</Text>
                </View>
              ))}
              {aiSuggestion && (
                <View style={styles.aiSuggestionCard}>
                  <Text style={styles.aiSuggestionTopic}>{aiSuggestion.topic}</Text>
                  <Text style={styles.aiSuggestionAdvice} numberOfLines={3}>{aiSuggestion.advice}</Text>
                  <TouchableOpacity style={styles.speakBtn} onPress={() => speakTts(aiSuggestion.advice)}>
                    <Icon name="volume-high" size={14} color={Colors.primary} />
                    <Text style={styles.speakText}>朗读话术</Text>
                  </TouchableOpacity>
                </View>
              )}
            </View>
          )}

          {complianceAlerts.length > 0 && (
            <View style={styles.sideSection}>
              <View style={styles.sideTitleRow}>
                <Icon name="shield-alert-outline" size={14} color={Colors.danger} />
                <Text style={[styles.sideTitle, { color: Colors.danger }]}>合规提醒</Text>
              </View>
              {complianceAlerts.slice(-2).map((alert, i) => (
                <View key={i} style={styles.complianceItem}>
                  <Text style={styles.complianceText}>{alert.description}</Text>
                </View>
              ))}
            </View>
          )}
        </View>
      </View>

      {/* 红线弹窗 */}
      {showRedLine && (
        <View style={styles.redLineOverlay}>
          <View style={styles.redLineBox}>
            <View style={styles.redLineIconCircle}>
              <Icon name="alert-octagon" size={40} color={Colors.danger} />
            </View>
            <Text style={styles.redLineTitle}>合规红线提醒</Text>
            <Text style={styles.redLineText}>{showRedLine}</Text>
            <Text style={styles.redLineHint}>请调整话术，避免不合规表述</Text>
            <TouchableOpacity style={styles.dismissBtn} onPress={() => setShowRedLine(null)}>
              <Text style={styles.dismissText}>我知道了</Text>
            </TouchableOpacity>
          </View>
        </View>
      )}

      {/* 转写中提示行（speaker 标签有就显示，没有就不显示，向后兼容） */}
      {(transcribing || liveText) && (
        <View style={{ paddingHorizontal: Spacing.md, paddingTop: Spacing.sm, backgroundColor: Colors.primarySurface }}>
          <Text style={{ fontSize: FontSize.xs, color: Colors.primary }}>
            {transcribing
              ? `${liveSpeaker === 'doctor' ? '医生' : liveSpeaker === 'rep' ? '代表' : ''}转写中：${liveText || '...'}`
              : '点击停止录音'}
          </Text>
        </View>
      )}

      {/* 底部操作栏 */}
      <View style={styles.bottomBar}>
        <TouchableOpacity
          style={[styles.simBtn, recording && { backgroundColor: Colors.danger }]}
          onPress={handleVoice}
          disabled={sending || transcribing}
        >
          <Icon name={recording ? 'stop-circle' : 'microphone'} size={16} color={Colors.textWhite} />
          <Text style={styles.simBtnText}>{recording ? '停止录音' : '录音'}</Text>
        </TouchableOpacity>
        <TouchableOpacity style={styles.simBtn} onPress={() => simulateInput('rep')} disabled={sending}>
          <Icon name="account-voice" size={16} color={Colors.textWhite} />
          <Text style={styles.simBtnText}>代表说</Text>
        </TouchableOpacity>
        <TouchableOpacity style={[styles.simBtn, styles.simBtnHcp]} onPress={() => simulateInput('hcp')} disabled={sending}>
          <Icon name="doctor" size={16} color={Colors.primary} />
          <Text style={styles.simBtnTextHcp}>医生说</Text>
        </TouchableOpacity>
        <TouchableOpacity style={styles.endBtn} onPress={handleEndVisit} disabled={recording || transcribing}>
          <Icon name="stop-circle-outline" size={16} color={Colors.textWhite} />
          <Text style={styles.endBtnText}>结束</Text>
        </TouchableOpacity>
      </View>
    </View>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1, backgroundColor: Colors.background },
  header: {
    backgroundColor: Colors.primary, paddingTop: 50, paddingBottom: 12,
    paddingHorizontal: Spacing.lg, flexDirection: 'row',
    alignItems: 'center', justifyContent: 'space-between',
    ...Shadow.header,
  },
  headerCenter: { alignItems: 'center' },
  headerTitle: { color: Colors.textWhite, fontSize: FontSize.lg, fontWeight: '700' },
  headerSub: { color: 'rgba(255,255,255,0.7)', fontSize: FontSize.xs },
  timerBox: {
    flexDirection: 'row', alignItems: 'center',
    backgroundColor: 'rgba(255,255,255,0.15)', paddingHorizontal: 12,
    paddingVertical: 6, borderRadius: BorderRadius.full, gap: 6,
  },
  recDot: { width: 8, height: 8, borderRadius: 4, backgroundColor: Colors.danger },
  timerText: { color: Colors.textWhite, fontSize: FontSize.sm, fontWeight: '600', fontVariant: ['tabular-nums'] },
  body: { flex: 1, flexDirection: 'row' },
  transcriptArea: { flex: 2, padding: Spacing.md },
  transcriptContent: { paddingBottom: Spacing.lg },
  placeholder: { flex: 1, justifyContent: 'center', alignItems: 'center', paddingTop: 80 },
  placeholderCircle: {
    width: 72, height: 72, borderRadius: 36,
    backgroundColor: Colors.border, alignItems: 'center', justifyContent: 'center',
    marginBottom: Spacing.lg,
  },
  placeholderText: { fontSize: FontSize.sm, color: Colors.textHint, textAlign: 'center', lineHeight: 22 },
  tsItem: { padding: Spacing.md, borderRadius: BorderRadius.md, marginBottom: Spacing.sm, maxWidth: '90%' },
  tsRep: { alignSelf: 'flex-end', backgroundColor: Colors.primarySurface },
  tsHcp: { alignSelf: 'flex-start', backgroundColor: Colors.white, ...Shadow.card },
  tsHead: { flexDirection: 'row', justifyContent: 'space-between', marginBottom: 4 },
  tsSpeaker: { fontSize: FontSize.xs, fontWeight: '600', color: Colors.textSecondary },
  tsTime: { fontSize: 10, color: Colors.textHint, fontVariant: ['tabular-nums'] },
  tsText: { fontSize: FontSize.md, color: Colors.textPrimary, lineHeight: 22 },
  analyzing: { flexDirection: 'row', alignItems: 'center', gap: Spacing.sm, alignSelf: 'center', padding: Spacing.sm },
  analyzingText: { color: Colors.textHint, fontSize: FontSize.xs },
  sidePanel: { flex: 1, backgroundColor: Colors.white, borderLeftWidth: 1, borderLeftColor: Colors.divider, padding: Spacing.sm },
  sideSection: { marginBottom: Spacing.lg },
  sideTitleRow: { flexDirection: 'row', alignItems: 'center', gap: Spacing.xs, marginBottom: Spacing.sm },
  sideTitle: { fontSize: FontSize.xs, fontWeight: '700', color: Colors.warning },
  objectionCard: {
    backgroundColor: Colors.warningLight, padding: Spacing.sm,
    borderRadius: BorderRadius.sm, marginBottom: Spacing.xs,
    borderLeftWidth: 3, borderLeftColor: Colors.warning,
  },
  objectionText: { fontSize: FontSize.xs, color: Colors.textPrimary, lineHeight: 18 },
  tipLabel: { fontSize: 10, color: Colors.primary, marginTop: 4, fontWeight: '600' },
  keyNodeRow: { flexDirection: 'row', alignItems: 'center', marginBottom: 6 },
  keyNodeBadge: { fontSize: 10, color: Colors.textWhite, paddingHorizontal: 6, paddingVertical: 2, borderRadius: 4, marginRight: 6, overflow: 'hidden' },
  keyNodeDecision: { backgroundColor: '#1677ff' },
  keyNodeInterest: { backgroundColor: '#52c41a' },
  keyNodeLabel: { flex: 1, fontSize: 12, color: Colors.textPrimary },
  aiSuggestionCard: { backgroundColor: Colors.backgroundAlt, borderRadius: 8, padding: 8, marginTop: 4 },
  aiSuggestionTopic: { fontSize: 12, fontWeight: '600', color: Colors.primary, marginBottom: 4 },
  aiSuggestionAdvice: { fontSize: 12, color: Colors.textPrimary, marginBottom: 6, lineHeight: 18 },
  speakBtn: { flexDirection: 'row', alignItems: 'center', alignSelf: 'flex-start' },
  speakText: { fontSize: 12, color: Colors.primary, marginLeft: 4 },
  complianceItem: {
    backgroundColor: Colors.dangerLight, padding: Spacing.sm,
    borderRadius: BorderRadius.sm, marginBottom: Spacing.xs,
  },
  complianceText: { fontSize: FontSize.xs, color: Colors.danger, lineHeight: 18 },
  redLineOverlay: {
    ...StyleSheet.absoluteFillObject, backgroundColor: 'rgba(0,0,0,0.5)',
    justifyContent: 'center', alignItems: 'center', zIndex: 100,
  },
  redLineBox: {
    backgroundColor: Colors.white, margin: Spacing.xxxl,
    borderRadius: BorderRadius.xl, padding: Spacing.xxl,
    alignItems: 'center', borderWidth: 2, borderColor: Colors.danger,
  },
  redLineIconCircle: { marginBottom: Spacing.md },
  redLineTitle: { fontSize: FontSize.lg, fontWeight: '700', color: Colors.danger, marginBottom: Spacing.md },
  redLineText: { fontSize: FontSize.md, color: Colors.textPrimary, textAlign: 'center', lineHeight: 22, marginBottom: Spacing.lg },
  redLineHint: { fontSize: FontSize.xs, color: Colors.textHint, marginBottom: Spacing.xl },
  dismissBtn: {
    backgroundColor: Colors.danger, paddingHorizontal: Spacing.xxxl,
    paddingVertical: Spacing.md, borderRadius: BorderRadius.full,
  },
  dismissText: { color: Colors.textWhite, fontSize: FontSize.md, fontWeight: '600' },
  bottomBar: {
    flexDirection: 'row', padding: Spacing.md, paddingBottom: 34,
    backgroundColor: Colors.white, borderTopWidth: 1, borderTopColor: Colors.divider, gap: Spacing.sm,
  },
  simBtn: {
    flex: 1, flexDirection: 'row', backgroundColor: Colors.primary,
    borderRadius: BorderRadius.lg, paddingVertical: 14,
    alignItems: 'center', justifyContent: 'center', gap: Spacing.sm,
  },
  simBtnHcp: { backgroundColor: Colors.white, borderWidth: 1, borderColor: Colors.primary },
  simBtnText: { color: Colors.textWhite, fontSize: FontSize.sm, fontWeight: '600' },
  simBtnTextHcp: { color: Colors.primary, fontSize: FontSize.sm, fontWeight: '600' },
  endBtn: {
    flexDirection: 'row', backgroundColor: Colors.danger,
    borderRadius: BorderRadius.lg, paddingVertical: 14, paddingHorizontal: Spacing.xl,
    alignItems: 'center', gap: Spacing.xs,
  },
  endBtnText: { color: Colors.textWhite, fontSize: FontSize.sm, fontWeight: '600' },
});
