import React, { useCallback, useState } from 'react';
import {
  View,
  Text,
  StyleSheet,
  ScrollView,
  TouchableOpacity,
  Alert,
  KeyboardAvoidingView,
  Platform,
} from 'react-native';
import { useSafeAreaInsets } from 'react-native-safe-area-context';
import { Ionicons } from '@expo/vector-icons';
import { useNavigation, useRoute } from '@react-navigation/native';
import type { NativeStackNavigationProp } from '@react-navigation/native-stack';
import type { RouteProp } from '@react-navigation/native';
import { useUser } from '../contexts/UserContext';
import { joinFamily } from '../services/family';
import PrimaryButton from '../components/PrimaryButton';
import TextInput from '../components/TextInput';
import { colors, typography, spacing, radius } from '../theme';
import type { AuthStackParamList } from '../types/auth';

export default function JoinFamilyScreen() {
  const insets = useSafeAreaInsets();
  const navigation =
    useNavigation<NativeStackNavigationProp<AuthStackParamList>>();
  const route = useRoute<RouteProp<AuthStackParamList, 'JoinFamily'>>();
  const { user } = useUser();

  const [inviteCode, setInviteCode] = useState(route.params?.inviteCode ?? '');
  const [relation, setRelation] = useState('');
  const [displayName, setDisplayName] = useState('');
  const [loading, setLoading] = useState(false);

  // 邀请码自动转大写、去空格
  const handleInviteCodeChange = (text: string) => {
    setInviteCode(text.replace(/\s/g, '').toUpperCase());
  };

  const trimmedCode = inviteCode.trim();

  const codeError =
    trimmedCode.length > 0 && trimmedCode.length < 6
      ? '邀请码至少需要 6 位'
      : undefined;

  const canSubmit =
    trimmedCode.length >= 6 && !codeError && !loading && !!user;

  const handleSubmit = useCallback(async () => {
    if (!canSubmit || !user) return;
    try {
      setLoading(true);
      const res = await joinFamily({
        user_id: user.id,
        invite_code: trimmedCode,
        relation: relation.trim() || undefined,
        display_name: displayName.trim() || undefined,
      });
      Alert.alert('加入成功', `你已成功加入家庭`, [
        { text: '好的', onPress: () => navigation.goBack() },
      ]);
    } catch (e: any) {
      Alert.alert('加入失败', e.message || '请稍后重试');
    } finally {
      setLoading(false);
    }
  }, [canSubmit, user, trimmedCode, relation, displayName, navigation]);

  return (
    <KeyboardAvoidingView
      style={[styles.container, { paddingTop: insets.top }]}
      behavior={Platform.OS === 'ios' ? 'padding' : undefined}
    >
      {/* 导航栏 */}
      <View style={styles.navBar}>
        <TouchableOpacity
          onPress={() => navigation.goBack()}
          hitSlop={{ top: 8, bottom: 8, left: 8, right: 8 }}
        >
          <Ionicons name="chevron-back" size={24} color={colors.textPrimary} />
        </TouchableOpacity>
        <Text style={styles.navTitle}>加入家庭</Text>
        <View style={{ width: 24 }} />
      </View>

      <ScrollView
        contentContainerStyle={styles.scrollContent}
        keyboardShouldPersistTaps="handled"
        showsVerticalScrollIndicator={false}
      >
        {/* 顶部说明 */}
        <View style={styles.header}>
          <View style={styles.headerIconCircle}>
            <Ionicons name="key-outline" size={32} color={colors.primary} />
          </View>
          <Text style={styles.headerTitle}>输入邀请码</Text>
          <Text style={styles.headerDesc}>
            请向家庭所有者或管理员索取邀请码
          </Text>
        </View>

        {/* 表单 */}
        <View style={styles.form}>
          <TextInput
            label="邀请码"
            placeholder="输入 6-8 位邀请码"
            value={inviteCode}
            onChangeText={handleInviteCodeChange}
            maxLength={8}
            autoCapitalize="characters"
            autoCorrect={false}
            error={codeError}
            autoFocus
            returnKeyType="next"
          />

          <TextInput
            label="家庭关系（选填）"
            placeholder="例如：妈妈、爸爸、孩子"
            value={relation}
            onChangeText={setRelation}
            maxLength={20}
            returnKeyType="next"
          />

          <TextInput
            label="家庭内昵称（选填）"
            placeholder="不填则使用你的用户昵称"
            value={displayName}
            onChangeText={setDisplayName}
            maxLength={50}
          />
        </View>

        <PrimaryButton
          title="加入家庭"
          onPress={handleSubmit}
          loading={loading}
          disabled={!canSubmit}
        />
      </ScrollView>
    </KeyboardAvoidingView>
  );
}

const styles = StyleSheet.create({
  container: {
    flex: 1,
    backgroundColor: colors.background,
  },

  /* 导航栏 */
  navBar: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    paddingHorizontal: spacing.lg,
    paddingVertical: spacing.md,
  },
  navTitle: {
    ...typography.h2,
    color: colors.textPrimary,
  },

  scrollContent: {
    paddingHorizontal: spacing.lg,
    paddingBottom: spacing.xxxl,
  },

  /* 顶部说明 */
  header: {
    alignItems: 'center',
    paddingVertical: spacing.xxl,
  },
  headerIconCircle: {
    width: 72,
    height: 72,
    borderRadius: 36,
    backgroundColor: colors.primarySubtle,
    alignItems: 'center',
    justifyContent: 'center',
    marginBottom: spacing.lg,
  },
  headerTitle: {
    ...typography.h2,
    color: colors.textPrimary,
    marginBottom: spacing.sm,
  },
  headerDesc: {
    ...typography.body,
    color: colors.textSecondary,
    textAlign: 'center',
  },

  /* 表单 */
  form: {
    marginBottom: spacing.xxl,
  },
});
