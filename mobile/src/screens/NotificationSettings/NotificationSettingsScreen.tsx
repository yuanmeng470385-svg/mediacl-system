/**
 * 通知设置页
 *
 * 2026-08-12 修复：移除 4 个 AsyncStorage 本地假开关（开关只存本地、后端无推送通道，
 * 打开/关闭都不产生任何效果，是"死开关"）→ 统一"即将上线"提示，不做假承诺。
 */
import React from 'react';
import { View, Text, ScrollView, StyleSheet, TouchableOpacity, Alert } from 'react-native';
import { useNavigation } from '@react-navigation/native';
import Icon from '../../components/Icon';
import { Colors, FontSize, Spacing, BorderRadius, Shadow } from '../../constants/theme';

const items = [
  { icon: 'calendar-check', label: '拜访提醒', desc: '拜访前15分钟推送提醒' },
  { icon: 'shield-alert', label: '合规告警', desc: '拦截到违规话术时通知' },
  { icon: 'message-text', label: '对话更新', desc: '数字专员有新的知识更新' },
  { icon: 'bell-ring', label: '系统通知', desc: '管理员公告与系统维护通知' },
];

export default function NotificationSettingsScreen() {
  const navigation = useNavigation();

  const handleComing = (label: string) => {
    Alert.alert('即将上线', `「${label}」推送通知功能正在开发中，上线后无需手动设置即可收到重要通知。`);
  };

  return (
    <View style={styles.container}>
      <View style={styles.header}>
        <TouchableOpacity onPress={() => navigation.goBack()}>
          <Icon name="chevron-left" size={22} color={Colors.textWhite} />
        </TouchableOpacity>
        <Text style={styles.headerTitle}>通知设置</Text>
        <View style={{ width: 24 }} />
      </View>
      <ScrollView contentContainerStyle={styles.content}>
        <View style={[styles.noticeCard, Shadow.card]}>
          <Icon name="bell-outline" size={18} color={Colors.primary} />
          <Text style={styles.noticeText}>
            推送通知功能尚未上线。合规红线拦截等关键告警在拜访中页面实时展示，不受影响。
          </Text>
        </View>
        <View style={[styles.card, Shadow.card]}>
          {items.map((item, i) => (
            <TouchableOpacity
              key={item.label}
              style={[styles.row, i < items.length - 1 && styles.rowBorder]}
              onPress={() => handleComing(item.label)}
              activeOpacity={0.7}
            >
              <View style={styles.iconBox}>
                <Icon name={item.icon} size={20} color={Colors.primary} />
              </View>
              <View style={styles.rowText}>
                <Text style={styles.label}>{item.label}</Text>
                <Text style={styles.desc}>{item.desc}</Text>
              </View>
              <View style={styles.comingBadge}>
                <Text style={styles.comingText}>即将上线</Text>
              </View>
            </TouchableOpacity>
          ))}
        </View>
        <View style={{ height: 40 }} />
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
  content: { padding: Spacing.lg },
  noticeCard: {
    backgroundColor: Colors.white, borderRadius: BorderRadius.xl,
    padding: Spacing.lg, flexDirection: 'row', gap: Spacing.md,
    marginBottom: Spacing.md, alignItems: 'center',
  },
  noticeText: { flex: 1, fontSize: FontSize.sm, color: Colors.textSecondary, lineHeight: 20 },
  card: { backgroundColor: Colors.white, borderRadius: BorderRadius.xl },
  row: {
    flexDirection: 'row', alignItems: 'center',
    padding: Spacing.lg, gap: Spacing.md,
  },
  rowBorder: { borderBottomWidth: StyleSheet.hairlineWidth, borderBottomColor: Colors.divider },
  iconBox: {
    width: 36, height: 36, borderRadius: 10,
    backgroundColor: Colors.primarySurface, alignItems: 'center', justifyContent: 'center',
  },
  rowText: { flex: 1 },
  label: { fontSize: FontSize.md, color: Colors.textPrimary, fontWeight: '500' },
  desc: { fontSize: FontSize.xs, color: Colors.textHint, marginTop: 2 },
  comingBadge: {
    paddingHorizontal: 10, paddingVertical: 4, borderRadius: BorderRadius.full,
    backgroundColor: Colors.background, borderWidth: 1, borderColor: Colors.border,
  },
  comingText: { fontSize: 10, color: Colors.textSecondary },
});
