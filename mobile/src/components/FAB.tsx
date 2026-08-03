/**
 * 浮动操作按钮 (FAB)
 */
import React from 'react';
import { TouchableOpacity, Text, StyleSheet } from 'react-native';
import { Colors, Shadow } from '../constants/theme';

interface FABProps {
  onPress: () => void;
  label?: string;
  icon?: string;
  bottom?: number;
  right?: number;
}

export default function FAB({
  onPress,
  label,
  icon = '+',
  bottom = 24,
  right = 20,
}: FABProps) {
  return (
    <TouchableOpacity
      style={[styles.fab, Shadow.button, { bottom, right }]}
      onPress={onPress}
      activeOpacity={0.8}
    >
      <Text style={styles.icon}>{icon}</Text>
      {label && <Text style={styles.label}>{label}</Text>}
    </TouchableOpacity>
  );
}

const styles = StyleSheet.create({
  fab: {
    position: 'absolute',
    backgroundColor: Colors.primary,
    flexDirection: 'row',
    alignItems: 'center',
    paddingHorizontal: 20,
    paddingVertical: 14,
    borderRadius: 28,
    gap: 6,
  },
  icon: {
    color: Colors.textWhite,
    fontSize: 22,
    fontWeight: '300',
  },
  label: {
    color: Colors.textWhite,
    fontSize: 15,
    fontWeight: '600',
  },
});
