/**
 * 医生详情页 - 基本信息 + 画像 + 互动历史
 *
 * 数据契约：hcp / profile / interactions 全部由 api 层（src/api/hcp.ts）映射为屏幕消费形状，
 * 屏幕不直接读后端原生字段。
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
  Modal,
  TextInput,
} from 'react-native';
import { useRoute, useNavigation } from '@react-navigation/native';
import type { RouteProp } from '@react-navigation/native';
import type { NativeStackNavigationProp } from '@react-navigation/native-stack';
import EmptyState from '../../components/EmptyState';
import Icon from '../../components/Icon';
import { ActionIcons } from '../../components/Icon';
import { hcpAPI } from '../../api/hcp';
import { Colors, FontSize, Spacing, BorderRadius, Shadow } from '../../constants/theme';
import type { RootStackParamList, HCPDetailParams } from '../../navigation/types';
import type { HCP, HCPProfile, HCPInteraction } from '../../types';

type RouteType = RouteProp<{ HCPDetail: HCPDetailParams }, 'HCPDetail'>;
type Nav = NativeStackNavigationProp<RootStackParamList>;

/** ISO/带空格时间 → "YYYY-MM-DD HH:mm"（空值回退 '--'） */
function formatVisitDate(v?: string): string {
  if (!v) return '--';
  const s = String(v).replace('T', ' ');
  return s.length > 16 ? s.slice(0, 16) : s;
}

export default function HCPDetailScreen() {
  const route = useRoute<RouteType>();
  const navigation = useNavigation<Nav>();
  const { hcpId } = route.params;

  const [hcp, setHcp] = useState<HCP | null>(null);
  const [profile, setProfile] = useState<HCPProfile | null>(null);
  const [interactions, setInteractions] = useState<HCPInteraction[]>([]);
  const [loading, setLoading] = useState(true);
  const [activeTab, setActiveTab] = useState<'profile' | 'history'>('profile');
  const [tagModalVisible, setTagModalVisible] = useState(false);
  const [newTag, setNewTag] = useState('');

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
    setNewTag('');
    setTagModalVisible(true);
  };

  const confirmAddTag = async () => {
    const tag = newTag.trim();
    setTagModalVisible(false);
    if (!tag || !hcp) return;
    try {
      await hcpAPI.addTags(hcpId, [tag]);
      setHcp({ ...hcp, tags: [...(hcp.tags || []), tag] });
    } catch {
      Alert.alert('失败', '添加标签失败');
    }
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
        icon="doctor"
        title="医生不存在"
        description="该医生信息可能已被删除"
      />
    );
  }

  // 画像是否有可渲染内容（无 → 显示"暂无画像"而非空白）
  const hasProfileContent = !!(
    profile?.academic_profile ||
    profile?.prescription_analysis ||
    profile?.communication_advice ||
    (profile?.compliance_risk && profile.compliance_risk.length > 0)
  );

  return (
    <View style={styles.container}>
      {/* 头部 */}
      <View style={styles.header}>
        <TouchableOpacity onPress={() => navigation.goBack()}>
          <Icon name={ActionIcons.back} size={22} color={Colors.textWhite} />
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
            {/* AI 画像未生成/降级 → "暂无画像"，而非空白 */}
            {profile && !hasProfileContent ? (
              <View style={[styles.card, Shadow.card]}>
                <Text style={styles.sectionTitle}>AI 画像</Text>
                <Text style={styles.profileText}>
                  {profile.ai_unavailable_reason || '暂无画像'}
                </Text>
              </View>
            ) : (
              <>
                {/* 学术背景 */}
                {profile?.academic_profile && (
                  <View style={[styles.card, Shadow.card]}>
                    <Text style={styles.sectionTitle}>学术背景</Text>
                    <Text style={styles.profileText}>
                      {profile.academic_profile.background}
                    </Text>
                    {profile.academic_profile.research_interests &&
                      profile.academic_profile.research_interests.length > 0 && (
                        <>
                          <Text style={styles.subLabel}>研究方向</Text>
                          <Text style={styles.profileText}>
                            {profile.academic_profile.research_interests.join('、')}
                          </Text>
                        </>
                      )}
                  </View>
                )}

                {/* 处方偏好 */}
                {profile?.prescription_analysis && (
                  <View style={[styles.card, Shadow.card]}>
                    <Text style={styles.sectionTitle}>处方偏好</Text>
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
                    <Text style={styles.sectionTitle}>沟通建议</Text>
                    {profile.communication_advice.raw_text ? (
                      <Text style={styles.profileText}>
                        {profile.communication_advice.raw_text}
                      </Text>
                    ) : (
                      <>
                        {profile.communication_advice.best_time ? (
                          <Text style={styles.profileText}>
                            最佳时间：{profile.communication_advice.best_time}
                          </Text>
                        ) : null}
                        {profile.communication_advice.preferred_channels &&
                          profile.communication_advice.preferred_channels.length > 0 && (
                            <Text style={styles.profileText}>
                              偏好方式：
                              {profile.communication_advice.preferred_channels.join('、')}
                            </Text>
                          )}
                        {profile.communication_advice.topics_to_avoid &&
                          profile.communication_advice.topics_to_avoid.length > 0 && (
                            <>
                              <Text
                                style={[styles.subLabel, { color: Colors.danger }]}
                              >
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
                      </>
                    )}
                  </View>
                )}

                {/* 合规风险 */}
                {profile?.compliance_risk && profile.compliance_risk.length > 0 && (
                  <View style={[styles.card, styles.warningCard]}>
                    <Text style={[styles.sectionTitle, { color: Colors.danger }]}>合规风险提示</Text>
                    <View style={styles.bulletList}>
                      {profile.compliance_risk.map((risk, i) => (
                        <Text key={i} style={styles.bulletItem}>
                          • {risk.description}
                        </Text>
                      ))}
                    </View>
                  </View>
                )}
              </>
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
                      {formatVisitDate(interaction.visit_date)}
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
                        ? '积极'
                        : interaction.sentiment === 'negative'
                        ? '消极'
                        : '中性'}
                    </Text>
                  </View>
                  <Text style={styles.interactionSummary} numberOfLines={3}>
                    {interaction.summary || '暂无摘要'}
                  </Text>
                  {interaction.key_points &&
                    interaction.key_points.length > 0 && (
                      <View style={styles.keyPointList}>
                        {interaction.key_points.map((point, i) => (
                          <Text key={i} style={styles.bulletItem}>
                            • {point}
                          </Text>
                        ))}
                      </View>
                    )}
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

      {/* 添加标签弹窗（自建 Modal，Android/iOS 均可输入） */}
      <Modal
        visible={tagModalVisible}
        transparent
        animationType="fade"
        onRequestClose={() => setTagModalVisible(false)}
      >
        <View style={styles.modalMask}>
          <View style={styles.modalCard}>
            <Text style={styles.modalTitle}>添加标签</Text>
            <TextInput
              style={styles.modalInput}
              value={newTag}
              onChangeText={setNewTag}
              placeholder="请输入标签名称"
              placeholderTextColor={Colors.textHint}
              autoFocus
              maxLength={20}
              returnKeyType="done"
              onSubmitEditing={confirmAddTag}
            />
            <View style={styles.modalBtnRow}>
              <TouchableOpacity
                style={[styles.modalBtn, styles.modalBtnSecondary]}
                onPress={() => setTagModalVisible(false)}
                activeOpacity={0.8}
              >
                <Text style={styles.modalBtnSecondaryText}>取消</Text>
              </TouchableOpacity>
              <TouchableOpacity
                style={[styles.modalBtn, styles.modalBtnPrimary]}
                onPress={confirmAddTag}
                activeOpacity={0.8}
              >
                <Text style={styles.modalBtnPrimaryText}>确定</Text>
              </TouchableOpacity>
            </View>
          </View>
        </View>
      </Modal>
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
  interactionSummary: { fontSize: FontSize.sm, color: Colors.textSecondary, lineHeight: 20 },
  keyPointList: { gap: Spacing.xs, marginTop: Spacing.sm },
  // 添加标签弹窗
  modalMask: {
    flex: 1,
    backgroundColor: 'rgba(0, 0, 0, 0.4)',
    alignItems: 'center',
    justifyContent: 'center',
    padding: Spacing.lg,
  },
  modalCard: {
    width: '100%',
    maxWidth: 340,
    backgroundColor: Colors.white,
    borderRadius: BorderRadius.lg,
    padding: Spacing.lg,
  },
  modalTitle: {
    fontSize: FontSize.lg,
    fontWeight: '700',
    color: Colors.textPrimary,
    textAlign: 'center',
    marginBottom: Spacing.lg,
  },
  modalInput: {
    borderWidth: 1,
    borderColor: Colors.border,
    borderRadius: BorderRadius.md,
    paddingHorizontal: Spacing.md,
    paddingVertical: 10,
    fontSize: FontSize.md,
    color: Colors.textPrimary,
  },
  modalBtnRow: {
    flexDirection: 'row',
    gap: Spacing.md,
    marginTop: Spacing.lg,
  },
  modalBtn: {
    flex: 1,
    paddingVertical: 10,
    borderRadius: BorderRadius.md,
    alignItems: 'center',
  },
  modalBtnSecondary: { backgroundColor: Colors.background },
  modalBtnSecondaryText: { fontSize: FontSize.md, color: Colors.textSecondary },
  modalBtnPrimary: { backgroundColor: Colors.primary },
  modalBtnPrimaryText: { fontSize: FontSize.md, fontWeight: '600', color: Colors.textWhite },
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
