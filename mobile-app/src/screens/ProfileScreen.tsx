import React from 'react';
import {
  View,
  Text,
  StyleSheet,
  Alert,
  TouchableOpacity,
  ScrollView,
  Image,
} from 'react-native';
import { useSafeAreaInsets } from 'react-native-safe-area-context';
import { Ionicons } from '@expo/vector-icons';
import { useNavigation } from '@react-navigation/native';
import type { NativeStackNavigationProp } from '@react-navigation/native-stack';
import { useUser } from '../contexts/UserContext';
import { removeToken } from '../services/api';
import { colors, typography, spacing, radius, shadow } from '../theme';
import type { AuthStackParamList } from '../types/auth';

export default function ProfileScreen() {
  const { user, clearUser } = useUser();
  const insets = useSafeAreaInsets();
  const navigation =
    useNavigation<NativeStackNavigationProp<AuthStackParamList>>();

  const handleGoProfileDetail = () => {
    navigation.navigate('ProfileDetail');
  };

  const nickname = user?.nickname ?? '未设置昵称';
  const avatarLetter = nickname.charAt(0).toUpperCase();

  const handleFamilyMgmt = () => {
    Alert.alert('家庭管理', '家庭管理功能即将上线，敬请期待');
  };

  const handleLogout = () => {
    Alert.alert('退出登录', '确定要退出当前账号吗？', [
      { text: '取消', style: 'cancel' },
      {
        text: '退出',
        style: 'destructive',
        onPress: async () => {
          await removeToken();
          clearUser();
          navigation.reset({
            index: 0,
            routes: [{ name: 'Login' }],
          });
        },
      },
    ]);
  };

  return (
    <View style={[styles.container, { paddingTop: insets.top }]}>
      <ScrollView
        contentContainerStyle={styles.scrollContent}
        showsVerticalScrollIndicator={false}
      >
        {/* 标题 */}
        <Text style={styles.pageTitle}>我的</Text>

        {/* 个人信息卡片 */}
        <TouchableOpacity
          style={styles.profileCard}
          activeOpacity={0.7}
          onPress={handleGoProfileDetail}
        >
          {/* 头像 */}
          <View style={styles.avatar}>
            {user?.avatar ? (
              <Image source={{ uri: user.avatar }} style={styles.avatarImage} />
            ) : (
              <Text style={styles.avatarText}>{avatarLetter}</Text>
            )}
          </View>

          {/* 用户名 + 家庭 */}
          <View style={styles.userInfo}>
            <Text style={styles.nickname} numberOfLines={1}>
              {nickname}
            </Text>
            <View style={styles.familyRow}>
              <Ionicons
                name="home-outline"
                size={14}
                color={colors.primary}
                style={styles.familyIcon}
              />
              <Text style={styles.familyText} numberOfLines={1}>
                未加入家庭
              </Text>
            </View>
          </View>

          {/* 编辑箭头 */}
          <Ionicons
            name="chevron-forward"
            size={20}
            color={colors.textSecondary}
          />
        </TouchableOpacity>

        {/* 菜单卡片 */}
        <View style={styles.menuCard}>
          {/* 家庭管理 */}
          <TouchableOpacity
            style={styles.menuItem}
            activeOpacity={0.6}
            onPress={handleFamilyMgmt}
          >
            <View style={[styles.menuIconBox, { backgroundColor: colors.primarySubtle }]}>
              <Ionicons name="people-outline" size={20} color={colors.primary} />
            </View>
            <Text style={styles.menuText}>家庭管理</Text>
            <Ionicons
              name="chevron-forward"
              size={18}
              color={colors.textSecondary}
            />
          </TouchableOpacity>

          {/* 分割线 */}
          <View style={styles.divider} />

          {/* 退出登录 */}
          <TouchableOpacity
            style={styles.menuItem}
            activeOpacity={0.6}
            onPress={handleLogout}
          >
            <View style={[styles.menuIconBox, { backgroundColor: colors.errorBackground }]}>
              <Ionicons name="log-out-outline" size={20} color={colors.error} />
            </View>
            <Text style={styles.menuTextDanger}>退出登录</Text>
            <Ionicons
              name="chevron-forward"
              size={18}
              color={colors.textSecondary}
            />
          </TouchableOpacity>
        </View>
      </ScrollView>
    </View>
  );
}

const styles = StyleSheet.create({
  container: {
    flex: 1,
    backgroundColor: colors.background,
  },
  scrollContent: {
    paddingHorizontal: spacing.lg,
    paddingBottom: spacing.xxxl,
  },

  /* 页面标题 */
  pageTitle: {
    ...typography.h1,
    color: colors.textPrimary,
    marginTop: spacing.lg,
    marginBottom: spacing.xxl,
  },

  /* 个人信息卡片 */
  profileCard: {
    backgroundColor: colors.surface,
    borderRadius: radius.lg,
    padding: spacing.xl,
    flexDirection: 'row',
    alignItems: 'center',
    ...shadow.card,
  },
  avatar: {
    width: 64,
    height: 64,
    borderRadius: 32,
    backgroundColor: colors.primaryLight,
    alignItems: 'center',
    justifyContent: 'center',
    borderWidth: 2,
    borderColor: colors.primarySubtle,
  },
  avatarText: {
    fontSize: 24,
    fontWeight: '700',
    color: colors.primary,
  },
  avatarImage: {
    width: 64,
    height: 64,
    borderRadius: 32,
  },
  userInfo: {
    flex: 1,
    marginLeft: spacing.lg,
  },
  nickname: {
    ...typography.h2,
    color: colors.textPrimary,
    marginBottom: spacing.xs,
  },
  familyRow: {
    flexDirection: 'row',
    alignItems: 'center',
  },
  familyIcon: {
    marginRight: spacing.xs,
  },
  familyText: {
    ...typography.caption,
    color: colors.textSecondary,
  },

  /* 菜单卡片 */
  menuCard: {
    backgroundColor: colors.surface,
    borderRadius: radius.lg,
    marginTop: spacing.lg,
    paddingVertical: spacing.xs,
    ...shadow.card,
  },
  menuItem: {
    flexDirection: 'row',
    alignItems: 'center',
    height: 52,
    paddingHorizontal: spacing.lg,
  },
  menuIconBox: {
    width: 36,
    height: 36,
    borderRadius: radius.md,
    alignItems: 'center',
    justifyContent: 'center',
  },
  menuText: {
    ...typography.body,
    color: colors.textPrimary,
    flex: 1,
    marginLeft: spacing.md,
  },
  menuTextDanger: {
    ...typography.body,
    color: colors.error,
    flex: 1,
    marginLeft: spacing.md,
  },
  divider: {
    height: StyleSheet.hairlineWidth,
    backgroundColor: colors.border,
    marginLeft: spacing.lg + 36 + spacing.md, // align with text
    marginRight: spacing.lg,
  },
});
