/**
 * 医生端新人引导闸门：包住 MainTabs——首登（AsyncStorage 无标记）自动 push Onboarding。
 * 深链优先（F2 语义）：pendingToken 存在（代表分享的激活链接待消费）时绝不弹引导，
 * 避免打断 TwinActivate 流程；激活完成后的下一次冷启动会补弹（正是需要引导的时刻）。
 */
import React, { useEffect } from 'react';
import AsyncStorage from '@react-native-async-storage/async-storage';
import { useNavigation } from '@react-navigation/native';
import { useAuth } from '../../store/AuthContext';
import { DOCTOR_ONBOARDING_KEY } from './doctorSlides';

export default function OnboardingGate({ children }: { children: React.ReactNode }) {
  const navigation = useNavigation();
  const { pendingToken } = useAuth();

  useEffect(() => {
    if (pendingToken) return; // 深链激活优先，不打断
    let alive = true;
    AsyncStorage.getItem(DOCTOR_ONBOARDING_KEY).then((v) => {
      if (alive && v === null) navigation.navigate('Onboarding' as never);
    }).catch(() => {/* 存储异常不挡主流程 */});
    return () => { alive = false; };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [pendingToken]);

  return <>{children}</>;
}
