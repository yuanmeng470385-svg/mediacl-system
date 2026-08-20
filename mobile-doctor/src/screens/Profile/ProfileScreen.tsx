/**
 * 我的 Tab（B9 填真实现）：
 *   登录用户信息卡（useAuth）+ 医师资格认证入口（→ CertUpload）+ 退出登录
 *   照 mobile SettingsScreen 的卡片/退出模式，样式令牌照 theme.ts
 */
import React, { useCallback, useState } from 'react';
import {
  Alert,
  ScrollView,
  StyleSheet,
  Text,
  TouchableOpacity,
  View,
} from 'react-native';
import { useFocusEffect, useNavigation } from '@react-navigation/native';
import type { NativeStackNavigationProp } from '@react-navigation/native-stack';
import Icon, { ActionIcons, FeatureIcons } from '../../components/Icon';
import { useAuth } from '../../store/AuthContext';
import { doctorAPI } from '../../api/doctor';
import type { RootStackParamList } from '../../navigation/types';
import { BorderRadius, Colors, FontSize, Shadow, Spacing } from '../../constants/theme';

type Nav = NativeStackNavigationProp<RootStackParamList>;

const CERT_STATUS_TEXT: Record<string, string> = {
  pending: '待审核',
  approved: '已通过',
  rejected: '已驳回',
};

const ROLE_TEXT: Record<string, string> = {
  doctor: '医生',
  admin: '管理员',
  manager: '管理者',
  rep: '医药代表',
  compliance: '合规专员',
  medical: '医学部',
  finance: '财务',
};

export default function ProfileScreen() {
  const navigation = useNavigation<Nav>();
  const { user, logout } = useAuth();
  const [certStatus, setCertStatus] = useState<string>('');

  // 每次回到本 Tab 刷新资质状态（提交/审核后回来看最新进度）
  useFocusEffect(
    useCallback(() => {
      let cancelled = false;
      doctorAPI
        .getMyCert()
        .then((cert) => {
          if (!cancelled) setCertStatus(cert?.cert_status || '');
        })
        .catch(() => {
          // 静默失败：入口行副标题退化为不带状态
        });
      return () => {
        cancelled = true;
      };
    }, [])
  );

  const confirmLogout = () => {
    Alert.alert('退出登录', '确定要退出当前账号吗？', [
      { text: '取消', style: 'cancel' },
      { text: '退出', style: 'destructive', onPress: logout },
    ]);
  };

  const initials = (user?.name || '医').slice(0, 2);
  const certStatusText = certStatus ? CERT_STATUS_TEXT[certStatus] || certStatus : '';

  return (
    <View style={styles.container}>
      <View style={styles.header}>
        <Text style={styles.headerTitle}>我的</Text>
        <Text style={styles.headerSubtitle}>账号信息与医师资格认证</Text>
      </View>

      <ScrollView contentContainerStyle={styles.content}>
        {/* 登录用户信息卡 */}
        <View style={[styles.card, Shadow.card, styles.userCard]}>
          <View style={styles.avatar}>
            <Text style={styles.avatarText}>{initials}</Text>
          </View>
          <View style={styles.userInfo}>
            <Text style={styles.userName}>{user?.name || '未登录'}</Text>
            <Text style={styles.userMeta}>
              {ROLE_TEXT[user?.role || ''] || user?.role || '—'}
            </Text>
          </View>
        </View>
        <View style={[styles.card, Shadow.card]}>
          {[
            { label: '手机号', value: user?.phone || '—' },
            { label: '科室', value: user?.department || '—' },
            { label: '地区', value: user?.region || '—' },
          ].map((row, i) => (
            <View key={row.label} style={[styles.infoRow, i > 0 && styles.rowBorder]}>
              <Text style={styles.infoLabel}>{row.label}</Text>
              <Text style={styles.infoValue}>{row.value}</Text>
            </View>
          ))}
        </View>

        {/* 学术卡片入口 */}
        <TouchableOpacity
          style={[styles.card, Shadow.card, styles.entryRow]}
          onPress={() => navigation.navigate('Inbox')}
          activeOpacity={0.7}
        >
          <View style={styles.iconBox}>
            <Icon name={FeatureIcons.content} size={20} color={Colors.primary} />
          </View>
          <View style={styles.rowText}>
            <Text style={styles.label}>学术卡片</Text>
            <Text style={styles.desc}>查看医药代表推送的学术内容</Text>
          </View>
          <Icon name="chevron-right" size={20} color={Colors.textHint} />
        </TouchableOpacity>

        {/* 偏好 + 个性化学术简报入口 */}
        <TouchableOpacity
          style={[styles.card, Shadow.card, styles.entryRow]}
          onPress={() => navigation.navigate('Preferences')}
          activeOpacity={0.7}
        >
          <View style={styles.iconBox}>
            <Icon name={FeatureIcons.knowledge} size={20} color={Colors.primary} />
          </View>
          <View style={styles.rowText}>
            <Text style={styles.label}>学术偏好</Text>
            <Text style={styles.desc}>设置兴趣领域与个性化学术简报</Text>
          </View>
          <Icon name="chevron-right" size={20} color={Colors.textHint} />
        </TouchableOpacity>

        {/* 官方广场入口 */}
        <TouchableOpacity
          style={[styles.card, Shadow.card, styles.entryRow]}
          onPress={() => navigation.navigate('DoctorPlaza')}
          activeOpacity={0.7}
        >
          <View style={styles.iconBox}>
            <Icon name={FeatureIcons.specialist} size={20} color={Colors.primary} />
          </View>
          <View style={styles.rowText}>
            <Text style={styles.label}>官方广场</Text>
            <Text style={styles.desc}>浏览并添加官方公共数字员工</Text>
          </View>
          <Icon name="chevron-right" size={20} color={Colors.textHint} />
        </TouchableOpacity>

        {/* 患教工具入口 */}
        <TouchableOpacity
          style={[styles.card, Shadow.card, styles.entryRow]}
          onPress={() => navigation.navigate('PatientEdu')}
          activeOpacity={0.7}
        >
          <View style={styles.iconBox}>
            <Icon name={FeatureIcons.content} size={20} color={Colors.primary} />
          </View>
          <View style={styles.rowText}>
            <Text style={styles.label}>患教工具</Text>
            <Text style={styles.desc}>选择模板生成患者教育卡片</Text>
          </View>
          <Icon name="chevron-right" size={20} color={Colors.textHint} />
        </TouchableOpacity>

        {/* 收藏历史入口 */}
        <TouchableOpacity
          style={[styles.card, Shadow.card, styles.entryRow]}
          onPress={() => navigation.navigate('Favorites')}
          activeOpacity={0.7}
        >
          <View style={styles.iconBox}>
            <Icon name={ActionIcons.star} size={20} color={Colors.primary} />
          </View>
          <View style={styles.rowText}>
            <Text style={styles.label}>收藏历史</Text>
            <Text style={styles.desc}>查看本人收藏的问答</Text>
          </View>
          <Icon name="chevron-right" size={20} color={Colors.textHint} />
        </TouchableOpacity>

        {/* 医师资格认证入口 */}
        <TouchableOpacity
          style={[styles.card, Shadow.card, styles.entryRow]}
          onPress={() => navigation.navigate('CertUpload')}
          activeOpacity={0.7}
        >
          <View style={styles.iconBox}>
            <Icon name={FeatureIcons.compliance} size={20} color={Colors.primary} />
          </View>
          <View style={styles.rowText}>
            <Text style={styles.label}>医师资格认证</Text>
            <Text style={styles.desc}>
              {certStatusText
                ? `提交医师资格证/执业证书，审核进度：${certStatusText}`
                : '提交医师资格证/执业证书，查看审核进度'}
            </Text>
          </View>
          <Icon name="chevron-right" size={20} color={Colors.textHint} />
        </TouchableOpacity>

        {/* 退出登录 */}
        <TouchableOpacity
          style={[styles.card, Shadow.card, styles.logoutBtn]}
          onPress={confirmLogout}
          activeOpacity={0.7}
        >
          <Text style={styles.logoutText}>退出登录</Text>
        </TouchableOpacity>
      </ScrollView>
    </View>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1, backgroundColor: Colors.background },
  header: {
    backgroundColor: Colors.primary,
    paddingHorizontal: Spacing.xl,
    paddingTop: 52,
    paddingBottom: Spacing.xl,
  },
  headerTitle: { color: Colors.textWhite, fontSize: FontSize.xl, fontWeight: '700' },
  headerSubtitle: {
    color: 'rgba(255,255,255,0.7)',
    fontSize: FontSize.sm,
    marginTop: 4,
  },
  content: { padding: Spacing.lg },
  card: {
    backgroundColor: Colors.white,
    borderRadius: BorderRadius.lg,
    marginBottom: Spacing.md,
  },
  userCard: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: Spacing.lg,
    padding: Spacing.lg,
  },
  avatar: {
    width: 56,
    height: 56,
    borderRadius: 28,
    backgroundColor: Colors.primary,
    alignItems: 'center',
    justifyContent: 'center',
  },
  avatarText: { color: Colors.textWhite, fontSize: FontSize.lg, fontWeight: '700' },
  userInfo: { flex: 1, gap: 4 },
  userName: { fontSize: FontSize.lg, fontWeight: '600', color: Colors.textPrimary },
  userMeta: { fontSize: FontSize.sm, color: Colors.textSecondary },
  infoRow: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    paddingHorizontal: Spacing.lg,
    paddingVertical: Spacing.md,
  },
  rowBorder: { borderTopWidth: StyleSheet.hairlineWidth, borderTopColor: Colors.divider },
  infoLabel: { fontSize: FontSize.md, color: Colors.textSecondary },
  infoValue: { fontSize: FontSize.md, color: Colors.textPrimary, fontWeight: '500' },
  entryRow: {
    flexDirection: 'row',
    alignItems: 'center',
    padding: Spacing.lg,
    gap: Spacing.md,
  },
  iconBox: {
    width: 36,
    height: 36,
    borderRadius: 10,
    backgroundColor: Colors.primarySurface,
    alignItems: 'center',
    justifyContent: 'center',
  },
  rowText: { flex: 1 },
  label: { fontSize: FontSize.md, color: Colors.textPrimary, fontWeight: '500' },
  desc: { fontSize: FontSize.xs, color: Colors.textHint, marginTop: 2 },
  logoutBtn: {
    alignItems: 'center',
    padding: Spacing.lg,
    marginTop: Spacing.sm,
  },
  logoutText: { color: Colors.danger, fontSize: FontSize.md, fontWeight: '600' },
});
