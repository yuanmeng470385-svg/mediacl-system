/**
 * 拜访前准备页 - 快速了解医生、准备话题、避免踩雷
 */
import React, { useEffect, useState } from 'react';
import {
  View,
  Text,
  ScrollView,
  StyleSheet,
  TouchableOpacity,
  ActivityIndicator,
  Alert,
} from 'react-native';
import { useRoute, useNavigation } from '@react-navigation/native';
import type { RouteProp } from '@react-navigation/native';
import type { NativeStackNavigationProp } from '@react-navigation/native-stack';
import { visitAPI } from '../../api/visit';
import { hcpAPI } from '../../api/hcp';
import { Colors, FontSize, Spacing, BorderRadius, Shadow } from '../../constants/theme';
import type { VisitPrepareParams, RootStackParamList } from '../../navigation/types';
import type { VisitPrepareData } from '../../types';

type RouteType = RouteProp<{ VisitPrepare: VisitPrepareParams }, 'VisitPrepare'>;
type Nav = NativeStackNavigationProp<RootStackParamList>;

export default function VisitPrepareScreen() {
  const route = useRoute<RouteType>();
  const navigation = useNavigation<Nav>();
  const { hcpId, hcpName, productId } = route.params;

  const [data, setData] = useState<VisitPrepareData | null>(null);
  const [loading, setLoading] = useState(true);
  const [selectedTopics, setSelectedTopics] = useState<Set<string>>(new Set());

  useEffect(() => {
    loadPrepareData();
  }, []);

  const loadPrepareData = async () => {
    try {
      const result = await visitAPI.prepareVisit({
        hcpId,
        productId: productId || 1,
      });
      setData(result);
      // 默认全选推荐话题
      if (result.recommendations?.suggested_topics) {
        setSelectedTopics(new Set(result.recommendations.suggested_topics));
      }
    } catch {
      // 降级：调医生画像 API
      try {
        const profile = await hcpAPI.getProfile(hcpId);
        setData({
          hcp_profile: profile,
          recommendations: {
            suggested_topics: ['产品最新临床数据', '区域学术会议邀请', '患者管理经验交流'],
            red_lines: ['不得做出疗效保证', '不得与竞品直接对比', '不得承诺回扣或利益'],
            opening_remarks: `主任您好，感谢您百忙之中抽出时间。`,
            materials: [],
            last_follow_up: '暂无上次拜访记录',
          },
        });
      } catch {
        Alert.alert('加载失败', '无法获取拜访准备数据，请检查网络后重试');
      }
    } finally {
      setLoading(false);
    }
  };

  const toggleTopic = (topic: string) => {
    setSelectedTopics((prev) => {
      const next = new Set(prev);
      if (next.has(topic)) next.delete(topic);
      else next.add(topic);
      return next;
    });
  };

  const handleStartVisit = async () => {
    try {
      const result = await visitAPI.startVisit({
        hcp_id: hcpId,
        product_id: productId || 1,
        planned_date: new Date().toISOString().split('T')[0],
        notes: `推荐话题：${[...selectedTopics].join('、')}`,
      });
      navigation.replace('VisitInProgress', {
        visitId: result.visit_id,
        hcpName: hcpName,
      });
    } catch (e: any) {
      Alert.alert('开始拜访失败', e.message || '请稍后重试');
    }
  };

  if (loading) {
    return (
      <View style={styles.centered}>
        <ActivityIndicator size="large" color={Colors.primary} />
        <Text style={styles.loadingText}>准备拜访资料...</Text>
      </View>
    );
  }

  return (
    <View style={styles.container}>
      {/* 头部 */}
      <View style={styles.header}>
        <TouchableOpacity onPress={() => navigation.goBack()}>
          <Text style={styles.backText}>← 返回</Text>
        </TouchableOpacity>
        <Text style={styles.headerTitle}>拜访前准备</Text>
        <View style={{ width: 60 }} />
      </View>

      <ScrollView
        style={styles.content}
        showsVerticalScrollIndicator={false}
      >
        {/* 医生信息 */}
        <View style={[styles.card, Shadow.card]}>
          <Text style={styles.sectionTitle}>👨‍⚕️ 医生信息</Text>
          <Text style={styles.hcpName}>
            {data?.hcp_profile?.basic_info?.name || hcpName}
          </Text>
          <Text style={styles.hcpInfo}>
            {data?.hcp_profile?.basic_info?.hospital} ·{' '}
            {data?.hcp_profile?.basic_info?.department} ·{' '}
            {data?.hcp_profile?.basic_info?.title}
          </Text>
          {data?.hcp_profile?.communication_advice && (
            <View style={styles.communicationBox}>
              <Text style={styles.commTitle}>沟通建议</Text>
              <Text style={styles.commText}>
                最佳时间：{data.hcp_profile.communication_advice.best_time}
              </Text>
              <Text style={styles.commText}>
                偏好方式：{data.hcp_profile.communication_advice.preferred_channels.join('、')}
              </Text>
            </View>
          )}
        </View>

        {/* 推荐话题（可勾选） */}
        <View style={[styles.card, Shadow.card]}>
          <Text style={styles.sectionTitle}>💡 推荐话题</Text>
          <Text style={styles.hintText}>勾选本次拜访准备讨论的话题</Text>
          {data?.recommendations?.suggested_topics?.map((topic, i) => (
            <TouchableOpacity
              key={i}
              style={styles.topicItem}
              onPress={() => toggleTopic(topic)}
              activeOpacity={0.7}
            >
              <View
                style={[
                  styles.checkbox,
                  selectedTopics.has(topic) && styles.checkboxChecked,
                ]}
              >
                {selectedTopics.has(topic) && (
                  <Text style={styles.checkmark}>✓</Text>
                )}
              </View>
              <Text style={styles.topicText}>{topic}</Text>
            </TouchableOpacity>
          ))}
        </View>

        {/* 红线提醒 */}
        <View style={[styles.card, styles.redCard]}>
          <Text style={styles.redTitle}>🚫 合规红线</Text>
          {data?.recommendations?.red_lines?.map((line, i) => (
            <View key={i} style={styles.redItem}>
              <Text style={styles.redDot}>•</Text>
              <Text style={styles.redText}>{line}</Text>
            </View>
          ))}
        </View>

        {/* 开场白建议 */}
        {data?.recommendations?.opening_remarks && (
          <View style={[styles.card, Shadow.card]}>
            <Text style={styles.sectionTitle}>🎯 开场白建议</Text>
            <View style={styles.openingBox}>
              <Text style={styles.openingText}>
                {data.recommendations.opening_remarks}
              </Text>
            </View>
          </View>
        )}

        {/* 上次跟进 */}
        {data?.recommendations?.last_follow_up && (
          <View style={[styles.card, Shadow.card]}>
            <Text style={styles.sectionTitle}>📝 上次跟进</Text>
            <Text style={styles.followText}>
              {data.recommendations.last_follow_up}
            </Text>
          </View>
        )}

        <View style={{ height: 100 }} />
      </ScrollView>

      {/* 底部开始按钮 */}
      <View style={styles.bottomBar}>
        <TouchableOpacity
          style={styles.startBtn}
          onPress={handleStartVisit}
          activeOpacity={0.8}
        >
          <Text style={styles.startBtnText}>开始拜访</Text>
        </TouchableOpacity>
      </View>
    </View>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1, backgroundColor: Colors.background },
  centered: { flex: 1, justifyContent: 'center', alignItems: 'center' },
  loadingText: { marginTop: Spacing.md, color: Colors.textHint, fontSize: FontSize.sm },
  // 头部
  header: {
    backgroundColor: Colors.primary,
    paddingTop: 50,
    paddingBottom: 12,
    paddingHorizontal: Spacing.lg,
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
  },
  backText: { color: Colors.textWhite, fontSize: FontSize.md },
  headerTitle: { color: Colors.textWhite, fontSize: FontSize.lg, fontWeight: '600' },
  content: { flex: 1, padding: Spacing.lg },
  // 卡片
  card: {
    backgroundColor: Colors.white,
    borderRadius: BorderRadius.lg,
    padding: Spacing.lg,
    marginBottom: Spacing.md,
  },
  sectionTitle: {
    fontSize: FontSize.lg,
    fontWeight: '700',
    color: Colors.textPrimary,
    marginBottom: Spacing.md,
  },
  hintText: { fontSize: FontSize.xs, color: Colors.textHint, marginBottom: Spacing.sm },
  hcpName: { fontSize: FontSize.xl, fontWeight: '700', color: Colors.textPrimary, marginBottom: 4 },
  hcpInfo: { fontSize: FontSize.sm, color: Colors.textSecondary },
  communicationBox: {
    marginTop: Spacing.md,
    backgroundColor: Colors.background,
    padding: Spacing.md,
    borderRadius: BorderRadius.md,
  },
  commTitle: { fontSize: FontSize.sm, fontWeight: '600', color: Colors.textPrimary, marginBottom: 4 },
  commText: { fontSize: FontSize.sm, color: Colors.textSecondary, marginTop: 2 },
  // 话题
  topicItem: {
    flexDirection: 'row',
    alignItems: 'center',
    paddingVertical: Spacing.sm,
    gap: Spacing.md,
  },
  checkbox: {
    width: 22,
    height: 22,
    borderRadius: 6,
    borderWidth: 2,
    borderColor: Colors.border,
    alignItems: 'center',
    justifyContent: 'center',
  },
  checkboxChecked: {
    backgroundColor: Colors.primary,
    borderColor: Colors.primary,
  },
  checkmark: { color: Colors.white, fontSize: 14, fontWeight: '700' },
  topicText: { fontSize: FontSize.md, color: Colors.textPrimary, flex: 1 },
  // 红线
  redCard: { backgroundColor: '#fef2f2', borderWidth: 1, borderColor: '#fecaca' },
  redTitle: { fontSize: FontSize.lg, fontWeight: '700', color: Colors.danger, marginBottom: Spacing.md },
  redItem: { flexDirection: 'row', marginBottom: Spacing.sm, gap: Spacing.sm },
  redDot: { color: Colors.danger, fontSize: FontSize.lg, lineHeight: 22 },
  redText: { fontSize: FontSize.sm, color: Colors.danger, flex: 1, lineHeight: 20 },
  // 开场白
  openingBox: {
    backgroundColor: '#eff6ff',
    padding: Spacing.lg,
    borderRadius: BorderRadius.md,
    borderLeftWidth: 4,
    borderLeftColor: Colors.primary,
  },
  openingText: { fontSize: FontSize.md, color: Colors.textPrimary, lineHeight: 24, fontStyle: 'italic' },
  // 上次跟进
  followText: { fontSize: FontSize.md, color: Colors.textSecondary, lineHeight: 22 },
  // 底部
  bottomBar: {
    padding: Spacing.lg,
    paddingBottom: 34,
    backgroundColor: Colors.white,
    borderTopWidth: 1,
    borderTopColor: Colors.divider,
  },
  startBtn: {
    backgroundColor: Colors.primary,
    borderRadius: BorderRadius.lg,
    paddingVertical: 16,
    alignItems: 'center',
  },
  startBtnText: { color: Colors.textWhite, fontSize: FontSize.lg, fontWeight: '700' },
});
