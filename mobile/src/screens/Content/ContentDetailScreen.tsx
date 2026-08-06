/**
 * 学术内容详情页 - 文档正文
 */
import React, { useEffect, useState } from 'react';
import { View, Text, ScrollView, StyleSheet, TouchableOpacity, ActivityIndicator } from 'react-native';
import { useRoute, useNavigation } from '@react-navigation/native';
import type { RouteProp } from '@react-navigation/native';
import Icon from '../../components/Icon';
import { contentAPI, type ContentDetail } from '../../api/content';
import { Colors, FontSize, Spacing, BorderRadius, Shadow } from '../../constants/theme';
import type { RootStackParamList } from '../../navigation/types';

type RouteType = RouteProp<RootStackParamList, 'ContentDetail'>;

export default function ContentDetailScreen() {
  const route = useRoute<RouteType>();
  const navigation = useNavigation();
  const { contentId } = route.params;
  const [doc, setDoc] = useState<ContentDetail | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');

  useEffect(() => {
    let cancelled = false;
    contentAPI.getDocument(contentId)
      .then((d) => { if (!cancelled) setDoc(d); })
      .catch((e: any) => { if (!cancelled) setError(e.message || '加载失败'); })
      .finally(() => { if (!cancelled) setLoading(false); });
    return () => { cancelled = true; };
  }, [contentId]);

  if (loading) {
    return (
      <View style={styles.centered}>
        <ActivityIndicator size="large" color={Colors.primary} />
      </View>
    );
  }
  if (error || !doc) {
    return (
      <View style={styles.centered}>
        <Text style={{ color: Colors.textSecondary }}>{error || '文档不存在'}</Text>
      </View>
    );
  }

  return (
    <View style={styles.container}>
      <View style={styles.header}>
        <TouchableOpacity onPress={() => navigation.goBack()}>
          <Icon name="chevron-left" size={22} color={Colors.textWhite} />
        </TouchableOpacity>
        <Text style={styles.headerTitle}>文档详情</Text>
        <View style={{ width: 24 }} />
      </View>
      <ScrollView contentContainerStyle={styles.content}>
        <Text style={styles.title}>{doc.title}</Text>
        <View style={styles.metaRow}>
          <Text style={styles.metaText}>{doc.source ?? ''} {doc.publish_date ? '· ' + doc.publish_date : ''}</Text>
        </View>
        <View style={[styles.card, Shadow.card]}>
          <Text style={styles.body}>{doc.content || '暂无正文内容'}</Text>
        </View>
        <View style={{ height: 40 }} />
      </ScrollView>
    </View>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1, backgroundColor: Colors.background },
  centered: { flex: 1, justifyContent: 'center', alignItems: 'center', backgroundColor: Colors.background },
  header: {
    backgroundColor: Colors.primary, paddingTop: 50, paddingBottom: 14,
    paddingHorizontal: Spacing.lg, flexDirection: 'row',
    alignItems: 'center', justifyContent: 'space-between', ...Shadow.header,
  },
  headerTitle: { color: Colors.textWhite, fontSize: FontSize.lg, fontWeight: '600' },
  content: { padding: Spacing.lg },
  title: { fontSize: FontSize.xl, fontWeight: '700', color: Colors.textPrimary, lineHeight: 30 },
  metaRow: { marginTop: Spacing.xs, marginBottom: Spacing.lg },
  metaText: { fontSize: FontSize.xs, color: Colors.textHint },
  card: { backgroundColor: Colors.white, borderRadius: BorderRadius.xl, padding: Spacing.lg },
  body: { fontSize: FontSize.md, color: Colors.textPrimary, lineHeight: 24 },
});
