/**
 * 通知设置页
 */
import React, { useEffect, useState } from 'react';
import { View, Text, ScrollView, StyleSheet, Switch, TouchableOpacity } from 'react-native';
import AsyncStorage from '@react-native-async-storage/async-storage';
import { useNavigation } from '@react-navigation/native';
import Icon from '../../components/Icon';
import { Colors, FontSize, Spacing, BorderRadius, Shadow } from '../../constants/theme';

const STORAGE_KEY = 'notification_settings';
const DEFAULT_TOGGLES = { visit_reminder: true, compliance_alert: true, chat_update: false, system: true };

const items = [
  { icon: 'calendar-check', label: '拜访提醒', desc: '拜访前15分钟推送提醒', key: 'visit_reminder' },
  { icon: 'shield-alert', label: '合规告警', desc: '拦截到违规话术时通知', key: 'compliance_alert' },
  { icon: 'message-text', label: '对话更新', desc: '数字专员有新的知识更新', key: 'chat_update' },
  { icon: 'bell-ring', label: '系统通知', desc: '管理员公告与系统维护通知', key: 'system' },
];

export default function NotificationSettingsScreen() {
  const navigation = useNavigation();
  const [toggles, setToggles] = useState<Record<string, boolean>>(DEFAULT_TOGGLES);

  useEffect(() => {
    let cancelled = false;
    AsyncStorage.getItem(STORAGE_KEY)
      .then((raw) => {
        if (!raw || cancelled) return;
        const saved = JSON.parse(raw);
        if (saved && typeof saved === 'object') {
          setToggles((prev) => ({ ...DEFAULT_TOGGLES, ...saved }));
        }
      })
      .catch(() => { /* 读失败用默认值 */ });
    return () => { cancelled = true; };
  }, []);

  const toggle = (key: string, value: boolean) => {
    setToggles((prev) => {
      const next = { ...prev, [key]: value };
      AsyncStorage.setItem(STORAGE_KEY, JSON.stringify(next)).catch(() => {});
      return next;
    });
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
        <View style={[styles.card, Shadow.card]}>
          {items.map((item, i) => (
            <View key={item.key} style={[styles.row, i < items.length - 1 && styles.rowBorder]}>
              <View style={styles.iconBox}>
                <Icon name={item.icon} size={20} color={Colors.primary} />
              </View>
              <View style={styles.rowText}>
                <Text style={styles.label}>{item.label}</Text>
                <Text style={styles.desc}>{item.desc}</Text>
              </View>
              <Switch
                value={toggles[item.key]}
                onValueChange={(v) => toggle(item.key, v)}
                trackColor={{ false: Colors.border, true: Colors.primaryLight }}
                thumbColor={toggles[item.key] ? Colors.primary : Colors.white}
              />
            </View>
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
