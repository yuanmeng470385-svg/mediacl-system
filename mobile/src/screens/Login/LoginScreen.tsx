/**
 * 登录页 - 手机号+验证码登录
 */
import React, { useState, useRef, useEffect } from 'react';
import {
  View,
  Text,
  TextInput,
  TouchableOpacity,
  StyleSheet,
  KeyboardAvoidingView,
  Platform,
  Alert,
  ActivityIndicator,
} from 'react-native';
import { useAuth } from '../../store/AuthContext';
import { authAPI } from '../../api/auth';
import { Colors, FontSize, Spacing, BorderRadius } from '../../constants/theme';

export default function LoginScreen() {
  const { login } = useAuth();
  const [phone, setPhone] = useState('');
  const [code, setCode] = useState('');
  const [agreed, setAgreed] = useState(false);
  const [sendingCode, setSendingCode] = useState(false);
  const [countdown, setCountdown] = useState(0);
  const [loading, setLoading] = useState(false);
  const codeInputRef = useRef<TextInput>(null);
  const timerRef = useRef<ReturnType<typeof setInterval>>();

  // 倒计时清理
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
      await authAPI.sendCode(phone);
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
      Alert.alert('提示', '验证码已发送');
    } catch (e: any) {
      Alert.alert('发送失败', e.message || '请稍后重试');
    } finally {
      setSendingCode(false);
    }
  };

  const handleLogin = async () => {
    if (!validatePhone(phone)) {
      Alert.alert('提示', '请输入正确的手机号');
      return;
    }
    if (!code || code.length < 4) {
      Alert.alert('提示', '请输入验证码');
      return;
    }
    if (!agreed) {
      Alert.alert('提示', '请先同意用户协议和隐私政策');
      return;
    }
    setLoading(true);
    try {
      await login(phone, code);
      // 登录成功——AuthContext 状态更新后自动跳转
    } catch (e: any) {
      Alert.alert('登录失败', e.message || '请检查手机号和验证码');
    } finally {
      setLoading(false);
    }
  };

  return (
    <KeyboardAvoidingView
      style={styles.container}
      behavior={Platform.OS === 'ios' ? 'padding' : undefined}
    >
      <View style={styles.content}>
        {/* Logo 区 */}
        <View style={styles.logoArea}>
          <Text style={styles.logo}>💊</Text>
          <Text style={styles.appName}>MedAgent</Text>
          <Text style={styles.subtitle}>医药代表数字员工</Text>
        </View>

        {/* 表单 */}
        <View style={styles.form}>
          {/* 手机号 */}
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

          {/* 验证码 */}
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
                style={[
                  styles.codeBtn,
                  (countdown > 0 || sendingCode || !validatePhone(phone)) &&
                    styles.codeBtnDisabled,
                ]}
                onPress={handleSendCode}
                disabled={countdown > 0 || sendingCode || !validatePhone(phone)}
                activeOpacity={0.7}
              >
                {sendingCode ? (
                  <ActivityIndicator color={Colors.primary} size="small" />
                ) : (
                  <Text
                    style={[
                      styles.codeBtnText,
                      countdown > 0 && styles.codeBtnTextDisabled,
                    ]}
                  >
                    {countdown > 0 ? `${countdown}s后重发` : '获取验证码'}
                  </Text>
                )}
              </TouchableOpacity>
            </View>
          </View>

          {/* 登录按钮 */}
          <TouchableOpacity
            style={[styles.loginBtn, loading && styles.loginBtnLoading]}
            onPress={handleLogin}
            disabled={loading}
            activeOpacity={0.8}
          >
            {loading ? (
              <ActivityIndicator color={Colors.white} />
            ) : (
              <Text style={styles.loginBtnText}>登 录</Text>
            )}
          </TouchableOpacity>

          {/* 协议 */}
          <TouchableOpacity
            style={styles.agreementRow}
            onPress={() => setAgreed(!agreed)}
            activeOpacity={0.7}
          >
            <View
              style={[
                styles.checkbox,
                agreed && styles.checkboxChecked,
              ]}
            >
              {agreed && <Text style={styles.checkmark}>✓</Text>}
            </View>
            <Text style={styles.agreementText}>
              已阅读并同意{' '}
              <Text style={styles.link}>《用户协议》</Text> 和{' '}
              <Text style={styles.link}>《隐私政策》</Text>
            </Text>
          </TouchableOpacity>
        </View>
      </View>
    </KeyboardAvoidingView>
  );
}

const styles = StyleSheet.create({
  container: {
    flex: 1,
    backgroundColor: Colors.white,
  },
  content: {
    flex: 1,
    justifyContent: 'center',
    paddingHorizontal: Spacing.xxxl,
  },
  // Logo
  logoArea: {
    alignItems: 'center',
    marginBottom: 48,
  },
  logo: {
    fontSize: 64,
    marginBottom: Spacing.lg,
  },
  appName: {
    fontSize: 28,
    fontWeight: '700',
    color: Colors.textPrimary,
    marginBottom: Spacing.sm,
  },
  subtitle: {
    fontSize: FontSize.md,
    color: Colors.textSecondary,
  },
  // 表单
  form: {
    gap: Spacing.xl,
  },
  inputGroup: {
    gap: Spacing.sm,
  },
  inputLabel: {
    fontSize: FontSize.sm,
    fontWeight: '600',
    color: Colors.textPrimary,
  },
  input: {
    borderWidth: 1,
    borderColor: Colors.border,
    borderRadius: BorderRadius.lg,
    paddingHorizontal: Spacing.lg,
    paddingVertical: 14,
    fontSize: FontSize.md,
    color: Colors.textPrimary,
    backgroundColor: Colors.background,
  },
  codeRow: {
    flexDirection: 'row',
    gap: Spacing.md,
  },
  codeInput: {
    flex: 1,
  },
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
  codeBtnDisabled: {
    borderColor: Colors.border,
  },
  codeBtnText: {
    color: Colors.primary,
    fontSize: FontSize.sm,
    fontWeight: '600',
  },
  codeBtnTextDisabled: {
    color: Colors.textHint,
  },
  // 登录按钮
  loginBtn: {
    backgroundColor: Colors.primary,
    borderRadius: BorderRadius.lg,
    paddingVertical: 16,
    alignItems: 'center',
    marginTop: Spacing.sm,
  },
  loginBtnLoading: {
    opacity: 0.7,
  },
  loginBtnText: {
    color: Colors.textWhite,
    fontSize: FontSize.lg,
    fontWeight: '600',
    letterSpacing: 4,
  },
  // 协议
  agreementRow: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: Spacing.sm,
  },
  checkbox: {
    width: 18,
    height: 18,
    borderRadius: 4,
    borderWidth: 1.5,
    borderColor: Colors.border,
    alignItems: 'center',
    justifyContent: 'center',
  },
  checkboxChecked: {
    backgroundColor: Colors.primary,
    borderColor: Colors.primary,
  },
  checkmark: {
    color: Colors.white,
    fontSize: 12,
    fontWeight: '700',
  },
  agreementText: {
    fontSize: FontSize.xs,
    color: Colors.textSecondary,
    flex: 1,
  },
  link: {
    color: Colors.primary,
  },
});
