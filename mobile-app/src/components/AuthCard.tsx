import React from 'react';
import { View, StyleSheet, ViewStyle } from 'react-native';
import { colors, radius, shadow, spacing } from '../theme';

interface AuthCardProps {
  children: React.ReactNode;
  style?: ViewStyle;
}

/**
 * 认证卡片 — 白色表面，微妙蓝色阴影
 *
 * 克制的容器：只提供表面和间距，
 * 让内部内容自己说话。
 */
export default function AuthCard({ children, style }: AuthCardProps) {
  return (
    <View style={[styles.card, style]}>
      {children}
    </View>
  );
}

const styles = StyleSheet.create({
  card: {
    backgroundColor: colors.surface,
    borderRadius: radius.lg,
    padding: spacing.xxl,
    marginHorizontal: spacing.lg,
    ...shadow.card,
  },
});
