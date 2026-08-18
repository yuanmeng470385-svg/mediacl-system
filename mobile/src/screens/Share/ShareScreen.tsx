/**
 * 分身分享页 —— 选择数字专员分身 → 生成分享链接 → 列表展示 + 复制。
 * 零新依赖：复制用 Alert 弹出完整 share_url 让用户长按复制（RN 内置 Clipboard 已废弃，
 * @react-native-clipboard/clipboard 是额外原生依赖，暂不引入）。
 * 临床精准风
 */
import React, { useEffect, useState, useCallback } from 'react';
import {
  View, Text, StyleSheet, FlatList, TouchableOpacity,
  ActivityIndicator, RefreshControl, Alert,
} from 'react-native';
import { useNavigation } from '@react-navigation/native';
import Icon from '../../components/Icon';
import EmptyState from '../../components/EmptyState';
import { shareAPI } from '../../api/share';
import { specialistAPI } from '../../api/specialist';
import type { ShareLinkItem, DigitalSpecialist } from '../../types';
import { Colors, FontSize, Spacing, BorderRadius, Shadow } from '../../constants/theme';

export default function ShareScreen() {
  const navigation = useNavigation();
  const [specialists, setSpecialists] = useState<DigitalSpecialist[]>([]);
  const [selectedId, setSelectedId] = useState<number | null>(null);
  const [links, setLinks] = useState<ShareLinkItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [generating, setGenerating] = useState(false);
  const [error, setError] = useState('');

  const loadData = useCallback(async () => {
    try {
      const [specList, linkList] = await Promise.all([
        specialistAPI.list({ page: 1, page_size: 100 }),
        shareAPI.list(),
      ]);
      // 只提供 active 分身供分享（draft/disabled 医生端不可订阅）
      const active = (specList || []).filter((s) => s.status === 'active');
      setSpecialists(active);
      setLinks(Array.isArray(linkList) ? linkList : []);
      setError('');
    } catch (e: any) {
      setError(e?.message || '分享链接加载失败，请检查网络');
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { loadData(); }, [loadData]);

  const onRefresh = async () => {
    setRefreshing(true);
    await loadData();
    setRefreshing(false);
  };

  /** 生成分享链接 → 成功即弹 share_url（长按复制）+ 刷新列表 */
  const handleGenerate = async () => {
    if (selectedId == null) {
      Alert.alert('请先选择分身', '在列表中选择一个数字专员分身后再生成分享链接。');
      return;
    }
    setGenerating(true);
    try {
      const created = await shareAPI.create(selectedId);
      setSelectedId(null);
      await loadData();
      Alert.alert(
        '分享链接已生成',
        created?.share_url || '（生成成功，但未返回链接地址）',
        [{ text: '知道了' }]
      );
    } catch (e: any) {
      Alert.alert('生成失败', e?.message || '请稍后重试');
    } finally {
      setGenerating(false);
    }
  };

  const handleCopy = (item: ShareLinkItem) => {
    Alert.alert('分享链接', item.share_url || '（无链接地址）', [
      { text: '知道了' },
    ]);
  };

  const renderLink = ({ item }: { item: ShareLinkItem }) => (
    <View style={[styles.card, Shadow.card]}>
      <View style={styles.cardHead}>
        <View style={styles.twinBadge}>
          <Icon name="robot-outline" size={12} color={Colors.primary} />
          <Text style={styles.twinText}>{item.twin_name || `分身 #${item.twin_id}`}</Text>
        </View>
        <View style={styles.addBadge}>
          <Icon name="account-multiple-outline" size={12} color={Colors.info} />
          <Text style={styles.addText}>已添加 {item.add_count ?? 0}</Text>
        </View>
      </View>
      <Text style={styles.linkUrl} numberOfLines={1}>{item.share_url || '（无链接）'}</Text>
      <View style={styles.cardFooter}>
        <View style={styles.metaRow}>
          <Icon name="clock-outline" size={12} color={Colors.textHint} />
          <Text style={styles.metaText}>
            {item.expire_at ? `有效期至 ${String(item.expire_at).slice(0, 10)}` : '永久有效'}
          </Text>
        </View>
        <TouchableOpacity style={styles.shareBtn} onPress={() => handleCopy(item)} activeOpacity={0.8}>
          <Icon name="share-variant-outline" size={14} color={Colors.primary} />
          <Text style={styles.shareBtnText}>分享</Text>
        </TouchableOpacity>
      </View>
    </View>
  );

  /** 列表头部：说明文案 + 分身选择 + 生成按钮 */
  const header = (
    <View>
      <Text style={styles.desc}>
        分享给医生：复制链接发送微信，医生点击后即可添加该分身对话。
      </Text>

      <View style={[styles.sectionCard, Shadow.card]}>
        <Text style={styles.sectionTitle}>选择分身</Text>
        {specialists.length === 0 ? (
          <Text style={styles.hintText}>暂无可分享的数字专员分身</Text>
        ) : (
          <View style={styles.specWrap}>
            {specialists.map((s) => {
              const selected = selectedId === s.id;
              return (
                <TouchableOpacity
                  key={s.id}
                  style={[styles.specChip, selected && styles.specChipActive]}
                  onPress={() => setSelectedId(selected ? null : s.id)}
                  activeOpacity={0.7}
                >
                  <Text style={[styles.specChipText, selected && styles.specChipTextActive]}>
                    {s.name}
                  </Text>
                </TouchableOpacity>
              );
            })}
          </View>
        )}

        <TouchableOpacity
          style={[styles.generateBtn, (selectedId == null || generating) && styles.generateBtnDisabled]}
          onPress={handleGenerate}
          disabled={selectedId == null || generating}
          activeOpacity={0.8}
        >
          {generating ? (
            <ActivityIndicator size="small" color={Colors.textWhite} />
          ) : (
            <Icon name="link-variant" size={16} color={Colors.textWhite} />
          )}
          <Text style={styles.generateBtnText}>{generating ? '生成中…' : '生成分享链接'}</Text>
        </TouchableOpacity>
      </View>

      <Text style={styles.listTitle}>已生成链接（{links.length}）</Text>
    </View>
  );

  return (
    <View style={styles.container}>
      <View style={styles.header}>
        <TouchableOpacity onPress={() => navigation.goBack()} style={styles.headerBtn}>
          <Icon name="chevron-left" size={22} color={Colors.textWhite} />
        </TouchableOpacity>
        <Text style={styles.headerTitle}>分身分享</Text>
        <View style={{ width: 24 }} />
      </View>

      {loading ? (
        <View style={styles.centered}>
          <ActivityIndicator size="large" color={Colors.primary} />
        </View>
      ) : error && links.length === 0 ? (
        <View style={styles.centered}>
          <Text style={styles.errorText}>{error}</Text>
          <TouchableOpacity style={styles.retryBtn} onPress={loadData} activeOpacity={0.8}>
            <Text style={styles.retryText}>重试</Text>
          </TouchableOpacity>
        </View>
      ) : (
        <FlatList
          data={links}
          renderItem={renderLink}
          keyExtractor={(item) => String(item.id)}
          ListHeaderComponent={header}
          contentContainerStyle={[styles.list, links.length === 0 && styles.listEmpty]}
          showsVerticalScrollIndicator={false}
          refreshControl={
            <RefreshControl refreshing={refreshing} onRefresh={onRefresh} tintColor={Colors.primary} colors={[Colors.primary]} />
          }
          ListEmptyComponent={
            <EmptyState icon="share-variant-outline" title="暂无分享链接" description="选择分身并生成链接后，可复制发送给医生" />
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
  list: { padding: Spacing.lg },
  listEmpty: { flexGrow: 1 },
  desc: {
    fontSize: FontSize.sm, color: Colors.textSecondary,
    lineHeight: 20, marginBottom: Spacing.lg,
  },
  sectionCard: {
    backgroundColor: Colors.white, borderRadius: BorderRadius.xl,
    padding: Spacing.lg, marginBottom: Spacing.lg,
  },
  sectionTitle: { fontSize: FontSize.md, color: Colors.textPrimary, fontWeight: '600', marginBottom: Spacing.md },
  hintText: { fontSize: FontSize.sm, color: Colors.textHint },
  specWrap: { flexDirection: 'row', flexWrap: 'wrap', gap: Spacing.sm },
  specChip: {
    paddingHorizontal: Spacing.lg, paddingVertical: Spacing.sm,
    borderRadius: BorderRadius.full, backgroundColor: Colors.background,
    borderWidth: 1, borderColor: Colors.border,
  },
  specChipActive: { backgroundColor: Colors.primarySurface, borderColor: Colors.primary },
  specChipText: { fontSize: FontSize.sm, color: Colors.textSecondary },
  specChipTextActive: { color: Colors.primary, fontWeight: '600' },
  generateBtn: {
    marginTop: Spacing.lg, flexDirection: 'row', alignItems: 'center',
    justifyContent: 'center', gap: Spacing.sm,
    backgroundColor: Colors.primary, paddingVertical: 12, borderRadius: BorderRadius.lg,
  },
  generateBtnDisabled: { backgroundColor: Colors.textHint },
  generateBtnText: { color: Colors.textWhite, fontSize: FontSize.md, fontWeight: '600' },
  listTitle: {
    fontSize: FontSize.md, color: Colors.textPrimary, fontWeight: '600',
    marginBottom: Spacing.md, marginTop: Spacing.sm,
  },
  card: {
    backgroundColor: Colors.white, borderRadius: BorderRadius.xl,
    padding: Spacing.lg, marginBottom: Spacing.md,
  },
  cardHead: { flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center', marginBottom: Spacing.sm },
  twinBadge: { flexDirection: 'row', alignItems: 'center', gap: 4, flex: 1 },
  twinText: { fontSize: FontSize.md, color: Colors.textPrimary, fontWeight: '600' },
  addBadge: { flexDirection: 'row', alignItems: 'center', gap: 4 },
  addText: { fontSize: 11, color: Colors.info, fontWeight: '600' },
  linkUrl: { fontSize: FontSize.sm, color: Colors.textSecondary, marginBottom: Spacing.md },
  cardFooter: {
    flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center',
  },
  metaRow: { flexDirection: 'row', alignItems: 'center', gap: 4 },
  metaText: { fontSize: 11, color: Colors.textHint },
  shareBtn: {
    flexDirection: 'row', alignItems: 'center', gap: 4,
    paddingHorizontal: Spacing.lg, paddingVertical: 6,
    borderRadius: BorderRadius.full, backgroundColor: Colors.primarySurface,
  },
  shareBtnText: { color: Colors.primary, fontSize: FontSize.sm, fontWeight: '600' },
});
