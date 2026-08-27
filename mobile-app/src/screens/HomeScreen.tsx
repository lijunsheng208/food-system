import React, { useCallback, useState } from 'react';
import {
  ActivityIndicator,
  Alert,
  Image,
  KeyboardAvoidingView,
  Modal,
  Platform,
  ScrollView,
  StyleSheet,
  Text,
  TextInput,
  TouchableOpacity,
  View,
} from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import { useFocusEffect, useNavigation } from '@react-navigation/native';
import type { NativeStackNavigationProp } from '@react-navigation/native-stack';
import { useSafeAreaInsets } from 'react-native-safe-area-context';
import { useUser } from '../contexts/UserContext';
import { getMyFamily, listMealPlanRatings, listMealPlans, updateMealPlan, upsertMealPlanRating } from '../services/family';
import { resolveDishImageUrl } from '../services/dish';
import type { FamilyMealPlanInfo, MealType } from '../types/family';
import { MealTypeLabel } from '../types/family';
import type { AuthStackParamList } from '../types/auth';
import { colors, radius, spacing } from '../theme';

const MEAL_TYPES: MealType[] = [1, 2, 3];

interface MealPlanReview {
  rating: number;
  comment: string;
}

// todayKey 返回本地时区的当天日期，避免菜单查询发生跨日偏移。
function todayKey() {
  const date = new Date();
  return `${date.getFullYear()}-${String(date.getMonth() + 1).padStart(2, '0')}-${String(date.getDate()).padStart(2, '0')}`;
}

// HomeScreen 展示家庭当天菜单，并提供负责人状态流转和成员评价入口。
export default function HomeScreen() {
  const insets = useSafeAreaInsets();
  const navigation = useNavigation<NativeStackNavigationProp<AuthStackParamList>>();
  const { user, familyName } = useUser();
  const [plans, setPlans] = useState<FamilyMealPlanInfo[]>([]);
  const [reviewByPlan, setReviewByPlan] = useState<Record<number, MealPlanReview | null>>({});
  const [hasFamily, setHasFamily] = useState(true);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [actionID, setActionID] = useState<number | null>(null);
  const [reviewingPlan, setReviewingPlan] = useState<FamilyMealPlanInfo | null>(null);
  const [draftRating, setDraftRating] = useState(0);
  const [draftComment, setDraftComment] = useState('');
  const [reviewError, setReviewError] = useState('');
  const [savingReview, setSavingReview] = useState(false);

  // load 加载当天菜单及当前用户已有评价，用于在首页回显评价状态。
  const load = useCallback(async () => {
    if (!user) return;
    setLoading(true);
    setError('');
    try {
      const family = await getMyFamily();
      setHasFamily(Boolean(family));
      if (!family) {
        setPlans([]);
        setReviewByPlan({});
        return;
      }
      const today = todayKey();
      const todayPlans = await listMealPlans(family.id, today, today);
      setPlans(todayPlans);
      const completed = todayPlans.filter((plan) => plan.status === 2);
      const reviewEntries = await Promise.all(completed.map(async (plan) => {
        const result = await listMealPlanRatings(plan.id);
        return [
          plan.id,
          result.my_rating === null
            ? null
            : { rating: result.my_rating, comment: result.my_comment || '' },
        ] as const;
      }));
      setReviewByPlan(Object.fromEntries(reviewEntries));
    } catch (e: any) {
      setError(e.message || '今日菜单加载失败');
    } finally {
      setLoading(false);
    }
  }, [user]);

  useFocusEffect(useCallback(() => { load(); }, [load]));

  // changeCookingStatus 只允许负责人通过后端状态接口推进做菜流程。
  const changeCookingStatus = useCallback(async (plan: FamilyMealPlanInfo, status: 1 | 2) => {
    setActionID(plan.id);
    try {
      await updateMealPlan(plan.id, { status });
      await load();
    } catch (e: any) {
      Alert.alert('操作失败', e.message || '暂时无法更新做菜状态');
    } finally {
      setActionID(null);
    }
  }, [load]);

  // openReview 打开评价弹窗；已有评价会回填，允许用户再次修改。
  const openReview = useCallback((plan: FamilyMealPlanInfo) => {
    const review = reviewByPlan[plan.id];
    setReviewingPlan(plan);
    setDraftRating(review?.rating ?? 0);
    setDraftComment(review?.comment ?? '');
    setReviewError('');
  }, [reviewByPlan]);

  // closeReview 在非提交状态下关闭评价弹窗，避免请求过程中误触丢失结果。
  const closeReview = useCallback(() => {
    if (savingReview) return;
    setReviewingPlan(null);
    setReviewError('');
  }, [savingReview]);

  // saveReview 将评分和文字评价一起提交到现有菜单评价接口。
  const saveReview = useCallback(async () => {
    if (!reviewingPlan || savingReview) return;
    if (draftRating < 1 || draftRating > 5) {
      setReviewError('请选择 1 到 5 星评分');
      return;
    }
    const comment = draftComment.trim();
    setSavingReview(true);
    setReviewError('');
    try {
      const saved = await upsertMealPlanRating(reviewingPlan.id, draftRating, comment);
      setReviewByPlan((current) => ({
        ...current,
        [reviewingPlan.id]: { rating: saved.rating, comment: saved.comment || '' },
      }));
      setReviewingPlan(null);
    } catch (e: any) {
      setReviewError(e.message || '暂时无法保存评价');
    } finally {
      setSavingReview(false);
    }
  }, [draftComment, draftRating, reviewingPlan, savingReview]);

  const date = new Date();
  const arrangedMealCount = MEAL_TYPES.filter((type) =>
    plans.some((plan) => plan.meal_type === type),
  ).length;
  const visibleMealTypes = MEAL_TYPES.filter((type) =>
    plans.some((plan) => plan.meal_type === type),
  );

  return (
    <View style={styles.container}>
      <ScrollView
        showsVerticalScrollIndicator={false}
        contentContainerStyle={{ paddingBottom: spacing.xxxl + insets.bottom }}
      >
        <View style={[styles.topBar, { paddingTop: insets.top + spacing.lg }]}>
          <View style={styles.topCopy}>
            <Text style={styles.familyLabel}>{familyName || 'FamilyOS'}</Text>
            <Text style={styles.greeting}>{user?.nickname || '你好'}，欢迎回来</Text>
            <Text style={styles.greetingHint}>看看家里今天吃什么</Text>
          </View>
          <View style={styles.dateTile}>
            <Text style={styles.dateMonth}>{date.getMonth() + 1}月</Text>
            <Text style={styles.dateDay}>{date.getDate()}</Text>
          </View>
        </View>

        <View style={styles.content}>
          <View style={styles.weekSectionHeader}>
            <View>
              <Text style={styles.sectionTitle}>本周菜谱</Text>
              <Text style={styles.sectionDate}>查看接下来几天的家庭安排</Text>
            </View>
            <TouchableOpacity onPress={() => navigation.navigate('FamilyMealPlan', { initialDate: todayKey() })}>
              <Text style={styles.viewWeekText}>查看全部</Text>
            </TouchableOpacity>
          </View>

          <View style={styles.sectionHeader}>
            <View>
              <Text style={styles.sectionTitle}>今日待办</Text>
              <Text style={styles.sectionDate}>
                {date.getFullYear()}年{date.getMonth() + 1}月{date.getDate()}日 · 菜单与做菜状态
              </Text>
            </View>
            {hasFamily && !loading && !error ? (
              <View style={styles.mealProgress}>
                <Text style={styles.progressStrong}>{arrangedMealCount}</Text>
                <Text style={styles.progressText}> / 3 餐已安排</Text>
              </View>
            ) : null}
          </View>

          {loading ? (
            <View style={styles.messagePanel}>
              <ActivityIndicator color={colors.primary} />
              <Text style={styles.messageText}>正在读取今天的菜单</Text>
            </View>
          ) : error ? (
            <View style={styles.messagePanel}>
              <View style={styles.messageIcon}>
                <Ionicons name="cloud-offline-outline" size={23} color={colors.primary} />
              </View>
              <View style={styles.messageCopy}>
                <Text style={styles.messageTitle}>菜单没有加载出来</Text>
                <Text style={styles.messageText}>{error}</Text>
              </View>
              <TouchableOpacity style={styles.textAction} onPress={load}>
                <Text style={styles.textActionLabel}>重试</Text>
              </TouchableOpacity>
            </View>
          ) : !hasFamily ? (
            <View style={styles.messagePanel}>
              <View style={styles.messageIcon}>
                <Ionicons name="people-outline" size={23} color={colors.primary} />
              </View>
              <View style={styles.messageCopy}>
                <Text style={styles.messageTitle}>还没有加入家庭</Text>
                <Text style={styles.messageText}>建立家庭后，就可以一起安排菜单。</Text>
              </View>
              <TouchableOpacity
                style={styles.textAction}
                onPress={() => navigation.navigate('FamilyManagement')}
              >
                <Text style={styles.textActionLabel}>去设置</Text>
              </TouchableOpacity>
            </View>
          ) : (
            <View style={styles.menuPanel}>
              {visibleMealTypes.length > 0 ? (
                visibleMealTypes.map((type, index) => (
                  <MealBlock
                    key={type}
                    type={type}
                    plans={plans.filter((plan) => plan.meal_type === type)}
                    showDivider={index < visibleMealTypes.length - 1}
                    currentUserID={user?.id ?? 0}
                    actionID={actionID}
                    reviewByPlan={reviewByPlan}
                    onStart={(plan) => changeCookingStatus(plan, 1)}
                    onComplete={(plan) => changeCookingStatus(plan, 2)}
                    onRate={openReview}
                    onDishPress={(plan) => navigation.navigate('RecipeDetail', {
                      dishId: plan.dish_id,
                      dishName: plan.dish_name,
                    })}
                  />
                ))
              ) : (
                <View style={styles.emptyToday}>
                  <View style={styles.emptyTodayCopy}>
                    <Text style={styles.emptyTodayTitle}>今天还没有安排</Text>
                    <Text style={styles.emptyTodayText}>从菜谱中选择一道想吃的菜。</Text>
                  </View>
                  <TouchableOpacity
                    style={styles.addTodayButton}
                    onPress={() => navigation.navigate('Recipes' as never)}
                  >
                    <Text style={styles.addTodayText}>添加菜谱</Text>
                  </TouchableOpacity>
                </View>
              )}

            </View>
          )}
        </View>
      </ScrollView>
      <MealPlanReviewModal
        visible={Boolean(reviewingPlan)}
        dishName={reviewingPlan?.dish_name || ''}
        rating={draftRating}
        comment={draftComment}
        error={reviewError}
        saving={savingReview}
        onRatingChange={(value) => {
          setDraftRating(value);
          setReviewError('');
        }}
        onCommentChange={setDraftComment}
        onClose={closeReview}
        onSave={saveReview}
      />
    </View>
  );
}

// MealBlock 按餐次展示当天菜品，并根据负责人和菜单状态提供对应操作。
function MealBlock({
  type,
  plans,
  showDivider,
  onDishPress,
  currentUserID,
  actionID,
  onStart,
  onComplete,
  onRate,
  reviewByPlan,
}: {
  type: MealType;
  plans: FamilyMealPlanInfo[];
  showDivider: boolean;
  onDishPress: (plan: FamilyMealPlanInfo) => void;
  currentUserID: number;
  actionID: number | null;
  onStart: (plan: FamilyMealPlanInfo) => void;
  onComplete: (plan: FamilyMealPlanInfo) => void;
  onRate: (plan: FamilyMealPlanInfo) => void;
  reviewByPlan: Record<number, MealPlanReview | null>;
}) {
  return (
    <View style={[styles.mealBlock, showDivider && styles.mealDivider]}>
      <View style={styles.mealHeader}>
        <Text style={styles.mealName}>{MealTypeLabel[type]}</Text>
        <Text style={styles.mealCount}>{plans.length}道菜</Text>
      </View>

      <View style={styles.mealDishes}>
        {plans.map((plan, index) => {
          const imageUrl = resolveDishImageUrl(plan.dish_image_key);
          return (
            <TouchableOpacity
              key={plan.id}
              style={[styles.dishRow, index > 0 && styles.dishRowBorder]}
              onPress={() => onDishPress(plan)}
              activeOpacity={0.72}
            >
              <Text style={styles.dishIndex}>{index + 1}</Text>
              {imageUrl ? (
                <Image source={{ uri: imageUrl }} style={styles.dishImage} />
              ) : (
                <View style={[styles.dishImage, styles.dishImageEmpty]}>
                  <Ionicons name="restaurant-outline" size={18} color={colors.primary} />
                </View>
              )}
              <View style={styles.dishCopy}>
                <Text style={styles.dishName} numberOfLines={1}>{plan.dish_name}</Text>
                <Text style={styles.dishMeta} numberOfLines={1}>
                  {plan.servings}人份 · {plan.cook_user_name || '负责人待定'}
                </Text>
              </View>
              <View style={styles.dishActionColumn}>
                <Text style={[styles.statusLabel, plan.status === 2 && styles.statusDone, plan.status === 1 && styles.statusCooking]}>
                  {plan.status === 0 ? '待开始' : plan.status === 1 ? '烹饪中' : plan.status === 2 ? '已完成' : '已取消'}
                </Text>
                {plan.cook_user_id === currentUserID && plan.status === 0 ? (
                  <TouchableOpacity
                    disabled={actionID === plan.id}
                    onPress={(event) => {
                      event.stopPropagation();
                      onStart(plan);
                    }}
                    style={styles.actionButton}
                  >
                    <Text style={styles.actionButtonText}>{actionID === plan.id ? '处理中' : '开始做菜'}</Text>
                  </TouchableOpacity>
                ) : plan.cook_user_id === currentUserID && plan.status === 1 ? (
                  <TouchableOpacity
                    disabled={actionID === plan.id}
                    onPress={(event) => {
                      event.stopPropagation();
                      onComplete(plan);
                    }}
                    style={styles.actionButton}
                  >
                    <Text style={styles.actionButtonText}>{actionID === plan.id ? '处理中' : '结束做菜'}</Text>
                  </TouchableOpacity>
                ) : plan.status === 2 && plan.cook_user_id !== currentUserID ? (
                  reviewByPlan[plan.id] ? (
                    <TouchableOpacity
                      disabled={actionID === plan.id}
                      onPress={(event) => {
                        event.stopPropagation();
                        onRate(plan);
                      }}
                      style={styles.ratedButton}
                      accessibilityRole="button"
                      accessibilityLabel={`修改对${plan.dish_name}的评价`}
                    >
                      <Text style={styles.ratedText}>已评价 · {reviewByPlan[plan.id]?.rating}分</Text>
                    </TouchableOpacity>
                  ) : (
                    <TouchableOpacity
                      disabled={actionID === plan.id}
                      onPress={(event) => {
                        event.stopPropagation();
                        onRate(plan);
                      }}
                      style={styles.rateButton}
                    >
                      <Text style={styles.rateButtonText}>评价</Text>
                    </TouchableOpacity>
                  )
                ) : null}
              </View>
            </TouchableOpacity>
          );
        })}
      </View>
    </View>
  );
}

// MealPlanReviewModal 收集家庭成员对一次已完成菜单的评分和文字评价。
function MealPlanReviewModal({
  visible,
  dishName,
  rating,
  comment,
  error,
  saving,
  onRatingChange,
  onCommentChange,
  onClose,
  onSave,
}: {
  visible: boolean;
  dishName: string;
  rating: number;
  comment: string;
  error: string;
  saving: boolean;
  onRatingChange: (value: number) => void;
  onCommentChange: (value: string) => void;
  onClose: () => void;
  onSave: () => void;
}) {
  return (
    <Modal transparent visible={visible} animationType="fade" onRequestClose={onClose}>
      <KeyboardAvoidingView
        style={styles.reviewBackdrop}
        behavior={Platform.OS === 'ios' ? 'padding' : undefined}
      >
        <TouchableOpacity
          style={StyleSheet.absoluteFill}
          activeOpacity={1}
          onPress={onClose}
          accessibilityRole="button"
          accessibilityLabel="关闭评价弹窗"
        />
        <View style={styles.reviewPanel}>
          <View style={styles.reviewHeader}>
            <View style={styles.reviewHeaderCopy}>
              <Text style={styles.reviewTitle}>评价这道菜</Text>
              <Text style={styles.reviewDishName} numberOfLines={1}>{dishName}</Text>
            </View>
            <TouchableOpacity
              style={styles.reviewCloseButton}
              onPress={onClose}
              disabled={saving}
              accessibilityRole="button"
              accessibilityLabel="关闭"
            >
              <Ionicons name="close" size={20} color={colors.textSecondary} />
            </TouchableOpacity>
          </View>

          <Text style={styles.reviewFieldLabel}>总体评分</Text>
          <View style={styles.starRow}>
            {[1, 2, 3, 4, 5].map((value) => (
              <TouchableOpacity
                key={value}
                style={styles.starButton}
                onPress={() => onRatingChange(value)}
                disabled={saving}
                accessibilityRole="button"
                accessibilityLabel={`${value}星`}
                accessibilityState={{ selected: rating === value }}
              >
                <Ionicons
                  name={value <= rating ? 'star' : 'star-outline'}
                  size={28}
                  color={value <= rating ? '#D97706' : '#9CA3AF'}
                />
              </TouchableOpacity>
            ))}
            <Text style={styles.ratingValue}>{rating > 0 ? `${rating} 分` : '请选择'}</Text>
          </View>

          <View style={styles.commentLabelRow}>
            <Text style={styles.reviewFieldLabel}>用餐感受</Text>
            <Text style={styles.optionalLabel}>选填</Text>
          </View>
          <TextInput
            style={styles.reviewInput}
            value={comment}
            onChangeText={onCommentChange}
            placeholder="例如：味道不错，下次可以少放一点盐"
            placeholderTextColor="#9CA3AF"
            multiline
            maxLength={500}
            textAlignVertical="top"
            editable={!saving}
            accessibilityLabel="用餐感受"
          />
          <Text style={styles.commentCount}>{comment.length}/500</Text>

          {error ? <Text style={styles.reviewError}>{error}</Text> : null}

          <View style={styles.reviewActions}>
            <TouchableOpacity
              style={styles.reviewCancelButton}
              onPress={onClose}
              disabled={saving}
              accessibilityRole="button"
            >
              <Text style={styles.reviewCancelText}>取消</Text>
            </TouchableOpacity>
            <TouchableOpacity
              style={[styles.reviewSaveButton, (rating === 0 || saving) && styles.reviewSaveButtonDisabled]}
              onPress={onSave}
              disabled={rating === 0 || saving}
              accessibilityRole="button"
            >
              {saving ? <ActivityIndicator size="small" color={colors.textOnPrimary} /> : null}
              <Text style={styles.reviewSaveText}>{saving ? '保存中' : '保存评价'}</Text>
            </TouchableOpacity>
          </View>
        </View>
      </KeyboardAvoidingView>
    </Modal>
  );
}

const styles = StyleSheet.create({
  container: {
    flex: 1,
    backgroundColor: '#F5F7FA',
  },
  topBar: {
    minHeight: 132,
    paddingHorizontal: spacing.lg,
    paddingBottom: spacing.xl,
    flexDirection: 'row',
    alignItems: 'center',
    backgroundColor: colors.surface,
    borderBottomWidth: StyleSheet.hairlineWidth,
    borderBottomColor: colors.border,
  },
  topCopy: {
    flex: 1,
    minWidth: 0,
  },
  familyLabel: {
    color: colors.primary,
    fontSize: 11,
    lineHeight: 16,
    fontWeight: '700',
  },
  greeting: {
    color: colors.textPrimary,
    fontSize: 20,
    lineHeight: 28,
    fontWeight: '700',
    marginTop: spacing.xs,
  },
  greetingHint: {
    color: colors.textSecondary,
    fontSize: 12,
    lineHeight: 18,
    marginTop: 2,
  },
  dateTile: {
    width: 58,
    height: 66,
    marginLeft: spacing.lg,
    borderRadius: radius.md,
    alignItems: 'center',
    justifyContent: 'center',
    backgroundColor: colors.primary,
  },
  dateMonth: {
    color: '#DCE8FF',
    fontSize: 10,
    lineHeight: 14,
  },
  dateDay: {
    color: colors.textOnPrimary,
    fontSize: 25,
    lineHeight: 29,
    fontWeight: '700',
  },
  content: {
    paddingHorizontal: spacing.lg,
  },
  sectionHeader: {
    minHeight: 80,
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
  },
  sectionTitle: {
    color: colors.textPrimary,
    fontSize: 18,
    lineHeight: 25,
    fontWeight: '700',
  },
  sectionDate: {
    color: colors.textSecondary,
    fontSize: 11,
    lineHeight: 16,
    marginTop: 1,
  },
  mealProgress: {
    flexDirection: 'row',
    alignItems: 'baseline',
  },
  progressStrong: {
    color: '#167052',
    fontSize: 18,
    lineHeight: 23,
    fontWeight: '700',
  },
  progressText: {
    color: colors.textSecondary,
    fontSize: 10,
  },
  menuPanel: {
    backgroundColor: colors.surface,
    borderWidth: StyleSheet.hairlineWidth,
    borderColor: colors.border,
    borderRadius: radius.md,
    paddingHorizontal: spacing.md,
    overflow: 'hidden',
  },
  mealBlock: {
    paddingVertical: spacing.md,
  },
  mealDivider: {
    borderBottomWidth: StyleSheet.hairlineWidth,
    borderBottomColor: colors.border,
  },
  mealHeader: {
    minHeight: 28,
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
  },
  mealName: {
    color: colors.primary,
    fontSize: 16,
    lineHeight: 22,
    fontWeight: '700',
  },
  mealCount: {
    color: colors.textSecondary,
    fontSize: 12,
    lineHeight: 18,
  },
  mealDishes: {
    flexDirection: 'column',
    paddingTop: spacing.sm,
  },
  dishRow: {
    width: '100%',
    minHeight: 76,
    flexDirection: 'row',
    alignItems: 'center',
    paddingVertical: spacing.sm,
  },
  dishRowBorder: {
    borderTopWidth: StyleSheet.hairlineWidth,
    borderTopColor: colors.border,
  },
  dishImage: {
    width: 56,
    height: 56,
    borderRadius: radius.sm,
    backgroundColor: colors.primarySubtle,
  },
  dishImageEmpty: {
    alignItems: 'center',
    justifyContent: 'center',
  },
  dishCopy: {
    flex: 1,
    minWidth: 0,
    marginHorizontal: spacing.md,
  },
  dishActionColumn: {
    alignItems: 'flex-end',
    minWidth: 92,
  },
  dishIndex: {
    width: 20,
    color: colors.textSecondary,
    fontSize: 15,
    lineHeight: 20,
    fontWeight: '700',
  },
  statusLabel: {
    color: colors.textSecondary,
    fontSize: 11,
    lineHeight: 16,
  },
  statusCooking: {
    color: colors.primary,
  },
  statusDone: {
    color: '#167052',
  },
  actionButton: {
    minHeight: 34,
    minWidth: 82,
    marginTop: 5,
    paddingHorizontal: 10,
    paddingVertical: 7,
    borderRadius: radius.sm,
    backgroundColor: colors.primary,
  },
  actionButtonText: {
    color: colors.textOnPrimary,
    fontSize: 12,
    lineHeight: 16,
    fontWeight: '700',
  },
  rateButton: {
    minHeight: 34,
    minWidth: 58,
    marginTop: 5,
    paddingHorizontal: 12,
    paddingVertical: 7,
    borderRadius: radius.sm,
    borderWidth: 1,
    borderColor: colors.primary,
  },
  rateButtonText: {
    color: colors.primary,
    fontSize: 12,
    lineHeight: 16,
    fontWeight: '700',
  },
  ratedText: {
    color: '#167052',
    fontSize: 11,
    lineHeight: 16,
    fontWeight: '600',
  },
  ratedButton: {
    minHeight: 34,
    marginTop: 5,
    justifyContent: 'center',
  },
  dishName: {
    color: colors.textPrimary,
    fontSize: 14,
    lineHeight: 20,
    fontWeight: '600',
  },
  dishMeta: {
    color: colors.textSecondary,
    fontSize: 11,
    lineHeight: 16,
    marginTop: 2,
  },
  emptyToday: {
    minHeight: 92,
    flexDirection: 'row',
    alignItems: 'center',
    paddingVertical: spacing.lg,
  },
  emptyTodayCopy: {
    flex: 1,
    minWidth: 0,
  },
  emptyTodayTitle: {
    color: colors.textPrimary,
    fontSize: 13,
    lineHeight: 19,
    fontWeight: '700',
  },
  emptyTodayText: {
    color: colors.textSecondary,
    fontSize: 10,
    lineHeight: 15,
    marginTop: 2,
  },
  addTodayButton: {
    minHeight: 34,
    justifyContent: 'center',
    paddingLeft: spacing.lg,
  },
  addTodayText: {
    color: colors.primary,
    fontSize: 11,
    lineHeight: 16,
    fontWeight: '700',
  },
  weekSectionHeader: {
    minHeight: 76,
    marginTop: spacing.lg,
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
  },
  viewWeekText: {
    color: colors.primary,
    fontSize: 13,
    lineHeight: 18,
    fontWeight: '600',
  },
  weekMenuFooter: {
    minHeight: 58,
    flexDirection: 'row',
    alignItems: 'center',
    borderTopWidth: StyleSheet.hairlineWidth,
    borderTopColor: colors.border,
  },
  weekMenuCopy: {
    flex: 1,
    minWidth: 0,
  },
  weekMenuTitle: {
    color: colors.textPrimary,
    fontSize: 13,
    lineHeight: 19,
    fontWeight: '700',
  },
  weekMenuHint: {
    color: colors.textSecondary,
    fontSize: 10,
    lineHeight: 15,
    marginTop: 1,
  },
  shoppingFooter: {
    minHeight: 64,
    marginTop: spacing.sm,
    paddingHorizontal: spacing.md,
    flexDirection: 'row',
    alignItems: 'center',
    backgroundColor: colors.surface,
    borderRadius: radius.md,
  },
  shoppingFooterIcon: {
    width: 34,
    height: 34,
    marginRight: spacing.sm,
    borderRadius: radius.sm,
    alignItems: 'center',
    justifyContent: 'center',
    backgroundColor: colors.primarySubtle,
  },
  messagePanel: {
    minHeight: 112,
    paddingHorizontal: spacing.md,
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'center',
    backgroundColor: colors.surface,
    borderWidth: StyleSheet.hairlineWidth,
    borderColor: colors.border,
    borderRadius: radius.md,
    gap: spacing.md,
  },
  messageIcon: {
    width: 40,
    height: 40,
    borderRadius: radius.md,
    alignItems: 'center',
    justifyContent: 'center',
    backgroundColor: colors.primarySubtle,
  },
  messageCopy: {
    flex: 1,
    minWidth: 0,
  },
  messageTitle: {
    color: colors.textPrimary,
    fontSize: 13,
    lineHeight: 19,
    fontWeight: '700',
  },
  messageText: {
    color: colors.textSecondary,
    fontSize: 11,
    lineHeight: 17,
    textAlign: 'left',
  },
  textAction: {
    minHeight: 36,
    justifyContent: 'center',
    paddingLeft: spacing.sm,
  },
  textActionLabel: {
    color: colors.primary,
    fontSize: 11,
    lineHeight: 16,
    fontWeight: '700',
  },
  reviewBackdrop: {
    flex: 1,
    justifyContent: 'center',
    padding: spacing.xl,
    backgroundColor: 'rgba(17, 24, 39, 0.48)',
  },
  reviewPanel: {
    width: '100%',
    maxWidth: 420,
    alignSelf: 'center',
    padding: spacing.xl,
    borderRadius: radius.md,
    backgroundColor: colors.surface,
  },
  reviewHeader: {
    flexDirection: 'row',
    alignItems: 'flex-start',
    marginBottom: spacing.xl,
  },
  reviewHeaderCopy: {
    flex: 1,
    minWidth: 0,
  },
  reviewTitle: {
    color: colors.textPrimary,
    fontSize: 18,
    lineHeight: 24,
    fontWeight: '700',
  },
  reviewDishName: {
    marginTop: 2,
    color: colors.textSecondary,
    fontSize: 13,
    lineHeight: 18,
  },
  reviewCloseButton: {
    width: 40,
    height: 40,
    marginTop: -8,
    marginRight: -8,
    alignItems: 'center',
    justifyContent: 'center',
  },
  reviewFieldLabel: {
    color: colors.textPrimary,
    fontSize: 13,
    lineHeight: 18,
    fontWeight: '600',
  },
  starRow: {
    minHeight: 52,
    flexDirection: 'row',
    alignItems: 'center',
    marginTop: spacing.xs,
    marginBottom: spacing.lg,
  },
  starButton: {
    width: 42,
    height: 44,
    alignItems: 'center',
    justifyContent: 'center',
  },
  ratingValue: {
    marginLeft: spacing.sm,
    color: colors.textSecondary,
    fontSize: 12,
    lineHeight: 18,
  },
  commentLabelRow: {
    flexDirection: 'row',
    alignItems: 'baseline',
    gap: spacing.xs,
  },
  optionalLabel: {
    color: colors.textSecondary,
    fontSize: 11,
    lineHeight: 16,
  },
  reviewInput: {
    minHeight: 104,
    maxHeight: 160,
    marginTop: spacing.sm,
    paddingHorizontal: spacing.md,
    paddingVertical: spacing.md,
    borderWidth: 1,
    borderColor: colors.border,
    borderRadius: radius.sm,
    color: colors.textPrimary,
    backgroundColor: '#F9FAFB',
    fontSize: 14,
    lineHeight: 20,
  },
  commentCount: {
    marginTop: spacing.xs,
    color: colors.textSecondary,
    fontSize: 11,
    lineHeight: 16,
    textAlign: 'right',
  },
  reviewError: {
    marginTop: spacing.sm,
    color: colors.error,
    fontSize: 12,
    lineHeight: 18,
  },
  reviewActions: {
    flexDirection: 'row',
    justifyContent: 'flex-end',
    gap: spacing.sm,
    marginTop: spacing.lg,
  },
  reviewCancelButton: {
    minWidth: 72,
    minHeight: 42,
    alignItems: 'center',
    justifyContent: 'center',
    paddingHorizontal: spacing.lg,
    borderWidth: 1,
    borderColor: colors.border,
    borderRadius: radius.sm,
    backgroundColor: colors.surface,
  },
  reviewCancelText: {
    color: colors.textPrimary,
    fontSize: 14,
    lineHeight: 20,
    fontWeight: '600',
  },
  reviewSaveButton: {
    minWidth: 104,
    minHeight: 42,
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'center',
    gap: spacing.sm,
    paddingHorizontal: spacing.lg,
    borderRadius: radius.sm,
    backgroundColor: colors.primary,
  },
  reviewSaveButtonDisabled: {
    opacity: 0.48,
  },
  reviewSaveText: {
    color: colors.textOnPrimary,
    fontSize: 14,
    lineHeight: 20,
    fontWeight: '700',
  },
});
