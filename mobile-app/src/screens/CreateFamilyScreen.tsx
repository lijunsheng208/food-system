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
import { useNavigation } from '@react-navigation/native';
import type { NativeStackNavigationProp } from '@react-navigation/native-stack';
import { useUser } from '../contexts/UserContext';
import { createFamily, updateFamily } from '../services/family';
import PrimaryButton from '../components/PrimaryButton';
import TextInput from '../components/TextInput';
import { colors, typography, spacing, radius } from '../theme';
import type { AuthStackParamList } from '../types/auth';

export default function CreateFamilyScreen() {
  const insets = useSafeAreaInsets();
  const navigation =
    useNavigation<NativeStackNavigationProp<AuthStackParamList>>();
  const { user } = useUser();

  const [name, setName] = useState('');
  const [description, setDescription] = useState('');
  const [loading, setLoading] = useState(false);

  const trimmedName = name.trim();

  // 表单校验
  const nameError =
    trimmedName.length > 50
      ? '家庭名称不能超过 50 个字'
      : undefined;

  const canSubmit = trimmedName.length > 0 && !nameError && !loading;

  const handleSubmit = useCallback(async () => {
    if (!canSubmit || !user) return;
    try {
      setLoading(true);
      await createFamily({
        user_id: user.id,
        name: trimmedName,
        description: description.trim() || undefined,
      });
      Alert.alert('创建成功', `家庭"${trimmedName}"已创建`, [
        { text: '好的', onPress: () => navigation.goBack() },
      ]);
    } catch (e: any) {
      Alert.alert('创建失败', e.message || '请稍后重试');
    } finally {
      setLoading(false);
    }
  }, [canSubmit, user, trimmedName, description, navigation]);

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
        <Text style={styles.navTitle}>创建家庭</Text>
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
            <Ionicons name="home-outline" size={32} color={colors.primary} />
          </View>
          <Text style={styles.headerTitle}>创建你的家庭</Text>
          <Text style={styles.headerDesc}>
            创建家庭后，你可以邀请家人加入，{'\n'}
            一起管理菜谱、购物和日常事务。
          </Text>
        </View>

        {/* 表单 */}
        <View style={styles.form}>
          <TextInput
            label="家庭名称"
            placeholder="例如：小明的一家"
            value={name}
            onChangeText={setName}
            maxLength={50}
            error={nameError}
            autoFocus
            returnKeyType="next"
          />
          <TextInput
            label="家庭简介（选填）"
            placeholder="一起认真吃饭，好好生活"
            value={description}
            onChangeText={setDescription}
            maxLength={255}
            multiline
            numberOfLines={3}
            style={{ height: 80, textAlignVertical: 'top' }}
          />
        </View>

        <PrimaryButton
          title="创建家庭"
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
    lineHeight: 22,
  },

  /* 表单 */
  form: {
    marginBottom: spacing.xxl,
  },
});
