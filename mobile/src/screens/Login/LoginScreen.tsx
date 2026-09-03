/**
 * 登录页 - 临床精准风
 * 深蓝渐变底 + 白色表单卡片 + 品牌感
 */
import React, { useState, useRef, useEffect } from 'react';
import {
  View, Text, TextInput, TouchableOpacity, StyleSheet,
  KeyboardAvoidingView, Platform, Alert, ActivityIndicator,
} from 'react-native';
import { useAuth } from '../../store/AuthContext';
import { authAPI } from '../../api/auth';
import { Colors, FontSize, Spacing, BorderRadius, Shadow } from '../../constants/theme';

export default function LoginScreen() {
  const { login, loginByPassword } = useAuth();
  const [mode, setMode] = useState<'code' | 'password'>('code');
  const [phone, setPhone] = useState('');
  const [code, setCode] = useState('');
  const [username, setUsername] = useState('');
  const [password, setPassword] = useState('');
  const [agreed, setAgreed] = useState(false);
  const [sendingCode, setSendingCode] = useState(false);
  const [countdown, setCountdown] = useState(0);
  const [loading, setLoading] = useState(false);
  const codeInputRef = useRef<TextInput>(null);
  const timerRef = useRef<ReturnType<typeof setInterval>>();

  useEffect(() => {
    return () => { if (timerRef.current) clearInterval(timerRef.current); };
  }, []);

  const validatePhone = (p: string) => /^1[3-9]\d{9}$/.test(p);

  const handleSendCode = async () => {
    if (!validatePhone(phone)) { Alert.alert('提示', '请输入正确的手机号'); return; }
    setSendingCode(true);
    try {
      await authAPI.sendCode(phone);
      setCountdown(60);
      timerRef.current = setInterval(() => {
        setCountdown((prev) => {
          if (prev <= 1) { if (timerRef.current) clearInterval(timerRef.current); return 0; }
          return prev - 1;
        });
      }, 1000);
      // 后端 send-code 对未注册手机号静默成功（防账号枚举），不能宣称"已发送"
      Alert.alert('提示', '若该手机号已开通账号，验证码将发送至该手机');
    } catch (e: any) {
      Alert.alert('发送失败', e.message || '请稍后重试');
    } finally {
      setSendingCode(false);
    }
  };

  const handleLogin = async () => {
    if (mode === 'password') {
      if (!username.trim()) { Alert.alert('提示', '请输入用户名'); return; }
      if (!password) { Alert.alert('提示', '请输入密码'); return; }
    } else {
      if (!validatePhone(phone)) { Alert.alert('提示', '请输入正确的手机号'); return; }
      if (!code || code.length < 4) { Alert.alert('提示', '请输入验证码'); return; }
    }
    if (!agreed) { Alert.alert('提示', '请先同意用户协议和隐私政策'); return; }
    setLoading(true);
    try {
      if (mode === 'password') {
        await loginByPassword(username.trim(), password);
      } else {
        await login(phone, code);
      }
    } catch (e: any) {
      Alert.alert('登录失败', e.message || (mode === 'password' ? '请检查用户名和密码' : '请检查手机号和验证码'));
    } finally {
      setLoading(false);
    }
  };

  const switchMode = () => {
    setMode((prev) => (prev === 'code' ? 'password' : 'code'));
    // 切换方式时清空另一种方式的输入，避免残留
    setCode('');
    setPassword('');
  };

  return (
    <KeyboardAvoidingView style={styles.container} behavior={Platform.OS === 'ios' ? 'padding' : undefined}>
      {/* 深蓝渐变背景 */}
      <View style={styles.bgTop} />
      <View style={styles.bgBottom} />

      <View style={styles.content}>
        {/* Logo */}
        <View style={styles.logoArea}>
          <View style={styles.logoCircle}>
            <Text style={styles.logoIcon}>MA</Text>
          </View>
          <Text style={styles.appName}>MedAgent</Text>
          <Text style={styles.subtitle}>医药代表数字员工系统</Text>
        </View>

        {/* 白色表单卡片 */}
        <View style={[styles.card, Shadow.card]}>
          {mode === 'code' ? (
            <>
              <View style={styles.inputGroup}>
                <Text style={styles.inputLabel}>手机号</Text>
                <TextInput
                  style={styles.input}
                  placeholder="请输入手机号"
                  placeholderTextColor={Colors.textHint}
                  keyboardType="phone-pad"
                  maxLength={11}
                  value={phone}
                  onChangeText={setPhone}
                />
              </View>

              <View style={styles.inputGroup}>
                <Text style={styles.inputLabel}>验证码</Text>
                <View style={styles.codeRow}>
                  <TextInput
                    ref={codeInputRef}
                    style={[styles.input, styles.codeInput]}
                    placeholder="请输入验证码"
                    placeholderTextColor={Colors.textHint}
                    keyboardType="number-pad"
                    maxLength={6}
                    value={code}
                    onChangeText={setCode}
                  />
                  <TouchableOpacity
                    style={[styles.codeBtn, (countdown > 0 || sendingCode || !validatePhone(phone)) && styles.codeBtnDisabled]}
                    onPress={handleSendCode}
                    disabled={countdown > 0 || sendingCode || !validatePhone(phone)}
                    activeOpacity={0.7}
                  >
                    {sendingCode ? (
                      <ActivityIndicator color={Colors.primary} size="small" />
                    ) : (
                      <Text style={[styles.codeBtnText, countdown > 0 && styles.codeBtnDisabledText]}>
                        {countdown > 0 ? `${countdown}s` : '获取验证码'}
                      </Text>
                    )}
                  </TouchableOpacity>
                </View>
              </View>
            </>
          ) : (
            <>
              <View style={styles.inputGroup}>
                <Text style={styles.inputLabel}>用户名</Text>
                <TextInput
                  style={styles.input}
                  placeholder="请输入用户名"
                  placeholderTextColor={Colors.textHint}
                  autoCapitalize="none"
                  autoCorrect={false}
                  value={username}
                  onChangeText={setUsername}
                />
              </View>

              <View style={styles.inputGroup}>
                <Text style={styles.inputLabel}>密码</Text>
                <TextInput
                  style={styles.input}
                  placeholder="请输入密码"
                  placeholderTextColor={Colors.textHint}
                  secureTextEntry
                  value={password}
                  onChangeText={setPassword}
                />
              </View>
            </>
          )}

          <TouchableOpacity style={[styles.loginBtn, loading && styles.loginBtnLoading]} onPress={handleLogin} disabled={loading} activeOpacity={0.8}>
            {loading ? <ActivityIndicator color={Colors.textWhite} /> : <Text style={styles.loginBtnText}>登 录</Text>}
          </TouchableOpacity>

          {/* 登录方式切换（需求 3.1.2：密码登录入口；后端同一 login 端点支持两种方式） */}
          <TouchableOpacity style={styles.switchRow} onPress={switchMode} activeOpacity={0.7}>
            <Text style={styles.switchText}>
              {mode === 'code' ? '使用密码登录' : '使用验证码登录'}
            </Text>
          </TouchableOpacity>

          <TouchableOpacity style={styles.agreementRow} onPress={() => setAgreed(!agreed)} activeOpacity={0.7}>
            <View style={[styles.checkbox, agreed && styles.checkboxChecked]}>
              {agreed && <Text style={styles.checkmark}>✓</Text>}
            </View>
            <Text style={styles.agreementText}>
              已阅读并同意 <Text style={styles.link}>《用户协议》</Text> 和 <Text style={styles.link}>《隐私政策》</Text>
            </Text>
          </TouchableOpacity>
        </View>
      </View>
    </KeyboardAvoidingView>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1, backgroundColor: Colors.background },
  bgTop: {
    position: 'absolute', top: 0, left: 0, right: 0, height: '45%',
    backgroundColor: Colors.primary,
    borderBottomLeftRadius: 40, borderBottomRightRadius: 40,
  },
  bgBottom: { position: 'absolute', bottom: 0, left: 0, right: 0, height: '55%', backgroundColor: Colors.background },
  content: { flex: 1, justifyContent: 'center', paddingHorizontal: Spacing.xxl },
  logoArea: { alignItems: 'center', marginBottom: 40 },
  logoCircle: {
    width: 72, height: 72, borderRadius: 20,
    backgroundColor: Colors.textWhite, alignItems: 'center', justifyContent: 'center',
    marginBottom: Spacing.lg, ...Shadow.fab,
  },
  logoIcon: { fontSize: 28, fontWeight: '800', color: Colors.primary, letterSpacing: -1 },
  appName: { fontSize: 30, fontWeight: '700', color: Colors.textWhite, marginBottom: Spacing.sm },
  subtitle: { fontSize: FontSize.md, color: 'rgba(255,255,255,0.7)' },
  card: {
    backgroundColor: Colors.white, borderRadius: BorderRadius.xl,
    padding: Spacing.xxl, gap: Spacing.xl,
  },
  inputGroup: { gap: Spacing.sm },
  inputLabel: { fontSize: FontSize.sm, fontWeight: '600', color: Colors.textPrimary },
  input: {
    borderWidth: 1, borderColor: Colors.border, borderRadius: BorderRadius.lg,
    paddingHorizontal: Spacing.lg, paddingVertical: 14,
    fontSize: FontSize.md, color: Colors.textPrimary, backgroundColor: Colors.backgroundAlt,
  },
  codeRow: { flexDirection: 'row', gap: Spacing.md },
  codeInput: { flex: 1 },
  codeBtn: {
    paddingHorizontal: Spacing.lg, paddingVertical: 14,
    borderRadius: BorderRadius.lg, borderWidth: 1, borderColor: Colors.primary,
    justifyContent: 'center', alignItems: 'center', minWidth: 110,
  },
  codeBtnDisabled: { borderColor: Colors.border },
  codeBtnText: { color: Colors.primary, fontSize: FontSize.sm, fontWeight: '600' },
  codeBtnDisabledText: { color: Colors.textHint },
  loginBtn: {
    backgroundColor: Colors.primary, borderRadius: BorderRadius.lg,
    paddingVertical: 16, alignItems: 'center', marginTop: Spacing.sm,
  },
  loginBtnLoading: { opacity: 0.7 },
  loginBtnText: { color: Colors.textWhite, fontSize: FontSize.lg, fontWeight: '600', letterSpacing: 4 },
  switchRow: { alignItems: 'center', marginTop: -Spacing.sm },
  switchText: { color: Colors.primary, fontSize: FontSize.sm, fontWeight: '500' },
  agreementRow: { flexDirection: 'row', alignItems: 'center', gap: Spacing.sm },
  checkbox: {
    width: 18, height: 18, borderRadius: 4, borderWidth: 1.5,
    borderColor: Colors.border, alignItems: 'center', justifyContent: 'center',
  },
  checkboxChecked: { backgroundColor: Colors.primary, borderColor: Colors.primary },
  checkmark: { color: Colors.white, fontSize: 12, fontWeight: '700' },
  agreementText: { fontSize: FontSize.xs, color: Colors.textSecondary, flex: 1 },
  link: { color: Colors.primary },
});
