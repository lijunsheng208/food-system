import React, { useCallback, useState } from 'react';
import {
  View,
  Text,
  StyleSheet,
  ScrollView,
  TouchableOpacity,
  Alert,
  ActivityIndicator,
  RefreshControl,
  Image,
} from 'react-native';
import { useSafeAreaInsets } from 'react-native-safe-area-context';
import { Ionicons } from '@expo/vector-icons';
import { useNavigation, useFocusEffect } from '@react-navigation/native';
import type { NativeStackNavigationProp } from '@react-navigation/native-stack';
import * as Clipboard from 'expo-clipboard';
import { useUser } from '../contexts/UserContext';
import {
  getMyFamily,
  listFamilyMembers,
  leaveFamily,
  dissolveFamily,
  resetInviteCode,
  removeMember,
} from '../services/family';
import { colors, typography, spacing, radius, shadow } from '../theme';
import {
  FamilyRoleLabel,
} from '../types/family';
import type {
  FamilyInfo,
  FamilyMemberInfo,
  FamilyRole,
} from '../types/family';
import type { AuthStackParamList } from '../types/auth';

export default function FamilyManagementScreen() {
  const insets = useSafeAreaInsets();
  const navigation =
    useNavigation<NativeStackNavigationProp<AuthStackParamList>>();
  const { user, setFamilyName } = useUser();

  const [family, setFamily] = useState<FamilyInfo | null>(null);
  const [members, setMembers] = useState<FamilyMemberInfo[]>([]);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [actionLoading, setActionLoading] = useState(false);

  const fetchData = useCallback(async () => {
    if (!user) return;
    try {
      const f = await getMyFamily(user.id);
      setFamily(f);
      if (f) {
        setFamilyName(f.name);
        const m = await listFamilyMembers(f.id, user.id);
        setMembers(m);
      } else {
        setFamilyName('');
        setMembers([]);
      }
    } catch (e: any) {
      Alert.alert('加载失败', e.message || '请稍后重试');
    }
  }, [user, setFamilyName]);

  useFocusEffect(
    useCallback(() => {
      (async () => {
        setLoading(true);
        await fetchData();
        setLoading(false);
      })();
    }, [fetchData]),
  );

  const handleRefresh = useCallback(async () => {
    setRefreshing(true);
    await fetchData();
    setRefreshing(false);
  }, [fetchData]);

  // ─── 权限判断 ────────────────────────────────────────────────

  const isOwner = family?.my_role === 1;
  const isAdmin = family?.my_role === 2;
  const canManage = isOwner || isAdmin;

  // ─── 操作处理 ────────────────────────────────────────────────

  const handleResetInviteCode = () => {
    if (!family || !user) return;
    Alert.alert('重置邀请码', '确定要重置邀请码吗？旧的邀请码将立即失效。', [
      { text: '取消', style: 'cancel' },
      {
        text: '重置',
        onPress: async () => {
          try {
            setActionLoading(true);
            const res = await resetInviteCode(family.id, user.id);
            setFamily({ ...family, invite_code: res.invite_code });
            Alert.alert('已重置', `新邀请码：${res.invite_code}`);
          } catch (e: any) {
            Alert.alert('重置失败', e.message || '请稍后重试');
          } finally {
            setActionLoading(false);
          }
        },
      },
    ]);
  };

  const handleLeaveFamily = () => {
    if (!user) return;
    Alert.alert('退出家庭', '退出后你需要重新通过邀请码加入。确定要退出吗？', [
      { text: '取消', style: 'cancel' },
      {
        text: '退出',
        style: 'destructive',
        onPress: async () => {
          try {
            setActionLoading(true);
            await leaveFamily(user.id);
            setFamily(null);
            setMembers([]);
            setFamilyName('');
          } catch (e: any) {
            Alert.alert('退出失败', e.message || '请稍后重试');
          } finally {
            setActionLoading(false);
          }
        },
      },
    ]);
  };

  const handleDissolveFamily = () => {
    if (!family || !user) return;
    Alert.alert(
      '解散家庭',
      '解散后所有成员将被移除，此操作不可撤销。确定要解散吗？',
      [
        { text: '取消', style: 'cancel' },
        {
          text: '解散',
          style: 'destructive',
          onPress: async () => {
            try {
              setActionLoading(true);
              await dissolveFamily(family.id, user.id);
              setFamily(null);
              setMembers([]);
              setFamilyName('');
            } catch (e: any) {
              Alert.alert('解散失败', e.message || '请稍后重试');
            } finally {
              setActionLoading(false);
            }
          },
        },
      ],
    );
  };

  const handleRemoveMember = (member: FamilyMemberInfo) => {
    if (!family || !user) return;
    const name = member.display_name || member.nickname;
    Alert.alert('移除成员', `确定要将「${name}」移出家庭吗？`, [
      { text: '取消', style: 'cancel' },
      {
        text: '移除',
        style: 'destructive',
        onPress: async () => {
          try {
            setActionLoading(true);
            await removeMember(family.id, user.id, member.user_id);
            setMembers((prev) =>
              prev.filter((m) => m.user_id !== member.user_id),
            );
            setFamily((prev) =>
              prev ? { ...prev, member_count: prev.member_count - 1 } : null,
            );
          } catch (e: any) {
            Alert.alert('移除失败', e.message || '请稍后重试');
          } finally {
            setActionLoading(false);
          }
        },
      },
    ]);
  };

  const handleEditMember = (member: FamilyMemberInfo) => {
    if (!family) return;
    navigation.navigate('FamilyMemberEdit', {
      familyId: family.id,
      member: {
        user_id: member.user_id,
        nickname: member.nickname,
        avatar: member.avatar,
        role: member.role,
        relation: member.relation,
        display_name: member.display_name,
      },
      myRole: family.my_role,
    });
  };

  const copyInviteCode = async () => {
    if (!family) return;
    await Clipboard.setStringAsync(family.invite_code);
    Alert.alert('已复制', '邀请码已复制到剪贴板，发给家人即可加入');
  };

  // 拼接头像网格 — 按人数动态排列，末行居中
  const renderMemberGrid = (list: FamilyMemberInfo[]) => {
    const count = list.length;
    const size = 56;

    if (count === 0) {
      return (
        <View style={[styles.gridPlaceholder, { width: size, height: size, backgroundColor: colors.primaryLight }]}>
          <Text style={styles.gridEmpty}>?</Text>
        </View>
      );
    }

    // 单人时占满整格
    if (count === 1) {
      const m = list[0];
      return (
        <View style={{ width: size, height: size, overflow: 'hidden' }}>
          {m.avatar ? (
            <Image source={{ uri: m.avatar }} style={{ width: size, height: size }} />
          ) : (
            <View style={[styles.gridPlaceholder, { width: size, height: size, backgroundColor: gridColor(0) }]}>
              <Text style={[styles.gridLetter, { fontSize: 24 }]}>
                {(m.display_name || m.nickname).charAt(0).toUpperCase()}
              </Text>
            </View>
          )}
        </View>
      );
    }

    // 按人数决定行布局（每行最多 3 列）
    const layout = getGridLayout(count);

    return (
      <View style={{ width: size, height: size, overflow: 'hidden', backgroundColor: colors.surface }}>
        {layout.map((row, ri) => {
          const cols = row.length;
          const cellSize = size / layout.length;
          const gap = 1.5;
          return (
            <View key={ri} style={{ flexDirection: 'row', height: cellSize, justifyContent: 'center' }}>
              {row.map((memberIdx) => {
                const m = list[memberIdx];
                const w = size / cols;
                const innerSize = Math.min(w, cellSize) - gap * 2;
                return (
                  <View
                    key={m.user_id}
                    style={{
                      width: w,
                      height: cellSize,
                      alignItems: 'center',
                      justifyContent: 'center',
                    }}
                  >
                    {m.avatar ? (
                      <Image
                        source={{ uri: m.avatar }}
                        style={{ width: innerSize, height: innerSize }}
                      />
                    ) : (
                      <View style={[styles.gridPlaceholder, {
                        width: innerSize,
                        height: innerSize,
                        backgroundColor: gridColor(memberIdx),
                      }]}>
                        <Text style={[styles.gridLetter, { fontSize: innerSize * 0.45 }]}>
                          {(m.display_name || m.nickname).charAt(0).toUpperCase()}
                        </Text>
                      </View>
                    )}
                  </View>
                );
              })}
            </View>
          );
        })}
      </View>
    );
  };

  const gridColor = (i: number) => {
    const palette = ['#DBEAFE', '#DCFCE7', '#FEF3C7', '#FCE7F3', '#E0E7FF', '#CCFBF1', '#FEE2E2', '#E9D5FF', '#D1FAE5'];
    return palette[i % palette.length];
  };

  // 按人数返回网格行布局，不足的行在最上面，成员按加入顺序从上到下
  const getGridLayout = (count: number): number[][] => {
    switch (count) {
      case 1:  return [[0]];
      case 2:  return [[0, 1]];
      case 3:  return [[0], [1, 2]];
      case 4:  return [[0, 1], [2, 3]];
      case 5:  return [[0, 1], [2, 3, 4]];
      case 6:  return [[0, 1, 2], [3, 4, 5]];
      case 7:  return [[0], [1, 2, 3], [4, 5, 6]];
      case 8:  return [[0, 1], [2, 3, 4], [5, 6, 7]];
      case 9:  return [[0, 1, 2], [3, 4, 5], [6, 7, 8]];
      default: return [[0, 1, 2], [3, 4, 5], [6, 7, 8]];
    }
  };

  const getRoleColor = (role: FamilyRole) => {
    if (role === 1) return colors.primary;
    if (role === 2) return colors.success;
    return colors.textSecondary;
  };

  // ─── 导航栏（复用） ────────────────────────────────────────────

  const renderNavBar = () => (
    <View style={styles.navBar}>
      <TouchableOpacity
        onPress={() => navigation.goBack()}
        hitSlop={{ top: 8, bottom: 8, left: 8, right: 8 }}
      >
        <Ionicons name="chevron-back" size={24} color={colors.textPrimary} />
      </TouchableOpacity>
      <Text style={styles.navTitle}>家庭管理</Text>
      <View style={{ width: 24 }} />
    </View>
  );

  // ─── 加载态 ──────────────────────────────────────────────────

  if (loading) {
    return (
      <View style={[styles.container, { paddingTop: insets.top }]}>
        {renderNavBar()}
        <View style={styles.loadingContainer}>
          <ActivityIndicator size="large" color={colors.primary} />
        </View>
      </View>
    );
  }

  // ─── 未加入家庭 ──────────────────────────────────────────────

  if (!family) {
    return (
      <View style={[styles.container, { paddingTop: insets.top }]}>
        {renderNavBar()}

        <ScrollView
          contentContainerStyle={styles.emptyScroll}
          showsVerticalScrollIndicator={false}
        >
          <View style={styles.emptyIllustration}>
            <View style={styles.emptyIconCircle}>
              <Ionicons name="people-outline" size={48} color={colors.primary} />
            </View>
            <Text style={styles.emptyTitle}>还没有家庭</Text>
            <Text style={styles.emptyDesc}>
              创建一个家庭或通过邀请码加入家人的家庭，{'\n'}
              一起管理菜谱、购物清单和日常事务。
            </Text>
          </View>

          <View style={styles.emptyActions}>
            <TouchableOpacity
              style={styles.createBtn}
              activeOpacity={0.85}
              onPress={() => navigation.navigate('CreateFamily')}
            >
              <Ionicons name="add-circle-outline" size={22} color={colors.textOnPrimary} />
              <Text style={styles.createBtnText}>创建家庭</Text>
            </TouchableOpacity>

            <TouchableOpacity
              style={styles.joinBtn}
              activeOpacity={0.85}
              onPress={() => navigation.navigate('JoinFamily', {})}
            >
              <Ionicons name="key-outline" size={22} color={colors.primary} />
              <Text style={styles.joinBtnText}>通过邀请码加入</Text>
            </TouchableOpacity>
          </View>
        </ScrollView>
      </View>
    );
  }

  // ─── 已加入家庭 ──────────────────────────────────────────────

  return (
    <View style={[styles.container, { paddingTop: insets.top }]}>
      {renderNavBar()}

      <ScrollView
        contentContainerStyle={styles.scrollContent}
        showsVerticalScrollIndicator={false}
        refreshControl={
          <RefreshControl
            refreshing={refreshing}
            onRefresh={handleRefresh}
            colors={[colors.primary]}
            tintColor={colors.primary}
          />
        }
      >
        {/* 家庭信息卡片 */}
        <View style={styles.familyCard}>
          <View style={styles.familyCardHeader}>
            {/* 多成员拼接头像 */}
            <View style={styles.familyAvatar}>
              {renderMemberGrid(members.slice(0, 9))}
            </View>
            <View style={styles.familyInfo}>
              <Text style={styles.familyName}>{family.name}</Text>
              {family.description ? (
                <Text style={styles.familyDesc} numberOfLines={2}>
                  {family.description}
                </Text>
              ) : null}
              <Text style={styles.memberCount}>
                {family.member_count}/{family.max_member_count} 位成员
              </Text>
            </View>
            {canManage && (
              <TouchableOpacity
                style={styles.editFamilyBtn}
                onPress={() =>
                  navigation.navigate('EditFamily', {
                    familyId: family.id,
                    name: family.name,
                    description: family.description ?? '',
                    avatar: family.avatar ?? '',
                  })
                }
                hitSlop={{ top: 8, bottom: 8, left: 8, right: 8 }}
              >
                <Ionicons name="create-outline" size={18} color={colors.primary} />
              </TouchableOpacity>
            )}
          </View>

          {/* 邀请码 */}
          <View style={styles.inviteSection}>
            <View style={styles.inviteLeft}>
              <Text style={styles.inviteLabel}>邀请码</Text>
              <TouchableOpacity onPress={copyInviteCode} activeOpacity={0.6}>
                <Text style={styles.inviteCode}>{family.invite_code}</Text>
              </TouchableOpacity>
            </View>
            <View style={styles.inviteActions}>
              <TouchableOpacity
                style={styles.inviteBtn}
                onPress={copyInviteCode}
                activeOpacity={0.7}
              >
                <Ionicons name="copy-outline" size={16} color={colors.primary} />
                <Text style={styles.inviteBtnText}>复制</Text>
              </TouchableOpacity>
              {canManage && (
                <TouchableOpacity
                  style={styles.inviteBtn}
                  onPress={handleResetInviteCode}
                  activeOpacity={0.7}
                >
                  <Ionicons name="refresh-outline" size={16} color={colors.primary} />
                  <Text style={styles.inviteBtnText}>重置</Text>
                </TouchableOpacity>
              )}
            </View>
          </View>
        </View>

        {/* 成员列表 */}
        <View style={styles.sectionHeader}>
          <Text style={styles.sectionTitle}>家庭成员</Text>
        </View>

        <View style={styles.memberCard}>
          {members.length === 0 ? (
            <View style={styles.emptyMembers}>
              <Text style={styles.emptyMembersText}>暂无成员</Text>
            </View>
          ) : (
            members.map((member, index) => {
              const isSelf = member.user_id === user?.id;
              const role = member.role as FamilyRole;
              const canEditThis =
                (isOwner && role !== 1) ||
                (isAdmin && role === 3);
              const canRemoveThis =
                (isOwner && role !== 1) ||
                (isAdmin && role === 3);

              return (
                <React.Fragment key={member.user_id}>
                  {index > 0 && <View style={styles.divider} />}
                  <TouchableOpacity
                    style={styles.memberRow}
                    activeOpacity={canEditThis || canRemoveThis ? 0.6 : 1}
                    onPress={() => {
                      if (canEditThis) handleEditMember(member);
                    }}
                  >
                    {/* 头像 */}
                    <View style={styles.memberAvatar}>
                      {member.avatar ? (
                        <Image source={{ uri: member.avatar }} style={styles.memberAvatarImg} />
                      ) : (
                        <Text style={styles.memberAvatarText}>
                          {(member.display_name || member.nickname)
                            .charAt(0)
                            .toUpperCase()}
                        </Text>
                      )}
                    </View>

                    {/* 信息 */}
                    <View style={styles.memberInfo}>
                      <View style={styles.memberNameRow}>
                        <Text style={styles.memberName} numberOfLines={1}>
                          {member.display_name || member.nickname}
                        </Text>
                        {isSelf && (
                          <Text style={styles.selfTag}>我</Text>
                        )}
                        <View
                          style={[
                            styles.roleTag,
                            { backgroundColor: getRoleColor(role) + '18' },
                          ]}
                        >
                          <Text
                            style={[
                              styles.roleTagText,
                              { color: getRoleColor(role) },
                            ]}
                          >
                            {FamilyRoleLabel[role]}
                          </Text>
                        </View>
                      </View>
                      {member.relation ? (
                        <Text style={styles.memberRelation} numberOfLines={1}>
                          {member.relation}
                        </Text>
                      ) : member.phone && !member.display_name ? (
                        <Text style={styles.memberRelation} numberOfLines={1}>
                          {member.phone.replace(/(\d{3})\d{4}(\d{4})/, '$1****$2')}
                        </Text>
                      ) : null}
                    </View>

                    {/* 操作按钮 */}
                    {(canEditThis || canRemoveThis) && !isSelf && (
                      <View style={styles.memberActions}>
                        {canEditThis && (
                          <TouchableOpacity
                            style={styles.memberActionBtn}
                            onPress={() => handleEditMember(member)}
                            hitSlop={{ top: 8, bottom: 8, left: 8, right: 8 }}
                          >
                            <Ionicons name="create-outline" size={18} color={colors.textSecondary} />
                          </TouchableOpacity>
                        )}
                        {canRemoveThis && (
                          <TouchableOpacity
                            style={styles.memberActionBtn}
                            onPress={() => handleRemoveMember(member)}
                            hitSlop={{ top: 8, bottom: 8, left: 8, right: 8 }}
                          >
                            <Ionicons name="person-remove-outline" size={18} color={colors.error} />
                          </TouchableOpacity>
                        )}
                      </View>
                    )}
                  </TouchableOpacity>
                </React.Fragment>
              );
            })
          )}
        </View>

        {/* 危险操作区 */}
        <View style={styles.dangerSection}>
          {!isOwner && (
            <TouchableOpacity
              style={styles.dangerBtn}
              activeOpacity={0.7}
              onPress={handleLeaveFamily}
            >
              <Ionicons name="exit-outline" size={20} color={colors.error} />
              <Text style={styles.dangerBtnText}>退出家庭</Text>
            </TouchableOpacity>
          )}

          {isOwner && (
            <TouchableOpacity
              style={[styles.dangerBtn, styles.dissolveBtn]}
              activeOpacity={0.7}
              onPress={handleDissolveFamily}
            >
              <Ionicons name="trash-outline" size={20} color={colors.error} />
              <Text style={styles.dangerBtnText}>解散家庭</Text>
            </TouchableOpacity>
          )}
        </View>
      </ScrollView>

      {/* 全局 loading 遮罩 */}
      {actionLoading && (
        <View style={styles.loadingOverlay}>
          <ActivityIndicator size="large" color={colors.primary} />
        </View>
      )}
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

  /* 加载态 */
  loadingContainer: {
    flex: 1,
    alignItems: 'center',
    justifyContent: 'center',
  },

  /* 未加入家庭 — 空态 */
  emptyScroll: {
    flex: 1,
    justifyContent: 'center',
    paddingHorizontal: spacing.xxxl,
    paddingBottom: 100,
  },
  emptyIllustration: {
    alignItems: 'center',
    marginBottom: spacing.xxxl,
  },
  emptyIconCircle: {
    width: 100,
    height: 100,
    borderRadius: 50,
    backgroundColor: colors.primarySubtle,
    alignItems: 'center',
    justifyContent: 'center',
    marginBottom: spacing.xxl,
  },
  emptyTitle: {
    ...typography.h2,
    color: colors.textPrimary,
    marginBottom: spacing.sm,
  },
  emptyDesc: {
    ...typography.body,
    color: colors.textSecondary,
    textAlign: 'center',
    lineHeight: 22,
  },
  emptyActions: {
    gap: spacing.md,
  },
  createBtn: {
    backgroundColor: colors.primary,
    height: 52,
    borderRadius: radius.lg,
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'center',
    gap: spacing.sm,
  },
  createBtnText: {
    ...typography.button,
    color: colors.textOnPrimary,
  },
  joinBtn: {
    backgroundColor: colors.surface,
    height: 52,
    borderRadius: radius.lg,
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'center',
    gap: spacing.sm,
    borderWidth: 1.5,
    borderColor: colors.primary,
  },
  joinBtnText: {
    ...typography.button,
    color: colors.primary,
  },

  /* 已加入家庭 */
  scrollContent: {
    paddingHorizontal: spacing.lg,
    paddingBottom: spacing.xxxl,
  },

  /* 家庭卡片 */
  familyCard: {
    backgroundColor: colors.surface,
    borderRadius: radius.lg,
    padding: spacing.xl,
    ...shadow.card,
  },
  familyCardHeader: {
    flexDirection: 'row',
    alignItems: 'flex-start',
  },
  familyAvatar: {
    width: 56,
    height: 56,
    overflow: 'hidden',
  },
  gridPlaceholder: {
    flex: 1,
    alignItems: 'center',
    justifyContent: 'center',
  },
  gridLetter: {
    fontWeight: '700',
    color: colors.primary,
  },
  gridEmpty: {
    fontSize: 28,
    fontWeight: '700',
    color: colors.primary,
  },
  familyInfo: {
    flex: 1,
    marginLeft: spacing.md,
  },
  familyName: {
    ...typography.h2,
    color: colors.textPrimary,
    marginBottom: 2,
  },
  familyDesc: {
    ...typography.caption,
    color: colors.textSecondary,
    marginBottom: 4,
  },
  memberCount: {
    ...typography.caption,
    color: colors.primary,
  },
  editFamilyBtn: {
    padding: spacing.xs,
  },

  /* 邀请码区 */
  inviteSection: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    marginTop: spacing.lg,
    paddingTop: spacing.lg,
    borderTopWidth: StyleSheet.hairlineWidth,
    borderTopColor: colors.border,
  },
  inviteLeft: {
    flex: 1,
  },
  inviteLabel: {
    ...typography.caption,
    color: colors.textSecondary,
    marginBottom: 2,
  },
  inviteCode: {
    fontSize: 20,
    fontWeight: '700',
    color: colors.textPrimary,
    letterSpacing: 2,
  },
  inviteActions: {
    flexDirection: 'row',
    gap: spacing.sm,
  },
  inviteBtn: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 4,
    paddingHorizontal: spacing.md,
    paddingVertical: spacing.sm,
    backgroundColor: colors.primarySubtle,
    borderRadius: radius.sm,
  },
  inviteBtnText: {
    ...typography.caption,
    color: colors.primary,
  },

  /* 成员列表 */
  sectionHeader: {
    marginTop: spacing.xxl,
    marginBottom: spacing.md,
  },
  sectionTitle: {
    ...typography.h2,
    color: colors.textPrimary,
  },
  memberCard: {
    backgroundColor: colors.surface,
    borderRadius: radius.lg,
    paddingVertical: spacing.xs,
    ...shadow.card,
  },
  memberRow: {
    flexDirection: 'row',
    alignItems: 'center',
    paddingHorizontal: spacing.lg,
    paddingVertical: spacing.md,
  },
  memberAvatar: {
    width: 44,
    height: 44,
    borderRadius: 22,
    backgroundColor: colors.primaryLight,
    alignItems: 'center',
    justifyContent: 'center',
    overflow: 'hidden',
  },
  memberAvatarText: {
    fontSize: 17,
    fontWeight: '600',
    color: colors.primary,
  },
  memberAvatarImg: {
    width: 44,
    height: 44,
    borderRadius: 22,
  },
  memberInfo: {
    flex: 1,
    marginLeft: spacing.md,
  },
  memberNameRow: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: spacing.sm,
  },
  memberName: {
    fontSize: 16,
    fontWeight: '500',
    color: colors.textPrimary,
    maxWidth: 120,
  },
  selfTag: {
    fontSize: 11,
    fontWeight: '600',
    color: colors.primary,
    backgroundColor: colors.primarySubtle,
    paddingHorizontal: 6,
    paddingVertical: 1,
    borderRadius: radius.sm,
    overflow: 'hidden',
  },
  roleTag: {
    paddingHorizontal: 6,
    paddingVertical: 1,
    borderRadius: radius.sm,
  },
  roleTagText: {
    fontSize: 11,
    fontWeight: '600',
  },
  memberRelation: {
    ...typography.caption,
    color: colors.textSecondary,
    marginTop: 2,
  },
  memberActions: {
    flexDirection: 'row',
    gap: spacing.sm,
  },
  memberActionBtn: {
    padding: spacing.xs,
  },
  divider: {
    height: StyleSheet.hairlineWidth,
    backgroundColor: colors.border,
    marginLeft: spacing.lg + 44 + spacing.md,
  },

  /* 空成员 */
  emptyMembers: {
    alignItems: 'center',
    paddingVertical: spacing.xxl,
  },
  emptyMembersText: {
    ...typography.caption,
    color: colors.textSecondary,
  },

  /* 危险操作 */
  dangerSection: {
    marginTop: spacing.xxl,
    gap: spacing.md,
  },
  dangerBtn: {
    backgroundColor: colors.surface,
    height: 48,
    borderRadius: radius.lg,
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'center',
    gap: spacing.sm,
    ...shadow.card,
  },
  dissolveBtn: {
    borderWidth: 1,
    borderColor: colors.error + '30',
  },
  dangerBtnText: {
    ...typography.button,
    color: colors.error,
  },

  /* loading 遮罩 */
  loadingOverlay: {
    ...StyleSheet.absoluteFill,
    backgroundColor: 'rgba(255,255,255,0.6)',
    alignItems: 'center',
    justifyContent: 'center',
  },
});
