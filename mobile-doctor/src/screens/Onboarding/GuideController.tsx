/**
 * 陪玩式新人引导控制器（2026-09-09 v2，替代 v1 OnboardingGate+轮播屏，自 mobile 移植）：
 * card（讲解卡 Modal）→「去试试」navigate(tryRoute) 收卡、目标页完全可操作 →
 * 顶部蓝色引导条常驻召回 → 点开召回卡 →「下一个」前进 /「上一个」回退重看（首步禁用）。
 * 进度 AsyncStorage 断点续传；跳过=完成；Profile「功能引导」清 key 后经
 * guideEvents.restartGuide() 事件重演。
 * 深链优先（F2 语义）：mount 时 pendingToken 存在（激活链接待消费）则本次不弹，
 * 激活完成后的下一次冷启动补弹——不打断 TwinActivate 流程。
 */
import React, { useCallback, useEffect, useState } from 'react';
import {
  View, Text, Modal, Pressable, TouchableOpacity, StyleSheet,
} from 'react-native';
import AsyncStorage from '@react-native-async-storage/async-storage';
import { useNavigation } from '@react-navigation/native';
import { Colors, FontSize, Spacing, BorderRadius, Shadow } from '../../constants/theme';
import { useAuth } from '../../store/AuthContext';
import { onGuideRestart, onGuideRecall, setGuideBar } from '../../events/guideEvents';
import type { GuideStep } from './doctorGuideSteps';

/** card=讲解卡；trying=已导航到目标页自由体验，浮条召回 */
type Phase = 'card' | 'trying';

export default function GuideController({
  steps,
  doneKey,
  progressKey,
  children,
}: {
  steps: GuideStep[];
  doneKey: string;
  progressKey: string;
  children: React.ReactNode;
}) {
  const navigation = useNavigation();
  const { pendingToken } = useAuth();
  const [active, setActive] = useState(false); // 引导进行中（含看卡/体验两态）
  const [cardVisible, setCardVisible] = useState(false); // 讲解/召回卡可见
  const [current, setCurrent] = useState(0);
  const [phase, setPhase] = useState<Phase>('card');

  // 首启：未看过自动开演（有断点从断点续传）；深链 pendingToken 存在时本次不弹
  useEffect(() => {
    if (pendingToken) return; // 深链激活优先，不打断（不依赖 pendingToken 重跑：冷启动补弹）
    let alive = true;
    (async () => {
      try {
        const done = await AsyncStorage.getItem(doneKey);
        if (alive && done === null) {
          const saved = Number(await AsyncStorage.getItem(progressKey));
          setCurrent(Number.isFinite(saved) && saved > 0 ? Math.min(saved, steps.length - 1) : 0);
          setPhase('card');
          setActive(true);
          setCardVisible(true);
        }
      } catch { /* 存储异常不挡主流程 */ }
    })();
    return () => { alive = false; };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [doneKey, progressKey, steps.length]);

  // 重看事件（Profile 清 key 后 emit）
  useEffect(() => onGuideRestart(() => {
    setCurrent(0);
    setPhase('card');
    setActive(true);
    setCardVisible(true);
  }), []);

  // 体验态全局召回条（GuideBar 挂 App 根，事件驱动——本屏被 Stack push 后 detach 时条仍常驻）
  useEffect(() => {
    setGuideBar(active && phase === 'trying');
    return () => setGuideBar(false);
  }, [active, phase]);

  // 点召回条 → 弹「我知道了，继续」召回卡。tryRoute 目标可能是 Stack push 的子页
  // （那时本屏视图被 detach、卡 Modal 渲染不出来）——先回主界面再弹卡
  useEffect(() => onGuideRecall(() => {
    navigation.navigate('MainTabs' as never);
    setCardVisible(true);
  }), [navigation]);

  const finish = useCallback(() => {
    AsyncStorage.setItem(doneKey, String(Date.now())).catch(() => {});
    AsyncStorage.removeItem(progressKey).catch(() => {});
    setActive(false);
    setCardVisible(false);
  }, [doneKey, progressKey]);

  /** 「下一个」→ 前进；末步收尾 */
  const advance = useCallback(() => {
    const next = current + 1;
    if (next >= steps.length) {
      finish();
      return;
    }
    AsyncStorage.setItem(progressKey, String(next)).catch(() => {});
    setCurrent(next);
    setPhase('card');
    setCardVisible(true);
  }, [current, steps.length, finish, progressKey]);

  /** 「上一个」→ 回退重看（首步禁用；召回卡里点也回上一步的讲解卡） */
  const back = useCallback(() => {
    if (current === 0) return;
    const prev = current - 1;
    AsyncStorage.setItem(progressKey, String(prev)).catch(() => {});
    setCurrent(prev);
    setPhase('card');
    setCardVisible(true);
  }, [current, progressKey]);

  /** 「去试试」→ 导航到目标页，收卡进体验态 */
  const goTry = useCallback(() => {
    const step = steps[current];
    if (!step?.tryRoute) return;
    AsyncStorage.setItem(progressKey, String(current)).catch(() => {});
    setPhase('trying');
    setCardVisible(false);
    navigation.navigate(step.tryRoute as never);
  }, [current, steps, navigation]);

  const step = steps[current];
  const isLast = current === steps.length - 1;
  const recall = active && phase === 'trying';

  return (
    <View style={{ flex: 1 }}>
      {children}
      <Modal
        visible={cardVisible && active}
        transparent
        animationType="fade"
        statusBarTranslucent
        onRequestClose={() => { if (recall) setCardVisible(false); }}
      >
        <Pressable style={styles.mask} onPress={() => { if (recall) setCardVisible(false); }}>
          <Pressable style={styles.card} onPress={() => {}}>
            {recall ? (
              <>
                <Text style={styles.title}>在「{step?.tryName ?? '目标页'}」逛得如何？</Text>
                <Text style={styles.hint}>{step?.tryHint}</Text>
                <View style={styles.btnRow}>
                  <TouchableOpacity
                    style={[styles.btnGhost, current === 0 && styles.btnDisabled]}
                    disabled={current === 0}
                    onPress={back}
                  >
                    <Text style={styles.btnGhostText}>上一个</Text>
                  </TouchableOpacity>
                  <View style={styles.btnGroup}>
                    <TouchableOpacity style={styles.btnGhost} onPress={() => setCardVisible(false)}>
                      <Text style={styles.btnGhostText}>先收起，继续逛</Text>
                    </TouchableOpacity>
                    <TouchableOpacity style={styles.btnPrimary} onPress={advance}>
                      <Text style={styles.btnPrimaryText}>下一个</Text>
                    </TouchableOpacity>
                  </View>
                </View>
              </>
            ) : (
              <>
                <View style={[styles.iconWrap, Shadow.card]}>
                  <Text style={styles.icon}>{step?.icon}</Text>
                </View>
                <Text style={styles.title}>{step?.title}</Text>
                {step?.bullets.map((b) => (
                  <View key={b} style={styles.bulletRow}>
                    <View style={styles.dot} />
                    <Text style={styles.bullet}>{b}</Text>
                  </View>
                ))}
                <View style={styles.dots}>
                  {steps.map((s, i) => (
                    <View key={s.title} style={[styles.pageDot, i === current && styles.pageDotActive]} />
                  ))}
                </View>
                <View style={styles.btnRow}>
                  <TouchableOpacity hitSlop={{ top: 8, bottom: 8 }} onPress={finish}>
                    <Text style={styles.skip}>跳过引导</Text>
                  </TouchableOpacity>
                  <View style={styles.btnGroup}>
                    <TouchableOpacity
                      style={[styles.btnGhost, current === 0 && styles.btnDisabled]}
                      disabled={current === 0}
                      onPress={back}
                    >
                      <Text style={styles.btnGhostText}>上一个</Text>
                    </TouchableOpacity>
                    {step?.tryRoute ? (
                      <TouchableOpacity style={styles.btnPrimary} onPress={goTry}>
                        <Text style={styles.btnPrimaryText}>去试试 →</Text>
                      </TouchableOpacity>
                    ) : (
                      <TouchableOpacity style={styles.btnPrimary} onPress={advance}>
                        <Text style={styles.btnPrimaryText}>
                          {isLast ? '完成引导' : current === 0 ? '开始逛逛' : '下一个'}
                        </Text>
                      </TouchableOpacity>
                    )}
                  </View>
                </View>
              </>
            )}
          </Pressable>
        </Pressable>
      </Modal>
    </View>
  );
}

const styles = StyleSheet.create({
  mask: { flex: 1, backgroundColor: 'rgba(0,0,0,0.55)', justifyContent: 'center', alignItems: 'center', padding: Spacing.xl },
  card: {
    width: '100%', backgroundColor: Colors.white, borderRadius: BorderRadius.xl,
    padding: Spacing.xl,
  },
  iconWrap: {
    width: 72, height: 72, borderRadius: BorderRadius.xl,
    backgroundColor: Colors.primarySurface, alignItems: 'center', justifyContent: 'center',
    marginBottom: Spacing.md, alignSelf: 'center',
  },
  icon: { fontSize: 36 },
  title: { fontSize: FontSize.lg, fontWeight: '700', color: Colors.primary, textAlign: 'center', marginBottom: Spacing.md },
  hint: { fontSize: FontSize.md, color: Colors.textSecondary, lineHeight: 24, marginBottom: Spacing.lg },
  bulletRow: { flexDirection: 'row', alignItems: 'flex-start', marginBottom: Spacing.sm },
  dot: { width: 6, height: 6, borderRadius: 3, backgroundColor: Colors.accent, marginTop: 8, marginRight: Spacing.sm },
  bullet: { flex: 1, fontSize: FontSize.md, color: Colors.textSecondary, lineHeight: 24 },
  dots: { flexDirection: 'row', justifyContent: 'center', gap: 6, marginVertical: Spacing.lg },
  pageDot: { width: 8, height: 8, borderRadius: 4, backgroundColor: '#D1D5DB' },
  pageDotActive: { width: 20, backgroundColor: Colors.primary },
  btnRow: { flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between' },
  btnGroup: { flexDirection: 'row', alignItems: 'center', gap: Spacing.md },
  btnDisabled: { opacity: 0.4 },
  skip: { fontSize: FontSize.md, color: Colors.textHint },
  btnPrimary: {
    backgroundColor: Colors.primary, borderRadius: BorderRadius.lg,
    paddingHorizontal: Spacing.xl, paddingVertical: Spacing.sm,
    marginLeft: 'auto',
  },
  btnPrimaryText: { color: '#fff', fontSize: FontSize.md, fontWeight: '600' },
  btnGhost: {
    borderWidth: 1, borderColor: Colors.border, borderRadius: BorderRadius.lg,
    paddingHorizontal: Spacing.lg, paddingVertical: Spacing.sm,
  },
  btnGhostText: { color: Colors.primary, fontSize: FontSize.md, fontWeight: '600' },
});
