/**
 * 浮动操作按钮 (FAB)
 */
import React from 'react';
import { TouchableOpacity, Text, StyleSheet } from 'react-native';
import Icon from './Icon';
import { Colors, Shadow, FontSize } from '../constants/theme';

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
  icon = 'plus',
  bottom = 24,
  right = 20,
}: FABProps) {
  return (
    <TouchableOpacity
      style={[styles.fab, Shadow.fab, { bottom, right }]}
      onPress={onPress}
      activeOpacity={0.8}
    >
      <Icon name={icon} size={22} color={Colors.textWhite} />
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
    gap: 8,
  },
  label: {
    color: Colors.textWhite,
    fontSize: FontSize.md,
    fontWeight: '600',
  },
});
