/**
 * 新人引导闸门：包住 MainTabs——首登（AsyncStorage 无标记）自动 push Onboarding 屏。
 * 已看过则零开销直接放行（无闪动）；跳过=完成语义在 OnboardingScreen 里落存储。
 */
import React, { useEffect } from 'react';
import AsyncStorage from '@react-native-async-storage/async-storage';
import { useNavigation } from '@react-navigation/native';
import { REP_ONBOARDING_KEY } from './repSlides';

export default function OnboardingGate({ children }: { children: React.ReactNode }) {
  const navigation = useNavigation();

  useEffect(() => {
    let alive = true;
    AsyncStorage.getItem(REP_ONBOARDING_KEY).then((v) => {
      if (alive && v === null) navigation.navigate('Onboarding' as never);
    }).catch(() => {/* 存储异常不挡主流程 */});
    return () => { alive = false; };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  return <>{children}</>;
}
