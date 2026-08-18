import React, { useCallback, useState } from 'react';
import {
  View,
  Text,
  StyleSheet,
  ScrollView,
  TouchableOpacity,
  Alert,
  Modal,
  TextInput,
  KeyboardAvoidingView,
  Platform,
  Image,
  ActivityIndicator,
} from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import * as ImagePicker from 'expo-image-picker';
import { useSafeAreaInsets } from 'react-native-safe-area-context';
import { useNavigation } from '@react-navigation/native';
import type { NativeStackNavigationProp } from '@react-navigation/native-stack';
import { useUser } from '../contexts/UserContext';
import { updateProfile, uploadAvatar } from '../services/auth';
import { colors, typography, spacing, radius, shadow } from '../theme';
import type { AuthStackParamList } from '../types/auth';

const GENDER_OPTIONS = [
  { label: '未设置', value: 0 },
  { label: '男', value: 1 },
  { label: '女', value: 2 },
];

export default function ProfileDetailScreen() {
  const insets = useSafeAreaInsets();
  const navigation =
    useNavigation<NativeStackNavigationProp<AuthStackParamList>>();
  const { user, familyName, setUser } = useUser();

  const nickname = user?.nickname ?? '未设置昵称';
  const phone = user?.phone ?? '未绑定';
  const avatarLetter = nickname.charAt(0).toUpperCase();
  const currentGender = user?.gender ?? 0;

  // 昵称编辑状态
  const [nicknameModalVisible, setNicknameModalVisible] = useState(false);
  const [nicknameDraft, setNicknameDraft] = useState('');

  // 修改昵称
  const handleOpenNickname = useCallback(() => {
    setNicknameDraft(nickname);
    setNicknameModalVisible(true);
  }, [nickname]);

  const handleSaveNickname = useCallback(async () => {
    const trimmed = nicknameDraft.trim();
    if (!trimmed || trimmed === nickname || !user) {
      setNicknameModalVisible(false);
      return;
    }
    try {
    await updateProfile({ nickname: trimmed });
      setUser({ ...user, nickname: trimmed });
      setNicknameModalVisible(false);
    } catch (e: any) {
      Alert.alert('更新失败', e.message || '请稍后重试');
    }
  }, [nicknameDraft, nickname, user, setUser]);

  // 头像上传状态
  const [avatarUploading, setAvatarUploading] = useState(false);

  // 更换头像
  const handleChangeAvatar = useCallback(async () => {
    if (!user) return;

    const perm = await ImagePicker.requestMediaLibraryPermissionsAsync();
    if (!perm.granted) {
      Alert.alert('权限不足', '请在设置中允许访问相册');
      return;
    }

    const result = await ImagePicker.launchImageLibraryAsync({
      mediaTypes: ['images'],
      allowsEditing: true,
      aspect: [1, 1],
      quality: 0.8,
    });

    if (result.canceled || !result.assets?.[0]) return;

    const asset = result.assets[0];
    const filename = asset.fileName ?? `avatar_${Date.now()}.jpg`;

    try {
      setAvatarUploading(true);
      // 1. 上传到 OSS
    const url = await uploadAvatar(asset.uri, filename);
      // 2. 更新用户信息
    await updateProfile({ avatar: url });
      // 3. 刷新本地状态
      setUser({ ...user, avatar: url });
    } catch (e: any) {
      Alert.alert('上传失败', e.message || '请稍后重试');
    } finally {
      setAvatarUploading(false);
    }
  }, [user, setUser]);

  // 修改性别
  const handleChangeGender = useCallback(() => {
    const labels = GENDER_OPTIONS.map((o) => o.label);
    labels.push('取消');

    Alert.alert('选择性别', undefined, [
      ...GENDER_OPTIONS.map((opt) => ({
        text: opt.label,
        onPress: async () => {
          if (!user) return;
          try {
      await updateProfile({ gender: opt.value });
            setUser({ ...user, gender: opt.value });
          } catch (e: any) {
            Alert.alert('更新失败', e.message || '请稍后重试');
          }
        },
      })),
      { text: '取消', style: 'cancel' as const },
    ]);
  }, [user, setUser]);

  return (
    <View style={[styles.container, { paddingTop: insets.top }]}>
      {/* 顶部导航栏 */}
      <View style={styles.navBar}>
        <TouchableOpacity
          onPress={() => navigation.goBack()}
          hitSlop={{ top: 8, bottom: 8, left: 8, right: 8 }}
        >
          <Ionicons name="chevron-back" size={24} color={colors.textPrimary} />
        </TouchableOpacity>
        <Text style={styles.navTitle}>个人信息</Text>
        <View style={{ width: 24 }} />
      </View>

      <ScrollView
        contentContainerStyle={styles.scrollContent}
        showsVerticalScrollIndicator={false}
      >
        {/* 头像 */}
        <TouchableOpacity
          style={styles.avatarSection}
          onPress={handleChangeAvatar}
          activeOpacity={0.7}
          disabled={avatarUploading}
        >
          <View style={styles.avatar}>
            {user?.avatar ? (
              <Image source={{ uri: user.avatar }} style={styles.avatarImage} />
            ) : (
              <Text style={styles.avatarText}>{avatarLetter}</Text>
            )}
            {avatarUploading && (
              <View style={styles.avatarOverlay}>
                <ActivityIndicator color="#fff" />
              </View>
            )}
          </View>
          <Text style={styles.avatarHint}>
            {avatarUploading ? '上传中…' : '点击更换头像'}
          </Text>
        </TouchableOpacity>

        {/* 信息卡片 */}
        <View style={styles.infoCard}>
          {/* 昵称（可编辑） */}
          <TouchableOpacity
            style={styles.infoRow}
            activeOpacity={0.6}
            onPress={handleOpenNickname}
          >
            <View style={styles.infoIconBox}>
              <Ionicons name="person-outline" size={20} color={colors.primary} />
            </View>
            <View style={styles.infoContent}>
              <Text style={styles.infoLabel}>用户名称</Text>
              <Text style={styles.infoValue}>{nickname}</Text>
            </View>
            <Ionicons name="chevron-forward" size={16} color={colors.textSecondary} />
          </TouchableOpacity>

          <View style={styles.divider} />

          {/* 手机号 */}
          <View style={styles.infoRow}>
            <View style={styles.infoIconBox}>
              <Ionicons name="call-outline" size={20} color={colors.primary} />
            </View>
            <View style={styles.infoContent}>
              <Text style={styles.infoLabel}>手机号</Text>
              <Text style={styles.infoValue}>{phone}</Text>
            </View>
          </View>

          <View style={styles.divider} />

          {/* 当前家庭 */}
          <View style={styles.infoRow}>
            <View style={styles.infoIconBox}>
              <Ionicons name="home-outline" size={20} color={colors.primary} />
            </View>
            <View style={styles.infoContent}>
              <Text style={styles.infoLabel}>当前家庭</Text>
              <Text style={familyName ? styles.infoValue : styles.infoValueMuted}>
                {familyName || '未加入家庭'}
              </Text>
            </View>
          </View>

          <View style={styles.divider} />

          {/* 性别（可编辑） */}
          <TouchableOpacity
            style={styles.infoRow}
            activeOpacity={0.6}
            onPress={handleChangeGender}
          >
            <View style={styles.infoIconBox}>
              <Ionicons
                name={currentGender === 1 ? 'male-outline' : currentGender === 2 ? 'female-outline' : 'help-circle-outline'}
                size={20}
                color={colors.primary}
              />
            </View>
            <View style={styles.infoContent}>
              <Text style={styles.infoLabel}>性别</Text>
              <Text style={styles.infoValue}>
                {currentGender === 1 ? '男' : currentGender === 2 ? '女' : '未设置'}
              </Text>
            </View>
            <Ionicons name="chevron-forward" size={16} color={colors.textSecondary} />
          </TouchableOpacity>
        </View>
      </ScrollView>

      {/* 修改昵称弹窗 */}
      <Modal
        visible={nicknameModalVisible}
        transparent
        animationType="fade"
        onRequestClose={() => setNicknameModalVisible(false)}
      >
        <KeyboardAvoidingView
          style={styles.modalOverlay}
          behavior={Platform.OS === 'ios' ? 'padding' : 'height'}
        >
          <View style={styles.modalContent}>
            <Text style={styles.modalTitle}>修改用户名称</Text>
            <TextInput
              style={styles.modalInput}
              value={nicknameDraft}
              onChangeText={setNicknameDraft}
              placeholder="输入新的名称"
              placeholderTextColor={colors.textSecondary}
              maxLength={20}
              autoFocus
              selectTextOnFocus
            />
            <View style={styles.modalActions}>
              <TouchableOpacity
                style={styles.modalCancelBtn}
                onPress={() => setNicknameModalVisible(false)}
              >
                <Text style={styles.modalCancelText}>取消</Text>
              </TouchableOpacity>
              <TouchableOpacity
                style={styles.modalConfirmBtn}
                onPress={handleSaveNickname}
              >
                <Text style={styles.modalConfirmText}>保存</Text>
              </TouchableOpacity>
            </View>
          </View>
        </KeyboardAvoidingView>
      </Modal>
    </View>
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
    paddingBottom: spacing.xxxl,
  },

  /* 头像区域 */
  avatarSection: {
    alignItems: 'center',
    paddingVertical: spacing.xxl,
  },
  avatar: {
    width: 88,
    height: 88,
    borderRadius: 44,
    backgroundColor: colors.primaryLight,
    alignItems: 'center',
    justifyContent: 'center',
    borderWidth: 3,
    borderColor: colors.primarySubtle,
  },
  avatarText: {
    fontSize: 32,
    fontWeight: '700',
    color: colors.primary,
  },
  avatarImage: {
    width: 88,
    height: 88,
    borderRadius: 44,
  },
  avatarOverlay: {
    position: 'absolute',
    top: 0,
    left: 0,
    right: 0,
    bottom: 0,
    borderRadius: 44,
    backgroundColor: 'rgba(0,0,0,0.3)',
    alignItems: 'center',
    justifyContent: 'center',
  },
  avatarHint: {
    ...typography.caption,
    color: colors.primary,
    marginTop: spacing.sm,
  },

  /* 信息卡片 */
  infoCard: {
    backgroundColor: colors.surface,
    borderRadius: radius.lg,
    marginHorizontal: spacing.lg,
    paddingVertical: spacing.xs,
    ...shadow.card,
  },
  infoRow: {
    flexDirection: 'row',
    alignItems: 'center',
    paddingHorizontal: spacing.lg,
    paddingVertical: spacing.lg,
  },
  infoIconBox: {
    width: 40,
    height: 40,
    borderRadius: radius.md,
    backgroundColor: colors.primarySubtle,
    alignItems: 'center',
    justifyContent: 'center',
    marginRight: spacing.md,
  },
  infoContent: {
    flex: 1,
  },
  infoLabel: {
    ...typography.caption,
    color: colors.textSecondary,
    marginBottom: 2,
  },
  infoValue: {
    fontSize: 16,
    fontWeight: '500',
    color: colors.textPrimary,
  },
  infoValueMuted: {
    fontSize: 16,
    fontWeight: '500',
    color: colors.textSecondary,
  },
  divider: {
    height: StyleSheet.hairlineWidth,
    backgroundColor: colors.border,
    marginLeft: spacing.lg + 40 + spacing.md,
  },

  /* 昵称编辑弹窗 */
  modalOverlay: {
    flex: 1,
    backgroundColor: 'rgba(0,0,0,0.4)',
    justifyContent: 'center',
    alignItems: 'center',
  },
  modalContent: {
    width: 300,
    backgroundColor: colors.surface,
    borderRadius: radius.lg,
    padding: spacing.xxl,
  },
  modalTitle: {
    ...typography.h2,
    color: colors.textPrimary,
    marginBottom: spacing.lg,
  },
  modalInput: {
    ...typography.body,
    color: colors.textPrimary,
    backgroundColor: colors.background,
    borderRadius: radius.md,
    paddingHorizontal: spacing.md,
    paddingVertical: spacing.md,
    borderWidth: 1,
    borderColor: colors.border,
  },
  modalActions: {
    flexDirection: 'row',
    justifyContent: 'flex-end',
    marginTop: spacing.xl,
    gap: spacing.md,
  },
  modalCancelBtn: {
    paddingHorizontal: spacing.lg,
    paddingVertical: spacing.sm,
  },
  modalCancelText: {
    ...typography.body,
    color: colors.textSecondary,
  },
  modalConfirmBtn: {
    paddingHorizontal: spacing.xl,
    paddingVertical: spacing.sm,
    backgroundColor: colors.primary,
    borderRadius: radius.md,
  },
  modalConfirmText: {
    ...typography.button,
    color: colors.textOnPrimary,
  },
});
