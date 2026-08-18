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
import { updateMember } from '../services/family';
import PrimaryButton from '../components/PrimaryButton';
import TextInput from '../components/TextInput';
import { colors, typography, spacing, radius } from '../theme';
import { FamilyRoleLabel } from '../types/family';
import type { FamilyRole } from '../types/family';
import type { AuthStackParamList } from '../types/auth';

export default function FamilyMemberEditScreen() {
  const insets = useSafeAreaInsets();
  const navigation =
    useNavigation<NativeStackNavigationProp<AuthStackParamList>>();
  const route =
    useRoute<RouteProp<AuthStackParamList, 'FamilyMemberEdit'>>();
  const { user } = useUser();

  const { familyId, member, myRole } = route.params;
  const isOwner = myRole === 1;
  const memberRole = member.role as FamilyRole;

  const [role, setRole] = useState<number>(member.role);
  const [relation, setRelation] = useState(member.relation ?? '');
  const [displayName, setDisplayName] = useState(member.display_name ?? '');
  const [loading, setLoading] = useState(false);

  const hasChanges =
    role !== member.role ||
    relation.trim() !== (member.relation ?? '') ||
    displayName.trim() !== (member.display_name ?? '');

  const canSubmit = hasChanges && !loading && !!user;

  const handleSubmit = useCallback(async () => {
    if (!canSubmit || !user) return;
    try {
      setLoading(true);
      await updateMember({
        family_id: familyId,
        member_user_id: member.user_id,
        role: isOwner ? role : undefined,
        relation: relation.trim(),
        display_name: displayName.trim(),
      });
      Alert.alert('更新成功', '成员信息已更新', [
        { text: '好的', onPress: () => navigation.goBack() },
      ]);
    } catch (e: any) {
      Alert.alert('更新失败', e.message || '请稍后重试');
    } finally {
      setLoading(false);
    }
  }, [canSubmit, user, familyId, member.user_id, isOwner, role, relation, displayName, navigation]);

  const memberName = member.display_name || member.nickname;

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
        <Text style={styles.navTitle}>编辑成员</Text>
        <View style={{ width: 24 }} />
      </View>

      <ScrollView
        contentContainerStyle={styles.scrollContent}
        keyboardShouldPersistTaps="handled"
        showsVerticalScrollIndicator={false}
      >
        {/* 成员信息头部 */}
        <View style={styles.memberHeader}>
          <View style={styles.memberAvatar}>
            <Text style={styles.memberAvatarText}>
              {memberName.charAt(0).toUpperCase()}
            </Text>
          </View>
          <Text style={styles.memberName}>{memberName}</Text>
          <View style={styles.roleTag}>
            <Text style={styles.roleTagText}>
              {FamilyRoleLabel[memberRole]}
            </Text>
          </View>
        </View>

        {/* 表单 */}
        <View style={styles.form}>
          {/* 角色选择 — 仅所有者可改 */}
          {isOwner && memberRole !== 1 && (
            <View style={styles.fieldGroup}>
              <Text style={styles.fieldLabel}>角色</Text>
              <View style={styles.roleSelector}>
                <TouchableOpacity
                  style={[
                    styles.roleOption,
                    role === 2 && styles.roleOptionActive,
                  ]}
                  onPress={() => setRole(2)}
                  activeOpacity={0.7}
                >
                  <Ionicons
                    name="shield-checkmark-outline"
                    size={18}
                    color={role === 2 ? colors.success : colors.textSecondary}
                  />
                  <Text
                    style={[
                      styles.roleOptionText,
                      role === 2 && { color: colors.success },
                    ]}
                  >
                    管理员
                  </Text>
                </TouchableOpacity>

                <TouchableOpacity
                  style={[
                    styles.roleOption,
                    role === 3 && styles.roleOptionActive,
                  ]}
                  onPress={() => setRole(3)}
                  activeOpacity={0.7}
                >
                  <Ionicons
                    name="person-outline"
                    size={18}
                    color={role === 3 ? colors.primary : colors.textSecondary}
                  />
                  <Text
                    style={[
                      styles.roleOptionText,
                      role === 3 && { color: colors.primary },
                    ]}
                  >
                    成员
                  </Text>
                </TouchableOpacity>
              </View>
            </View>
          )}

          {/* 家庭关系 */}
          <TextInput
            label="家庭关系（选填）"
            placeholder="例如：妈妈、爸爸、孩子"
            value={relation}
            onChangeText={setRelation}
            maxLength={20}
          />

          {/* 家庭内昵称 */}
          <TextInput
            label="家庭内昵称（选填）"
            placeholder="不填则使用用户昵称"
            value={displayName}
            onChangeText={setDisplayName}
            maxLength={50}
          />
        </View>

        <PrimaryButton
          title="保存修改"
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

  /* 成员头部 */
  memberHeader: {
    alignItems: 'center',
    paddingVertical: spacing.xxl,
  },
  memberAvatar: {
    width: 72,
    height: 72,
    borderRadius: 36,
    backgroundColor: colors.primaryLight,
    alignItems: 'center',
    justifyContent: 'center',
    marginBottom: spacing.md,
    borderWidth: 2,
    borderColor: colors.primarySubtle,
  },
  memberAvatarText: {
    fontSize: 26,
    fontWeight: '700',
    color: colors.primary,
  },
  memberName: {
    ...typography.h2,
    color: colors.textPrimary,
    marginBottom: spacing.sm,
  },
  roleTag: {
    paddingHorizontal: spacing.md,
    paddingVertical: 4,
    backgroundColor: colors.primarySubtle,
    borderRadius: radius.sm,
  },
  roleTagText: {
    ...typography.caption,
    color: colors.primary,
    fontWeight: '600',
  },

  /* 表单 */
  form: {
    marginBottom: spacing.xxl,
  },
  fieldGroup: {
    marginBottom: spacing.lg,
  },
  fieldLabel: {
    ...typography.caption,
    color: colors.textSecondary,
    marginBottom: spacing.sm,
  },
  roleSelector: {
    flexDirection: 'row',
    gap: spacing.md,
  },
  roleOption: {
    flex: 1,
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'center',
    gap: spacing.sm,
    height: 48,
    backgroundColor: colors.surface,
    borderRadius: radius.md,
    borderWidth: 1.5,
    borderColor: colors.border,
  },
  roleOptionActive: {
    borderColor: colors.primary,
    backgroundColor: colors.primarySubtle,
  },
  roleOptionText: {
    ...typography.body,
    fontWeight: '500',
    color: colors.textSecondary,
  },
});
