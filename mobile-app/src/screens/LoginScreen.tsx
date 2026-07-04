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
import { validateLogin } from '../utils/validation';
import { loginAndSaveToken } from '../services/auth';
import { saveUserId } from '../services/api';
import { ErrorMessages } from '../types/auth';
import type { AuthStackParamList } from '../types/auth';
import { useUser } from '../contexts/UserContext';

import LogoHeader from '../components/LogoHeader';
import AuthCard from '../components/AuthCard';
import TextInput from '../components/TextInput';
import PrimaryButton from '../components/PrimaryButton';

type Props = {
  navigation: NativeStackNavigationProp<AuthStackParamList, 'Login'>;
};

export default function LoginScreen({ navigation }: Props) {
  const [phone, setPhone] = useState('');
  const [password, setPassword] = useState('');
  const [errors, setErrors] = useState<Record<string, string>>({});
  const [loading, setLoading] = useState(false);
  const { setUser } = useUser();

  const handleLogin = async () => {
    const validationErrors = validateLogin({ phone, password });
    if (Object.keys(validationErrors).length > 0) {
      setErrors(validationErrors as Record<string, string>);
      return;
    }
    setErrors({});
    setLoading(true);

    try {
      const resp = await loginAndSaveToken(phone, password);
      if (resp.code === 0) {
        setUser(resp.user);
        saveUserId(resp.user.id);
        navigation.reset({
          index: 0,
          routes: [{ name: 'Main' }],
        });
      } else {
        const msg = ErrorMessages[resp.code] || resp.message || '登录失败';
        setErrors({ phone: msg });
      }
    } catch {
      Alert.alert('网络错误', '无法连接到服务器，请检查网络后重试');
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
            placeholder="输入密码"
            secureTextEntry
            error={errors.password}
            autoCapitalize="none"
          />

          <PrimaryButton
            title="登录"
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
