/**
 * Skill 广场（二期 H）：展示已上架 Skill 模版（名称/风格标签/热度），
 * 加载（load）后回到陪练场（PracticeList）。
 */
import React, { useCallback, useEffect, useState } from 'react';
import {
  Alert, ScrollView, StyleSheet, Text, TouchableOpacity, View,
} from 'react-native';
import { useNavigation } from '@react-navigation/native';
import type { NativeStackNavigationProp } from '@react-navigation/native-stack';
import Icon from '../../components/Icon';
import { plazaAPI } from '../../api/practice';
import type { RootStackParamList } from '../../navigation/types';
import { BorderRadius, Colors, FontSize, Shadow, Spacing } from '../../constants/theme';

type Nav = NativeStackNavigationProp<RootStackParamList>;

interface PlazaItem {
  id: number;
  name?: string;
  style_tags?: string[] | null;
  heat?: number;
  approval_rate?: number | null;
}

export default function PlazaScreen() {
  const navigation = useNavigation<Nav>();
  const [items, setItems] = useState<PlazaItem[]>([]);
  const [loaded, setLoaded] = useState(false);
  const [loadingId, setLoadingId] = useState<number | null>(null);

  const load = useCallback(async () => {
    setLoaded(false);
    try {
      const res = await plazaAPI.list();
      setItems(Array.isArray(res?.items) ? res.items : []);
    } catch (err: any) {
      Alert.alert('加载失败', err?.message || '无法获取广场内容，请稍后重试');
    } finally {
      setLoaded(true);
    }
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  const loadSkill = async (item: PlazaItem) => {
    setLoadingId(item.id);
    try {
      await plazaAPI.load(item.id);
      Alert.alert('已加载', `「${item.name || 'Skill'}」已加载到陪练场`);
      // 把已加载 Skill 的 id 带进陪练场，创建会话时写入 skill_id（让 AI 医生按该模版风格陪练）
      navigation.navigate('PracticeList', { skillId: item.id });
    } catch (err: any) {
      Alert.alert('加载失败', err?.message || '请稍后重试');
    } finally {
      setLoadingId(null);
    }
  };

  const renderTags = (tags?: string[] | null) => {
    if (!Array.isArray(tags) || tags.length === 0) return null;
    return (
      <View style={styles.tagWrap}>
        {tags.map((t, i) => (
          <View key={`${t}-${i}`} style={styles.tag}>
            <Text style={styles.tagText}>{t}</Text>
          </View>
        ))}
      </View>
    );
  };

  return (
    <View style={styles.container}>
      <View style={styles.header}>
        <TouchableOpacity onPress={() => navigation.goBack()}>
          <Icon name="chevron-left" size={22} color={Colors.textWhite} />
        </TouchableOpacity>
        <Text style={styles.headerTitle}>Skill 广场</Text>
        <View style={{ width: 24 }} />
      </View>

      <ScrollView contentContainerStyle={styles.content}>
        {!loaded ? (
          <Text style={styles.emptyText}>加载中…</Text>
        ) : items.length === 0 ? (
          <Text style={styles.emptyText}>广场暂无已上架的 Skill 模版</Text>
        ) : (
          items.map((item) => (
            <View key={item.id} style={[styles.card, Shadow.card]}>
              <View style={styles.cardTop}>
                <View style={styles.iconBox}>
                  <Icon name="storefront-outline" size={20} color={Colors.primary} />
                </View>
                <View style={{ flex: 1 }}>
                  <Text style={styles.name} numberOfLines={1}>{item.name || `Skill #${item.id}`}</Text>
                  {renderTags(item.style_tags)}
                </View>
                <View style={styles.heatBox}>
                  <Icon name="fire" size={16} color={Colors.warning} />
                  <Text style={styles.heatText}>{item.heat ?? 0}</Text>
                </View>
              </View>
              <TouchableOpacity
                style={[styles.loadBtn, loadingId === item.id && { opacity: 0.6 }]}
                disabled={loadingId === item.id}
                onPress={() => loadSkill(item)}
                activeOpacity={0.7}
              >
                <Icon name="download-outline" size={16} color={Colors.primary} />
                <Text style={styles.loadText}>{loadingId === item.id ? '加载中…' : '加载到陪练场'}</Text>
              </TouchableOpacity>
            </View>
          ))
        )}
      </ScrollView>
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
  emptyText: { fontSize: FontSize.sm, color: Colors.textHint, textAlign: 'center', paddingVertical: Spacing.xxl },
  card: { backgroundColor: Colors.card, borderRadius: BorderRadius.md, padding: Spacing.lg, marginBottom: Spacing.md },
  cardTop: { flexDirection: 'row', alignItems: 'center', gap: Spacing.md },
  iconBox: {
    width: 40, height: 40, borderRadius: 12,
    backgroundColor: Colors.primarySurface, alignItems: 'center', justifyContent: 'center',
  },
  name: { fontSize: FontSize.md, fontWeight: '600', color: Colors.textPrimary },
  tagWrap: { flexDirection: 'row', flexWrap: 'wrap', gap: Spacing.xs, marginTop: Spacing.xs },
  tag: {
    backgroundColor: Colors.accentLight, borderRadius: BorderRadius.sm,
    paddingHorizontal: Spacing.sm, paddingVertical: 2,
  },
  tagText: { fontSize: FontSize.xs, color: Colors.info },
  heatBox: { flexDirection: 'row', alignItems: 'center', gap: 4 },
  heatText: { fontSize: FontSize.md, fontWeight: '700', color: Colors.warning },
  loadBtn: {
    marginTop: Spacing.md, flexDirection: 'row', alignItems: 'center', justifyContent: 'center',
    gap: Spacing.sm, borderWidth: 1, borderColor: Colors.primary,
    borderRadius: BorderRadius.sm, padding: Spacing.sm,
  },
  loadText: { color: Colors.primary, fontSize: FontSize.sm, fontWeight: '600' },
});
