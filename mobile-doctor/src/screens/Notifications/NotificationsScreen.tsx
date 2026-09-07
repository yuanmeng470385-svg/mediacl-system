/**
 * 站内通知中心 —— 医生端（2026-09-07 A-1：此前通知只写不读，代表推送新卡片无提醒入口，
 * 只能主动开收件箱）。照代表端 NotificationsScreen 精简移植：医生端主要收 card_new。
 */
import React, { useCallback, useEffect, useState } from 'react';
import {
  View, Text, StyleSheet, FlatList, TouchableOpacity,
  ActivityIndicator, RefreshControl, Alert,
} from 'react-native';
import { useNavigation } from '@react-navigation/native';
import type { NativeStackNavigationProp } from '@react-navigation/native-stack';
import Icon from '../../components/Icon';
import { inboxAPI, AppNotification } from '../../api/inbox';
import { Colors, FontSize, Spacing, BorderRadius, Shadow } from '../../constants/theme';
import type { RootStackParamList } from '../../navigation/types';

/** ISO 时间 → 本地可读串（YYYY-MM-DD HH:mm；解析失败返回原串） */
function formatTime(iso: string | null): string {
  if (!iso) return '';
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return iso;
  const p = (n: number) => String(n).padStart(2, '0');
  return `${d.getFullYear()}-${p(d.getMonth() + 1)}-${p(d.getDate())} ${p(d.getHours())}:${p(d.getMinutes())}`;
}

type Nav = NativeStackNavigationProp<RootStackParamList>;

/** 通知类型 → 图标/配色（医生端主要收 card_new，其余类型走兜底图标） */
const TYPE_CONFIG: Record<string, { icon: string; color: string; bg: string }> = {
  card_new: { icon: 'card-text-outline', color: Colors.info, bg: Colors.infoLight },
};

/** 后端 link → 医生端路由（/briefings 等代表端路径医生端不跳） */
function routeForLink(link: string | null): keyof RootStackParamList | null {
  if (link === '/card-pushes') return 'Inbox';
  return null;
}

export default function NotificationsScreen() {
  const navigation = useNavigation<Nav>();
  const [items, setItems] = useState<AppNotification[]>([]);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [marking, setMarking] = useState(false);
  const [error, setError] = useState('');

  const load = useCallback(async () => {
    try {
      const res = await inboxAPI.notifications(1, 50);
      setItems(Array.isArray(res?.items) ? res.items : []);
      setError('');
    } catch (e: any) {
      setError(e?.message || '通知加载失败，请检查网络');
    } finally {
      setLoading(false);
      setRefreshing(false);
    }
  }, []);

  useEffect(() => { load(); }, [load]);

  const handleItemPress = async (n: AppNotification) => {
    // 点开即读（后端幂等：已读再标不报错）
    if (!n.isRead) {
      try {
        await inboxAPI.markRead(n.id);
        setItems((prev) => prev.map((x) => (x.id === n.id ? { ...x, isRead: true } : x)));
      } catch { /* 已读失败不阻塞跳转 */ }
    }
    const route = routeForLink(n.link);
    if (route) navigation.navigate(route as never);
  };

  const handleMarkAll = async () => {
    setMarking(true);
    try {
      await inboxAPI.markRead(undefined, true);
      setItems((prev) => prev.map((x) => ({ ...x, isRead: true })));
    } catch (e: any) {
      Alert.alert('操作失败', e?.message || '请稍后重试');
    } finally {
      setMarking(false);
    }
  };

  const unread = items.filter((x) => !x.isRead).length;

  const renderItem = ({ item }: { item: AppNotification }) => {
    const cfg = TYPE_CONFIG[item.type] || { icon: 'bell-outline', color: Colors.primary, bg: Colors.primarySurface };
    return (
      <TouchableOpacity style={styles.card} activeOpacity={0.7} onPress={() => handleItemPress(item)}>
        <View style={[styles.iconWrap, { backgroundColor: cfg.bg }]}>
          <Icon name={cfg.icon} size={22} color={cfg.color} />
        </View>
        <View style={styles.body}>
          <View style={styles.titleRow}>
            {!item.isRead && <View style={styles.unreadDot} />}
            <Text style={styles.title} numberOfLines={1}>{item.title}</Text>
          </View>
          {!!item.content && (
            <Text style={styles.content} numberOfLines={2}>{item.content}</Text>
          )}
          <Text style={styles.time}>{formatTime(item.createdAt)}</Text>
        </View>
        {routeForLink(item.link) && (
          <Icon name="chevron-right" size={20} color={Colors.textHint} />
        )}
      </TouchableOpacity>
    );
  };

  if (loading) {
    return <View style={styles.center}><ActivityIndicator size="large" color={Colors.primary} /></View>;
  }

  return (
    <View style={styles.container}>
      {error ? (
        <View style={styles.emptyWrap}>
          <Icon name="alert-circle-outline" size={48} color={Colors.textHint} />
          <Text style={styles.emptyTitle}>加载失败</Text>
          <Text style={styles.emptyDesc}>{error}</Text>
          <TouchableOpacity style={styles.retryBtn} onPress={load} activeOpacity={0.7}>
            <Text style={styles.retryText}>重试</Text>
          </TouchableOpacity>
        </View>
      ) : items.length === 0 ? (
        <View style={styles.emptyWrap}>
          <Icon name="bell-off-outline" size={48} color={Colors.textHint} />
          <Text style={styles.emptyTitle}>暂无通知</Text>
          <Text style={styles.emptyDesc}>医药代表推送新学术卡片时会在这里提醒你</Text>
        </View>
      ) : (
        <>
          <FlatList
            data={items}
            keyExtractor={(x) => String(x.id)}
            renderItem={renderItem}
            contentContainerStyle={{ padding: Spacing.md, paddingBottom: 32 }}
            refreshControl={
              <RefreshControl refreshing={refreshing} onRefresh={() => { setRefreshing(true); load(); }} />
            }
          />
          {unread > 0 && (
            <TouchableOpacity
              style={styles.markAllBtn}
              onPress={handleMarkAll}
              disabled={marking}
              activeOpacity={0.8}
            >
              {marking ? <ActivityIndicator color={Colors.white} /> : (
                <Text style={styles.markAllText}>全部标为已读（{unread}）</Text>
              )}
            </TouchableOpacity>
          )}
        </>
      )}
    </View>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1, backgroundColor: Colors.background },
  center: { flex: 1, justifyContent: 'center', alignItems: 'center', backgroundColor: Colors.background },
  emptyWrap: {
    flex: 1, justifyContent: 'center', alignItems: 'center',
    paddingHorizontal: Spacing.xl, backgroundColor: Colors.background,
  },
  emptyTitle: { fontSize: FontSize.lg, color: Colors.textPrimary, fontWeight: '600', marginTop: Spacing.md },
  emptyDesc: { fontSize: FontSize.sm, color: Colors.textHint, marginTop: Spacing.sm, textAlign: 'center' },
  retryBtn: {
    marginTop: Spacing.lg, paddingHorizontal: Spacing.xl, paddingVertical: Spacing.sm,
    backgroundColor: Colors.primary, borderRadius: BorderRadius.md,
  },
  retryText: { color: Colors.white, fontSize: FontSize.md },
  card: {
    flexDirection: 'row', alignItems: 'center', backgroundColor: Colors.card,
    borderRadius: BorderRadius.md, padding: Spacing.md, marginBottom: Spacing.sm,
    ...Shadow.card,
  },
  iconWrap: {
    width: 44, height: 44, borderRadius: 22, justifyContent: 'center', alignItems: 'center',
    marginRight: Spacing.md,
  },
  body: { flex: 1 },
  titleRow: { flexDirection: 'row', alignItems: 'center' },
  unreadDot: {
    width: 8, height: 8, borderRadius: 4, backgroundColor: Colors.danger, marginRight: 6,
  },
  title: { fontSize: FontSize.md, color: Colors.textPrimary, fontWeight: '600', flexShrink: 1 },
  content: { fontSize: FontSize.sm, color: Colors.textSecondary, marginTop: 4 },
  time: { fontSize: FontSize.xs, color: Colors.textHint, marginTop: 4 },
  markAllBtn: {
    position: 'absolute', bottom: Spacing.xl, left: Spacing.xl, right: Spacing.xl,
    backgroundColor: Colors.primary, borderRadius: BorderRadius.lg,
    paddingVertical: Spacing.md, alignItems: 'center',
    ...Shadow.button,
  },
  markAllText: { color: Colors.white, fontSize: FontSize.md, fontWeight: '600' },
});
