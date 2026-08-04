/**
 * 拜访卡片组件 - 展示单条拜访记录
 */
import React from 'react';
import { View, Text, StyleSheet, TouchableOpacity } from 'react-native';
import Icon from './Icon';
import { ActionIcons, VisitIcons } from './Icon';
import { Colors, FontSize, BorderRadius, Shadow, Spacing } from '../constants/theme';
import type { VisitRecord } from '../types';

interface VisitCardProps {
  visit: VisitRecord;
  onPress?: () => void;
}

const statusConfig: Record<string, { label: string; color: string; bg: string }> = {
  pending: { label: '待开始', color: Colors.warning, bg: Colors.warningLight },
  in_progress: { label: '进行中', color: Colors.info, bg: Colors.infoLight },
  completed: { label: '已完成', color: Colors.success, bg: Colors.successLight },
  cancelled: { label: '已取消', color: Colors.textHint, bg: Colors.border },
};

export default function VisitCard({ visit, onPress }: VisitCardProps) {
  const status = statusConfig[visit.status] || statusConfig.pending;

  return (
    <TouchableOpacity
      style={[styles.card, Shadow.card]}
      onPress={onPress}
      activeOpacity={0.7}
    >
      <View style={styles.header}>
        <View style={styles.nameRow}>
          <Icon name={VisitIcons.doctor} size={20} color={Colors.primary} />
          <Text style={styles.hcpName}>{visit.hcp_name || '未知医生'}</Text>
          {visit.status === 'pending' && (
            <View style={styles.priorityBadge}>
              <Text style={styles.priorityText}>高优</Text>
            </View>
          )}
        </View>
        <View style={[styles.statusBadge, { backgroundColor: status.bg }]}>
          <Text style={[styles.statusText, { color: status.color }]}>
            {status.label}
          </Text>
        </View>
      </View>

      <View style={styles.info}>
        <View style={styles.infoRow}>
          <Icon name={VisitIcons.calendar} size={14} color={Colors.textHint} />
          <Text style={styles.infoText}>{visit.planned_date || '未排期'}</Text>
        </View>
        {visit.actual_start_time && (
          <View style={styles.infoRow}>
            <Icon name={VisitIcons.clock} size={14} color={Colors.textHint} />
            <Text style={styles.infoText}>
              {visit.actual_start_time} - {visit.actual_end_time || '进行中'}
            </Text>
          </View>
        )}
      </View>

      {visit.ai_summary && (
        <View style={styles.summary}>
          <Text style={styles.summaryText} numberOfLines={2}>
            {visit.ai_summary.summary}
          </Text>
        </View>
      )}
    </TouchableOpacity>
  );
}

const styles = StyleSheet.create({
  card: {
    backgroundColor: Colors.white,
    borderRadius: BorderRadius.lg,
    padding: Spacing.lg,
    marginBottom: Spacing.md,
    borderLeftWidth: 3,
    borderLeftColor: Colors.primary,
  },
  header: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
    marginBottom: Spacing.sm,
  },
  nameRow: {
    flexDirection: 'row',
    alignItems: 'center',
    flex: 1,
    gap: Spacing.sm,
  },
  hcpName: {
    fontSize: FontSize.lg,
    fontWeight: '600',
    color: Colors.textPrimary,
  },
  priorityBadge: {
    backgroundColor: Colors.dangerLight,
    paddingHorizontal: 6,
    paddingVertical: 2,
    borderRadius: BorderRadius.sm,
  },
  priorityText: {
    fontSize: FontSize.xs,
    color: Colors.danger,
    fontWeight: '600',
  },
  statusBadge: {
    paddingHorizontal: 10,
    paddingVertical: 4,
    borderRadius: BorderRadius.full,
  },
  statusText: {
    fontSize: FontSize.xs,
    fontWeight: '600',
  },
  info: {
    gap: Spacing.xs,
    marginBottom: Spacing.sm,
  },
  infoRow: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: Spacing.xs,
  },
  infoText: {
    fontSize: FontSize.sm,
    color: Colors.textSecondary,
  },
  summary: {
    backgroundColor: Colors.backgroundAlt,
    padding: Spacing.md,
    borderRadius: BorderRadius.md,
    borderLeftWidth: 2,
    borderLeftColor: Colors.accent,
  },
  summaryText: {
    fontSize: FontSize.sm,
    color: Colors.textSecondary,
    lineHeight: 20,
  },
});
