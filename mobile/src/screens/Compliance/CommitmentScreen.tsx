/**
 * 合规承诺书页（二期 F）：勾选同意 → 发送短信验证码 → 输入验证码 → 签署。
 * sendCommitmentCode 为 POST 空 body {}，signCommitment 提交 code。
 */
import React, { useState } from 'react';
import { Alert, ScrollView, StyleSheet, Text, TextInput, TouchableOpacity, View } from 'react-native';
import { useNavigation } from '@react-navigation/native';
import { examAPI } from '../../api/exam';
import Icon from '../../components/Icon';
import { BorderRadius, Colors, FontSize, Shadow, Spacing } from '../../constants/theme';

export default function CommitmentScreen() {
  const navigation = useNavigation();
  const [agreed, setAgreed] = useState(false);
  const [code, setCode] = useState('');
  const [sending, setSending] = useState(false);
  const [signed, setSigned] = useState(false);

  const sendCode = async () => {
    if (!agreed) { Alert.alert('提示', '请先勾选同意承诺书内容'); return; }
    setSending(true);
    try { await examAPI.sendCommitmentCode(); Alert.alert('已发送', '短信验证码已发送至手机号'); }
    catch { Alert.alert('发送失败', '请稍后重试'); }
    finally { setSending(false); }
  };

  const sign = async () => {
    if (!code.trim()) { Alert.alert('提示', '请输入验证码'); return; }
    try {
      await examAPI.signCommitment(code.trim());
      setSigned(true);
      Alert.alert('已签署', '年度合规承诺书签署完成', [{ text: '好', onPress: () => navigation.goBack() }]);
    } catch { Alert.alert('签署失败', '验证码错误或已过期'); }
  };

  return (
    <View style={styles.container}>
      <View style={styles.header}><TouchableOpacity onPress={() => navigation.goBack()}><Icon name="chevron-left" size={22} color={Colors.textWhite} /></TouchableOpacity><Text style={styles.headerTitle}>合规承诺书</Text><View style={{ width: 24 }} /></View>
      <ScrollView contentContainerStyle={styles.content}>
        <View style={[styles.card, Shadow.card]}>
          <Text style={styles.cardTitle}>年度合规承诺书</Text>
          <Text style={styles.body}>
            {"本人承诺：\n\n1. 严格遵守《医药代表管理办法》及相关法律法规；\n2. 仅从事学术推广，不承担销售任务，不进行统方；\n3. 不提供财物或其他利益，不附加销售条件，不隐瞒不良反应，不误导用药；\n4. 配合平台合规管理，按时完成培训与考试。\n\n本承诺书由本人签署，平台留存并接受监管检查。"}
          </Text>
        </View>
        <TouchableOpacity style={styles.agreeRow} onPress={() => setAgreed(!agreed)}>
          <Icon name={agreed ? 'check-circle' : 'circle-outline'} size={20} color={agreed ? Colors.primary : Colors.textHint} />
          <Text style={styles.agreeText}>我已知悉并同意以上内容</Text>
        </TouchableOpacity>
        <TouchableOpacity style={[styles.submitBtn, (!agreed || sending) && { opacity: 0.6 }]} disabled={!agreed || sending} onPress={sendCode}>
          <Text style={styles.submitText}>{sending ? '发送中…' : '发送短信验证码'}</Text>
        </TouchableOpacity>
        <TextInput style={styles.input} value={code} onChangeText={setCode} placeholder="输入验证码" placeholderTextColor={Colors.textHint} maxLength={6} keyboardType="number-pad" />
        <TouchableOpacity style={[styles.submitBtn, !code.trim() && { opacity: 0.6 }]} disabled={!code.trim()} onPress={sign}>
          <Text style={styles.submitText}>{signed ? '已签署' : '签署承诺书'}</Text>
        </TouchableOpacity>
      </ScrollView>
    </View>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1, backgroundColor: Colors.background },
  header: { backgroundColor: Colors.primary, paddingTop: 50, paddingBottom: 14, paddingHorizontal: Spacing.lg, flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', ...Shadow.header },
  headerTitle: { color: Colors.textWhite, fontSize: FontSize.lg, fontWeight: '600' },
  content: { padding: Spacing.md },
  card: { backgroundColor: Colors.card, borderRadius: BorderRadius.md, padding: Spacing.lg, marginBottom: Spacing.md },
  cardTitle: { fontSize: FontSize.md, fontWeight: '600', color: Colors.textPrimary, marginBottom: Spacing.sm },
  body: { fontSize: FontSize.sm, color: Colors.textSecondary, lineHeight: 24 },
  agreeRow: { flexDirection: 'row', alignItems: 'center', gap: 8, marginBottom: Spacing.md },
  agreeText: { flex: 1, fontSize: FontSize.md, color: Colors.textPrimary },
  input: { borderWidth: 1, borderColor: Colors.border, borderRadius: BorderRadius.sm, padding: Spacing.sm, color: Colors.textPrimary, fontSize: FontSize.md, marginBottom: Spacing.md },
  submitBtn: { backgroundColor: Colors.primary, borderRadius: BorderRadius.sm, padding: Spacing.md, alignItems: 'center', marginBottom: Spacing.sm },
  submitText: { color: Colors.textWhite, fontSize: FontSize.md, fontWeight: '600' },
});
