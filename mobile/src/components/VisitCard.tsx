/**
 * 拜访卡片组件 - 展示单条拜访记录
 */
import React from 'react';
import { View, Text, StyleSheet, TouchableOpacity } from 'react-native';
import { Colors, FontSize, BorderRadius, Shadow, Spacing } from '../constants/theme';
import type { VisitRecord } from '../types';

interface VisitCardProps {
  visit: VisitRecord;
  onPress?: () => void;
}

const statusConfig: Record<string, { label: string; color: string; bg: string }> = {
  pending: { label: '待开始', color: '#f59e0b', bg: '#fef3c7' },
  in_progress: { label: '进行中', color: '#3b82f6', bg: '#dbeafe' },
  completed: { label: '已完成', color: '#22c55e', bg: '#dcfce7' },
  cancelled: { label: '已取消', color: '#6b7280', bg: '#f3f4f6' },
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
          <Text style={styles.hcpName}>{visit.hcp_name || '未知医生'}</Text>
          {visit.status === 'pending' && (
            <Text style={styles.priority}>高优</Text>
          )}
        </View>
        <View style={[styles.statusBadge, { backgroundColor: status.bg }]}>
          <Text style={[styles.statusText, { color: status.color }]}>
            {status.label}
          </Text>
        </View>
      </View>

      <View style={styles.info}>
        <Text style={styles.infoText}>
          📅 {visit.planned_date || '未排期'}
        </Text>
        {visit.actual_start_time && (
          <Text style={styles.infoText}>
            ⏱ {visit.actual_start_time} - {visit.actual_end_time || '进行中'}
          </Text>
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
  },
  hcpName: {
    fontSize: FontSize.lg,
    fontWeight: '600',
    color: Colors.textPrimary,
  },
  priority: {
    fontSize: FontSize.xs,
    color: Colors.danger,
    backgroundColor: '#fee2e2',
    paddingHorizontal: 6,
    paddingVertical: 2,
    borderRadius: BorderRadius.sm,
    marginLeft: Spacing.sm,
    overflow: 'hidden',
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
    flexDirection: 'row',
    gap: Spacing.lg,
    marginBottom: Spacing.sm,
  },
  infoText: {
    fontSize: FontSize.sm,
    color: Colors.textSecondary,
  },
  summary: {
    backgroundColor: Colors.background,
    padding: Spacing.md,
    borderRadius: BorderRadius.md,
  },
  summaryText: {
    fontSize: FontSize.sm,
    color: Colors.textSecondary,
    lineHeight: 20,
  },
});
