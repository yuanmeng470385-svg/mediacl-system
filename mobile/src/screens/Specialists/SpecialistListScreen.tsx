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
import { specialistAPI } from '../../api/specialist';
import { Colors, FontSize, Spacing, BorderRadius, Shadow } from '../../constants/theme';
import type { DigitalSpecialist } from '../../types';
import type { RootStackParamList } from '../../navigation/types';

type Nav = NativeStackNavigationProp<RootStackParamList>;

const avatarColors = ['#3b82f6', '#8b5cf6', '#ec4899', '#f59e0b', '#22c55e'];

export default function SpecialistListScreen() {
  const navigation = useNavigation<Nav>();
  const [specialists, setSpecialists] = useState<DigitalSpecialist[]>([]);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);

  const loadSpecialists = useCallback(async () => {
    try {
      const result = await specialistAPI.list({ page_size: 50 });
      setSpecialists(result.items || []);
    } catch {
      // 后端不可用——展示示例数据
      setSpecialists([
        {
          id: 1,
          name: '肿瘤产品专员-小K',
          product_id: 1,
          product_name: '肿瘤产品线',
          persona: '专业、严谨的肿瘤学顾问',
          knowledge_scope: '肺癌、乳腺癌、结直肠癌',
          compliance_level: 'high',
          prompt_version: 'v1.0',
          status: 'configuring',
        },
      ]);
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
        disabled={item.status === 'configuring'}
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
            <View
              style={[
                styles.statusBadge,
                {
                  backgroundColor:
                    item.status === 'active'
                      ? '#dcfce7'
                      : item.status === 'configuring'
                      ? '#fef3c7'
                      : '#f3f4f6',
                },
              ]}
            >
              <Text
                style={[
                  styles.statusText,
                  {
                    color:
                      item.status === 'active'
                        ? Colors.success
                        : item.status === 'configuring'
                        ? Colors.warning
                        : Colors.textHint,
                  },
                ]}
              >
                {item.status === 'active'
                  ? '可用'
                  : item.status === 'configuring'
                  ? '配置中'
                  : '已停用'}
              </Text>
            </View>
          </View>
          <Text style={styles.product}>{item.product_name || item.knowledge_scope}</Text>
          <Text style={styles.persona} numberOfLines={2}>
            {item.persona}
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
              {isActive ? '开始对话' : '待配置'}
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
            icon="🤖"
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
