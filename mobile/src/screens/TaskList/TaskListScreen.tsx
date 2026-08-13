/**
 * 我的任务页 - 拜访后续任务（end_visit / follow-up 自动生成 + 手动状态流转）
 * 临床精准风：深海军蓝头部 + 白卡片列表 + 状态筛选 chips
 */
import React, { useEffect, useState, useCallback } from 'react';
import {
  View, Text, StyleSheet, FlatList, TouchableOpacity,
  ActivityIndicator, RefreshControl, Alert,
} from 'react-native';
import { useNavigation } from '@react-navigation/native';
import Icon from '../../components/Icon';
import EmptyState from '../../components/EmptyState';
import { taskAPI, TASK_TYPE_LABELS } from '../../api/tasks';
import type { TaskItem } from '../../api/tasks';
import { Colors, FontSize, Spacing, BorderRadius, Shadow } from '../../constants/theme';
import type { RootStackParamList } from '../../navigation/types';
import type { NativeStackNavigationProp } from '@react-navigation/native-stack';

type Nav = NativeStackNavigationProp<RootStackParamList>;

/** 筛选 chips：全部 / 进行中(open) / 已完成(done) / 已取消(cancelled) */
const FILTERS: { label: string; value: string | undefined }[] = [
  { label: '全部', value: undefined },
  { label: '进行中', value: 'open' },
  { label: '已完成', value: 'done' },
  { label: '已取消', value: 'cancelled' },
];

const STATUS_LABELS: Record<string, { label: string; color: string; bg: string }> = {
  open: { label: '进行中', color: Colors.info, bg: Colors.infoLight },
  done: { label: '已完成', color: Colors.success, bg: Colors.successLight },
  cancelled: { label: '已取消', color: Colors.textHint, bg: Colors.border },
};

export default function TaskListScreen() {
  const navigation = useNavigation<Nav>();
  const [tasks, setTasks] = useState<TaskItem[]>([]);
  const [filter, setFilter] = useState<string | undefined>(undefined);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [error, setError] = useState('');

  const loadTasks = useCallback(async () => {
    try {
      const result = await taskAPI.list({ page: 1, page_size: 100, status: filter });
      setTasks(result.items || []);
      setError('');
    } catch (e: any) {
      setError(e?.message || '任务加载失败，请检查网络');
    } finally {
      setLoading(false);
    }
  }, [filter]);

  useEffect(() => {
    setLoading(true);
    loadTasks();
  }, [loadTasks]);

  const onRefresh = async () => {
    setRefreshing(true);
    await loadTasks();
    setRefreshing(false);
  };

  /** 状态流转：完成 / 取消 / 重开 —— 改完刷新列表 */
  const changeStatus = async (task: TaskItem, status: 'done' | 'cancelled' | 'open') => {
    try {
      await taskAPI.updateStatus(task.id, status);
      await loadTasks();
    } catch (e: any) {
      Alert.alert('操作失败', e?.message || '请稍后重试');
    }
  };

  const confirmAction = (task: TaskItem, status: 'done' | 'cancelled', verb: string) => {
    Alert.alert(verb, `确认「${task.title}」${verb}？`, [
      { text: '取消', style: 'cancel' },
      { text: '确认', onPress: () => changeStatus(task, status) },
    ]);
  };

  const renderTask = ({ item }: { item: TaskItem }) => {
    const st = STATUS_LABELS[item.status] || STATUS_LABELS.open;
    return (
      <View style={[styles.card, Shadow.card]}>
        <View style={styles.cardHead}>
          <View style={styles.typeBadge}>
            <Text style={styles.typeText}>{TASK_TYPE_LABELS[item.task_type] || item.task_type || '任务'}</Text>
          </View>
          <View style={[styles.statusBadge, { backgroundColor: st.bg }]}>
            <Text style={[styles.statusText, { color: st.color }]}>{st.label}</Text>
          </View>
        </View>
        <Text style={styles.taskTitle}>{item.title}</Text>
        {item.description ? (
          <Text style={styles.taskDesc} numberOfLines={2}>{item.description}</Text>
        ) : null}
        <View style={styles.cardMeta}>
          {item.due_date ? (
            <View style={styles.metaRow}>
              <Icon name="calendar-outline" size={12} color={Colors.textHint} />
              <Text style={styles.metaText}>截止 {item.due_date}</Text>
            </View>
          ) : null}
          {item.channel ? (
            <View style={styles.metaRow}>
              <Icon name="phone-outline" size={12} color={Colors.textHint} />
              <Text style={styles.metaText}>{item.channel}</Text>
            </View>
          ) : null}
        </View>

        {/* 操作：进行中 → 完成/取消；已完成/已取消 → 重开 */}
        {item.status === 'open' && (
          <View style={styles.actions}>
            <TouchableOpacity
              style={[styles.actionBtn, styles.doneBtn]}
              onPress={() => confirmAction(item, 'done', '完成任务')}
              activeOpacity={0.8}
            >
              <Icon name="check" size={14} color={Colors.textWhite} />
              <Text style={styles.doneBtnText}>完成</Text>
            </TouchableOpacity>
            <TouchableOpacity
              style={[styles.actionBtn, styles.cancelBtn]}
              onPress={() => confirmAction(item, 'cancelled', '取消任务')}
              activeOpacity={0.8}
            >
              <Text style={styles.cancelBtnText}>取消</Text>
            </TouchableOpacity>
          </View>
        )}
        {item.status !== 'open' && (
          <TouchableOpacity style={styles.reopenBtn} onPress={() => changeStatus(item, 'open')} activeOpacity={0.8}>
            <Text style={styles.reopenText}>重开任务</Text>
          </TouchableOpacity>
        )}
      </View>
    );
  };

  return (
    <View style={styles.container}>
      <View style={styles.header}>
        <TouchableOpacity onPress={() => navigation.goBack()} style={styles.headerBtn}>
          <Icon name="chevron-left" size={22} color={Colors.textWhite} />
        </TouchableOpacity>
        <Text style={styles.headerTitle}>我的任务</Text>
        <View style={{ width: 24 }} />
      </View>

      <View style={styles.filterBar}>
        {FILTERS.map((f) => (
          <TouchableOpacity
            key={f.label}
            style={[styles.filterChip, filter === f.value && styles.filterChipActive]}
            onPress={() => setFilter(f.value)}
          >
            <Text style={[styles.filterText, filter === f.value && styles.filterTextActive]}>{f.label}</Text>
          </TouchableOpacity>
        ))}
      </View>

      {loading ? (
        <View style={styles.centered}>
          <ActivityIndicator size="large" color={Colors.primary} />
        </View>
      ) : error && tasks.length === 0 ? (
        <View style={styles.centered}>
          <Text style={styles.errorText}>{error}</Text>
          <TouchableOpacity style={styles.retryBtn} onPress={loadTasks} activeOpacity={0.8}>
            <Text style={styles.retryText}>重试</Text>
          </TouchableOpacity>
        </View>
      ) : (
        <FlatList
          data={tasks}
          renderItem={renderTask}
          keyExtractor={(item) => String(item.id)}
          contentContainerStyle={[styles.list, tasks.length === 0 && styles.listEmpty]}
          showsVerticalScrollIndicator={false}
          refreshControl={
            <RefreshControl refreshing={refreshing} onRefresh={onRefresh} tintColor={Colors.primary} colors={[Colors.primary]} />
          }
          ListEmptyComponent={
            <EmptyState icon="clipboard-check-outline" title="暂无任务" description="结束拜访后会自动生成跟进任务" />
          }
        />
      )}
    </View>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1, backgroundColor: Colors.background },
  centered: { flex: 1, justifyContent: 'center', alignItems: 'center' },
  errorText: {
    fontSize: FontSize.md, color: Colors.danger,
    marginBottom: Spacing.lg, paddingHorizontal: Spacing.xl, textAlign: 'center',
  },
  retryBtn: {
    backgroundColor: Colors.primary, borderRadius: BorderRadius.md,
    paddingHorizontal: Spacing.xl, paddingVertical: Spacing.sm,
  },
  retryText: { color: Colors.textWhite, fontSize: FontSize.md, fontWeight: '600' },
  header: {
    backgroundColor: Colors.primary, paddingTop: 50, paddingBottom: 14,
    paddingHorizontal: Spacing.lg, flexDirection: 'row',
    alignItems: 'center', justifyContent: 'space-between', ...Shadow.header,
  },
  headerBtn: { padding: 4 },
  headerTitle: { color: Colors.textWhite, fontSize: FontSize.lg, fontWeight: '600' },
  filterBar: {
    flexDirection: 'row', padding: Spacing.lg, gap: Spacing.sm,
    backgroundColor: Colors.white, borderBottomWidth: 1, borderBottomColor: Colors.divider,
  },
  filterChip: {
    paddingHorizontal: Spacing.lg, paddingVertical: Spacing.sm,
    borderRadius: BorderRadius.full, backgroundColor: Colors.background,
  },
  filterChipActive: { backgroundColor: Colors.primary },
  filterText: { fontSize: FontSize.sm, color: Colors.textSecondary },
  filterTextActive: { color: Colors.textWhite, fontWeight: '600' },
  list: { padding: Spacing.lg },
  listEmpty: { flexGrow: 1, justifyContent: 'center' },
  card: {
    backgroundColor: Colors.white, borderRadius: BorderRadius.xl,
    padding: Spacing.lg, marginBottom: Spacing.md,
  },
  cardHead: { flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center', marginBottom: Spacing.sm },
  typeBadge: {
    backgroundColor: Colors.primarySurface, paddingHorizontal: 8,
    paddingVertical: 2, borderRadius: BorderRadius.sm,
  },
  typeText: { fontSize: 10, color: Colors.primary, fontWeight: '600' },
  statusBadge: { paddingHorizontal: 10, paddingVertical: 3, borderRadius: BorderRadius.full },
  statusText: { fontSize: 10, fontWeight: '600' },
  taskTitle: { fontSize: FontSize.md, color: Colors.textPrimary, fontWeight: '600', lineHeight: 22 },
  taskDesc: { fontSize: FontSize.sm, color: Colors.textSecondary, marginTop: 4, lineHeight: 20 },
  cardMeta: {
    flexDirection: 'row', gap: Spacing.lg, marginTop: Spacing.md,
  },
  metaRow: { flexDirection: 'row', alignItems: 'center', gap: 4 },
  metaText: { fontSize: 11, color: Colors.textHint },
  actions: { flexDirection: 'row', gap: Spacing.md, marginTop: Spacing.md },
  actionBtn: {
    flex: 1, flexDirection: 'row', alignItems: 'center', justifyContent: 'center',
    gap: 4, paddingVertical: 10, borderRadius: BorderRadius.lg,
  },
  doneBtn: { backgroundColor: Colors.success },
  doneBtnText: { color: Colors.textWhite, fontSize: FontSize.sm, fontWeight: '600' },
  cancelBtn: { backgroundColor: Colors.white, borderWidth: 1, borderColor: Colors.border },
  cancelBtnText: { color: Colors.textSecondary, fontSize: FontSize.sm, fontWeight: '600' },
  reopenBtn: {
    marginTop: Spacing.md, paddingVertical: 10, borderRadius: BorderRadius.lg,
    alignItems: 'center', borderWidth: 1, borderColor: Colors.primary,
  },
  reopenText: { color: Colors.primary, fontSize: FontSize.sm, fontWeight: '600' },
});
