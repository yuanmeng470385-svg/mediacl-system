/**
 * 医生详情页 - 基本信息 + 画像 + 互动历史
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
import EmptyState from '../../components/EmptyState';
import { hcpAPI } from '../../api/hcp';
import { visitAPI } from '../../api/visit';
import { Colors, FontSize, Spacing, BorderRadius, Shadow } from '../../constants/theme';
import type { RootStackParamList, HCPDetailParams } from '../../navigation/types';
import type { HCP, HCPProfile, HCPInteraction } from '../../types';

type RouteType = RouteProp<{ HCPDetail: HCPDetailParams }, 'HCPDetail'>;
type Nav = NativeStackNavigationProp<RootStackParamList>;

export default function HCPDetailScreen() {
  const route = useRoute<RouteType>();
  const navigation = useNavigation<Nav>();
  const { hcpId } = route.params;

  const [hcp, setHcp] = useState<HCP | null>(null);
  const [profile, setProfile] = useState<HCPProfile | null>(null);
  const [interactions, setInteractions] = useState<HCPInteraction[]>([]);
  const [loading, setLoading] = useState(true);
  const [activeTab, setActiveTab] = useState<'profile' | 'history'>('profile');

  useEffect(() => {
    loadAll();
  }, []);

  const loadAll = async () => {
    try {
      const [hcpData, profileData, interactionData] = await Promise.all([
        hcpAPI.getById(hcpId),
        hcpAPI.getProfile(hcpId).catch(() => null),
        hcpAPI.getInteractions(hcpId).catch(() => []),
      ]);
      setHcp(hcpData);
      setProfile(profileData);
      setInteractions(interactionData || []);
    } catch {
      Alert.alert('加载失败', '无法获取医生信息');
    } finally {
      setLoading(false);
    }
  };

  const handleAddTag = () => {
    Alert.prompt
      ? Alert.prompt('添加标签', '', async (tag) => {
          if (tag && hcp) {
            try {
              await hcpAPI.addTags(hcpId, [tag]);
              setHcp({ ...hcp, tags: [...hcp.tags, tag] });
            } catch {
              Alert.alert('失败', '添加标签失败');
            }
          }
        })
      : Alert.alert('提示', '请输入标签名称');
  };

  const handleRemoveTag = async (tag: string) => {
    try {
      await hcpAPI.removeTags(hcpId, [tag]);
      if (hcp) setHcp({ ...hcp, tags: hcp.tags.filter((t) => t !== tag) });
    } catch {
      Alert.alert('失败', '删除标签失败');
    }
  };

  if (loading) {
    return (
      <View style={styles.centered}>
        <ActivityIndicator size="large" color={Colors.primary} />
      </View>
    );
  }

  if (!hcp) {
    return (
      <EmptyState
        icon="👨‍⚕️"
        title="医生不存在"
        description="该医生信息可能已被删除"
      />
    );
  }

  return (
    <View style={styles.container}>
      {/* 头部 */}
      <View style={styles.header}>
        <TouchableOpacity onPress={() => navigation.goBack()}>
          <Text style={styles.backText}>← 返回</Text>
        </TouchableOpacity>
        <Text style={styles.headerTitle}>医生详情</Text>
        <View style={{ width: 60 }} />
      </View>

      <ScrollView showsVerticalScrollIndicator={false}>
        {/* 基本信息 */}
        <View style={styles.profileCard}>
          <View style={[styles.avatarLarge, { backgroundColor: Colors.primary }]}>
            <Text style={styles.avatarLargeText}>
              {hcp.name?.charAt(0) || '医'}
            </Text>
          </View>
          <Text style={styles.name}>{hcp.name}</Text>
          <Text style={styles.dept}>
            {hcp.hospital} · {hcp.department}
          </Text>
          <Text style={styles.title}>{hcp.title}</Text>

          {/* 标签 */}
          <View style={styles.tagSection}>
            <View style={styles.tagRow}>
              {hcp.tags?.map((tag, i) => (
                <TouchableOpacity
                  key={i}
                  style={styles.tag}
                  onLongPress={() => handleRemoveTag(tag)}
                >
                  <Text style={styles.tagText}>{tag}</Text>
                </TouchableOpacity>
              ))}
              <TouchableOpacity
                style={styles.addTagBtn}
                onPress={handleAddTag}
              >
                <Text style={styles.addTagText}>+ 添加</Text>
              </TouchableOpacity>
            </View>
            <Text style={styles.tagHint}>长按标签可删除</Text>
          </View>
        </View>

        {/* Tab 切换 */}
        <View style={styles.tabBar}>
          <TouchableOpacity
            style={[styles.tab, activeTab === 'profile' && styles.tabActive]}
            onPress={() => setActiveTab('profile')}
          >
            <Text
              style={[
                styles.tabText,
                activeTab === 'profile' && styles.tabTextActive,
              ]}
            >
              学术画像
            </Text>
          </TouchableOpacity>
          <TouchableOpacity
            style={[styles.tab, activeTab === 'history' && styles.tabActive]}
            onPress={() => setActiveTab('history')}
          >
            <Text
              style={[
                styles.tabText,
                activeTab === 'history' && styles.tabTextActive,
              ]}
            >
              互动历史
            </Text>
          </TouchableOpacity>
        </View>

        {activeTab === 'profile' ? (
          <View style={styles.tabContent}>
            {/* 学术背景 */}
            {profile?.academic_profile && (
              <View style={[styles.card, Shadow.card]}>
                <Text style={styles.sectionTitle}>🎓 学术背景</Text>
                <Text style={styles.profileText}>
                  {profile.academic_profile.background}
                </Text>
                {profile.academic_profile.research_interests && (
                  <>
                    <Text style={styles.subLabel}>研究方向</Text>
                    <Text style={styles.profileText}>
                      {profile.academic_profile.research_interests}
                    </Text>
                  </>
                )}
              </View>
            )}

            {/* 处方偏好 */}
            {profile?.prescription_analysis && (
              <View style={[styles.card, Shadow.card]}>
                <Text style={styles.sectionTitle}>💊 处方偏好</Text>
                <Text style={styles.profileText}>
                  {profile.prescription_analysis.preference}
                </Text>
                {profile.prescription_analysis.decision_factors &&
                  profile.prescription_analysis.decision_factors.length > 0 && (
                  <>
                    <Text style={styles.subLabel}>决策因素</Text>
                    <View style={styles.bulletList}>
                      {profile.prescription_analysis.decision_factors.map(
                        (factor, i) => (
                          <Text key={i} style={styles.bulletItem}>
                            • {factor}
                          </Text>
                        )
                      )}
                    </View>
                  </>
                )}
              </View>
            )}

            {/* 沟通建议 */}
            {profile?.communication_advice && (
              <View style={[styles.card, Shadow.card]}>
                <Text style={styles.sectionTitle}>💬 沟通建议</Text>
                <Text style={styles.profileText}>
                  最佳时间：{profile.communication_advice.best_time}
                </Text>
                <Text style={styles.profileText}>
                  偏好方式：{profile.communication_advice.preferred_channels.join('、')}
                </Text>
                {profile.communication_advice.topics_to_avoid &&
                  profile.communication_advice.topics_to_avoid.length > 0 && (
                  <>
                    <Text style={[styles.subLabel, { color: Colors.danger }]}>
                      避免话题
                    </Text>
                    <View style={styles.bulletList}>
                      {profile.communication_advice.topics_to_avoid.map(
                        (topic, i) => (
                          <Text
                            key={i}
                            style={[styles.bulletItem, { color: Colors.danger }]}
                          >
                            • {topic}
                          </Text>
                        )
                      )}
                    </View>
                  </>
                )}
              </View>
            )}

            {/* 合规风险 */}
            {profile?.compliance_risk && profile.compliance_risk.length > 0 && (
              <View style={[styles.card, styles.warningCard]}>
                <Text style={styles.sectionTitle}>⚠️ 合规风险提示</Text>
                <View style={styles.bulletList}>
                  {profile.compliance_risk.map((risk, i) => (
                    <Text key={i} style={styles.bulletItem}>
                      • {risk}
                    </Text>
                  ))}
                </View>
              </View>
            )}
          </View>
        ) : (
          <View style={styles.tabContent}>
            {interactions.length === 0 ? (
              <EmptyState
                icon="📋"
                title="暂无互动记录"
                description="完成首次拜访后这里会显示互动历史"
              />
            ) : (
              interactions.map((interaction) => (
                <View key={interaction.id} style={[styles.card, Shadow.card]}>
                  <View style={styles.interactionHead}>
                    <Text style={styles.interactionDate}>
                      {interaction.visit_date}
                    </Text>
                    <Text
                      style={[
                        styles.sentiment,
                        {
                          color:
                            interaction.sentiment === 'positive'
                              ? Colors.success
                              : interaction.sentiment === 'negative'
                              ? Colors.danger
                              : Colors.textHint,
                        },
                      ]}
                    >
                      {interaction.sentiment === 'positive'
                        ? '😊 积极'
                        : interaction.sentiment === 'negative'
                        ? '😔 消极'
                        : '😐 中性'}
                    </Text>
                  </View>
                  <Text style={styles.interactionProduct}>
                    {interaction.product_name}
                  </Text>
                  <Text style={styles.interactionSummary} numberOfLines={3}>
                    {interaction.summary}
                  </Text>
                  <Text style={styles.interactionOutcome}>
                    结果：{interaction.outcome}
                  </Text>
                </View>
              ))
            )}
          </View>
        )}
      </ScrollView>

      {/* 底部操作 */}
      <View style={styles.bottomBar}>
        <TouchableOpacity
          style={styles.prepareBtn}
          onPress={() =>
            navigation.navigate('VisitPrepare', {
              hcpId,
              hcpName: hcp.name,
            })
          }
          activeOpacity={0.8}
        >
          <Text style={styles.prepareBtnText}>开始拜访准备</Text>
        </TouchableOpacity>
      </View>
    </View>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1, backgroundColor: Colors.background },
  centered: { flex: 1, justifyContent: 'center', alignItems: 'center' },
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
  // 医生信息
  profileCard: {
    backgroundColor: Colors.white,
    alignItems: 'center',
    padding: Spacing.xxl,
    marginBottom: Spacing.sm,
  },
  avatarLarge: {
    width: 80,
    height: 80,
    borderRadius: 40,
    alignItems: 'center',
    justifyContent: 'center',
    marginBottom: Spacing.md,
  },
  avatarLargeText: { color: Colors.textWhite, fontSize: 32, fontWeight: '700' },
  name: { fontSize: FontSize.xxl, fontWeight: '700', color: Colors.textPrimary },
  dept: { fontSize: FontSize.sm, color: Colors.textSecondary, marginTop: 4 },
  title: { fontSize: FontSize.sm, color: Colors.textHint, marginTop: 2 },
  tagSection: { marginTop: Spacing.lg, width: '100%', alignItems: 'center' },
  tagRow: { flexDirection: 'row', flexWrap: 'wrap', gap: Spacing.sm, justifyContent: 'center' },
  tag: {
    backgroundColor: Colors.background,
    paddingHorizontal: Spacing.md,
    paddingVertical: Spacing.xs,
    borderRadius: BorderRadius.full,
    borderWidth: 1,
    borderColor: Colors.border,
  },
  tagText: { fontSize: FontSize.xs, color: Colors.textPrimary },
  addTagBtn: {
    paddingHorizontal: Spacing.md,
    paddingVertical: Spacing.xs,
    borderRadius: BorderRadius.full,
    borderWidth: 1,
    borderColor: Colors.primary,
    borderStyle: 'dashed',
  },
  addTagText: { fontSize: FontSize.xs, color: Colors.primary },
  tagHint: { fontSize: 10, color: Colors.textHint, marginTop: 4 },
  // Tab
  tabBar: {
    flexDirection: 'row',
    backgroundColor: Colors.white,
    borderBottomWidth: 1,
    borderBottomColor: Colors.divider,
  },
  tab: {
    flex: 1,
    paddingVertical: Spacing.md,
    alignItems: 'center',
    borderBottomWidth: 2,
    borderBottomColor: 'transparent',
  },
  tabActive: { borderBottomColor: Colors.primary },
  tabText: { fontSize: FontSize.md, color: Colors.textSecondary },
  tabTextActive: { color: Colors.primary, fontWeight: '600' },
  tabContent: { padding: Spacing.lg },
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
  subLabel: {
    fontSize: FontSize.sm,
    fontWeight: '600',
    color: Colors.textSecondary,
    marginTop: Spacing.md,
    marginBottom: Spacing.sm,
  },
  profileText: { fontSize: FontSize.md, color: Colors.textPrimary, lineHeight: 22 },
  bulletList: { gap: Spacing.xs },
  bulletItem: { fontSize: FontSize.md, color: Colors.textPrimary, lineHeight: 22 },
  warningCard: { backgroundColor: '#fef2f2', borderWidth: 1, borderColor: '#fecaca' },
  // 互动历史
  interactionHead: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
    marginBottom: Spacing.sm,
  },
  interactionDate: { fontSize: FontSize.sm, fontWeight: '600', color: Colors.textSecondary },
  sentiment: { fontSize: FontSize.sm, fontWeight: '600' },
  interactionProduct: { fontSize: FontSize.md, fontWeight: '600', color: Colors.textPrimary, marginBottom: 4 },
  interactionSummary: { fontSize: FontSize.sm, color: Colors.textSecondary, lineHeight: 20 },
  interactionOutcome: {
    fontSize: FontSize.sm,
    color: Colors.primary,
    marginTop: Spacing.sm,
    fontWeight: '500',
  },
  // 底部
  bottomBar: {
    padding: Spacing.lg,
    paddingBottom: 34,
    backgroundColor: Colors.white,
    borderTopWidth: 1,
    borderTopColor: Colors.divider,
  },
  prepareBtn: {
    backgroundColor: Colors.primary,
    borderRadius: BorderRadius.lg,
    paddingVertical: 16,
    alignItems: 'center',
  },
  prepareBtnText: { color: Colors.textWhite, fontSize: FontSize.lg, fontWeight: '700' },
});
