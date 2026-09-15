/**
 * 我的分身（2026-09-15 自 TwinManageScreen 拆出）：
 * 分身列表（风格三选 + 暂停/启用 + 删除）。删除为软删（后端 status=disabled，
 * 对话/审计历史留存），列表过滤 disabled——删除后即从代表侧"消失"。
 */
import React, { useCallback, useEffect, useState } from 'react';
import {
  Alert, ScrollView, StyleSheet, Text, TouchableOpacity, View,
} from 'react-native';
import { useNavigation } from '@react-navigation/native';
import type { NativeStackNavigationProp } from '@react-navigation/native-stack';
import Icon from '../../components/Icon';
import { specialistAPI } from '../../api/specialist';
import { twinAPI } from '../../api/practice';
import { useAuth } from '../../store/AuthContext';
import type { RootStackParamList } from '../../navigation/types';
import { BorderRadius, Colors, FontSize, Shadow, Spacing } from '../../constants/theme';

type Nav = NativeStackNavigationProp<RootStackParamList>;

interface TwinStyle {
  formal_level?: string;
  reply_length?: string;
  opening_mode?: string;
}

interface Twin {
  id: number;
  name?: string;
  status?: string;
  representative_id?: number;
  persona?: { style?: TwinStyle } | null;
}

const FORMAL_OPTIONS = ['非常严谨', '标准学术', '略带亲和力'];
const LENGTH_OPTIONS = ['简洁', '标准', '详尽'];
const OPENING_OPTIONS = ['直切主题', '先寒暄再进入'];

export default function MyTwinsScreen() {
  const navigation = useNavigation<Nav>();
  const { user } = useAuth();
  const [twins, setTwins] = useState<Twin[]>([]);
  const [loaded, setLoaded] = useState(false);
  const [busyId, setBusyId] = useState<number | null>(null);

  const loadTwins = useCallback(async () => {
    setLoaded(false);
    try {
      const all: any[] = await specialistAPI.list();
      // disabled = 已删除（软删），代表侧不可见
      const mine: Twin[] = all.filter(
        (s) => s.representative_id === user?.id && s.status !== 'disabled',
      );
      setTwins(mine);
    } catch {
      // 保留空列表
    } finally {
      setLoaded(true);
    }
  }, [user?.id]);

  useEffect(() => {
    loadTwins();
  }, [loadTwins]);

  // 从「创建分身」向导返回时刷新（新分身要出现）
  useEffect(() => {
    const unsub = navigation.addListener('focus', loadTwins);
    return unsub;
  }, [navigation, loadTwins]);

  const togglePause = async (twin: Twin) => {
    setBusyId(twin.id);
    try {
      if (twin.status === 'paused') {
        await twinAPI.resume(twin.id);
      } else {
        await twinAPI.pause(twin.id);
      }
      await loadTwins();
    } catch (err: any) {
      Alert.alert('操作失败', err?.message || '请稍后重试');
    } finally {
      setBusyId(null);
    }
  };

  const confirmDelete = (twin: Twin) => {
    Alert.alert(
      '删除分身',
      `确定删除「${twin.name || `分身 #${twin.id}`}」吗？删除后医生将无法再与其对话，历史记录将依规留存。`,
      [
        { text: '取消', style: 'cancel' },
        {
          text: '删除',
          style: 'destructive',
          onPress: async () => {
            setBusyId(twin.id);
            try {
              await twinAPI.delete(twin.id);
              await loadTwins();
            } catch (err: any) {
              Alert.alert('删除失败', err?.message || '请稍后重试');
            } finally {
              setBusyId(null);
            }
          },
        },
      ],
    );
  };

  const saveStyle = async (twin: Twin, style: TwinStyle) => {
    if (!style.formal_level && !style.reply_length && !style.opening_mode) return;
    setBusyId(twin.id);
    try {
      await twinAPI.setStyle(twin.id, style as Record<string, string>);
      await loadTwins();
    } catch (err: any) {
      Alert.alert('保存失败', err?.message || '请稍后重试');
    } finally {
      setBusyId(null);
    }
  };

  return (
    <View style={styles.container}>
      <View style={styles.header}>
        <TouchableOpacity onPress={() => navigation.goBack()}>
          <Icon name="chevron-left" size={22} color={Colors.textWhite} />
        </TouchableOpacity>
        <Text style={styles.headerTitle}>我的分身</Text>
        <TouchableOpacity
          onPress={() => navigation.navigate('CreateTwin')}
          hitSlop={{ top: 8, bottom: 8, left: 8, right: 8 }}
        >
          <Icon name="plus" size={24} color={Colors.textWhite} />
        </TouchableOpacity>
      </View>

      <ScrollView contentContainerStyle={styles.content}>
        <View style={[styles.card, Shadow.card]}>
          {!loaded ? (
            <Text style={styles.emptyText}>加载中…</Text>
          ) : twins.length === 0 ? (
            <View style={styles.emptyWrap}>
              <Text style={styles.emptyText}>暂无分身</Text>
              <TouchableOpacity
                style={styles.createBtn}
                activeOpacity={0.7}
                onPress={() => navigation.navigate('CreateTwin')}
              >
                <Icon name="account-tie-outline" size={16} color={Colors.textWhite} />
                <Text style={styles.createText}>去创建第一个分身</Text>
              </TouchableOpacity>
            </View>
          ) : (
            twins.map((twin) => (
              <View key={twin.id} style={styles.twinCard}>
                <View style={styles.twinTop}>
                  <View style={styles.iconBox}>
                    <Icon name="robot-outline" size={18} color={Colors.primary} />
                  </View>
                  <Text style={styles.twinName} numberOfLines={1}>{twin.name || `分身 #${twin.id}`}</Text>
                  <View style={[styles.statusPill, twin.status === 'active' ? styles.pillActive : styles.pillPaused]}>
                    <Text style={[styles.statusText, twin.status === 'active' ? styles.statusTextActive : styles.statusTextPaused]}>
                      {twin.status === 'active' ? '工作中' : twin.status === 'paused' ? '已暂停' : twin.status || '草稿'}
                    </Text>
                  </View>
                </View>

                <StylePicker
                  label="正式程度"
                  options={FORMAL_OPTIONS}
                  value={twin.persona?.style?.formal_level}
                  onChange={(v) => saveStyle(twin, { formal_level: v })}
                />
                <StylePicker
                  label="回复长度"
                  options={LENGTH_OPTIONS}
                  value={twin.persona?.style?.reply_length}
                  onChange={(v) => saveStyle(twin, { reply_length: v })}
                />
                <StylePicker
                  label="开场方式"
                  options={OPENING_OPTIONS}
                  value={twin.persona?.style?.opening_mode}
                  onChange={(v) => saveStyle(twin, { opening_mode: v })}
                />

                <View style={styles.actionRow}>
                  <TouchableOpacity
                    style={[styles.toggleBtn, twin.status === 'paused' && styles.toggleBtnResume]}
                    disabled={busyId === twin.id}
                    onPress={() => togglePause(twin)}
                    activeOpacity={0.7}
                  >
                    <Icon
                      name={twin.status === 'paused' ? 'play' : 'pause'}
                      size={16}
                      color={twin.status === 'paused' ? Colors.success : Colors.warning}
                    />
                    <Text style={[styles.toggleText, twin.status === 'paused' && { color: Colors.success }]}>
                      {busyId === twin.id ? '处理中…' : twin.status === 'paused' ? '启用' : '暂停'}
                    </Text>
                  </TouchableOpacity>
                  <TouchableOpacity
                    style={styles.deleteBtn}
                    disabled={busyId === twin.id}
                    onPress={() => confirmDelete(twin)}
                    activeOpacity={0.7}
                  >
                    <Icon name="trash-outline" size={16} color={Colors.danger} />
                    <Text style={styles.deleteText}>删除</Text>
                  </TouchableOpacity>
                </View>
              </View>
            ))
          )}
        </View>
      </ScrollView>
    </View>
  );
}

function StylePicker({ label, options, value, onChange }: {
  label: string; options: string[]; value?: string; onChange: (v: string) => void;
}) {
  return (
    <View style={styles.picker}>
      <Text style={styles.pickerLabel}>{label}</Text>
      <View style={styles.chipWrap}>
        {options.map((opt) => {
          const active = value === opt;
          return (
            <TouchableOpacity
              key={opt}
              style={[styles.chip, active && styles.chipActive]}
              onPress={() => onChange(opt)}
              activeOpacity={0.7}
            >
              <Text style={[styles.chipText, active && styles.chipTextActive]}>{opt}</Text>
            </TouchableOpacity>
          );
        })}
      </View>
    </View>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1, backgroundColor: Colors.background },
  header: {
    backgroundColor: Colors.primary, paddingTop: 50, paddingBottom: 14,
    paddingHorizontal: Spacing.lg, flexDirection: 'row',
    alignItems: 'center', justifyContent: 'space-between', ...Shadow.header,
  },
  headerTitle: { color: Colors.textWhite, fontSize: FontSize.lg, fontWeight: '600' },
  content: { padding: Spacing.md },
  card: { backgroundColor: Colors.card, borderRadius: BorderRadius.md, padding: Spacing.lg, marginBottom: Spacing.md },
  emptyWrap: { alignItems: 'center', paddingVertical: Spacing.lg },
  emptyText: { fontSize: FontSize.sm, color: Colors.textHint, textAlign: 'center', paddingVertical: Spacing.sm },
  createBtn: {
    marginTop: Spacing.sm, backgroundColor: Colors.primary, borderRadius: BorderRadius.sm,
    paddingHorizontal: Spacing.lg, paddingVertical: Spacing.sm,
    flexDirection: 'row', alignItems: 'center', gap: Spacing.sm,
  },
  createText: { color: Colors.textWhite, fontSize: FontSize.sm, fontWeight: '600' },
  twinCard: { borderWidth: 1, borderColor: Colors.divider, borderRadius: BorderRadius.md, padding: Spacing.md, marginBottom: Spacing.md },
  twinTop: { flexDirection: 'row', alignItems: 'center', gap: Spacing.sm, marginBottom: Spacing.sm },
  iconBox: {
    width: 36, height: 36, borderRadius: 10,
    backgroundColor: Colors.primarySurface, alignItems: 'center', justifyContent: 'center',
  },
  twinName: { flex: 1, fontSize: FontSize.md, fontWeight: '600', color: Colors.textPrimary },
  statusPill: { borderRadius: BorderRadius.full, paddingHorizontal: Spacing.sm, paddingVertical: 2 },
  pillActive: { backgroundColor: Colors.successLight },
  pillPaused: { backgroundColor: Colors.warningLight },
  statusText: { fontSize: FontSize.xs, fontWeight: '600' },
  statusTextActive: { color: Colors.success },
  statusTextPaused: { color: Colors.warning },
  picker: { marginBottom: Spacing.sm },
  pickerLabel: { fontSize: FontSize.xs, color: Colors.textSecondary, marginBottom: Spacing.xs },
  chipWrap: { flexDirection: 'row', flexWrap: 'wrap', gap: Spacing.sm },
  chip: {
    paddingHorizontal: Spacing.md, paddingVertical: Spacing.xs,
    borderRadius: BorderRadius.full, borderWidth: 1, borderColor: Colors.border,
    backgroundColor: Colors.white,
  },
  chipActive: { backgroundColor: Colors.primarySurface, borderColor: Colors.primary },
  chipText: { fontSize: FontSize.sm, color: Colors.textSecondary },
  chipTextActive: { color: Colors.primary, fontWeight: '600' },
  actionRow: { flexDirection: 'row', gap: Spacing.sm, marginTop: Spacing.sm },
  toggleBtn: {
    flex: 1, flexDirection: 'row', alignItems: 'center', justifyContent: 'center',
    gap: Spacing.sm, borderWidth: 1, borderColor: Colors.warning,
    borderRadius: BorderRadius.sm, padding: Spacing.sm,
  },
  toggleBtnResume: { borderColor: Colors.success },
  toggleText: { color: Colors.warning, fontSize: FontSize.sm, fontWeight: '600' },
  deleteBtn: {
    flex: 1, flexDirection: 'row', alignItems: 'center', justifyContent: 'center',
    gap: Spacing.sm, borderWidth: 1, borderColor: Colors.danger,
    borderRadius: BorderRadius.sm, padding: Spacing.sm,
  },
  deleteText: { color: Colors.danger, fontSize: FontSize.sm, fontWeight: '600' },
});
