/**
 * 数字专员列表页
 */
import React, { useEffect, useState, useCallback } from 'react';
import {
  View,
  Text,
  StyleSheet,
  FlatList,
  TouchableOpacity,
  RefreshControl,
  ActivityIndicator,
} from 'react-native';
import { useNavigation } from '@react-navigation/native';
import type { NativeStackNavigationProp } from '@react-navigation/native-stack';
import EmptyState from '../../components/EmptyState';
import Icon from '../../components/Icon';
import { ActionIcons } from '../../components/Icon';
import { specialistAPI } from '../../api/specialist';
import { Colors, FontSize, Spacing, BorderRadius, Shadow } from '../../constants/theme';
import type { DigitalSpecialist } from '../../types';
import type { RootStackParamList } from '../../navigation/types';

type Nav = NativeStackNavigationProp<RootStackParamList>;

const avatarColors = ['#0D3B66', '#1565C0', '#00ACC1', '#2E7D32', '#C62828'];

/** 状态 → 展示文案/样式（后端枚举 draft/active/disabled，见 types） */
const STATUS_CONFIG: Record<string, { label: string; bg: string; color: string }> = {
  active: { label: '正常', bg: '#dcfce7', color: Colors.success },
  draft: { label: '草稿', bg: '#fef3c7', color: Colors.warning },
  disabled: { label: '已停用', bg: '#f3f4f6', color: Colors.textHint },
};
const STATUS_FALLBACK = { label: '已停用', bg: '#f3f4f6', color: Colors.textHint };

export default function SpecialistListScreen() {
  const navigation = useNavigation<Nav>();
  const [specialists, setSpecialists] = useState<DigitalSpecialist[]>([]);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [error, setError] = useState('');

  const loadSpecialists = useCallback(async () => {
    setError('');
    try {
      const result = await specialistAPI.list({ page_size: 50 });
      setSpecialists(result || []);
    } catch (e: any) {
      // 真实失败显示错误态 + 重试，不用写死的假专员兜底
      setError(e?.message || '专员列表加载失败，请检查网络');
      setSpecialists([]);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    loadSpecialists();
  }, [loadSpecialists]);

  const onRefresh = async () => {
    setRefreshing(true);
    await loadSpecialists();
    setRefreshing(false);
  };

  const getAvatarColor = (id: number) =>
    avatarColors[id % avatarColors.length];

  const renderItem = ({ item }: { item: DigitalSpecialist }) => {
    const initials = item.name.slice(0, 2);
    const isActive = item.status === 'active';
    const status = STATUS_CONFIG[item.status] || STATUS_FALLBACK;

    return (
      <TouchableOpacity
        style={[styles.card, Shadow.card]}
        onPress={() =>
          navigation.navigate('Chat', {
            specialistId: item.id,
            specialistName: item.name,
          })
        }
        activeOpacity={0.7}
        disabled={!isActive}
      >
        {/* 头像 */}
        <View
          style={[
            styles.avatar,
            { backgroundColor: getAvatarColor(item.id) },
          ]}
        >
          <Text style={styles.avatarText}>{initials}</Text>
          {isActive && <View style={styles.onlineDot} />}
        </View>

        {/* 信息 */}
        <View style={styles.info}>
          <View style={styles.nameRow}>
            <Text style={styles.name}>{item.name}</Text>
            <View style={[styles.statusBadge, { backgroundColor: status.bg }]}>
              <Text style={[styles.statusText, { color: status.color }]}>
                {status.label}
              </Text>
            </View>
          </View>
          <Text style={styles.product}>{item.product_name || item.knowledge_scope}</Text>
          <Text style={styles.persona} numberOfLines={2}>
            {/* persona 两形态并存：历史数据是 string，二期 H style-test/style
                设置写入 {style:{...}} 对象 —— 对象直接进 Text 会红屏
                （Objects are not valid as a React child），此处仅展示字符串形态 */}
            {typeof item.persona === 'string' ? item.persona : ''}
          </Text>
          {/* 对话入口 */}
          <TouchableOpacity
            style={[
              styles.chatBtn,
              !isActive && styles.chatBtnDisabled,
            ]}
            onPress={() =>
              isActive &&
              navigation.navigate('Chat', {
                specialistId: item.id,
                specialistName: item.name,
              })
            }
            activeOpacity={0.7}
            disabled={!isActive}
          >
            <Text style={styles.chatBtnText}>
              {isActive ? '开始对话' : item.status === 'draft' ? '待配置' : '已停用'}
            </Text>
          </TouchableOpacity>
        </View>
      </TouchableOpacity>
    );
  };

  if (loading) {
    return (
      <View style={styles.centered}>
        <ActivityIndicator size="large" color={Colors.primary} />
        <Text style={styles.loadingText}>加载专员列表...</Text>
      </View>
    );
  }

  if (error && specialists.length === 0) {
    return (
      <View style={styles.centered}>
        <Text style={styles.errorText}>{error}</Text>
        <TouchableOpacity
          style={styles.retryBtn}
          onPress={loadSpecialists}
          activeOpacity={0.8}
        >
          <Text style={styles.retryText}>重试</Text>
        </TouchableOpacity>
      </View>
    );
  }

  return (
    <View style={styles.container}>
      <View style={styles.header}>
        <Text style={styles.headerTitle}>数字专员</Text>
        <Text style={styles.headerSubtitle}>
          选择专员开始专业对话
        </Text>
      </View>
      <FlatList
        data={specialists}
        renderItem={renderItem}
        keyExtractor={(item) => item.id.toString()}
        contentContainerStyle={styles.list}
        refreshControl={
          <RefreshControl
            refreshing={refreshing}
            onRefresh={onRefresh}
            colors={[Colors.primary]}
          />
        }
        ListEmptyComponent={
          <EmptyState
            icon="robot-outline"
            title="暂无数字专员"
            description="请联系管理员在百炼控制台创建数字专员 App"
          />
        }
      />
    </View>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1, backgroundColor: Colors.background },
  centered: { flex: 1, justifyContent: 'center', alignItems: 'center' },
  loadingText: { marginTop: Spacing.md, color: Colors.textHint, fontSize: FontSize.sm },
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
    backgroundColor: Colors.primary,
    paddingHorizontal: Spacing.xl,
    paddingTop: 52,
    paddingBottom: Spacing.xl,
  },
  headerTitle: { color: Colors.textWhite, fontSize: FontSize.xl, fontWeight: '700' },
  headerSubtitle: { color: 'rgba(255,255,255,0.7)', fontSize: FontSize.sm, marginTop: 4 },
  list: { padding: Spacing.lg },
  card: {
    backgroundColor: Colors.white,
    borderRadius: BorderRadius.lg,
    padding: Spacing.lg,
    marginBottom: Spacing.md,
    flexDirection: 'row',
    gap: Spacing.lg,
  },
  avatar: {
    width: 56,
    height: 56,
    borderRadius: 28,
    alignItems: 'center',
    justifyContent: 'center',
  },
  avatarText: { color: Colors.textWhite, fontSize: FontSize.lg, fontWeight: '700' },
  onlineDot: {
    position: 'absolute',
    bottom: 2,
    right: 2,
    width: 12,
    height: 12,
    borderRadius: 6,
    backgroundColor: Colors.success,
    borderWidth: 2,
    borderColor: Colors.white,
  },
  info: { flex: 1, gap: 4 },
  nameRow: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
  },
  name: { fontSize: FontSize.lg, fontWeight: '600', color: Colors.textPrimary },
  statusBadge: {
    paddingHorizontal: 8,
    paddingVertical: 2,
    borderRadius: BorderRadius.full,
  },
  statusText: { fontSize: FontSize.xs, fontWeight: '600' },
  product: { fontSize: FontSize.sm, color: Colors.textSecondary },
  persona: { fontSize: FontSize.xs, color: Colors.textHint, lineHeight: 18 },
  chatBtn: {
    backgroundColor: Colors.primary,
    borderRadius: BorderRadius.full,
    paddingVertical: 8,
    paddingHorizontal: Spacing.xl,
    alignSelf: 'flex-start',
    marginTop: Spacing.sm,
  },
  chatBtnDisabled: { backgroundColor: Colors.border },
  chatBtnText: { color: Colors.textWhite, fontSize: FontSize.sm, fontWeight: '600' },
});
