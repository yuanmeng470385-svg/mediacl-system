/**
 * 体验态顶部召回条（全局唯一实例，挂 App 根、导航器外）：
 * GuideController 进 trying 态时经 guideEvents.setGuideBar 点亮；点击 recallGuide
 * 召回「我知道了，继续」卡。必须在导航器外——native-stack push 后 MainTabs 屏
 * 视图会被 detach，普通渲染在屏内的条会被一并藏掉。
 */
import React, { useEffect, useState } from 'react';
import { Text, TouchableOpacity, StyleSheet, StatusBar } from 'react-native';
import { Colors, FontSize } from '../constants/theme';
import { onGuideBar, recallGuide } from '../events/guideEvents';

export default function GuideBar() {
  const [visible, setVisible] = useState(false);

  useEffect(() => onGuideBar(setVisible), []);

  if (!visible) return null;
  return (
    <TouchableOpacity
      style={styles.bar}
      activeOpacity={0.85}
      onPress={recallGuide}
    >
      <Text style={styles.barText}>🧭 引导进行中 · 逛完点这里继续</Text>
    </TouchableOpacity>
  );
}

const styles = StyleSheet.create({
  bar: {
    position: 'absolute', top: 0, left: 0, right: 0,
    paddingTop: (StatusBar.currentHeight ?? 24) + 8, paddingBottom: 10,
    backgroundColor: 'rgba(22, 119, 255, 0.94)', alignItems: 'center',
    zIndex: 100, elevation: 12,
  },
  barText: { color: '#fff', fontSize: FontSize.sm, fontWeight: '600' },
});
