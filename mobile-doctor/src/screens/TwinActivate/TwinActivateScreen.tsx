/**
 * 分身激活页：分享链接 token 激活 + 知情同意弹窗 + 订阅
 *
 * 知情同意去重语义（一期简化）：每次从链接激活都走 activate；
 * 已订阅（subscribed=true）直接进对话跳过弹窗；未订阅弹知情同意 Modal，
 * 同意后 subscribe（consent_agreed: true 已含）再进对话。
 * 同代表多分身"不重复弹窗"由后端 consent 留痕 + 前端 subscribed 判定兜底。
 */
import React, { useState } from 'react';
import {
  Alert,
  Modal,
  StyleSheet,
  Text,
  TextInput,
  TouchableOpacity,
  View,
  ActivityIndicator,
} from 'react-native';
import { useNavigation, useRoute } from '@react-navigation/native';
import type { NativeStackNavigationProp } from '@react-navigation/native-stack';
import type { RouteProp } from '@react-navigation/native';
import Icon, { ActionIcons, FeatureIcons } from '../../components/Icon';
import { twinAPI } from '../../api/twin';
import type { TwinInfo } from '../../types';
import type { RootStackParamList } from '../../navigation/types';
import { BorderRadius, Colors, FontSize, Shadow, Spacing } from '../../constants/theme';

type Nav = NativeStackNavigationProp<RootStackParamList>;
type RouteType = RouteProp<RootStackParamList, 'TwinActivate'>;

export default function TwinActivateScreen() {
  const navigation = useNavigation<Nav>();
  const route = useRoute<RouteType>();
  const [token, setToken] = useState(route.params?.token || '');
  const [activating, setActivating] = useState(false);
  const [pendingTwin, setPendingTwin] = useState<TwinInfo | null>(null);
  const [subscribing, setSubscribing] = useState(false);

  const activate = async (tokenToUse: string) => {
    setActivating(true);
    try {
      const res = await twinAPI.activate(tokenToUse); // {twin, subscribed}
      if (res.subscribed) {
        navigation.replace('TwinChat', {
          twinId: res.twin.id,
          twinName: res.twin.name,
        });
        return;
      }
      setPendingTwin(res.twin); // 弹知情同意 Modal
    } catch (e: any) {
      Alert.alert('激活失败', e.message || '请检查分享链接后重试');
    } finally {
      setActivating(false);
    }
  };

  const handleActivate = () => {
    const trimmed = token.trim();
    if (!trimmed) {
      Alert.alert('提示', '请输入分享链接中的激活码');
      return;
    }
    activate(trimmed);
  };

  const agree = async () => {
    if (!pendingTwin) return;
    setSubscribing(true);
    try {
      await twinAPI.subscribe(pendingTwin.id); // consent_agreed: true 已含
      navigation.replace('TwinChat', {
        twinId: pendingTwin.id,
        twinName: pendingTwin.name,
      });
    } catch (e: any) {
      Alert.alert('添加失败', e.message || '请稍后重试');
      setSubscribing(false);
    }
  };

  const decline = () => {
    setPendingTwin(null);
  };

  return (
    <View style={styles.container}>
      <View style={styles.header}>
        <TouchableOpacity onPress={() => navigation.goBack()}>
          <Icon name={ActionIcons.back} size={22} color={Colors.textWhite} />
        </TouchableOpacity>
        <Text style={styles.headerTitle}>添加数字员工</Text>
        <View style={{ width: 24 }} />
      </View>

      <View style={styles.content}>
        <View style={[styles.card, Shadow.card]}>
          <View style={styles.iconRow}>
            <Icon name={FeatureIcons.specialist} size={28} color={Colors.primary} />
            <Text style={styles.cardTitle}>通过分享链接激活</Text>
          </View>
          <Text style={styles.desc}>
            输入医药代表分享链接中的激活码，即可添加其数字员工分身
          </Text>
          <TextInput
            style={styles.input}
            value={token}
            onChangeText={setToken}
            placeholder="粘贴激活码"
            placeholderTextColor={Colors.textHint}
            autoCapitalize="none"
            autoCorrect={false}
          />
          <TouchableOpacity
            style={[styles.activateBtn, activating && { opacity: 0.6 }]}
            onPress={handleActivate}
            disabled={activating}
            activeOpacity={0.7}
          >
            {activating ? (
              <ActivityIndicator color={Colors.textWhite} size="small" />
            ) : (
              <Text style={styles.activateBtnText}>激活并查看</Text>
            )}
          </TouchableOpacity>
        </View>
      </View>

      {/* 知情同意 Modal（文案逐字对齐需求 5.3(5)） */}
      <Modal
        visible={pendingTwin !== null}
        transparent
        animationType="fade"
        onRequestClose={decline}
      >
        <View style={styles.modalMask}>
          <View style={styles.modalCard}>
            <Text style={styles.modalTitle}>知情同意</Text>
            <Text style={styles.modalBody}>
              您即将添加数字员工「{pendingTwin?.name}」。与该数字员工的对话内容将同步给
              该数字员工所属医药代表（用于次日简报）及平台合规审计。
              该数字员工由 AI 生成，其回答不构成诊疗建议。
            </Text>
            <View style={styles.modalActions}>
              <TouchableOpacity
                style={[styles.modalBtn, styles.modalBtnSecondary]}
                onPress={decline}
                disabled={subscribing}
                activeOpacity={0.7}
              >
                <Text style={styles.modalBtnSecondaryText}>暂不添加</Text>
              </TouchableOpacity>
              <TouchableOpacity
                style={[styles.modalBtn, styles.modalBtnPrimary, subscribing && { opacity: 0.6 }]}
                onPress={agree}
                disabled={subscribing}
                activeOpacity={0.7}
              >
                {subscribing ? (
                  <ActivityIndicator color={Colors.textWhite} size="small" />
                ) : (
                  <Text style={styles.modalBtnPrimaryText}>同意并添加</Text>
                )}
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
  header: {
    backgroundColor: Colors.primary,
    paddingTop: 50,
    paddingBottom: 14,
    paddingHorizontal: Spacing.lg,
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    ...Shadow.header,
  },
  headerTitle: { color: Colors.textWhite, fontSize: FontSize.lg, fontWeight: '600' },
  content: { padding: Spacing.md },
  card: {
    backgroundColor: Colors.card,
    borderRadius: BorderRadius.md,
    padding: Spacing.lg,
  },
  iconRow: { flexDirection: 'row', alignItems: 'center', gap: Spacing.sm },
  cardTitle: { fontSize: FontSize.lg, fontWeight: '600', color: Colors.textPrimary },
  desc: {
    fontSize: FontSize.sm,
    color: Colors.textSecondary,
    marginTop: Spacing.sm,
    lineHeight: 20,
  },
  input: {
    borderWidth: 1,
    borderColor: Colors.border,
    borderRadius: BorderRadius.sm,
    padding: Spacing.sm,
    marginTop: Spacing.lg,
    color: Colors.textPrimary,
    fontSize: FontSize.md,
    backgroundColor: Colors.backgroundAlt,
  },
  activateBtn: {
    marginTop: Spacing.lg,
    backgroundColor: Colors.primary,
    borderRadius: BorderRadius.sm,
    padding: Spacing.md,
    alignItems: 'center',
  },
  activateBtnText: { color: Colors.textWhite, fontSize: FontSize.md, fontWeight: '600' },
  modalMask: {
    flex: 1,
    backgroundColor: 'rgba(0,0,0,0.45)',
    justifyContent: 'center',
    padding: Spacing.xl,
  },
  modalCard: {
    backgroundColor: Colors.white,
    borderRadius: BorderRadius.lg,
    padding: Spacing.xl,
  },
  modalTitle: {
    fontSize: FontSize.lg,
    fontWeight: '700',
    color: Colors.textPrimary,
    marginBottom: Spacing.md,
  },
  modalBody: { fontSize: FontSize.sm, color: Colors.textSecondary, lineHeight: 22 },
  modalActions: { flexDirection: 'row', gap: Spacing.md, marginTop: Spacing.xl },
  modalBtn: {
    flex: 1,
    paddingVertical: 12,
    borderRadius: BorderRadius.sm,
    alignItems: 'center',
  },
  modalBtnSecondary: {
    borderWidth: 1,
    borderColor: Colors.border,
    backgroundColor: Colors.backgroundAlt,
  },
  modalBtnSecondaryText: { color: Colors.textSecondary, fontSize: FontSize.md },
  modalBtnPrimary: { backgroundColor: Colors.primary },
  modalBtnPrimaryText: {
    color: Colors.textWhite,
    fontSize: FontSize.md,
    fontWeight: '600',
  },
});
