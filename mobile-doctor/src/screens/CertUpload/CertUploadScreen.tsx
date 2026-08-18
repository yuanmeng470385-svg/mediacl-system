/**
 * 执业资质上传页（照 mobile ComplianceCenterScreen 的表单+DocumentPicker 模式）：
 *   审核状态回显（pending/approved/rejected+驳回原因）/ 证书类型选择 /
 *   文件选择 / 提交（multipart 走 doctorAPI.submitCert）/ 重新提交重置为待审核
 */
import React, { useCallback, useEffect, useState } from 'react';
import {
  Alert,
  ScrollView,
  StyleSheet,
  Text,
  TouchableOpacity,
  View,
} from 'react-native';
import { useNavigation } from '@react-navigation/native';
import type { NativeStackNavigationProp } from '@react-navigation/native-stack';
import DocumentPicker from 'react-native-document-picker';
import Icon, { ActionIcons } from '../../components/Icon';
import { doctorAPI } from '../../api/doctor';
import type { DoctorCert } from '../../types';
import type { RootStackParamList } from '../../navigation/types';
import { BorderRadius, Colors, FontSize, Shadow, Spacing } from '../../constants/theme';

type PickedFile = { uri: string; name: string; type: string };
type Nav = NativeStackNavigationProp<RootStackParamList>;

const CERT_TYPE_OPTIONS: { value: 'physician' | 'practice'; label: string }[] = [
  { value: 'physician', label: '医师资格证' },
  { value: 'practice', label: '执业证书' },
];

const AUDIT_TEXT: Record<string, string> = {
  pending: '待审核',
  approved: '已通过',
  rejected: '已驳回',
};
const AUDIT_COLOR: Record<string, string> = {
  pending: Colors.warning,
  approved: Colors.success,
  rejected: Colors.danger,
};

export default function CertUploadScreen() {
  const navigation = useNavigation<Nav>();
  const [cert, setCert] = useState<DoctorCert | null>(null);
  const [loaded, setLoaded] = useState(false);
  const [certType, setCertType] = useState<'physician' | 'practice'>('physician');
  const [file, setFile] = useState<PickedFile | null>(null);
  const [submitting, setSubmitting] = useState(false);

  const load = useCallback(async () => {
    setLoaded(false);
    try {
      const c = await doctorAPI.getMyCert();
      setCert(c);
      if (c?.cert_type) setCertType(c.cert_type);
    } catch {
      Alert.alert('加载失败', '无法获取资质信息，请检查网络后重试');
    } finally {
      setLoaded(true);
    }
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  const pickFile = async () => {
    try {
      const res = await DocumentPicker.pick({
        type: [DocumentPicker.types.pdf, DocumentPicker.types.images],
      });
      const picked = Array.isArray(res) ? res[0] : res;
      setFile({
        uri: picked.uri,
        name: picked.name || 'cert',
        type: picked.type || 'application/pdf',
      });
    } catch (err: any) {
      if (DocumentPicker.isCancel(err)) return; // 用户取消不弹错
      Alert.alert('选择失败', err?.message || '无法打开文件选择器');
    }
  };

  const submit = async () => {
    if (!file && !cert?.cert_image_url) {
      Alert.alert('提示', '请先选择证书文件');
      return;
    }
    setSubmitting(true);
    try {
      await doctorAPI.submitCert({ cert_type: certType, cert: file || undefined });
      Alert.alert('已提交', '资质材料已提交，等待审核');
      setFile(null);
      await load();
    } catch (err: any) {
      Alert.alert('提交失败', err?.message || '请稍后重试');
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <View style={styles.container}>
      <View style={styles.header}>
        <TouchableOpacity onPress={() => navigation.goBack()}>
          <Icon name={ActionIcons.back} size={22} color={Colors.textWhite} />
        </TouchableOpacity>
        <Text style={styles.headerTitle}>执业资质</Text>
        <View style={{ width: 24 }} />
      </View>

      <ScrollView contentContainerStyle={styles.content}>
        {/* 审核状态卡 */}
        <View style={[styles.card, Shadow.card]}>
          <Text style={styles.cardTitle}>审核状态</Text>
          <View style={styles.statusRow}>
            <Text
              style={[
                styles.statusValue,
                { color: AUDIT_COLOR[cert?.cert_status || 'pending'] },
              ]}
            >
              {cert ? AUDIT_TEXT[cert.cert_status] || cert.cert_status : '尚未提交'}
            </Text>
            {cert?.reject_reason ? (
              <Text style={styles.desc}>驳回原因：{cert.reject_reason}</Text>
            ) : null}
            {!cert && <Text style={styles.desc}>提交后由医学部/合规部人工审核</Text>}
          </View>
        </View>

        {/* 提交表单卡 */}
        <View style={[styles.card, Shadow.card]}>
          <Text style={styles.cardTitle}>{cert ? '更新材料' : '提交材料'}</Text>

          <Text style={styles.label}>证书类型</Text>
          <View style={styles.typeRow}>
            {CERT_TYPE_OPTIONS.map((opt) => {
              const selected = certType === opt.value;
              return (
                <TouchableOpacity
                  key={opt.value}
                  style={[styles.typeChip, selected && styles.typeChipSelected]}
                  onPress={() => setCertType(opt.value)}
                  activeOpacity={0.7}
                >
                  <Text
                    style={[
                      styles.typeChipText,
                      selected && styles.typeChipTextSelected,
                    ]}
                  >
                    {opt.label}
                  </Text>
                </TouchableOpacity>
              );
            })}
          </View>

          <TouchableOpacity style={styles.pickBtn} onPress={pickFile} activeOpacity={0.7}>
            <Icon name="file-pdf-box" size={20} color={Colors.primary} />
            <Text style={styles.pickText} numberOfLines={1}>
              {file
                ? file.name
                : cert?.cert_image_url
                ? '证书图片（已上传，可重新选择）'
                : '选择证书图片（PDF 或图片）'}
            </Text>
          </TouchableOpacity>

          <TouchableOpacity
            style={[styles.submitBtn, (submitting || !loaded) && { opacity: 0.6 }]}
            disabled={submitting || !loaded}
            onPress={submit}
            activeOpacity={0.7}
          >
            <Text style={styles.submitText}>{submitting ? '提交中…' : '提交审核'}</Text>
          </TouchableOpacity>
          <Text style={styles.footnote}>
            重新提交将回到待审核状态；首次提交必须上传证书文件
          </Text>
        </View>
      </ScrollView>
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
    marginBottom: Spacing.md,
  },
  cardTitle: {
    fontSize: FontSize.md,
    fontWeight: '600',
    color: Colors.textPrimary,
    marginBottom: Spacing.sm,
  },
  statusRow: { marginBottom: Spacing.xs },
  statusValue: {
    fontSize: FontSize.lg,
    fontWeight: '600',
    color: Colors.textPrimary,
    marginBottom: Spacing.xs,
  },
  desc: { fontSize: FontSize.sm, color: Colors.textSecondary, marginTop: 2 },
  label: { fontSize: FontSize.sm, color: Colors.textSecondary, marginTop: Spacing.sm },
  typeRow: { flexDirection: 'row', gap: Spacing.sm, marginTop: Spacing.xs },
  typeChip: {
    flex: 1,
    paddingVertical: 10,
    borderRadius: BorderRadius.sm,
    borderWidth: 1,
    borderColor: Colors.border,
    alignItems: 'center',
    backgroundColor: Colors.backgroundAlt,
  },
  typeChipSelected: {
    borderColor: Colors.primary,
    backgroundColor: Colors.primarySurface,
  },
  typeChipText: { fontSize: FontSize.sm, color: Colors.textSecondary },
  typeChipTextSelected: { color: Colors.primary, fontWeight: '600' },
  pickBtn: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 8,
    marginTop: Spacing.md,
    borderWidth: 1,
    borderColor: Colors.border,
    borderRadius: BorderRadius.sm,
    padding: Spacing.sm,
  },
  pickText: { flex: 1, fontSize: FontSize.sm, color: Colors.textPrimary },
  submitBtn: {
    marginTop: Spacing.lg,
    backgroundColor: Colors.primary,
    borderRadius: BorderRadius.sm,
    padding: Spacing.md,
    alignItems: 'center',
  },
  submitText: { color: Colors.textWhite, fontSize: FontSize.md, fontWeight: '600' },
  footnote: {
    marginTop: Spacing.sm,
    fontSize: FontSize.xs,
    color: Colors.textHint,
    textAlign: 'center',
  },
});
