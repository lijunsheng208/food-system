import React from 'react';
import { View, Text, StyleSheet } from 'react-native';
import { useUser } from '../contexts/UserContext';
import { colors, typography, spacing } from '../theme';
import LogoHeader from '../components/LogoHeader';
import AuthCard from '../components/AuthCard';

export default function HomeScreen() {
  const { user } = useUser();
  const nickname = user?.nickname ?? '用户';

  return (
    <View style={styles.container}>
      <LogoHeader subtitle={`${nickname}，欢迎回来`} />

      <AuthCard style={styles.card}>
        <Text style={styles.greeting}>你已经成功登录 FamilyOS。</Text>
        <Text style={styles.hint}>更多功能即将上线，敬请期待。</Text>
      </AuthCard>
    </View>
  );
}

const styles = StyleSheet.create({
  container: {
    flex: 1,
    backgroundColor: colors.background,
    justifyContent: 'center',
  },
  card: {
    alignItems: 'center',
  },
  greeting: {
    ...typography.body,
    color: colors.textPrimary,
    textAlign: 'center',
    marginBottom: spacing.sm,
  },
  hint: {
    ...typography.caption,
    color: colors.textSecondary,
    textAlign: 'center',
  },
});
