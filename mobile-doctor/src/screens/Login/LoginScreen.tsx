/**
 * 登录页 - 医生端
 * 手机号 + 验证码登录（authAPI.sendCode / useAuth.login）
 */
import React, { useState } from 'react';
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
import { Colors, FontSize, Spacing, BorderRadius, Shadow } from '../../constants/theme';

export default function LoginScreen() {
  const { login } = useAuth();
  const [phone, setPhone] = useState('');
  const [code, setCode] = useState('');
  const [sendingCode, setSendingCode] = useState(false);
  const [loading, setLoading] = useState(false);

  const validatePhone = (p: string) => /^1[3-9]\d{9}$/.test(p);

  const handleSendCode = async () => {
    if (!validatePhone(phone)) {
      Alert.alert('提示', '请输入正确的手机号');
      return;
    }
    setSendingCode(true);
    try {
      await authAPI.sendCode(phone);
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
    setLoading(true);
    try {
      await login(phone, code);
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
        <View style={styles.logoArea}>
          <View style={styles.logoCircle}>
            <Text style={styles.logoIcon}>MD</Text>
          </View>
          <Text style={styles.appName}>MedAgent·医生端</Text>
          <Text style={styles.subtitle}>医药数字员工 · 医生工作台</Text>
        </View>

        <View style={[styles.card, Shadow.card]}>
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
                style={[styles.input, styles.codeInput]}
                placeholder="请输入验证码"
                placeholderTextColor={Colors.textHint}
                keyboardType="number-pad"
                maxLength={6}
                value={code}
                onChangeText={setCode}
              />
              <TouchableOpacity
                style={styles.codeButton}
                onPress={handleSendCode}
                disabled={sendingCode}
              >
                <Text style={styles.codeButtonText}>
                  {sendingCode ? '发送中...' : '获取验证码'}
                </Text>
              </TouchableOpacity>
            </View>
          </View>

          <TouchableOpacity
            style={[styles.loginButton, loading && styles.loginButtonDisabled]}
            onPress={handleLogin}
            disabled={loading}
          >
            {loading ? (
              <ActivityIndicator color={Colors.textWhite} />
            ) : (
              <Text style={styles.loginButtonText}>登录</Text>
            )}
          </TouchableOpacity>
        </View>
      </View>
    </KeyboardAvoidingView>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1, backgroundColor: Colors.primary },
  content: { flex: 1, justifyContent: 'center', paddingHorizontal: Spacing.xl },
  logoArea: { alignItems: 'center', marginBottom: Spacing.xxxl },
  logoCircle: {
    width: 72,
    height: 72,
    borderRadius: BorderRadius.xl,
    backgroundColor: Colors.textWhite,
    alignItems: 'center',
    justifyContent: 'center',
    marginBottom: Spacing.lg,
  },
  logoIcon: { fontSize: FontSize.xxl, fontWeight: '800', color: Colors.primary },
  appName: { fontSize: FontSize.xxl, fontWeight: '700', color: Colors.textWhite },
  subtitle: { fontSize: FontSize.sm, color: Colors.primarySurface, marginTop: Spacing.sm },
  card: {
    backgroundColor: Colors.card,
    borderRadius: BorderRadius.xl,
    padding: Spacing.xl,
  },
  inputGroup: { marginBottom: Spacing.lg },
  inputLabel: {
    fontSize: FontSize.sm,
    color: Colors.textSecondary,
    marginBottom: Spacing.sm,
    fontWeight: '600',
  },
  input: {
    height: 48,
    borderWidth: 1,
    borderColor: Colors.border,
    borderRadius: BorderRadius.md,
    paddingHorizontal: Spacing.md,
    fontSize: FontSize.md,
    color: Colors.textPrimary,
    backgroundColor: Colors.backgroundAlt,
  },
  codeRow: { flexDirection: 'row', alignItems: 'center' },
  codeInput: { flex: 1, marginRight: Spacing.sm },
  codeButton: {
    height: 48,
    paddingHorizontal: Spacing.lg,
    borderRadius: BorderRadius.md,
    backgroundColor: Colors.primarySurface,
    alignItems: 'center',
    justifyContent: 'center',
  },
  codeButtonText: { fontSize: FontSize.sm, color: Colors.primary, fontWeight: '600' },
  loginButton: {
    height: 48,
    borderRadius: BorderRadius.md,
    backgroundColor: Colors.primary,
    alignItems: 'center',
    justifyContent: 'center',
    marginTop: Spacing.sm,
  },
  loginButtonDisabled: { opacity: 0.6 },
  loginButtonText: { fontSize: FontSize.md, color: Colors.textWhite, fontWeight: '700' },
});
