/**
 * 设置页 - 个人资料 / 团队 / 关于
 */
import React from 'react';
import { View, Text, ScrollView, StyleSheet, TouchableOpacity, Alert } from 'react-native';
import { useNavigation } from '@react-navigation/native';
import Icon from '../../components/Icon';
import { Colors, FontSize, Spacing, BorderRadius, Shadow } from '../../constants/theme';
import { useAuth } from '../../store/AuthContext';

const APP_VERSION: string = require('../../package.json').version;

const sections = [
  { title: '个人资料', items: [
    { icon: 'account', label: '编辑资料', desc: '姓名、手机号、区域' },
    { icon: 'shield-account', label: '账号安全', desc: '密码、绑定设备' },
  ]},
  { title: '工作', items: [
    { icon: 'account-group', label: '我的团队', desc: '团队成员与协作' },
    { icon: 'chart-bar', label: '业绩统计', desc: '拜访、对话、合规数据' },
  ]},
  { title: '通用', items: [
    { icon: 'translate', label: '语言', desc: '简体中文' },
    { icon: 'palette', label: '主题', desc: '临床精准 / 浅色' },
    { icon: 'information', label: '关于 MedAgent', desc: 'v' + APP_VERSION },
  ]},
];

export default function SettingsScreen() {
  const navigation = useNavigation();
  const { user, logout } = useAuth();

  return (
    <View style={styles.container}>
      <View style={styles.header}>
        <TouchableOpacity onPress={() => navigation.goBack()}>
          <Icon name="chevron-left" size={22} color={Colors.textWhite} />
        </TouchableOpacity>
        <Text style={styles.headerTitle}>设置</Text>
        <View style={{ width: 24 }} />
      </View>
      <ScrollView contentContainerStyle={styles.content}>
        <View style={[styles.card, Shadow.card, { marginBottom: Spacing.md, padding: Spacing.lg }]}>
          <Text style={styles.label}>{user?.name || '未登录'}</Text>
          <Text style={styles.desc}>{(user?.department || '—') + ' · ' + (user?.region || '—') + ' · ' + (user?.role || '—')}</Text>
        </View>
        <TouchableOpacity
          style={[styles.card, Shadow.card, { marginBottom: Spacing.lg, alignItems: 'center', padding: Spacing.lg }]}
          onPress={() => Alert.alert('退出登录', '确定要退出当前账号吗？', [
            { text: '取消', style: 'cancel' },
            { text: '退出', style: 'destructive', onPress: logout },
          ])}
        >
          <Text style={{ color: Colors.danger, fontSize: FontSize.md }}>退出登录</Text>
        </TouchableOpacity>
        {sections.map((section, si) => (
          <View key={si}>
            <Text style={styles.sectionTitle}>{section.title}</Text>
            <View style={[styles.card, Shadow.card]}>
              {section.items.map((item, ii) => (
                <TouchableOpacity
                  key={ii}
                  style={[styles.row, ii < section.items.length - 1 && styles.rowBorder]}
                  activeOpacity={0.7}
                >
                  <View style={styles.iconBox}>
                    <Icon name={item.icon} size={20} color={Colors.primary} />
                  </View>
                  <View style={styles.rowText}>
                    <Text style={styles.label}>{item.label}</Text>
                    <Text style={styles.desc}>{item.desc}</Text>
                  </View>
                  <Icon name="chevron-right" size={20} color={Colors.textHint} />
                </TouchableOpacity>
              ))}
            </View>
          </View>
        ))}
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
  sectionTitle: {
    fontSize: FontSize.sm, fontWeight: '600', color: Colors.textSecondary,
    marginTop: Spacing.lg, marginBottom: Spacing.sm, marginLeft: Spacing.xs,
  },
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
});
