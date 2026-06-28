import React, { useState } from 'react';
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
import { validateRegister } from '../utils/validation';
import { register } from '../services/auth';
import { ErrorMessages } from '../types/auth';
import type { AuthStackParamList } from '../types/auth';

import LogoHeader from '../components/LogoHeader';
import AuthCard from '../components/AuthCard';
import TextInput from '../components/TextInput';
import PrimaryButton from '../components/PrimaryButton';

type Props = {
  navigation: NativeStackNavigationProp<AuthStackParamList, 'Register'>;
};

export default function RegisterScreen({ navigation }: Props) {
  const [nickname, setNickname] = useState('');
  const [phone, setPhone] = useState('');
  const [password, setPassword] = useState('');
  const [confirmPassword, setConfirmPassword] = useState('');
  const [errors, setErrors] = useState<Record<string, string>>({});
  const [loading, setLoading] = useState(false);
  const [serverError, setServerError] = useState('');

  const handleRegister = async () => {
    setServerError('');
    const validationErrors = validateRegister({
      phone,
      password,
      nickname,
      confirmPassword,
    });
    if (Object.keys(validationErrors).length > 0) {
      setErrors(validationErrors as Record<string, string>);
      return;
    }
    setErrors({});
    setLoading(true);

    try {
      const resp = await register(phone, password, nickname);
      if (resp.code === 0) {
        // 注册成功 → 显示成功提示 → 跳转到登录页
        Alert.alert('注册成功', '账号已创建，请登录', [
          {
            text: '去登录',
            onPress: () => {
              navigation.reset({
                index: 0,
                routes: [{ name: 'Login' }],
              });
            },
          },
        ]);
      } else {
        // 服务端业务错误 → 显示在卡片上方，不在具体字段上
        const msg = ErrorMessages[resp.code] || resp.message || '注册失败';
        setServerError(msg);
      }
    } catch {
      setServerError('无法连接到服务器，请检查网络后重试');
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
        {/* 签名元素：同心圆 Logo + 语义化副标题 */}
        <LogoHeader subtitle="创建你的账号" />

        <AuthCard>
          {serverError !== '' && (
            <Text style={styles.serverError}>{serverError}</Text>
          )}

          <TextInput
            label="昵称"
            value={nickname}
            onChangeText={(text) => {
              setNickname(text);
              if (errors.nickname) setErrors((e) => ({ ...e, nickname: '' }));
            }}
            placeholder="你的名字"
            error={errors.nickname}
            autoCapitalize="none"
          />

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

          <TextInput
            label="密码"
            value={password}
            onChangeText={(text) => {
              setPassword(text);
              if (errors.password) setErrors((e) => ({ ...e, password: '' }));
            }}
            placeholder="至少6位密码"
            secureTextEntry
            error={errors.password}
            autoCapitalize="none"
          />

          <TextInput
            label="确认密码"
            value={confirmPassword}
            onChangeText={(text) => {
              setConfirmPassword(text);
              if (errors.confirmPassword)
                setErrors((e) => ({ ...e, confirmPassword: '' }));
            }}
            placeholder="再次输入密码"
            secureTextEntry
            error={errors.confirmPassword}
            autoCapitalize="none"
          />

          <PrimaryButton
            title="注册"
            onPress={handleRegister}
            loading={loading}
            style={styles.registerButton}
          />
        </AuthCard>

        {/* 切换回登录 */}
        <View style={styles.footer}>
          <Text style={styles.footerText}>已有账号？</Text>
          <TouchableOpacity onPress={() => navigation.goBack()}>
            <Text style={styles.footerLink}>返回登录</Text>
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
  registerButton: {
    marginTop: spacing.sm,
  },
  serverError: {
    ...typography.caption,
    color: colors.error,
    backgroundColor: colors.errorBackground,
    paddingHorizontal: spacing.md,
    paddingVertical: spacing.sm,
    borderRadius: 6,
    marginBottom: spacing.md,
    textAlign: 'center',
    overflow: 'hidden',
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
