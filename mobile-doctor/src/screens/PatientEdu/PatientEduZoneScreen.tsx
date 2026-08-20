/**
 * 患教专区（三期 M 医生端）：
 *   - 进入拉取 doctorExpAPI.zoneList()（仅 shared + approved 内容）
 *   - 列表渲染每张卡片（标题 / AI 生成 badge / 正文 / 注意事项 / 就医指征）
 *   - 空态 + 重试
 *
 * 卡片渲染结构复用 PatientEduScreen 的 eduCard sections，样式令牌照 theme.ts。
 */
import React, { useCallback, useState } from 'react';
import {
  ActivityIndicator,
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
import type { EduCard } from '../../types';
import { BorderRadius, Colors, FontSize, Shadow, Spacing } from '../../constants/theme';

/** 单张患教卡片（内联组件，复用 PatientEduScreen 的 eduCard 视觉结构） */
function EduCardView({ card }: { card: EduCard }) {
  const content = card.content;
  if (!content) return null;
  return (
    <View style={[styles.card, Shadow.card]}>
      <View style={styles.eduCardHeader}>
        <Icon name={FeatureIcons.content} size={20} color={Colors.primary} />
        <Text style={styles.eduCardTitle}>{content.title || '患教卡片'}</Text>
      </View>

      <View style={styles.eduSection}>
        <Text style={styles.eduSectionLabel}>正文</Text>
        <Text style={styles.eduBody}>{content.body || '—'}</Text>
      </View>

      {content.notes ? (
        <View style={styles.eduSection}>
          <Text style={styles.eduSectionLabel}>注意事项</Text>
          <Text style={styles.eduNotes}>{content.notes}</Text>
        </View>
      ) : null}

      {content.seek_care ? (
        <View style={[styles.eduSection, styles.seekCare]}>
          <Text style={styles.eduSectionLabel}>就医指征</Text>
          <Text style={styles.eduSeekCare}>{content.seek_care}</Text>
        </View>
      ) : null}

      <View style={styles.eduMetaRow}>
        {card.is_ai_generated ? (
          <View style={styles.aiBadge}>
            <Text style={styles.aiBadgeText}>AI 生成</Text>
          </View>
        ) : null}
        <Text style={styles.eduMetaText}>仅供患者教育参考</Text>
      </View>
    </View>
  );
}

export default function PatientEduZoneScreen() {
  const [items, setItems] = useState<EduCard[]>([]);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [error, setError] = useState('');

  const load = useCallback(async () => {
    setError('');
    try {
      const res = await doctorExpAPI.zoneList();
      setItems(Array.isArray(res?.items) ? res.items : []);
    } catch (e: any) {
      setError(e?.message || '专区加载失败，请检查网络');
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

  if (loading) {
    return (
      <View style={styles.centered}>
        <ActivityIndicator size="large" color={Colors.primary} />
        <Text style={styles.loadingText}>加载患教专区...</Text>
      </View>
    );
  }

  return (
    <View style={styles.container}>
      <View style={styles.header}>
        <Text style={styles.headerTitle}>患教专区</Text>
        <Text style={styles.headerSubtitle}>审核通过并分享的患教内容</Text>
      </View>

      <FlatList
        data={items}
        renderItem={({ item }) => <EduCardView card={item} />}
        keyExtractor={(item) => item.id.toString()}
        contentContainerStyle={styles.list}
        refreshControl={
          <RefreshControl refreshing={refreshing} onRefresh={onRefresh} colors={[Colors.primary]} />
        }
        ListEmptyComponent={
          <View style={styles.empty}>
            <Icon name={FeatureIcons.content} size={48} color={Colors.textHint} />
            <Text style={styles.emptyTitle}>{error || '暂无专区内容'}</Text>
            <Text style={styles.emptyDesc}>审核通过并分享的患教卡片会出现在这里</Text>
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
  },
  eduCardHeader: { flexDirection: 'row', alignItems: 'center', gap: Spacing.sm, marginBottom: Spacing.md },
  eduCardTitle: { flex: 1, fontSize: FontSize.lg, fontWeight: '700', color: Colors.textPrimary },
  eduSection: { marginBottom: Spacing.md },
  eduSectionLabel: {
    fontSize: FontSize.xs,
    fontWeight: '600',
    color: Colors.textSecondary,
    marginBottom: Spacing.xs,
  },
  eduBody: { fontSize: FontSize.md, color: Colors.textPrimary, lineHeight: 22 },
  eduNotes: { fontSize: FontSize.sm, color: Colors.textSecondary, lineHeight: 20 },
  seekCare: {
    padding: Spacing.md,
    borderRadius: BorderRadius.md,
    backgroundColor: Colors.warningLight,
  },
  eduSeekCare: { fontSize: FontSize.sm, color: Colors.warning, lineHeight: 20 },
  eduMetaRow: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: Spacing.sm,
    marginTop: Spacing.xs,
  },
  aiBadge: {
    backgroundColor: Colors.accentLight,
    borderRadius: BorderRadius.sm,
    paddingHorizontal: 6,
    paddingVertical: 2,
  },
  aiBadgeText: { fontSize: FontSize.xs, color: Colors.info, fontWeight: '600' },
  eduMetaText: { fontSize: FontSize.xs, color: Colors.textHint },
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
