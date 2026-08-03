/**
 * 拜访中页面 - 实时转写 + 异议警告 + 话术提示 + 红线拦截
 */
import React, { useState, useRef, useEffect, useCallback } from 'react';
import {
  View,
  Text,
  ScrollView,
  StyleSheet,
  TouchableOpacity,
  Alert,
  ActivityIndicator,
} from 'react-native';
import { useRoute, useNavigation } from '@react-navigation/native';
import type { RouteProp } from '@react-navigation/native';
import type { NativeStackNavigationProp } from '@react-navigation/native-stack';
import { visitAPI } from '../../api/visit';
import { Colors, FontSize, Spacing, BorderRadius, Shadow } from '../../constants/theme';
import type { RootStackParamList, VisitInProgressParams } from '../../navigation/types';
import type { ObjectionAlert } from '../../types';

type RouteType = RouteProp<{ VisitInProgress: VisitInProgressParams }, 'VisitInProgress'>;
type Nav = NativeStackNavigationProp<RootStackParamList>;

interface TranscriptSegment {
  id: string;
  speaker: 'rep' | 'hcp';
  text: string;
  time: string;
}

export default function VisitInProgressScreen() {
  const route = useRoute<RouteType>();
  const navigation = useNavigation<Nav>();
  const { visitId, hcpName } = route.params;

  const [transcript, setTranscript] = useState<TranscriptSegment[]>([]);
  const [objections, setObjections] = useState<ObjectionAlert[]>([]);
  const [complianceAlerts, setComplianceAlerts] = useState<
    { rule_code: string; description: string }[]
  >([]);
  const [elapsed, setElapsed] = useState(0); // 秒
  const [sending, setSending] = useState(false);
  const [showRedLine, setShowRedLine] = useState<string | null>(null);
  const timerRef = useRef<ReturnType<typeof setInterval>>();
  const scrollRef = useRef<ScrollView>(null);

  // 计时器
  useEffect(() => {
    timerRef.current = setInterval(() => {
      setElapsed((prev) => prev + 1);
    }, 1000);
    return () => {
      if (timerRef.current) clearInterval(timerRef.current);
    };
  }, []);

  const formatTime = (seconds: number) => {
    const m = Math.floor(seconds / 60);
    const s = seconds % 60;
    return `${m.toString().padStart(2, '0')}:${s.toString().padStart(2, '0')}`;
  };

  // 模拟录入转写文本（真实场景用通义听悟实时流）
  const addTranscript = useCallback(
    async (text: string, speaker: 'rep' | 'hcp') => {
      const seg: TranscriptSegment = {
        id: `ts_${Date.now()}`,
        speaker,
        text,
        time: formatTime(elapsed),
      };
      setTranscript((prev) => [...prev, seg]);

      // 发送到后端做合规检查 + 异议识别
      setSending(true);
      try {
        const result = await visitAPI.sendTranscript(visitId, { text });
        if (result.objections?.length) {
          setObjections((prev) => [...prev, ...result.objections]);
        }
        if (result.compliance_alerts?.length) {
          setComplianceAlerts((prev) => [
            ...prev,
            ...result.compliance_alerts,
          ]);
          // 红线拦截弹窗
          const critical = result.compliance_alerts.find(
            (a) => a.rule_code?.startsWith('R00')
          );
          if (critical) {
            setShowRedLine(critical.description);
          }
        }
      } catch {
        // 后端不可用不阻塞
      } finally {
        setSending(false);
      }
    },
    [visitId, elapsed]
  );

  const handleEndVisit = () => {
    Alert.alert('结束拜访', '确认结束本次拜访并生成总结？', [
      { text: '取消', style: 'cancel' },
      {
        text: '确认结束',
        onPress: async () => {
          try {
            await visitAPI.endVisit(visitId);
          } catch {
            // 失败也跳转
          }
          navigation.replace('VisitEnd', { visitId });
        },
      },
    ]);
  };

  // 模拟语音录入按钮
  const simulateInput = (speaker: 'rep' | 'hcp') => {
    const samples = {
      rep: [
        '主任，关于这个产品最新的临床数据您关注过吗？',
        '我们的产品在这一适应症上有很好的疗效数据支持。',
        '您觉得患者对这类治疗方案接受度怎么样？',
      ],
      hcp: [
        '这个数据和国际指南一致吗？',
        '我对这个方案的安全性还有些顾虑。',
        '价格方面对患者来说还是比较大的负担。',
      ],
    };
    const list = samples[speaker];
    const text = list[Math.floor(Math.random() * list.length)];
    addTranscript(text, speaker);
  };

  return (
    <View style={styles.container}>
      {/* 头部 */}
      <View style={styles.header}>
        <TouchableOpacity onPress={() => navigation.goBack()}>
          <Text style={styles.backText}>← </Text>
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
        {/* 转写内容 */}
        <ScrollView
          ref={scrollRef}
          style={styles.transcriptArea}
          contentContainerStyle={styles.transcriptContent}
          onContentSizeChange={() => scrollRef.current?.scrollToEnd()}
          showsVerticalScrollIndicator={false}
        >
          {transcript.length === 0 && (
            <View style={styles.placeholder}>
              <Text style={styles.placeholderIcon}>🎙️</Text>
              <Text style={styles.placeholderText}>
                点击底部按钮模拟语音输入{'\n'}
                开始录音后将实时转写对话内容
              </Text>
            </View>
          )}
          {transcript.map((seg) => (
            <View
              key={seg.id}
              style={[
                styles.tsItem,
                seg.speaker === 'rep'
                  ? styles.tsRep
                  : styles.tsHcp,
              ]}
            >
              <View style={styles.tsHead}>
                <Text style={styles.tsSpeaker}>
                  {seg.speaker === 'rep' ? '代表' : hcpName}
                </Text>
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

        {/* 右侧面板：异议 + 话术 */}
        <View style={styles.sidePanel}>
          {/* 异议警告 */}
          {objections.length > 0 && (
            <View style={styles.sideSection}>
              <Text style={styles.sideTitle}>⚠️ 异议</Text>
              {objections.slice(-3).map((obj, i) => (
                <TouchableOpacity
                  key={i}
                  style={[
                    styles.objectionCard,
                    obj.severity === 'critical' && styles.criticalCard,
                  ]}
                  onPress={() =>
                    Alert.alert(
                      '应对话术',
                      obj.suggested_response || '暂无建议话术'
                    )
                  }
                >
                  <Text style={styles.objectionText} numberOfLines={2}>
                    {obj.description}
                  </Text>
                  {obj.suggested_response && (
                    <Text style={styles.tipLabel}>点击查看话术 →</Text>
                  )}
                </TouchableOpacity>
              ))}
            </View>
          )}

          {/* 合规提醒 */}
          {complianceAlerts.length > 0 && (
            <View style={styles.sideSection}>
              <Text style={[styles.sideTitle, { color: Colors.danger }]}>
                🚫 合规提醒
              </Text>
              {complianceAlerts.slice(-2).map((alert, i) => (
                <View key={i} style={styles.complianceItem}>
                  <Text style={styles.complianceText}>{alert.description}</Text>
                </View>
              ))}
            </View>
          )}
        </View>
      </View>

      {/* 红线拦截弹窗 */}
      {showRedLine && (
        <View style={styles.redLineOverlay}>
          <View style={styles.redLineBox}>
            <Text style={styles.redLineIcon}>⚠️</Text>
            <Text style={styles.redLineTitle}>合规红线提醒</Text>
            <Text style={styles.redLineText}>{showRedLine}</Text>
            <Text style={styles.redLineHint}>
              请调整话术，避免不合规表述
            </Text>
            <TouchableOpacity
              style={styles.dismissBtn}
              onPress={() => setShowRedLine(null)}
            >
              <Text style={styles.dismissText}>我知道了</Text>
            </TouchableOpacity>
          </View>
        </View>
      )}

      {/* 底部操作 */}
      <View style={styles.bottomBar}>
        <TouchableOpacity
          style={styles.simBtn}
          onPress={() => simulateInput('rep')}
          disabled={sending}
        >
          <Text style={styles.simBtnText}>代表说</Text>
        </TouchableOpacity>
        <TouchableOpacity
          style={[styles.simBtn, styles.simBtnHcp]}
          onPress={() => simulateInput('hcp')}
          disabled={sending}
        >
          <Text style={styles.simBtnTextHcp}>医生说</Text>
        </TouchableOpacity>
        <TouchableOpacity
          style={styles.endBtn}
          onPress={handleEndVisit}
        >
          <Text style={styles.endBtnText}>结束拜访</Text>
        </TouchableOpacity>
      </View>
    </View>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1, backgroundColor: Colors.background },
  // 头部
  header: {
    backgroundColor: Colors.primary,
    paddingTop: 50,
    paddingBottom: 12,
    paddingHorizontal: Spacing.lg,
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
  },
  backText: { color: Colors.textWhite, fontSize: FontSize.md, paddingRight: 16 },
  headerCenter: { alignItems: 'center' },
  headerTitle: { color: Colors.textWhite, fontSize: FontSize.lg, fontWeight: '700' },
  headerSub: { color: 'rgba(255,255,255,0.7)', fontSize: FontSize.xs },
  timerBox: {
    flexDirection: 'row',
    alignItems: 'center',
    backgroundColor: 'rgba(255,255,255,0.2)',
    paddingHorizontal: 12,
    paddingVertical: 6,
    borderRadius: BorderRadius.full,
    gap: 6,
  },
  recDot: { width: 8, height: 8, borderRadius: 4, backgroundColor: Colors.danger },
  timerText: { color: Colors.textWhite, fontSize: FontSize.sm, fontWeight: '600', fontVariant: ['tabular-nums'] },
  // 主体
  body: { flex: 1, flexDirection: 'row' },
  // 转写区
  transcriptArea: { flex: 2, padding: Spacing.md },
  transcriptContent: { paddingBottom: Spacing.lg },
  placeholder: {
    flex: 1,
    justifyContent: 'center',
    alignItems: 'center',
    paddingTop: 80,
  },
  placeholderIcon: { fontSize: 48, marginBottom: Spacing.lg },
  placeholderText: {
    fontSize: FontSize.sm,
    color: Colors.textHint,
    textAlign: 'center',
    lineHeight: 22,
  },
  tsItem: {
    padding: Spacing.md,
    borderRadius: BorderRadius.md,
    marginBottom: Spacing.sm,
    maxWidth: '90%',
  },
  tsRep: { alignSelf: 'flex-end', backgroundColor: '#dbeafe' },
  tsHcp: { alignSelf: 'flex-start', backgroundColor: Colors.white, ...Shadow.card },
  tsHead: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    marginBottom: 4,
  },
  tsSpeaker: { fontSize: FontSize.xs, fontWeight: '600', color: Colors.textSecondary },
  tsTime: { fontSize: 10, color: Colors.textHint, fontVariant: ['tabular-nums'] },
  tsText: { fontSize: FontSize.md, color: Colors.textPrimary, lineHeight: 22 },
  analyzing: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: Spacing.sm,
    alignSelf: 'center',
    padding: Spacing.sm,
  },
  analyzingText: { color: Colors.textHint, fontSize: FontSize.xs },
  // 侧面板
  sidePanel: {
    flex: 1,
    backgroundColor: Colors.white,
    borderLeftWidth: 1,
    borderLeftColor: Colors.divider,
    padding: Spacing.sm,
  },
  sideSection: { marginBottom: Spacing.lg },
  sideTitle: {
    fontSize: FontSize.xs,
    fontWeight: '700',
    color: Colors.warning,
    marginBottom: Spacing.sm,
  },
  objectionCard: {
    backgroundColor: '#fffbeb',
    padding: Spacing.sm,
    borderRadius: BorderRadius.sm,
    marginBottom: Spacing.xs,
    borderLeftWidth: 3,
    borderLeftColor: Colors.warning,
  },
  criticalCard: { backgroundColor: '#fef2f2', borderLeftColor: Colors.danger },
  objectionText: { fontSize: FontSize.xs, color: Colors.textPrimary, lineHeight: 18 },
  tipLabel: { fontSize: 10, color: Colors.primary, marginTop: 4 },
  complianceItem: {
    backgroundColor: '#fef2f2',
    padding: Spacing.sm,
    borderRadius: BorderRadius.sm,
    marginBottom: Spacing.xs,
  },
  complianceText: { fontSize: FontSize.xs, color: Colors.danger, lineHeight: 18 },
  // 红线弹窗
  redLineOverlay: {
    ...StyleSheet.absoluteFillObject,
    backgroundColor: 'rgba(0,0,0,0.5)',
    justifyContent: 'center',
    alignItems: 'center',
    zIndex: 100,
  },
  redLineBox: {
    backgroundColor: Colors.white,
    margin: Spacing.xxxl,
    borderRadius: BorderRadius.xl,
    padding: Spacing.xxl,
    alignItems: 'center',
    borderWidth: 2,
    borderColor: Colors.danger,
  },
  redLineIcon: { fontSize: 48, marginBottom: Spacing.md },
  redLineTitle: { fontSize: FontSize.lg, fontWeight: '700', color: Colors.danger, marginBottom: Spacing.md },
  redLineText: { fontSize: FontSize.md, color: Colors.textPrimary, textAlign: 'center', lineHeight: 22, marginBottom: Spacing.lg },
  redLineHint: { fontSize: FontSize.xs, color: Colors.textHint, marginBottom: Spacing.xl },
  dismissBtn: {
    backgroundColor: Colors.danger,
    paddingHorizontal: Spacing.xxxl,
    paddingVertical: Spacing.md,
    borderRadius: BorderRadius.full,
  },
  dismissText: { color: Colors.textWhite, fontSize: FontSize.md, fontWeight: '600' },
  // 底部栏
  bottomBar: {
    flexDirection: 'row',
    padding: Spacing.md,
    paddingBottom: 34,
    backgroundColor: Colors.white,
    borderTopWidth: 1,
    borderTopColor: Colors.divider,
    gap: Spacing.sm,
  },
  simBtn: {
    flex: 1,
    backgroundColor: Colors.primary,
    borderRadius: BorderRadius.lg,
    paddingVertical: 14,
    alignItems: 'center',
  },
  simBtnHcp: {
    backgroundColor: Colors.white,
    borderWidth: 1,
    borderColor: Colors.primary,
  },
  simBtnText: { color: Colors.textWhite, fontSize: FontSize.sm, fontWeight: '600' },
  simBtnTextHcp: { color: Colors.primary, fontSize: FontSize.sm, fontWeight: '600' },
  endBtn: {
    backgroundColor: Colors.danger,
    borderRadius: BorderRadius.lg,
    paddingVertical: 14,
    paddingHorizontal: Spacing.xl,
    alignItems: 'center',
  },
  endBtnText: { color: Colors.textWhite, fontSize: FontSize.sm, fontWeight: '600' },
});
