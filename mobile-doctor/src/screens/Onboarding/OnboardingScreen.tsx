/**
 * 医生端新人引导轮播（与代表端同构，文案独立）：价值叙事开场 → 操作说明收尾。
 * 触发两条：首登 OnboardingGate 自动 push（深链 pendingToken 存在时不弹，激活优先）；
 * 「我的 → 功能引导」手动重看。
 */
import React, { useRef, useState } from 'react';
import {
  View, Text, ScrollView, StyleSheet, Dimensions, TouchableOpacity, NativeSyntheticEvent, NativeScrollEvent,
} from 'react-native';
import AsyncStorage from '@react-native-async-storage/async-storage';
import { useNavigation } from '@react-navigation/native';
import { Colors, FontSize, Spacing, BorderRadius, Shadow } from '../../constants/theme';
import { DOCTOR_ONBOARDING_SLIDES, DOCTOR_ONBOARDING_KEY } from './doctorSlides';

const { width: SCREEN_W } = Dimensions.get('window');

export default function OnboardingScreen() {
  const navigation = useNavigation();
  const scrollRef = useRef<ScrollView>(null);
  const [page, setPage] = useState(0);
  const total = DOCTOR_ONBOARDING_SLIDES.length;
  const isLast = page === total - 1;

  const finish = async () => {
    // 跳过=完成：写标记后不再自动弹
    await AsyncStorage.setItem(DOCTOR_ONBOARDING_KEY, String(Date.now()));
    if (navigation.canGoBack()) navigation.goBack();
  };

  const onPageChange = (e: NativeSyntheticEvent<NativeScrollEvent>) => {
    setPage(Math.round(e.nativeEvent.contentOffset.x / SCREEN_W));
  };

  return (
    <View style={styles.container}>
      <ScrollView
        ref={scrollRef}
        horizontal
        pagingEnabled
        showsHorizontalScrollIndicator={false}
        onMomentumScrollEnd={onPageChange}
      >
        {DOCTOR_ONBOARDING_SLIDES.map((s) => (
          <View key={s.title} style={styles.slide}>
            <View style={[styles.iconWrap, Shadow.card]}>
              <Text style={styles.icon}>{s.icon}</Text>
            </View>
            <Text style={styles.title}>{s.title}</Text>
            {s.bullets.map((b) => (
              <View key={b} style={styles.bulletRow}>
                <View style={styles.dot} />
                <Text style={styles.bullet}>{b}</Text>
              </View>
            ))}
          </View>
        ))}
      </ScrollView>

      <View style={styles.footer}>
        <TouchableOpacity onPress={finish} hitSlop={{ top: 8, bottom: 8 }}>
          <Text style={styles.skip}>跳过</Text>
        </TouchableOpacity>
        <View style={styles.dots}>
          {DOCTOR_ONBOARDING_SLIDES.map((s, i) => (
            <View key={s.title} style={[styles.pageDot, i === page && styles.pageDotActive]} />
          ))}
        </View>
        <TouchableOpacity
          style={[styles.btn, isLast ? styles.btnPrimary : styles.btnGhost]}
          onPress={() => {
            if (isLast) finish();
            else scrollRef.current?.scrollTo({ x: (page + 1) * SCREEN_W, animated: true });
          }}
        >
          <Text style={[styles.btnText, isLast ? styles.btnTextPrimary : styles.btnTextGhost]}>
            {isLast ? '开始使用' : '下一步'}
          </Text>
        </TouchableOpacity>
      </View>
    </View>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1, backgroundColor: Colors.white },
  slide: { width: SCREEN_W, paddingHorizontal: Spacing.xl, paddingTop: '18%', alignItems: 'flex-start' },
  iconWrap: {
    width: 96, height: 96, borderRadius: BorderRadius.xl,
    backgroundColor: Colors.primarySurface, alignItems: 'center', justifyContent: 'center',
    marginBottom: Spacing.lg,
  },
  icon: { fontSize: 48 },
  title: { fontSize: FontSize.xl, fontWeight: '700', color: Colors.primary, marginBottom: Spacing.md },
  bulletRow: { flexDirection: 'row', alignItems: 'flex-start', marginBottom: Spacing.sm, alignSelf: 'stretch' },
  dot: { width: 6, height: 6, borderRadius: 3, backgroundColor: Colors.accent, marginTop: 8, marginRight: Spacing.sm },
  bullet: { flex: 1, fontSize: FontSize.md, color: Colors.textSecondary, lineHeight: 24 },
  footer: { flexDirection: 'row', alignItems: 'center', paddingHorizontal: Spacing.lg, paddingBottom: Spacing.xl, gap: Spacing.md },
  skip: { fontSize: FontSize.md, color: Colors.textHint },
  dots: { flex: 1, flexDirection: 'row', justifyContent: 'center', gap: 6 },
  pageDot: { width: 8, height: 8, borderRadius: 4, backgroundColor: '#D1D5DB' },
  pageDotActive: { width: 20, backgroundColor: Colors.primary },
  btn: { paddingHorizontal: Spacing.xl, paddingVertical: Spacing.sm, borderRadius: BorderRadius.lg },
  btnPrimary: { backgroundColor: Colors.primary },
  btnGhost: { borderWidth: 1, borderColor: Colors.border },
  btnText: { fontSize: FontSize.md, fontWeight: '600' },
  btnTextPrimary: { color: '#fff' },
  btnTextGhost: { color: Colors.primary },
});
