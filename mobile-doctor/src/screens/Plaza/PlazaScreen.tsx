/**
 * 官方广场（二期 I 医生端）：
 *   - 官方公共数字员工列表（名称 / 被添加数）
 *   - 「添加」按钮 → 知情同意弹窗 → subscribePlaza（后端幂等）
 *
 * 样式令牌照 theme.ts，列表卡片范式照 MyTwinsScreen。
 */
import React, { useCallback, useState } from 'react';
import {
  ActivityIndicator,
  Alert,
  FlatList,
  RefreshControl,
  StyleSheet,
  Text,
  TouchableOpacity,
  View,
} from 'react-native';
import { useFocusEffect } from '@react-navigation/native';
import Icon, { FeatureIcons } from '../../components/Icon';
import { doctorExpAPI } from '../../api/doctorExp';
import type { PlazaTwin } from '../../types';
import { BorderRadius, Colors, FontSize, Shadow, Spacing } from '../../constants/theme';

const avatarColors = ['#0D3B66', '#1565C0', '#00ACC1', '#2E7D32', '#C62828'];

/** 知情同意文案（对齐需求 5.6(2) 添加前知情同意确认） */
const CONSENT_TITLE = '知情同意';
const CONSENT_BODY =
  '添加该官方数字员工后，你将订阅其内容并可与它对话。平台将记录你的订阅与同意留痕，用于合规审计。是否同意并添加？';

export default function PlazaScreen() {
  const [items, setItems] = useState<PlazaTwin[]>([]);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [error, setError] = useState('');
  const [subscribingId, setSubscribingId] = useState<number | null>(null);

  const load = useCallback(async () => {
    setError('');
    try {
      const res = await doctorExpAPI.plazaList();
      setItems(Array.isArray(res?.items) ? res.items : []);
    } catch (e: any) {
      setError(e?.message || '广场加载失败，请检查网络');
      setItems([]);
    } finally {
      setLoading(false);
    }
  }, []);

  useFocusEffect(
    useCallback(() => {
      load();
    }, [load])
  );

  const onRefresh = async () => {
    setRefreshing(true);
    await load();
    setRefreshing(false);
  };

  const handleSubscribe = (twin: PlazaTwin) => {
    Alert.alert(CONSENT_TITLE, CONSENT_BODY, [
      { text: '取消', style: 'cancel' },
      {
        text: '同意并添加',
        onPress: () => doSubscribe(twin),
      },
    ]);
  };

  const doSubscribe = async (twin: PlazaTwin) => {
    if (subscribingId !== null) return;
    setSubscribingId(twin.id);
    try {
      await doctorExpAPI.subscribePlaza(twin.id);
      Alert.alert('添加成功', `已添加「${twin.name}」，可在「分身」页查看`);
    } catch (e: any) {
      Alert.alert('添加失败', e?.message || '请稍后重试');
    } finally {
      setSubscribingId(null);
    }
  };

  const getAvatarColor = (id: number) => avatarColors[id % avatarColors.length];

  const renderItem = ({ item }: { item: PlazaTwin }) => {
    const name = item.name || `官方数字员工 #${item.id}`;
    const busy = subscribingId === item.id;
    return (
      <View style={[styles.card, Shadow.card]}>
        <View style={[styles.avatar, { backgroundColor: getAvatarColor(item.id) }]}>
          <Text style={styles.avatarText}>{name.slice(0, 2)}</Text>
        </View>
        <View style={styles.info}>
          <Text style={styles.name}>{name}</Text>
          <Text style={styles.meta}>被添加 {item.added_count ?? 0} 次</Text>
        </View>
        <TouchableOpacity
          style={[styles.addBtn, busy && { opacity: 0.6 }]}
          onPress={() => handleSubscribe(item)}
          disabled={busy}
          activeOpacity={0.7}
        >
          {busy ? (
            <ActivityIndicator size="small" color={Colors.primary} />
          ) : (
            <Text style={styles.addBtnText}>添加</Text>
          )}
        </TouchableOpacity>
      </View>
    );
  };

  if (loading) {
    return (
      <View style={styles.centered}>
        <ActivityIndicator size="large" color={Colors.primary} />
        <Text style={styles.loadingText}>加载官方广场...</Text>
      </View>
    );
  }

  return (
    <View style={styles.container}>
      <View style={styles.header}>
        <Text style={styles.headerTitle}>官方广场</Text>
        <Text style={styles.headerSubtitle}>浏览并添加官方公共数字员工</Text>
      </View>

      <FlatList
        data={items}
        renderItem={renderItem}
        keyExtractor={(item) => item.id.toString()}
        contentContainerStyle={styles.list}
        refreshControl={
          <RefreshControl refreshing={refreshing} onRefresh={onRefresh} colors={[Colors.primary]} />
        }
        ListEmptyComponent={
          <View style={styles.empty}>
            <Icon name={FeatureIcons.specialist} size={48} color={Colors.textHint} />
            <Text style={styles.emptyTitle}>{error || '暂无官方数字员工'}</Text>
            <Text style={styles.emptyDesc}>官方上线的公共数字员工会出现在这里</Text>
            {error ? (
              <TouchableOpacity style={styles.retryBtn} onPress={load} activeOpacity={0.8}>
                <Text style={styles.retryText}>重试</Text>
              </TouchableOpacity>
            ) : null}
          </View>
        }
      />
    </View>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1, backgroundColor: Colors.background },
  centered: { flex: 1, justifyContent: 'center', alignItems: 'center', backgroundColor: Colors.background },
  loadingText: { marginTop: Spacing.md, color: Colors.textHint, fontSize: FontSize.sm },
  header: {
    backgroundColor: Colors.primary,
    paddingHorizontal: Spacing.xl,
    paddingTop: 52,
    paddingBottom: Spacing.xl,
  },
  headerTitle: { color: Colors.textWhite, fontSize: FontSize.xl, fontWeight: '700' },
  headerSubtitle: {
    color: 'rgba(255,255,255,0.7)',
    fontSize: FontSize.sm,
    marginTop: 4,
  },
  list: { padding: Spacing.lg },
  card: {
    backgroundColor: Colors.white,
    borderRadius: BorderRadius.lg,
    padding: Spacing.lg,
    marginBottom: Spacing.md,
    flexDirection: 'row',
    alignItems: 'center',
    gap: Spacing.lg,
  },
  avatar: {
    width: 48,
    height: 48,
    borderRadius: 24,
    alignItems: 'center',
    justifyContent: 'center',
  },
  avatarText: { color: Colors.textWhite, fontSize: FontSize.md, fontWeight: '700' },
  info: { flex: 1, gap: 4 },
  name: { fontSize: FontSize.lg, fontWeight: '600', color: Colors.textPrimary },
  meta: { fontSize: FontSize.xs, color: Colors.textHint },
  addBtn: {
    borderWidth: 1,
    borderColor: Colors.primary,
    borderRadius: BorderRadius.full,
    paddingVertical: 6,
    paddingHorizontal: Spacing.xl,
    justifyContent: 'center',
    alignItems: 'center',
    minWidth: 68,
  },
  addBtnText: { color: Colors.primary, fontSize: FontSize.sm, fontWeight: '600' },
  empty: { alignItems: 'center', paddingTop: Spacing.huge },
  emptyTitle: {
    fontSize: FontSize.md,
    fontWeight: '600',
    color: Colors.textSecondary,
    marginTop: Spacing.md,
  },
  emptyDesc: {
    fontSize: FontSize.sm,
    color: Colors.textHint,
    marginTop: Spacing.xs,
    textAlign: 'center',
  },
  retryBtn: {
    backgroundColor: Colors.primary,
    borderRadius: BorderRadius.md,
    paddingHorizontal: Spacing.xl,
    paddingVertical: Spacing.sm,
    marginTop: Spacing.lg,
  },
  retryText: { color: Colors.textWhite, fontSize: FontSize.md, fontWeight: '600' },
});
