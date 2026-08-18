import React, { useEffect, useState } from 'react';
import {
  View,
  Text,
  StyleSheet,
  KeyboardAvoidingView,
  Platform,
  ScrollView,
  Alert,
  TouchableOpacity,
} from 'react-native';
import { NativeStackNavigationProp } from '@react-navigation/native-stack';
import { colors, typography, spacing } from '../theme';
import { isValidPhone, isValidVerificationCode, validateLogin } from '../utils/validation';
import { loginAndSaveCredentials, sendSMSCode, smsLogin } from '../services/auth';
import type { SMSCodeResponse } from '../services/auth';
import { ErrorMessages } from '../types/auth';
import type { AuthStackParamList, SMSLoginResponse, UserInfo } from '../types/auth';
import { useUser } from '../contexts/UserContext';

import LogoHeader from '../components/LogoHeader';
import AuthCard from '../components/AuthCard';
import TextInput from '../components/TextInput';
import PrimaryButton from '../components/PrimaryButton';

type Props = {
  navigation: NativeStackNavigationProp<AuthStackParamList, 'Login'>;
};

export default function LoginScreen({ navigation }: Props) {
  const [mode, setMode] = useState<'password' | 'sms'>('password');
  const [phone, setPhone] = useState('');
  const [password, setPassword] = useState('');
  const [verificationCode, setVerificationCode] = useState('');
  const [countdown, setCountdown] = useState(0);
  const [sendingCode, setSendingCode] = useState(false);
  const [errors, setErrors] = useState<Record<string, string>>({});
  const [loading, setLoading] = useState(false);
  const { setUser } = useUser();

  useEffect(() => {
    if (countdown <= 0) return;
    const timer = setInterval(() => {
      setCountdown((current) => Math.max(current - 1, 0));
    }, 1000);
    return () => clearInterval(timer);
  }, [countdown]);

  const switchMode = (nextMode: 'password' | 'sms') => {
    setMode(nextMode);
    setErrors({});
  };

  const handleSendCode = async () => {
    if (sendingCode || countdown > 0) return;
    if (!isValidPhone(phone)) {
      setErrors({ phone: '请输入正确的手机号' });
      return;
    }
    setErrors({});
    setSendingCode(true);
    try {
      const resp = await sendSMSCode(phone);
      if (resp.code === 0) {
        setCountdown(Math.max(resp.retry_after_seconds || 60, 1));
        return;
      }
      if (resp.retry_after_seconds > 0) setCountdown(resp.retry_after_seconds);
      setErrors({ phone: resp.message || '验证码发送失败' });
    } catch (error: any) {
      const response = error?.response?.data as Partial<SMSCodeResponse> | undefined;
      if (response?.retry_after_seconds) setCountdown(response.retry_after_seconds);
      setErrors({ phone: response?.message || '验证码发送失败，请稍后重试' });
    } finally {
      setSendingCode(false);
    }
  };

  const finishLogin = (user: UserInfo) => {
    setUser(user);
    navigation.reset({ index: 0, routes: [{ name: 'Main' }] });
  };

  const handleLogin = async () => {
    const validationErrors = mode === 'password'
      ? validateLogin({ phone, password })
      : {
          ...(phone.trim() ? {} : { phone: '请输入手机号' }),
          ...(phone && !isValidPhone(phone) ? { phone: '手机号格式不正确' } : {}),
          ...(verificationCode ? {} : { verificationCode: '请输入验证码' }),
          ...(verificationCode && !isValidVerificationCode(verificationCode)
            ? { verificationCode: '请输入6位数字验证码' }
            : {}),
        };
    if (Object.keys(validationErrors).length > 0) {
      setErrors(validationErrors as Record<string, string>);
      return;
    }
    setErrors({});
    setLoading(true);

    try {
      const resp = mode === 'password'
        ? await loginAndSaveCredentials(phone, password)
        : await smsLogin(phone, verificationCode);
      if (resp.code === 0) {
        finishLogin(resp.user);
      } else {
        const msg = ErrorMessages[resp.code] || resp.message || '登录失败';
        setErrors({ phone: msg });
      }
    } catch (error: any) {
      const response = error?.response?.data as Partial<SMSLoginResponse> | undefined;
      if (mode === 'sms' && response?.message) {
        setErrors({ verificationCode: response.message });
      } else {
        Alert.alert('网络错误', '无法连接到服务器，请检查网络后重试');
      }
    } finally {
      setLoading(false);
    }
  };

  return (
    <KeyboardAvoidingView
      style={styles.container}
      behavior={Platform.OS === 'ios' ? 'padding' : 'height'}
    >
      <ScrollView
        contentContainerStyle={styles.scrollContent}
        keyboardShouldPersistTaps="handled"
      >
        {/* 签名元素：同心圆 Logo + 问候语 */}
        <LogoHeader subtitle="欢迎回家" />

        {/* 认证卡片 */}
        <AuthCard>
          <View style={styles.modeSwitch}>
            <TouchableOpacity
              accessibilityRole="tab"
              accessibilityState={{ selected: mode === 'password' }}
              style={[styles.modeOption, mode === 'password' && styles.modeOptionActive]}
              onPress={() => switchMode('password')}
            >
              <Text style={[styles.modeText, mode === 'password' && styles.modeTextActive]}>密码登录</Text>
            </TouchableOpacity>
            <TouchableOpacity
              accessibilityRole="tab"
              accessibilityState={{ selected: mode === 'sms' }}
              style={[styles.modeOption, mode === 'sms' && styles.modeOptionActive]}
              onPress={() => switchMode('sms')}
            >
              <Text style={[styles.modeText, mode === 'sms' && styles.modeTextActive]}>验证码登录</Text>
            </TouchableOpacity>
          </View>

          <TextInput
            label="手机号"
            value={phone}
            onChangeText={(text) => {
              setPhone(text);
              if (errors.phone) setErrors((e) => ({ ...e, phone: '' }));
            }}
            placeholder="输入手机号"
            keyboardType="phone-pad"
            maxLength={11}
            error={errors.phone}
            autoCapitalize="none"
          />

          {mode === 'password' ? (
            <TextInput
              label="密码"
              value={password}
              onChangeText={(text) => {
                setPassword(text);
                if (errors.password) setErrors((e) => ({ ...e, password: '' }));
              }}
              placeholder="输入密码"
              secureTextEntry
              error={errors.password}
              autoCapitalize="none"
            />
          ) : (
            <View style={styles.codeRow}>
              <TextInput
                label="短信验证码"
                value={verificationCode}
                onChangeText={(text) => {
                  setVerificationCode(text.replace(/\D/g, '').slice(0, 6));
                  if (errors.verificationCode) setErrors((e) => ({ ...e, verificationCode: '' }));
                }}
                placeholder="输入6位验证码"
                keyboardType="number-pad"
                maxLength={6}
                error={errors.verificationCode}
                containerStyle={styles.codeInput}
              />
              <TouchableOpacity
                accessibilityRole="button"
                accessibilityState={{ disabled: sendingCode || countdown > 0 }}
                style={[
                  styles.sendCodeButton,
                  (sendingCode || countdown > 0) && styles.sendCodeButtonDisabled,
                ]}
                onPress={handleSendCode}
                disabled={sendingCode || countdown > 0}
              >
                <Text style={styles.sendCodeText}>
                  {sendingCode
                    ? '发送中...'
                    : countdown > 0
                      ? `${countdown}s后重发`
                      : '获取验证码'}
                </Text>
              </TouchableOpacity>
            </View>
          )}

          <PrimaryButton
            title={mode === 'password' ? '登录' : '验证码登录'}
            onPress={handleLogin}
            loading={loading}
            style={styles.loginButton}
          />
        </AuthCard>

        {/* 切换到注册 */}
        <View style={styles.footer}>
          <Text style={styles.footerText}>还没有账号？</Text>
          <TouchableOpacity onPress={() => navigation.navigate('Register')}>
            <Text style={styles.footerLink}>创建新账号</Text>
          </TouchableOpacity>
        </View>
      </ScrollView>
    </KeyboardAvoidingView>
  );
}

const styles = StyleSheet.create({
  container: {
    flex: 1,
    backgroundColor: colors.background,
  },
  scrollContent: {
    flexGrow: 1,
    justifyContent: 'center',
    paddingBottom: spacing.xxxl,
  },
  loginButton: {
    marginTop: spacing.sm,
  },
  modeSwitch: {
    flexDirection: 'row',
    backgroundColor: colors.background,
    borderRadius: 10,
    padding: 3,
    marginBottom: spacing.xl,
  },
  modeOption: {
    flex: 1,
    minHeight: 38,
    alignItems: 'center',
    justifyContent: 'center',
    borderRadius: 8,
  },
  modeOptionActive: {
    backgroundColor: colors.surface,
    shadowColor: colors.textPrimary,
    shadowOpacity: 0.08,
    shadowRadius: 5,
    shadowOffset: { width: 0, height: 2 },
    elevation: 2,
  },
  modeText: {
    ...typography.caption,
    color: colors.textSecondary,
  },
  modeTextActive: {
    color: colors.primary,
    fontWeight: '700',
  },
  codeRow: {
    flexDirection: 'row',
    alignItems: 'flex-start',
    gap: spacing.sm,
  },
  codeInput: {
    flex: 1,
  },
  sendCodeButton: {
    minWidth: 106,
    height: 48,
    marginTop: 25,
    borderRadius: 8,
    alignItems: 'center',
    justifyContent: 'center',
    backgroundColor: colors.primarySubtle,
    paddingHorizontal: spacing.sm,
  },
  sendCodeButtonDisabled: {
    opacity: 0.55,
  },
  sendCodeText: {
    ...typography.caption,
    color: colors.primary,
    fontWeight: '700',
  },
  footer: {
    flexDirection: 'row',
    justifyContent: 'center',
    alignItems: 'center',
    marginTop: spacing.xxl,
    gap: spacing.xs,
  },
  footerText: {
    ...typography.body,
    color: colors.textSecondary,
  },
  footerLink: {
    ...typography.body,
    color: colors.primary,
    fontWeight: '600',
  },
});
