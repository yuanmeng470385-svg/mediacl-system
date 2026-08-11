/**
 * 设置页 - 个人资料 / 通知 / 团队 / 关于
 */
import React, { useState } from 'react';
import {
  View, Text, ScrollView, StyleSheet, TouchableOpacity, Alert, Modal,
} from 'react-native';
import { useNavigation } from '@react-navigation/native';
import type { NativeStackNavigationProp } from '@react-navigation/native-stack';
import Icon from '../../components/Icon';
import { Colors, FontSize, Spacing, BorderRadius, Shadow } from '../../constants/theme';
import { useAuth } from '../../store/AuthContext';
import type { RootStackParamList } from '../../navigation/types';

type Nav = NativeStackNavigationProp<RootStackParamList>;

const APP_VERSION: string = require('../../../package.json').version;

type RowAction = 'profile' | 'notifications' | 'coming' | 'about';

const sections: { title: string; items: { icon: string; label: string; desc: string; action: RowAction }[] }[] = [
  { title: '个人资料', items: [
    { icon: 'account', label: '编辑资料', desc: '姓名、手机号、区域', action: 'profile' },
    { icon: 'shield-account', label: '账号安全', desc: '密码、绑定设备', action: 'coming' },
  ]},
  { title: '工作', items: [
    { icon: 'account-group', label: '我的团队', desc: '团队成员与协作', action: 'coming' },
    { icon: 'chart-bar', label: '业绩统计', desc: '拜访、对话、合规数据', action: 'coming' },
  ]},
  { title: '通用', items: [
    { icon: 'bell-outline', label: '通知', desc: '拜访提醒、合规告警等推送设置', action: 'notifications' },
    { icon: 'translate', label: '语言', desc: '简体中文', action: 'coming' },
    { icon: 'palette', label: '主题', desc: '临床精准 / 浅色', action: 'coming' },
    { icon: 'information', label: '关于 MedAgent', desc: 'v' + APP_VERSION, action: 'about' },
  ]},
];

export default function SettingsScreen() {
  const navigation = useNavigation<Nav>();
  const { user, logout } = useAuth();
  const [profileVisible, setProfileVisible] = useState(false);

  const handleRowPress = (action: RowAction) => {
    switch (action) {
      case 'profile':
        setProfileVisible(true);
        break;
      case 'notifications':
        navigation.navigate('NotificationSettings');
        break;
      case 'about':
        Alert.alert('关于 MedAgent', `MedAgent 医药代表数字员工系统\n版本 v${APP_VERSION}`);
        break;
      default:
        Alert.alert('提示', '该功能将在后续版本开放，敬请期待');
    }
  };

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
        <TouchableOpacity
          style={[styles.card, Shadow.card, { marginBottom: Spacing.md, padding: Spacing.lg }]}
          onPress={() => setProfileVisible(true)}
          activeOpacity={0.7}
        >
          <Text style={styles.label}>{user?.name || '未登录'}</Text>
          <Text style={styles.desc}>{(user?.department || '—') + ' · ' + (user?.region || '—') + ' · ' + (user?.role || '—')}</Text>
        </TouchableOpacity>
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
                  onPress={() => handleRowPress(item.action)}
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

      {/* 个人信息弹窗（后端无独立资料编辑接口，展示当前账号信息） */}
      <Modal
        visible={profileVisible}
        transparent
        animationType="fade"
        onRequestClose={() => setProfileVisible(false)}
      >
        <View style={styles.modalOverlay}>
          <View style={styles.modalBox}>
            <Text style={styles.modalTitle}>个人信息</Text>
            {[
              { label: '姓名', value: user?.name || '--' },
              { label: '手机号', value: user?.phone || '--' },
              { label: '角色', value: user?.role || '--' },
              { label: '区域', value: user?.region || '--' },
            ].map((row) => (
              <View key={row.label} style={styles.modalRow}>
                <Text style={styles.modalLabel}>{row.label}</Text>
                <Text style={styles.modalValue}>{row.value}</Text>
              </View>
            ))}
            <TouchableOpacity
              style={styles.modalCloseBtn}
              onPress={() => setProfileVisible(false)}
              activeOpacity={0.8}
            >
              <Text style={styles.modalCloseText}>关闭</Text>
            </TouchableOpacity>
          </View>
        </View>
      </Modal>
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
  // 个人信息弹窗
  modalOverlay: {
    flex: 1, backgroundColor: 'rgba(0,0,0,0.5)',
    justifyContent: 'center', padding: Spacing.xxl,
  },
  modalBox: {
    backgroundColor: Colors.white, borderRadius: BorderRadius.xl,
    padding: Spacing.xl,
  },
  modalTitle: {
    fontSize: FontSize.lg, fontWeight: '700', color: Colors.textPrimary,
    textAlign: 'center', marginBottom: Spacing.lg,
  },
  modalRow: {
    flexDirection: 'row', justifyContent: 'space-between',
    paddingVertical: Spacing.md, borderBottomWidth: StyleSheet.hairlineWidth,
    borderBottomColor: Colors.divider,
  },
  modalLabel: { fontSize: FontSize.md, color: Colors.textSecondary },
  modalValue: { fontSize: FontSize.md, color: Colors.textPrimary, fontWeight: '500' },
  modalCloseBtn: {
    backgroundColor: Colors.primary, borderRadius: BorderRadius.lg,
    paddingVertical: 14, alignItems: 'center', marginTop: Spacing.xl,
  },
  modalCloseText: { color: Colors.textWhite, fontSize: FontSize.md, fontWeight: '600' },
});
