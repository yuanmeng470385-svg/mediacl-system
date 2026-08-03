/**
 * 进度环组件 - 用于工作台展示今日拜访进度
 */
import React from 'react';
import { View, Text, StyleSheet } from 'react-native';
import { Colors, FontSize } from '../constants/theme';

interface ProgressRingProps {
  completed: number;
  total: number;
  size?: number;
  strokeWidth?: number;
  label?: string;
}

export default function ProgressRing({
  completed,
  total,
  size = 120,
  strokeWidth = 10,
  label = '今日拜访',
}: ProgressRingProps) {
  const percentage = total > 0 ? Math.round((completed / total) * 100) : 0;
  // 使用纯 View 模拟环形进度（避免依赖 react-native-svg）
  const radius = (size - strokeWidth) / 2;
  const isComplete = completed >= total && total > 0;

  return (
    <View style={[styles.container, { width: size, height: size }]}>
      {/* 外环背景 */}
      <View
        style={[
          styles.ringBg,
          {
            width: size,
            height: size,
            borderRadius: size / 2,
            borderWidth: strokeWidth,
          },
        ]}
      />
      {/* 进度指示器——简化版：4个象限 */}
      <View style={styles.ringProgress}>
        {[0, 90, 180, 270].map((deg, i) => {
          const quadrantFilled = percentage > i * 25;
          return (
            <View
              key={i}
              style={[
                styles.quadrant,
                {
                  backgroundColor: quadrantFilled
                    ? isComplete
                      ? Colors.success
                      : Colors.primary
                    : 'transparent',
                  transform: [{ rotate: `${deg}deg` }],
                },
              ]}
            />
          );
        })}
      </View>
      {/* 中心文字 */}
      <View style={styles.center}>
        <Text style={[styles.number, { color: isComplete ? Colors.success : Colors.primary }]}>
          {completed}/{total}
        </Text>
        {percentage > 0 && (
          <Text style={styles.percent}>{percentage}%</Text>
        )}
        <Text style={styles.label}>{label}</Text>
      </View>
    </View>
  );
}

const styles = StyleSheet.create({
  container: {
    alignItems: 'center',
    justifyContent: 'center',
    alignSelf: 'center',
  },
  ringBg: {
    position: 'absolute',
    borderColor: '#e5e7eb',
  },
  ringProgress: {
    position: 'absolute',
    width: '100%',
    height: '100%',
    alignItems: 'center',
    justifyContent: 'center',
  },
  quadrant: {
    position: 'absolute',
    width: 8,
    height: 8,
    borderRadius: 4,
  },
  center: {
    alignItems: 'center',
    justifyContent: 'center',
  },
  number: {
    fontSize: FontSize.xxl,
    fontWeight: '700',
  },
  percent: {
    fontSize: FontSize.xs,
    color: Colors.textHint,
    marginTop: 2,
  },
  label: {
    fontSize: FontSize.xs,
    color: Colors.textSecondary,
    marginTop: 4,
  },
});
