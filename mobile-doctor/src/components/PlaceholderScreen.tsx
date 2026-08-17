/**
 * 占位屏 - 医生端骨架阶段通用占位组件（B8 填真实现）
 */
import React from 'react';
import { View, Text, StyleSheet } from 'react-native';
import { Colors, FontSize } from '../constants/theme';

interface PlaceholderScreenProps {
  title: string;
  description?: string;
}

export default function PlaceholderScreen({ title, description }: PlaceholderScreenProps) {
  return (
    <View style={styles.container}>
      <Text style={styles.title}>{title}</Text>
      {description ? <Text style={styles.description}>{description}</Text> : null}
    </View>
  );
}

const styles = StyleSheet.create({
  container: {
    flex: 1,
    justifyContent: 'center',
    alignItems: 'center',
    backgroundColor: Colors.background,
  },
  title: {
    fontSize: FontSize.xl,
    fontWeight: '700',
    color: Colors.textPrimary,
  },
  description: {
    fontSize: FontSize.sm,
    color: Colors.textHint,
    marginTop: 8,
  },
});
