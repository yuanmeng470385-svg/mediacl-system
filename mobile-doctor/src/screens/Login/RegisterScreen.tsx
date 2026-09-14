/**
 * 注册页 - 医生端（验证码制注册，2026-09-14 升级）
 * 手机号+验证码（scene=register，只对未注册号发）+姓名（医院/科室/职称选填），
 * 注册即登录；不设密码，登录走验证码（登录页密码模式对未设密码账号不适用）。
 * 视觉/交互照 LoginScreen（同一张卡片范式），校验口径与后端 register 端点一致。
 */
import React, { useState, useEffect } from 'react';
import {
  View,
  Text,
  TextInput,
  TouchableOpacity,
  StyleSheet,
  KeyboardAvoidingView,
  Platform,
  ScrollView,
  Alert,
  ActivityIndicator,
} from 'react-native';
import { useNavigation } from '@react-navigation/native';
import type { NativeStackNavigationProp } from '@react-navigation/native-stack';
import { useAuth } from '../../store/AuthContext';
import { authAPI } from '../../api/auth';
import { Colors, FontSize, Spacing, BorderRadius, Shadow } from '../../constants/theme';
import type { RootStackParamList } from '../../navigation/types';

export default function RegisterScreen() {
  const navigation =
    useNavigation<NativeStackNavigationProp<RootStackParamList, 'Register'>>();
  const { register } = useAuth();

  const [phone, setPhone] = useState('');
  const [code, setCode] = useState('');
  const [fullName, setFullName] = useState('');
  const [hospital, setHospital] = useState('');
  const [department, setDepartment] = useState('');
  const [title, setTitle] = useState('');
  const [agreed, setAgreed] = useState(false);
  const [sendingCode, setSendingCode] = useState(false);
  const [countdown, setCountdown] = useState(0);
  const [loading, setLoading] = useState(false);
  const timerRef = React.useRef<ReturnType<typeof setInterval>>();

  useEffect(() => {
    return () => {
      if (timerRef.current) clearInterval(timerRef.current);
    };
  }, []);

  const validatePhone = (p: string) => /^1[3-9]\d{9}$/.test(p);

  const handleSendCode = async () => {
    if (!validatePhone(phone)) {
      Alert.alert('提示', '请输入正确的手机号');
      return;
    }
    setSendingCode(true);
    try {
      // 注册场景：只对未注册号发码；已注册号后端返回 4001「请直接登录」
      await authAPI.sendCode(phone, 'register');
      setCountdown(60);
      timerRef.current = setInterval(() => {
        setCountdown((prev) => {
          if (prev <= 1) {
            if (timerRef.current) clearInterval(timerRef.current);
            return 0;
          }
          return prev - 1;
        });
      }, 1000);
      Alert.alert('提示', '验证码已发送，请查收短信');
    } catch (e: any) {
      Alert.alert('发送失败', e.message || '请稍后重试');
    } finally {
      setSendingCode(false);
    }
  };

  const handleRegister = async () => {
    if (!validatePhone(phone)) {
      Alert.alert('提示', '请输入正确的手机号');
      return;
    }
    if (!code || code.length < 4) {
      Alert.alert('提示', '请输入验证码');
      return;
    }
    const name = fullName.trim();
    if (name.length < 2 || name.length > 30) {
      Alert.alert('提示', '姓名长度须为 2-30 个字符');
      return;
    }
    if (!agreed) {
      Alert.alert('提示', '请先同意用户协议和隐私政策');
      return;
    }
    setLoading(true);
    try {
      // 注册即登录：AuthContext 更新登录态后导航栈自动切到主 Tab
      await register({
        phone,
        code,
        full_name: name,
        hospital: hospital.trim() || undefined,
        department: department.trim() || undefined,
        title: title.trim() || undefined,
      });
    } catch (e: any) {
      Alert.alert('注册失败', e.message || '请稍后重试');
    } finally {
      setLoading(false);
    }
  };

  return (
    <KeyboardAvoidingView
      style={styles.container}
      behavior={Platform.OS === 'ios' ? 'padding' : undefined}
    >
      <View style={styles.bgTop} />
      <ScrollView
        style={styles.content}
        contentContainerStyle={styles.contentInner}
        keyboardShouldPersistTaps="handled"
      >
        <View style={styles.header}>
          <TouchableOpacity onPress={() => navigation.goBack()} activeOpacity={0.7}>
            <Text style={styles.backText}>‹ 返回登录</Text>
          </TouchableOpacity>
        </View>

        <View style={styles.logoArea}>
          <View style={styles.logoCircle}>
            <Text style={styles.logoIcon}>MD</Text>
          </View>
          <Text style={styles.appName}>注册医生账号</Text>
          <Text style={styles.subtitle}>注册即登录 · 立即使用医生工作台</Text>
        </View>

        <View style={[styles.card, Shadow.card]}>
          <View style={styles.inputGroup}>
            <Text style={styles.inputLabel}>手机号 *</Text>
            <TextInput
              style={styles.input}
              placeholder="用于注册与接收验证码"
              placeholderTextColor={Colors.textHint}
              keyboardType="phone-pad"
              maxLength={11}
              value={phone}
              onChangeText={setPhone}
            />
          </View>

          <View style={styles.inputGroup}>
            <Text style={styles.inputLabel}>验证码 *</Text>
            <View style={styles.codeRow}>
              <TextInput
                style={[styles.input, styles.codeInput]}
                placeholder="短信验证码"
                placeholderTextColor={Colors.textHint}
                keyboardType="number-pad"
                maxLength={6}
                value={code}
                onChangeText={setCode}
              />
              <TouchableOpacity
                style={[
                  styles.codeBtn,
                  (countdown > 0 || sendingCode || !validatePhone(phone)) && styles.codeBtnDisabled,
                ]}
                onPress={handleSendCode}
                disabled={countdown > 0 || sendingCode || !validatePhone(phone)}
                activeOpacity={0.7}
              >
                {sendingCode ? (
                  <ActivityIndicator color={Colors.primary} size="small" />
                ) : (
                  <Text
                    style={[styles.codeBtnText, countdown > 0 && styles.codeBtnDisabledText]}
                  >
                    {countdown > 0 ? `${countdown}s` : '获取验证码'}
                  </Text>
                )}
              </TouchableOpacity>
            </View>
          </View>

          <View style={styles.inputGroup}>
            <Text style={styles.inputLabel}>姓名 *</Text>
            <TextInput
              style={styles.input}
              placeholder="真实姓名（2-30 个字符）"
              placeholderTextColor={Colors.textHint}
              maxLength={30}
              value={fullName}
              onChangeText={setFullName}
            />
          </View>

          <Text style={styles.sectionHint}>以下信息选填，便于代表更好地服务您</Text>

          <View style={styles.inputGroup}>
            <Text style={styles.inputLabel}>医院</Text>
            <TextInput
              style={styles.input}
              placeholder="选填"
              placeholderTextColor={Colors.textHint}
              maxLength={50}
              value={hospital}
              onChangeText={setHospital}
            />
          </View>

          <View style={styles.halfRow}>
            <View style={[styles.inputGroup, styles.halfCol]}>
              <Text style={styles.inputLabel}>科室</Text>
              <TextInput
                style={styles.input}
                placeholder="选填"
                placeholderTextColor={Colors.textHint}
                maxLength={30}
                value={department}
                onChangeText={setDepartment}
              />
            </View>
            <View style={[styles.inputGroup, styles.halfCol]}>
              <Text style={styles.inputLabel}>职称</Text>
              <TextInput
                style={styles.input}
                placeholder="选填"
                placeholderTextColor={Colors.textHint}
                maxLength={20}
                value={title}
                onChangeText={setTitle}
              />
            </View>
          </View>

          <TouchableOpacity
            style={[styles.registerBtn, loading && styles.registerBtnLoading]}
            onPress={handleRegister}
            disabled={loading}
            activeOpacity={0.8}
          >
            {loading ? (
              <ActivityIndicator color={Colors.textWhite} />
            ) : (
              <Text style={styles.registerBtnText}>注 册</Text>
            )}
          </TouchableOpacity>

          <TouchableOpacity
            style={styles.agreementRow}
            onPress={() => setAgreed(!agreed)}
            activeOpacity={0.7}
          >
            <View style={[styles.checkbox, agreed && styles.checkboxChecked]}>
              {agreed && <Text style={styles.checkmark}>✓</Text>}
            </View>
            <Text style={styles.agreementText}>
              已阅读并同意 <Text style={styles.link}>《用户协议》</Text> 和{' '}
              <Text style={styles.link}>《隐私政策》</Text>
            </Text>
          </TouchableOpacity>

          <TouchableOpacity
            style={styles.toLoginRow}
            onPress={() => navigation.goBack()}
            activeOpacity={0.7}
          >
            <Text style={styles.toLoginText}>已有账号？返回登录</Text>
          </TouchableOpacity>
        </View>
      </ScrollView>
    </KeyboardAvoidingView>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1, backgroundColor: Colors.background },
  bgTop: {
    position: 'absolute',
    top: 0,
    left: 0,
    right: 0,
    height: '32%',
    backgroundColor: Colors.primary,
    borderBottomLeftRadius: 40,
    borderBottomRightRadius: 40,
  },
  content: { flex: 1 },
  contentInner: { paddingHorizontal: Spacing.xxl, paddingBottom: Spacing.xxl },
  header: { marginTop: Spacing.xl },
  backText: { color: Colors.textWhite, fontSize: FontSize.md, fontWeight: '500' },
  logoArea: { alignItems: 'center', marginBottom: 32, marginTop: Spacing.lg },
  logoCircle: {
    width: 64,
    height: 64,
    borderRadius: 18,
    backgroundColor: Colors.textWhite,
    alignItems: 'center',
    justifyContent: 'center',
    marginBottom: Spacing.md,
    ...Shadow.fab,
  },
  logoIcon: { fontSize: 26, fontWeight: '800', color: Colors.primary, letterSpacing: -1 },
  appName: {
    fontSize: FontSize.xl,
    fontWeight: '700',
    color: Colors.textWhite,
    marginBottom: Spacing.xs,
  },
  subtitle: { fontSize: FontSize.sm, color: 'rgba(255,255,255,0.7)' },
  card: {
    backgroundColor: Colors.white,
    borderRadius: BorderRadius.xl,
    padding: Spacing.xxl,
    gap: Spacing.lg,
  },
  inputGroup: { gap: Spacing.sm },
  inputLabel: { fontSize: FontSize.sm, fontWeight: '600', color: Colors.textPrimary },
  input: {
    borderWidth: 1,
    borderColor: Colors.border,
    borderRadius: BorderRadius.lg,
    paddingHorizontal: Spacing.lg,
    paddingVertical: 14,
    fontSize: FontSize.md,
    color: Colors.textPrimary,
    backgroundColor: Colors.backgroundAlt,
  },
  codeRow: { flexDirection: 'row', gap: Spacing.md },
  codeInput: { flex: 1 },
  codeBtn: {
    paddingHorizontal: Spacing.lg,
    paddingVertical: 14,
    borderRadius: BorderRadius.lg,
    borderWidth: 1,
    borderColor: Colors.primary,
    justifyContent: 'center',
    alignItems: 'center',
    minWidth: 110,
  },
  codeBtnDisabled: { borderColor: Colors.border },
  codeBtnText: { color: Colors.primary, fontSize: FontSize.sm, fontWeight: '600' },
  codeBtnDisabledText: { color: Colors.textHint },
  sectionHint: { fontSize: FontSize.xs, color: Colors.textHint, marginTop: Spacing.sm },
  halfRow: { flexDirection: 'row', gap: Spacing.md },
  halfCol: { flex: 1 },
  registerBtn: {
    backgroundColor: Colors.primary,
    borderRadius: BorderRadius.lg,
    paddingVertical: 16,
    alignItems: 'center',
    marginTop: Spacing.sm,
  },
  registerBtnLoading: { opacity: 0.7 },
  registerBtnText: {
    color: Colors.textWhite,
    fontSize: FontSize.lg,
    fontWeight: '600',
    letterSpacing: 4,
  },
  agreementRow: { flexDirection: 'row', alignItems: 'center', gap: Spacing.sm },
  checkbox: {
    width: 18,
    height: 18,
    borderRadius: 4,
    borderWidth: 1.5,
    borderColor: Colors.border,
    alignItems: 'center',
    justifyContent: 'center',
  },
  checkboxChecked: { backgroundColor: Colors.primary, borderColor: Colors.primary },
  checkmark: { color: Colors.white, fontSize: 12, fontWeight: '700' },
  agreementText: { fontSize: FontSize.xs, color: Colors.textSecondary, flex: 1 },
  link: { color: Colors.primary },
  toLoginRow: { alignItems: 'center' },
  toLoginText: { color: Colors.primary, fontSize: FontSize.sm, fontWeight: '500' },
});
