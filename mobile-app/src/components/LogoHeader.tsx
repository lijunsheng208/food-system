import React from 'react';
import { View, Text, StyleSheet } from 'react-native';
import { colors, typography, spacing } from '../theme';

/**
 * LogoHeader — 页面的签名元素
 *
 * 同心蓝色圆圈组成的抽象家庭肖像：
 * 不同深浅的蓝色圆圈交错重叠，象征家庭成员在同一屋檐下。
 * 这是此页面让人记住的独特元素，不是模板化的 App 图标。
 */
export default function LogoHeader({ subtitle }: { subtitle?: string }) {
  return (
    <View style={styles.container}>
      {/* 抽象家庭肖像：三个同心/交错的蓝色圆圈 */}
      <View style={styles.logoContainer}>
        {/* 外层大圆 — 最浅蓝，代表"家" */}
        <View style={[styles.circle, styles.outerCircle]} />
        {/* 中层圆 — 中蓝 */}
        <View style={[styles.circle, styles.middleCircle]} />
        {/* 内层小圆 — 最深蓝，代表核心 */}
        <View style={[styles.circle, styles.innerCircle]} />
      </View>

      <Text style={styles.title}>FamilyOS</Text>
      {subtitle && <Text style={styles.subtitle}>{subtitle}</Text>}
    </View>
  );
}

const CIRCLE_SIZE = 80;

const styles = StyleSheet.create({
  container: {
    alignItems: 'center',
    paddingVertical: spacing.xxxl,
  },
  logoContainer: {
    width: CIRCLE_SIZE,
    height: CIRCLE_SIZE,
    alignItems: 'center',
    justifyContent: 'center',
    marginBottom: spacing.lg,
  },
  circle: {
    position: 'absolute',
    borderRadius: 9999,
    borderWidth: 3,
  },
  outerCircle: {
    width: CIRCLE_SIZE,
    height: CIRCLE_SIZE,
    borderColor: '#93C5FD',   // blue-300
    backgroundColor: 'rgba(219, 234, 254, 0.4)',
  },
  middleCircle: {
    width: CIRCLE_SIZE * 0.62,
    height: CIRCLE_SIZE * 0.62,
    borderColor: '#3B82F6',   // blue-500
    backgroundColor: 'rgba(147, 197, 253, 0.3)',
  },
  innerCircle: {
    width: CIRCLE_SIZE * 0.3,
    height: CIRCLE_SIZE * 0.3,
    borderColor: '#1A56DB',   // primary
    backgroundColor: 'rgba(59, 130, 246, 0.25)',
  },
  title: {
    ...typography.h1,
    color: colors.primary,
  },
  subtitle: {
    ...typography.caption,
    color: colors.textSecondary,
    marginTop: spacing.xs,
  },
});
