/**
 * AI 陪练 - 场景选择 + 历史列表（二期 H）
 * 预置科室/性格场景 → 创建陪练会话 → 进入对话；历史列表展示评分/轮数。
 */
import React, { useCallback, useEffect, useState } from 'react';
import {
  Alert, Modal, Pressable, ScrollView, StyleSheet, Text, TouchableOpacity, View,
} from 'react-native';
import { useNavigation, useRoute } from '@react-navigation/native';
import type { NativeStackNavigationProp } from '@react-navigation/native-stack';
import type { RouteProp } from '@react-navigation/native';
import Icon from '../../components/Icon';
import { practiceAPI, plazaAPI } from '../../api/practice';
import type { RootStackParamList } from '../../navigation/types';
import { BorderRadius, Colors, FontSize, Shadow, Spacing } from '../../constants/theme';

type Nav = NativeStackNavigationProp<RootStackParamList>;
type Route = RouteProp<RootStackParamList, 'PracticeList'>;

/** 预置场景（科室 × 性格组合成可选项） */
const SCENARIOS = [
  '心内科推广',
  '肿瘤科推广',
  '内分泌科推广',
  '呼吸科推广',
  '神内科推广',
];

/** 预置医生性格（拼接进场景文案） */
const PERSONAS = ['严谨型', '挑剔型', '温和型'];

interface HistoryItem {
  id: number;
  scenario?: string;
  status?: string;
  turn_count?: number;
  scores?: { overall?: number } | null;
}

/** 广场公开 Skill（GET /skill-packages/public 项） */
interface SkillItem {
  id: number;
  name?: string;
  description?: string | null;
  heat?: number;
}

export default function PracticeListScreen() {
  const navigation = useNavigation<Nav>();
  const route = useRoute<Route>();
  // Skill 模版（2026-09-15 屏内直选）：初始值来自广场「加载」带参跳转（route.params
  // 保证 react-navigation 复用已有实例时参数刷新仍生效），屏内可再改/移除
  const [skillId, setSkillId] = useState<number | undefined>(route.params?.skillId);
  const [skills, setSkills] = useState<SkillItem[]>([]);
  const [skillModalOpen, setSkillModalOpen] = useState(false);
  const [skillsLoading, setSkillsLoading] = useState(false);
  const [pickedInModal, setPickedInModal] = useState<number | undefined>(undefined);
  const [scenario, setScenario] = useState(SCENARIOS[0]);
  const [persona, setPersona] = useState(PERSONAS[0]);
  const [history, setHistory] = useState<HistoryItem[]>([]);
  const [loaded, setLoaded] = useState(false);
  const [starting, setStarting] = useState(false);

  const selectedSkill = skills.find((s) => s.id === skillId);

  const loadSkills = useCallback(async () => {
    setSkillsLoading(true);
    try {
      const res = await plazaAPI.list({ page: 1, page_size: 50 });
      setSkills(Array.isArray(res?.items) ? res.items : []);
    } catch {
      // 广场拉取失败不阻塞裸场景陪练，弹窗内提示重试
      setSkills([]);
    } finally {
      setSkillsLoading(false);
    }
  }, []);

  const openSkillModal = () => {
    setPickedInModal(skillId);
    setSkillModalOpen(true);
    if (skills.length === 0) loadSkills();
  };

  const confirmSkill = () => {
    setSkillId(pickedInModal);
    setSkillModalOpen(false);
  };

  const loadHistory = useCallback(async () => {
    setLoaded(false);
    try {
      const res = await practiceAPI.list();
      setHistory(Array.isArray(res?.items) ? res.items : []);
    } catch {
      // 历史列表拉取失败不阻塞场景选择，保留空列表
    } finally {
      setLoaded(true);
    }
  }, []);

  useEffect(() => {
    loadHistory();
  }, [loadHistory]);

  const startPractice = async () => {
    setStarting(true);
    try {
      const fullScenario = `${scenario}·${persona}医生`;
      const session = await practiceAPI.create({ scenario: fullScenario, skill_id: skillId });
      navigation.navigate('PracticeChat', { sessionId: session.id });
    } catch (err: any) {
      Alert.alert('创建失败', err?.message || '无法创建陪练会话，请稍后重试');
    } finally {
      setStarting(false);
    }
  };

  return (
    <View style={styles.container}>
      <View style={styles.header}>
        <TouchableOpacity onPress={() => navigation.goBack()}>
          <Icon name="chevron-left" size={22} color={Colors.textWhite} />
        </TouchableOpacity>
        <Text style={styles.headerTitle}>AI 陪练</Text>
        <View style={{ width: 24 }} />
      </View>

      <ScrollView contentContainerStyle={styles.content}>
        {/* Skill 模版选择（2026-09-15 屏内直选；与广场「加载」带参跳转同一 skill_id 契约） */}
        <View style={[styles.card, Shadow.card]}>
          <Text style={styles.cardTitle}>Skill 模版（可选）</Text>
          {skillId != null && selectedSkill ? (
            <View style={styles.skillPicked}>
              <View style={{ flex: 1 }}>
                <Text style={styles.skillName} numberOfLines={1}>{selectedSkill.name || `Skill #${selectedSkill.id}`}</Text>
                {selectedSkill.description ? (
                  <Text style={styles.skillDesc} numberOfLines={2}>{selectedSkill.description}</Text>
                ) : null}
              </View>
              <TouchableOpacity
                style={styles.skillRemove}
                onPress={() => setSkillId(undefined)}
                hitSlop={{ top: 6, bottom: 6, left: 6, right: 6 }}
              >
                <Icon name="close" size={16} color={Colors.danger} />
              </TouchableOpacity>
            </View>
          ) : (
            <TouchableOpacity style={styles.skillPickBtn} onPress={openSkillModal} activeOpacity={0.7}>
              <Icon name="view-grid-outline" size={16} color={Colors.primary} />
              <Text style={styles.skillPickText}>
                {skillId != null ? `使用 Skill 模版 #${skillId}` : '选择 Skill 模版'}
              </Text>
              <Icon name="chevron-right" size={16} color={Colors.border} />
            </TouchableOpacity>
          )}
          <Text style={styles.skillHint}>
            加载后 AI 医生按模版风格陪练，评分对照模版风格参数；不选则自由陪练
          </Text>
        </View>

        {/* 场景选择 */}
        <View style={[styles.card, Shadow.card]}>
          <Text style={styles.cardTitle}>选择场景（科室）</Text>
          <View style={styles.chipWrap}>
            {SCENARIOS.map((s) => {
              const active = s === scenario;
              return (
                <TouchableOpacity
                  key={s}
                  style={[styles.chip, active && styles.chipActive]}
                  onPress={() => setScenario(s)}
                  activeOpacity={0.7}
                >
                  <Text style={[styles.chipText, active && styles.chipTextActive]}>{s}</Text>
                </TouchableOpacity>
              );
            })}
          </View>

          <Text style={styles.cardTitle}>医生性格</Text>
          <View style={styles.chipWrap}>
            {PERSONAS.map((p) => {
              const active = p === persona;
              return (
                <TouchableOpacity
                  key={p}
                  style={[styles.chip, active && styles.chipActive]}
                  onPress={() => setPersona(p)}
                  activeOpacity={0.7}
                >
                  <Text style={[styles.chipText, active && styles.chipTextActive]}>{p}</Text>
                </TouchableOpacity>
              );
            })}
          </View>

          {skillId != null && (
            <Text style={styles.loadedHint}>已加载 Skill 模版：评分时会对照该模版的风格参数（正式程度/回复长度/开场白）给出风格匹配分；「医生性格」是你的对手配置，两者互不影响</Text>
          )}

          <TouchableOpacity
            style={[styles.startBtn, starting && { opacity: 0.6 }]}
            disabled={starting}
            onPress={startPractice}
            activeOpacity={0.7}
          >
            <Icon name="play" size={18} color={Colors.textWhite} />
            <Text style={styles.startText}>{starting ? '创建中…' : '开始陪练'}</Text>
          </TouchableOpacity>
        </View>

        {/* 历史列表 */}
        <View style={[styles.card, Shadow.card]}>
          <Text style={styles.cardTitle}>历史陪练</Text>
          {!loaded ? (
            <Text style={styles.emptyText}>加载中…</Text>
          ) : history.length === 0 ? (
            <Text style={styles.emptyText}>暂无陪练记录，去开启第一场吧</Text>
          ) : (
            history.map((item, index) => (
              <View key={item.id} style={[styles.historyRow, index > 0 && styles.rowBorder]}>
                <View style={styles.historyIconBox}>
                  <Icon name="robot-outline" size={18} color={Colors.primary} />
                </View>
                <View style={{ flex: 1 }}>
                  <Text style={styles.historyScenario} numberOfLines={1}>
                    {item.scenario || `陪练 #${item.id}`}
                  </Text>
                  <Text style={styles.historyMeta}>轮数 {item.turn_count ?? 0}</Text>
                </View>
                <View style={styles.scoreBox}>
                  <Text style={styles.scoreLabel}>评分</Text>
                  <Text style={styles.scoreValue}>
                    {item.scores?.overall != null ? item.scores.overall : '--'}
                  </Text>
                </View>
              </View>
            ))
          )}
        </View>
      </ScrollView>

      {/* Skill 选择弹窗：广场 approved+公开模版单选（不调 /load，创建会话带 skill_id 即可） */}
      <Modal visible={skillModalOpen} transparent animationType="fade" onRequestClose={() => setSkillModalOpen(false)}>
        <TouchableOpacity style={styles.modalMask} activeOpacity={1} onPress={() => setSkillModalOpen(false)}>
          <PressableCard>
            <View style={styles.modalHead}>
              <Text style={styles.modalTitle}>选择 Skill 模版</Text>
              <TouchableOpacity onPress={() => setSkillModalOpen(false)} hitSlop={{ top: 8, bottom: 8 }}>
                <Icon name="close" size={20} color={Colors.textSecondary} />
              </TouchableOpacity>
            </View>
            {skillsLoading ? (
              <Text style={styles.modalEmpty}>加载中…</Text>
            ) : skills.length === 0 ? (
              <View style={styles.modalEmptyWrap}>
                <Text style={styles.modalEmpty}>广场暂无可用 Skill 模版</Text>
                <TouchableOpacity style={styles.modalRetry} onPress={loadSkills} activeOpacity={0.7}>
                  <Text style={styles.modalRetryText}>重新加载</Text>
                </TouchableOpacity>
              </View>
            ) : (
              <ScrollView style={styles.skillScroll} nestedScrollEnabled>
                <TouchableOpacity
                  style={[styles.skillRow, pickedInModal == null && styles.skillRowActive]}
                  onPress={() => setPickedInModal(undefined)}
                  activeOpacity={0.7}
                >
                  <View style={{ flex: 1 }}>
                    <Text style={styles.skillName}>不使用模版（自由陪练）</Text>
                  </View>
                  {pickedInModal == null && <Icon name="check-circle" size={20} color={Colors.primary} />}
                </TouchableOpacity>
                {skills.map((s) => {
                  const active = pickedInModal === s.id;
                  return (
                    <TouchableOpacity
                      key={s.id}
                      style={[styles.skillRow, active && styles.skillRowActive]}
                      onPress={() => setPickedInModal(s.id)}
                      activeOpacity={0.7}
                    >
                      <View style={{ flex: 1 }}>
                        <Text style={styles.skillName} numberOfLines={1}>{s.name || `Skill #${s.id}`}</Text>
                        {s.description ? (
                          <Text style={styles.skillDesc} numberOfLines={2}>{s.description}</Text>
                        ) : (
                          <Text style={styles.skillMeta}>热度 {s.heat ?? 0}</Text>
                        )}
                      </View>
                      {active && <Icon name="check-circle" size={20} color={Colors.primary} />}
                    </TouchableOpacity>
                  );
                })}
              </ScrollView>
            )}
            <TouchableOpacity style={styles.modalConfirm} onPress={confirmSkill} activeOpacity={0.7}>
              <Text style={styles.modalConfirmText}>确定</Text>
            </TouchableOpacity>
          </PressableCard>
        </TouchableOpacity>
      </Modal>
    </View>
  );
}

/** 阻止点击卡片内容误关弹窗（Modal 内层容器：空 onPress 拦截穿透） */
function PressableCard({ children }: { children: React.ReactNode }) {
  return (
    <Pressable style={styles.modalCard} onPress={() => {}}>
      {children}
    </Pressable>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1, backgroundColor: Colors.background },
  header: {
    backgroundColor: Colors.primary, paddingTop: 50, paddingBottom: 14,
    paddingHorizontal: Spacing.lg, flexDirection: 'row',
    alignItems: 'center', justifyContent: 'space-between', ...Shadow.header,
  },
  headerTitle: { color: Colors.textWhite, fontSize: FontSize.lg, fontWeight: '600' },
  content: { padding: Spacing.md },
  card: { backgroundColor: Colors.card, borderRadius: BorderRadius.md, padding: Spacing.lg, marginBottom: Spacing.md },
  cardTitle: { fontSize: FontSize.md, fontWeight: '600', color: Colors.textPrimary, marginBottom: Spacing.sm, marginTop: Spacing.xs },
  chipWrap: { flexDirection: 'row', flexWrap: 'wrap', gap: Spacing.sm, marginBottom: Spacing.xs },
  chip: {
    paddingHorizontal: Spacing.lg, paddingVertical: Spacing.sm,
    borderRadius: BorderRadius.full, borderWidth: 1, borderColor: Colors.border,
    backgroundColor: Colors.white,
  },
  chipActive: { backgroundColor: Colors.primarySurface, borderColor: Colors.primary },
  chipText: { fontSize: FontSize.sm, color: Colors.textSecondary },
  chipTextActive: { color: Colors.primary, fontWeight: '600' },
  startBtn: {
    marginTop: Spacing.lg, backgroundColor: Colors.primary, borderRadius: BorderRadius.sm,
    padding: Spacing.md, alignItems: 'center', flexDirection: 'row',
    justifyContent: 'center', gap: Spacing.sm,
  },
  startText: { color: Colors.textWhite, fontSize: FontSize.md, fontWeight: '600' },
  loadedHint: {
    fontSize: FontSize.xs, color: Colors.info, marginTop: Spacing.sm,
    backgroundColor: Colors.primarySurface, padding: Spacing.sm, borderRadius: BorderRadius.sm,
  },
  skillPicked: {
    flexDirection: 'row', alignItems: 'center', gap: Spacing.sm,
    borderWidth: 1, borderColor: Colors.primary, borderRadius: BorderRadius.sm,
    backgroundColor: Colors.primarySurface, padding: Spacing.md,
  },
  skillName: { fontSize: FontSize.md, color: Colors.textPrimary, fontWeight: '600' },
  skillDesc: { fontSize: FontSize.xs, color: Colors.textSecondary, marginTop: 2, lineHeight: 17 },
  skillMeta: { fontSize: FontSize.xs, color: Colors.textHint, marginTop: 2 },
  skillRemove: {
    width: 28, height: 28, borderRadius: BorderRadius.full,
    borderWidth: 1, borderColor: Colors.danger, alignItems: 'center', justifyContent: 'center',
  },
  skillPickBtn: {
    flexDirection: 'row', alignItems: 'center', gap: Spacing.sm,
    borderWidth: 1, borderColor: Colors.border, borderRadius: BorderRadius.sm,
    backgroundColor: Colors.white, padding: Spacing.md,
  },
  skillPickText: { flex: 1, fontSize: FontSize.sm, color: Colors.textPrimary },
  skillHint: { fontSize: FontSize.xs, color: Colors.textHint, marginTop: Spacing.sm },
  modalMask: {
    flex: 1, backgroundColor: 'rgba(0,0,0,0.5)', alignItems: 'center',
    justifyContent: 'center', padding: Spacing.lg,
  },
  modalCard: {
    backgroundColor: Colors.card, borderRadius: BorderRadius.lg, padding: Spacing.lg,
    width: '100%', maxHeight: '80%',
  },
  modalHead: {
    flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between',
    marginBottom: Spacing.sm,
  },
  modalTitle: { fontSize: FontSize.md, fontWeight: '700', color: Colors.textPrimary },
  modalEmpty: { fontSize: FontSize.sm, color: Colors.textHint, textAlign: 'center', paddingVertical: Spacing.lg },
  modalEmptyWrap: { alignItems: 'center' },
  modalRetry: {
    borderWidth: 1, borderColor: Colors.primary, borderRadius: BorderRadius.sm,
    paddingHorizontal: Spacing.lg, paddingVertical: Spacing.xs, marginBottom: Spacing.sm,
  },
  modalRetryText: { color: Colors.primary, fontSize: FontSize.sm, fontWeight: '600' },
  skillScroll: { maxHeight: 360 },
  skillRow: {
    flexDirection: 'row', alignItems: 'center', gap: Spacing.md,
    paddingVertical: Spacing.md, paddingHorizontal: Spacing.sm,
    borderRadius: BorderRadius.sm, marginBottom: Spacing.xs,
  },
  skillRowActive: { backgroundColor: Colors.primarySurface },
  modalConfirm: {
    marginTop: Spacing.sm, backgroundColor: Colors.primary, borderRadius: BorderRadius.sm,
    padding: Spacing.md, alignItems: 'center',
  },
  modalConfirmText: { color: Colors.textWhite, fontSize: FontSize.md, fontWeight: '600' },
  emptyText: { fontSize: FontSize.sm, color: Colors.textHint, textAlign: 'center', paddingVertical: Spacing.lg },
  historyRow: { flexDirection: 'row', alignItems: 'center', paddingVertical: Spacing.md, gap: Spacing.md },
  rowBorder: { borderTopWidth: StyleSheet.hairlineWidth, borderTopColor: Colors.divider },
  historyIconBox: {
    width: 36, height: 36, borderRadius: 10,
    backgroundColor: Colors.primarySurface, alignItems: 'center', justifyContent: 'center',
  },
  historyScenario: { fontSize: FontSize.md, color: Colors.textPrimary, fontWeight: '500' },
  historyMeta: { fontSize: FontSize.xs, color: Colors.textSecondary, marginTop: 2 },
  scoreBox: { alignItems: 'center', minWidth: 48 },
  scoreLabel: { fontSize: FontSize.xs, color: Colors.textHint },
  scoreValue: { fontSize: FontSize.lg, fontWeight: '700', color: Colors.accent },
});
