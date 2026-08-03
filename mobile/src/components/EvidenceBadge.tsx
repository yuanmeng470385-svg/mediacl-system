/**
 * 证据等级标签组件
 */
import React from 'react';
import { View, Text, StyleSheet } from 'react-native';
import { Colors, FontSize, BorderRadius } from '../constants/theme';

interface EvidenceBadgeProps {
  level: string;
  compact?: boolean;
}

const levelConfig: Record<string, { color: string; bg: string; label: string }> = {
  A: { color: Colors.evidenceA, bg: '#dcfce7', label: 'A 级证据' },
  B: { color: Colors.evidenceB, bg: '#dbeafe', label: 'B 级证据' },
  C: { color: Colors.evidenceC, bg: '#fef3c7', label: 'C 级证据' },
  D: { color: Colors.evidenceD, bg: '#fee2e2', label: 'D 级证据' },
};

export default function EvidenceBadge({
  level,
  compact = false,
}: EvidenceBadgeProps) {
  const config = levelConfig[level] || {
    color: Colors.textHint,
    bg: Colors.background,
    label: `${level} 级`,
  };

  return (
    <View style={[styles.badge, { backgroundColor: config.bg }]}>
      {!compact && (
        <View style={[styles.dot, { backgroundColor: config.color }]} />
      )}
      <Text
        style={[
          styles.text,
          { color: config.color },
          compact && styles.compactText,
        ]}
      >
        {compact ? level : config.label}
      </Text>
    </View>
  );
}

const styles = StyleSheet.create({
  badge: {
    flexDirection: 'row',
    alignItems: 'center',
    paddingHorizontal: 10,
    paddingVertical: 4,
    borderRadius: BorderRadius.full,
    alignSelf: 'flex-start',
    gap: 6,
  },
  dot: {
    width: 8,
    height: 8,
    borderRadius: 4,
  },
  text: {
    fontSize: FontSize.xs,
    fontWeight: '600',
  },
  compactText: {
    fontSize: FontSize.xs,
    paddingHorizontal: 2,
  },
});
