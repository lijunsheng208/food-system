import React, { useCallback, useState } from 'react';
import {
  ActivityIndicator,
  Image,
  ScrollView,
  StyleSheet,
  Text,
  TouchableOpacity,
  View,
} from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import { useFocusEffect, useNavigation } from '@react-navigation/native';
import type { NativeStackNavigationProp } from '@react-navigation/native-stack';
import { useSafeAreaInsets } from 'react-native-safe-area-context';
import { useUser } from '../contexts/UserContext';
import { getMyFamily, listMealPlans } from '../services/family';
import { resolveDishImageUrl } from '../services/dish';
import type { FamilyMealPlanInfo, MealType } from '../types/family';
import { MealTypeLabel } from '../types/family';
import type { AuthStackParamList } from '../types/auth';
import { colors, radius, spacing } from '../theme';

const MEAL_TYPES: MealType[] = [1, 2, 3];

function todayKey() {
  const date = new Date();
  return `${date.getFullYear()}-${String(date.getMonth() + 1).padStart(2, '0')}-${String(date.getDate()).padStart(2, '0')}`;
}

export default function HomeScreen() {
  const insets = useSafeAreaInsets();
  const navigation = useNavigation<NativeStackNavigationProp<AuthStackParamList>>();
  const { user, familyName } = useUser();
  const [plans, setPlans] = useState<FamilyMealPlanInfo[]>([]);
  const [hasFamily, setHasFamily] = useState(true);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');

  const load = useCallback(async () => {
    if (!user) return;
    setLoading(true);
    setError('');
    try {
    const family = await getMyFamily();
      setHasFamily(Boolean(family));
      setPlans(
        family
      ? await listMealPlans(family.id, todayKey(), todayKey())
          : [],
      );
    } catch (e: any) {
      setError(e.message || '今日菜单加载失败');
    } finally {
      setLoading(false);
    }
  }, [user]);

  useFocusEffect(useCallback(() => { load(); }, [load]));

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
          <View style={styles.sectionHeader}>
            <View>
              <Text style={styles.sectionTitle}>今日菜单</Text>
              <Text style={styles.sectionDate}>
                {date.getFullYear()}年{date.getMonth() + 1}月{date.getDate()}日
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

              <TouchableOpacity
                style={styles.weekMenuFooter}
                onPress={() => navigation.navigate('FamilyMealPlan', { initialDate: todayKey() })}
                accessibilityRole="button"
              >
                <View style={styles.weekMenuCopy}>
                  <Text style={styles.weekMenuTitle}>查看家庭周菜单</Text>
                  <Text style={styles.weekMenuHint}>安排和调整本周菜单</Text>
                </View>
                <Ionicons name="chevron-forward" size={18} color={colors.textSecondary} />
              </TouchableOpacity>
            </View>
          )}
        </View>
      </ScrollView>
    </View>
  );
}

function MealBlock({
  type,
  plans,
  showDivider,
  onDishPress,
}: {
  type: MealType;
  plans: FamilyMealPlanInfo[];
  showDivider: boolean;
  onDishPress: (plan: FamilyMealPlanInfo) => void;
}) {
  return (
    <View style={[styles.mealBlock, showDivider && styles.mealDivider]}>
      <View style={styles.mealLabelColumn}>
        <Text style={styles.mealName}>{MealTypeLabel[type]}</Text>
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
              <Ionicons name="chevron-forward" size={17} color="#B7BFCA" />
            </TouchableOpacity>
          );
        })}
      </View>
    </View>
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
    minHeight: 86,
    flexDirection: 'row',
    alignItems: 'stretch',
    paddingVertical: spacing.md,
  },
  mealDivider: {
    borderBottomWidth: StyleSheet.hairlineWidth,
    borderBottomColor: colors.border,
  },
  mealLabelColumn: {
    width: 48,
    alignItems: 'flex-start',
    justifyContent: 'flex-start',
    paddingTop: spacing.sm,
  },
  mealName: {
    color: colors.primary,
    fontSize: 11,
    lineHeight: 16,
    fontWeight: '700',
  },
  mealDishes: {
    flex: 1,
    minWidth: 0,
    justifyContent: 'center',
    paddingLeft: spacing.md,
  },
  dishRow: {
    minHeight: 56,
    flexDirection: 'row',
    alignItems: 'center',
    paddingVertical: spacing.xs,
  },
  dishRowBorder: {
    borderTopWidth: StyleSheet.hairlineWidth,
    borderTopColor: colors.border,
  },
  dishImage: {
    width: 44,
    height: 44,
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
  dishName: {
    color: colors.textPrimary,
    fontSize: 13,
    lineHeight: 19,
    fontWeight: '600',
  },
  dishMeta: {
    color: colors.textSecondary,
    fontSize: 10,
    lineHeight: 15,
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
});
