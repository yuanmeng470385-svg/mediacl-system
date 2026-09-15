/**
 * 分身管理入口 hub（2026-09-15 重构）：双入口——
 * 「我的分身」（列表/风格/暂停/删除）与「创建分身」（三步向导：问卷→记录→起名）。
 * 原内嵌 5 题问卷与 StyleSource 独立屏均收编进向导（CreateTwinWizardScreen）。
 */
import React from 'react';
import { StyleSheet, Text, TouchableOpacity, View } from 'react-native';
import { useNavigation } from '@react-navigation/native';
import type { NativeStackNavigationProp } from '@react-navigation/native-stack';
import Icon from '../../components/Icon';
import type { RootStackParamList } from '../../navigation/types';
import { BorderRadius, Colors, FontSize, Shadow, Spacing } from '../../constants/theme';

type Nav = NativeStackNavigationProp<RootStackParamList>;

export default function TwinManageScreen() {
  const navigation = useNavigation<Nav>();

  return (
    <View style={styles.container}>
      <View style={styles.header}>
        <TouchableOpacity onPress={() => navigation.goBack()}>
          <Icon name="chevron-left" size={22} color={Colors.textWhite} />
        </TouchableOpacity>
        <Text style={styles.headerTitle}>分身管理</Text>
        <View style={{ width: 24 }} />
      </View>

      <View style={styles.content}>
        <TouchableOpacity
          style={[styles.entryCard, Shadow.card]}
          activeOpacity={0.7}
          onPress={() => navigation.navigate('MyTwins')}
        >
          <View style={styles.iconBox}>
            <Icon name="robot-outline" size={24} color={Colors.primary} />
          </View>
          <View style={{ flex: 1 }}>
            <Text style={styles.entryTitle}>我的分身</Text>
            <Text style={styles.entryDesc}>查看已创建的分身，调整风格、暂停或删除</Text>
          </View>
          <Icon name="chevron-right" size={18} color={Colors.border} />
        </TouchableOpacity>

        <TouchableOpacity
          style={[styles.entryCard, Shadow.card]}
          activeOpacity={0.7}
          onPress={() => navigation.navigate('CreateTwin')}
        >
          <View style={styles.iconBox}>
            <Icon name="account-tie-outline" size={24} color={Colors.primary} />
          </View>
          <View style={{ flex: 1 }}>
            <Text style={styles.entryTitle}>创建分身</Text>
            <Text style={styles.entryDesc}>5 题问卷定方向 + 真实对话记录提炼风格，三步生成</Text>
          </View>
          <Icon name="chevron-right" size={18} color={Colors.border} />
        </TouchableOpacity>
      </View>
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
  entryCard: {
    backgroundColor: Colors.card, borderRadius: BorderRadius.md, padding: Spacing.lg,
    marginBottom: Spacing.md, flexDirection: 'row', alignItems: 'center', gap: Spacing.md,
  },
  iconBox: {
    width: 48, height: 48, borderRadius: BorderRadius.lg,
    backgroundColor: Colors.primarySurface, alignItems: 'center', justifyContent: 'center',
  },
  entryTitle: { fontSize: FontSize.md, fontWeight: '600', color: Colors.textPrimary, marginBottom: 2 },
  entryDesc: { fontSize: FontSize.sm, color: Colors.textSecondary, lineHeight: 20 },
});
