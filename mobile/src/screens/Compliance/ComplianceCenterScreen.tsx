/**
 * 个人合规中心（需求文档 4.2(4)）：
 *   备案状态 / 90 天到期提醒 / 资质审核状态 / 备案号+有效期录入 / 证书上传提交
 */
import React, { useCallback, useEffect, useState } from 'react';
import {
  Alert, ScrollView, StyleSheet, Text, TextInput, TouchableOpacity, View,
} from 'react-native';
import { useNavigation } from '@react-navigation/native';
import type { NativeStackNavigationProp } from '@react-navigation/native-stack';
import DocumentPicker from 'react-native-document-picker';
import Icon from '../../components/Icon';
import { qualificationAPI } from '../../api/qualification';
import type { Qualification } from '../../types';
import type { RootStackParamList } from '../../navigation/types';
import { BorderRadius, Colors, FontSize, Shadow, Spacing } from '../../constants/theme';

type PickedFile = { uri: string; name: string; type: string };
type Nav = NativeStackNavigationProp<RootStackParamList>;

const AUDIT_TEXT: Record<string, string> = {
  pending: '待审核', approved: '已通过', rejected: '已驳回',
};
const FILING_TEXT: Record<string, string> = {
  valid: '有效', expired: '已过期', not_filed: '未备案',
};
const AUDIT_COLOR: Record<string, string> = {
  pending: Colors.warning, approved: Colors.success, rejected: Colors.danger,
};

export default function ComplianceCenterScreen() {
  const navigation = useNavigation<Nav>();
  const [qual, setQual] = useState<Qualification | null>(null);
  const [loaded, setLoaded] = useState(false);
  const [filingNumber, setFilingNumber] = useState('');
  const [expireDate, setExpireDate] = useState('');
  const [education, setEducation] = useState<PickedFile | null>(null);
  const [training, setTraining] = useState<PickedFile | null>(null);
  const [submitting, setSubmitting] = useState(false);

  const load = useCallback(async () => {
    setLoaded(false);
    try {
      const q = await qualificationAPI.getMy();
      setQual(q);
      if (q?.filing_number) setFilingNumber(q.filing_number);
      if (q?.filing_expire_date) setExpireDate(q.filing_expire_date);
    } catch {
      Alert.alert('加载失败', '无法获取备案信息，请检查网络后重试');
    } finally {
      setLoaded(true);
    }
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  const pickFile = async (target: 'education' | 'training') => {
    try {
      const res = await DocumentPicker.pick({
        type: [DocumentPicker.types.pdf, DocumentPicker.types.images],
      });
      const picked = Array.isArray(res) ? res[0] : res;
      const file: PickedFile = {
        uri: picked.uri,
        name: picked.name || 'cert',
        type: picked.type || 'application/pdf',
      };
      if (target === 'education') setEducation(file);
      else setTraining(file);
    } catch (err: any) {
      if (DocumentPicker.isCancel(err)) return; // 用户取消不弹错
      Alert.alert('选择失败', err?.message || '无法打开文件选择器');
    }
  };

  const submit = async () => {
    if (!education && !qual?.education_cert) {
      Alert.alert('提示', '请先选择学历证明文件');
      return;
    }
    if (expireDate.trim() && !/^\d{4}-\d{2}-\d{2}$/.test(expireDate.trim())) {
      Alert.alert('提示', '有效期格式应为 YYYY-MM-DD，如 2028-06-30');
      return;
    }
    setSubmitting(true);
    try {
      await qualificationAPI.submit({
        filing_number: filingNumber.trim() || undefined,
        filing_expire_date: expireDate.trim() || undefined,
        educationCert: education || undefined,
        trainingCert: training || undefined,
      });
      Alert.alert('已提交', '资质与备案材料已提交，等待医学部/合规部审核');
      setEducation(null);
      setTraining(null);
      await load();
    } catch (err: any) {
      Alert.alert('提交失败', err?.message || '请稍后重试');
    } finally {
      setSubmitting(false);
    }
  };

  const filingStatus = qual?.filing_status || 'not_filed';
  const days = qual?.days_until_expiry;
  const expiringSoon = days !== null && days !== undefined && days <= 90 && days > 0;
  const expired = filingStatus === 'expired';

  return (
    <View style={styles.container}>
      <View style={styles.header}>
        <TouchableOpacity onPress={() => navigation.goBack()}>
          <Icon name="chevron-left" size={22} color={Colors.textWhite} />
        </TouchableOpacity>
        <Text style={styles.headerTitle}>备案与资质</Text>
        <View style={{ width: 24 }} />
      </View>
      <ScrollView contentContainerStyle={styles.content}>
        {/* 备案状态卡 */}
        <View style={[styles.card, Shadow.card]}>
          <Text style={styles.cardTitle}>备案状态</Text>
          <View style={styles.statusRow}>
            <Text style={styles.statusValue}>
              {FILING_TEXT[filingStatus] || filingStatus}
            </Text>
            {qual?.filing_number ? (
              <Text style={styles.desc}>备案号：{qual.filing_number}</Text>
            ) : (
              <Text style={styles.desc}>尚未录入备案号</Text>
            )}
            {qual?.filing_expire_date ? (
              <Text style={styles.desc}>有效期至：{qual.filing_expire_date}</Text>
            ) : null}
          </View>
          {expiringSoon && (
            <View style={styles.warnBox}>
              <Icon name="alert-circle" size={16} color={Colors.danger} />
              <Text style={styles.warnText}>备案将在 {days} 天后到期，请及时办理续期</Text>
            </View>
          )}
          {expired && (
            <View style={styles.warnBox}>
              <Icon name="alert-circle" size={16} color={Colors.danger} />
              <Text style={styles.warnText}>备案已过期，账号将被冻结，请尽快续期并重新提交</Text>
            </View>
          )}
        </View>

        {/* 资质审核状态卡 */}
        <View style={[styles.card, Shadow.card]}>
          <Text style={styles.cardTitle}>资质审核</Text>
          <View style={styles.statusRow}>
            <Text style={[styles.statusValue, { color: AUDIT_COLOR[qual?.audit_status || 'pending'] }]}>
              {AUDIT_TEXT[qual?.audit_status || 'pending']}
            </Text>
            {qual?.reject_reason ? (
              <Text style={styles.desc}>驳回原因：{qual.reject_reason}</Text>
            ) : null}
            {!qual && <Text style={styles.desc}>尚未提交资质材料</Text>}
          </View>
        </View>

        {/* 提交表单卡 */}
        <View style={[styles.card, Shadow.card]}>
          <Text style={styles.cardTitle}>提交 / 更新材料</Text>
          <Text style={styles.label}>备案号</Text>
          <TextInput
            style={styles.input}
            value={filingNumber}
            onChangeText={setFilingNumber}
            placeholder="国家备案平台备案号"
            placeholderTextColor={Colors.textHint}
          />
          <Text style={styles.label}>备案有效期（YYYY-MM-DD）</Text>
          <TextInput
            style={styles.input}
            value={expireDate}
            onChangeText={setExpireDate}
            placeholder="如 2028-06-30"
            placeholderTextColor={Colors.textHint}
          />
          <TouchableOpacity style={styles.pickBtn} onPress={() => pickFile('education')} activeOpacity={0.7}>
            <Icon name="file-pdf-box" size={20} color={Colors.primary} />
            <Text style={styles.pickText} numberOfLines={1}>
              {education ? education.name : qual?.education_cert ? '学历证明（已上传，可重新选择）' : '选择学历证明（必传）'}
            </Text>
          </TouchableOpacity>
          <TouchableOpacity style={styles.pickBtn} onPress={() => pickFile('training')} activeOpacity={0.7}>
            <Icon name="file-pdf-box" size={20} color={Colors.primary} />
            <Text style={styles.pickText} numberOfLines={1}>
              {training ? training.name : '选择培训考核合格证明（可选）'}
            </Text>
          </TouchableOpacity>
          <TouchableOpacity
            style={[styles.submitBtn, submitting && { opacity: 0.6 }]}
            disabled={submitting || !loaded}
            onPress={submit}
            activeOpacity={0.7}
          >
            <Text style={styles.submitText}>{submitting ? '提交中…' : '提交审核'}</Text>
          </TouchableOpacity>
          <Text style={styles.footnote}>提交后由医学部/合规部人工审核；重新提交将回到待审核状态</Text>
        </View>
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
  content: { padding: Spacing.md },
  card: { backgroundColor: Colors.card, borderRadius: BorderRadius.md, padding: Spacing.lg, marginBottom: Spacing.md },
  cardTitle: { fontSize: FontSize.md, fontWeight: '600', color: Colors.textPrimary, marginBottom: Spacing.sm },
  statusRow: { marginBottom: Spacing.xs },
  statusValue: { fontSize: FontSize.lg, fontWeight: '600', color: Colors.textPrimary, marginBottom: Spacing.xs },
  desc: { fontSize: FontSize.sm, color: Colors.textSecondary, marginTop: 2 },
  warnBox: { flexDirection: 'row', alignItems: 'center', marginTop: Spacing.sm, gap: 6 },
  warnText: { flex: 1, fontSize: FontSize.sm, color: Colors.danger },
  label: { fontSize: FontSize.sm, color: Colors.textSecondary, marginTop: Spacing.sm },
  input: {
    borderWidth: 1, borderColor: Colors.border, borderRadius: BorderRadius.sm,
    padding: Spacing.sm, marginTop: Spacing.xs, color: Colors.textPrimary, fontSize: FontSize.md,
  },
  pickBtn: {
    flexDirection: 'row', alignItems: 'center', gap: 8, marginTop: Spacing.md,
    borderWidth: 1, borderColor: Colors.border, borderRadius: BorderRadius.sm, padding: Spacing.sm,
  },
  pickText: { flex: 1, fontSize: FontSize.sm, color: Colors.textPrimary },
  submitBtn: {
    marginTop: Spacing.lg, backgroundColor: Colors.primary, borderRadius: BorderRadius.sm,
    padding: Spacing.md, alignItems: 'center',
  },
  submitText: { color: Colors.textWhite, fontSize: FontSize.md, fontWeight: '600' },
  footnote: { marginTop: Spacing.sm, fontSize: FontSize.xs, color: Colors.textHint, textAlign: 'center' },
});
