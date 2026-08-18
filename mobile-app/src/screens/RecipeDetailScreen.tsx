import React, { useCallback, useEffect, useMemo, useState } from 'react';
import {
  ActivityIndicator,
  Alert,
  Image,
  Modal,
  ScrollView,
  StyleSheet,
  Text,
  TouchableOpacity,
  View,
} from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import { useNavigation, useRoute } from '@react-navigation/native';
import type { RouteProp } from '@react-navigation/native';
import type { NativeStackNavigationProp } from '@react-navigation/native-stack';
import { useSafeAreaInsets } from 'react-native-safe-area-context';
import {
  fetchDishDetail,
  resolveDishImageUrl,
} from '../services/dish';
import type {
  DishDetailInfo,
  DishStepInfo,
  IngredientInfo,
} from '../services/dish';
import { colors, spacing, radius } from '../theme';
import type { AuthStackParamList } from '../types/auth';
import { useUser } from '../contexts/UserContext';
import { createMealPlan, getMyFamily, listFamilyMembers } from '../services/family';
import type { FamilyMemberInfo, MealType } from '../types/family';
import { MealTypeLabel } from '../types/family';

const herbGreen = '#287A4D';
const stoveOrange = '#B45309';
const stoveOrangeSoft = '#FFF7E8';
const pageBackground = '#F5F7FB';

const DIFFICULTY_LABELS: Record<number, string> = {
  1: '简单',
  2: '中等',
  3: '较难',
};

function formatAmount(
  ingredient: IngredientInfo,
  scale: number,
): string {
  if (ingredient.amount === null) {
    return ingredient.amount_text || '适量';
  }

  const scaled = ingredient.amount * scale;
  const rounded = Math.round(scaled * 100) / 100;
  return `${Number.isInteger(rounded) ? rounded : rounded.toFixed(2).replace(/0+$/, '').replace(/\.$/, '')}${ingredient.unit}`;
}

export default function RecipeDetailScreen() {
  const insets = useSafeAreaInsets();
  const navigation =
    useNavigation<NativeStackNavigationProp<AuthStackParamList>>();
  const route = useRoute<RouteProp<AuthStackParamList, 'RecipeDetail'>>();
  const { user } = useUser();

  const [dish, setDish] = useState<DishDetailInfo | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [servings, setServings] = useState(1);
  const [failedImages, setFailedImages] = useState<Set<string>>(
    () => new Set(),
  );
  const [menuOpen, setMenuOpen] = useState(false);
  const [familyId, setFamilyId] = useState<number | null>(null);
  const [members, setMembers] = useState<FamilyMemberInfo[]>([]);
  const [mealDate, setMealDate] = useState(() => localDateKey(new Date()));
  const [mealType, setMealType] = useState<MealType>(3);
  const [cookUserId, setCookUserId] = useState<number | undefined>();
  const [menuLoading, setMenuLoading] = useState(false);

  const loadDetail = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const detail = await fetchDishDetail(route.params.dishId);
      setDish(detail);
      setServings(Math.max(1, detail.servings || 1));
    } catch (e: any) {
      setError(e.message || '菜谱加载失败');
    } finally {
      setLoading(false);
    }
  }, [route.params.dishId]);

  useEffect(() => {
    loadDetail();
  }, [loadDetail]);

  const baseServings = Math.max(1, dish?.servings || 1);
  const amountScale = servings / baseServings;
  const heroImageUrl = useMemo(
    () => resolveDishImageUrl(dish?.image_key ?? ''),
    [dish?.image_key],
  );

  const markImageFailed = useCallback((url: string) => {
    setFailedImages((current) => {
      const next = new Set(current);
      next.add(url);
      return next;
    });
  }, []);

  const openMealPlan = useCallback(async () => {
    if (!user) return;
    setMenuOpen(true);
    setMenuLoading(true);
    try {
    const family = await getMyFamily();
      if (!family) {
        setMenuOpen(false);
        Alert.alert('还没有家庭', '请先在“我的”中创建或加入家庭。');
        return;
      }
      setFamilyId(family.id);
    setMembers(await listFamilyMembers(family.id));
    } catch (e: any) {
      setMenuOpen(false);
      Alert.alert('加载失败', e.message || '暂时无法读取家庭信息');
    } finally {
      setMenuLoading(false);
    }
  }, [user]);

  const addToMealPlan = useCallback(async () => {
    if (!user || !familyId || !dish) return;
    setMenuLoading(true);
    try {
      await createMealPlan({
        family_id: familyId, dish_id: dish.id, meal_date: mealDate,
    meal_type: mealType, servings, cook_user_id: cookUserId,
      });
      setMenuOpen(false);
      Alert.alert('已加入家庭菜单', `${formatMenuDate(mealDate)} · ${MealTypeLabel[mealType]}`, [
        { text: '继续看菜谱' },
        { text: '查看菜单', onPress: () => navigation.navigate('FamilyMealPlan', { initialDate: mealDate }) },
      ]);
    } catch (e: any) {
      Alert.alert('加入失败', e.message || '请稍后重试');
    } finally {
      setMenuLoading(false);
    }
  }, [cookUserId, dish, familyId, mealDate, mealType, navigation, servings, user]);

  if (loading) {
    return (
      <View style={[styles.centerState, { paddingTop: insets.top }]}> 
        <ActivityIndicator color={colors.primary} size="large" />
        <Text style={styles.stateTitle}>正在准备菜谱</Text>
        <Text style={styles.stateMessage}>
          {route.params.dishName || '请稍候'}
        </Text>
      </View>
    );
  }

  if (error || !dish) {
    return (
      <View style={[styles.centerState, { paddingTop: insets.top }]}> 
        <TouchableOpacity
          style={[styles.backButton, styles.stateBackButton]}
          onPress={() => navigation.goBack()}
          accessibilityRole="button"
          accessibilityLabel="返回菜谱列表"
        >
          <Ionicons name="chevron-back" size={24} color={colors.textPrimary} />
        </TouchableOpacity>
        <View style={styles.errorIcon}>
          <Ionicons name="cloud-offline-outline" size={34} color={colors.primary} />
        </View>
        <Text style={styles.stateTitle}>没有加载到菜谱</Text>
        <Text style={styles.stateMessage}>{error || '菜谱不存在'}</Text>
        <TouchableOpacity
          style={styles.retryButton}
          onPress={loadDetail}
          activeOpacity={0.75}
        >
          <Ionicons name="refresh" size={18} color={colors.textOnPrimary} />
          <Text style={styles.retryButtonText}>重新加载</Text>
        </TouchableOpacity>
      </View>
    );
  }

  return (
    <View style={styles.container}>
      <ScrollView
        showsVerticalScrollIndicator={false}
        contentContainerStyle={{
          paddingBottom: dish.steps.length > 0
            ? spacing.lg
            : Math.max(insets.bottom, spacing.xxl),
        }}
      >
        <View style={styles.hero}>
          {heroImageUrl && !failedImages.has(heroImageUrl) ? (
            <Image
              source={{ uri: heroImageUrl }}
              style={styles.heroImage}
              resizeMode="cover"
              onError={() => markImageFailed(heroImageUrl)}
            />
          ) : (
            <View style={styles.heroPlaceholder}>
              <View style={styles.heroPlate}>
                <Ionicons name="restaurant" size={44} color={colors.primary} />
              </View>
            </View>
          )}

          <TouchableOpacity
            style={[styles.backButton, { top: insets.top + spacing.sm }]}
            onPress={() => navigation.goBack()}
            activeOpacity={0.72}
            accessibilityRole="button"
            accessibilityLabel="返回菜谱列表"
          >
            <Ionicons name="chevron-back" size={24} color={colors.textPrimary} />
          </TouchableOpacity>
        </View>

        <View style={styles.introSection}>
          <Text style={styles.dishName}>{dish.name}</Text>
          {dish.description ? (
            <Text style={styles.description}>{dish.description}</Text>
          ) : null}

          <View style={styles.metaRow}>
            <View style={styles.metaItem}>
              <Ionicons name="time-outline" size={18} color={colors.primary} />
              <Text style={styles.metaValue}>
                {dish.cook_minutes > 0 ? `${dish.cook_minutes}分钟` : '未设置'}
              </Text>
              <Text style={styles.metaLabel}>烹饪时间</Text>
            </View>
            <View style={styles.metaDivider} />
            <View style={styles.metaItem}>
              <Ionicons name="speedometer-outline" size={18} color={stoveOrange} />
              <Text style={styles.metaValue}>
                {DIFFICULTY_LABELS[dish.difficulty] || '简单'}
              </Text>
              <Text style={styles.metaLabel}>难度</Text>
            </View>
            <View style={styles.metaDivider} />
            <View style={styles.metaItem}>
              <Ionicons name="people-outline" size={18} color={herbGreen} />
              <Text style={styles.metaValue}>{servings}人份</Text>
              <Text style={styles.metaLabel}>份量</Text>
            </View>
          </View>
        </View>

        <View style={styles.section}>
          <View style={styles.sectionHeader}>
            <View>
              <Text style={styles.sectionEyebrow}>准备食材</Text>
              <Text style={styles.sectionTitle}>用料</Text>
            </View>
            <View style={styles.servingsControl}>
              <TouchableOpacity
                style={styles.servingsButton}
                onPress={() => setServings((value) => Math.max(1, value - 1))}
                disabled={servings <= 1}
                hitSlop={6}
                accessibilityRole="button"
                accessibilityLabel="减少一人份"
              >
                <Ionicons
                  name="remove"
                  size={18}
                  color={servings <= 1 ? colors.border : colors.primary}
                />
              </TouchableOpacity>
              <Text style={styles.servingsValue}>{servings}</Text>
              <TouchableOpacity
                style={styles.servingsButton}
                onPress={() => setServings((value) => Math.min(20, value + 1))}
                disabled={servings >= 20}
                hitSlop={6}
                accessibilityRole="button"
                accessibilityLabel="增加一人份"
              >
                <Ionicons
                  name="add"
                  size={18}
                  color={servings >= 20 ? colors.border : colors.primary}
                />
              </TouchableOpacity>
            </View>
          </View>

          {dish.ingredient_groups.length === 0 ? (
            <View style={styles.inlineEmpty}>
              <Ionicons name="basket-outline" size={24} color={colors.textSecondary} />
              <Text style={styles.inlineEmptyText}>这道菜还没有添加用料</Text>
            </View>
          ) : (
            dish.ingredient_groups.map((group) => (
              <View key={group.name || '未分组'} style={styles.ingredientGroup}>
                {group.name ? (
                  <Text style={styles.groupName}>{group.name}</Text>
                ) : null}
                {group.ingredients.map((ingredient) => (
                  <View key={ingredient.id} style={styles.ingredientRow}>
                    <Text style={styles.ingredientName}>{ingredient.name}</Text>
                    <Text style={styles.ingredientAmount}>
                      {formatAmount(ingredient, amountScale)}
                    </Text>
                  </View>
                ))}
              </View>
            ))
          )}
        </View>

        <View style={styles.sectionGap} />

        <View style={styles.section}>
          <Text style={styles.sectionEyebrow}>开始烹饪</Text>
          <Text style={styles.sectionTitle}>做法</Text>

          {dish.steps.length === 0 ? (
            <View style={styles.inlineEmpty}>
              <Ionicons name="list-outline" size={24} color={colors.textSecondary} />
              <Text style={styles.inlineEmptyText}>这道菜还没有添加步骤</Text>
            </View>
          ) : (
            <View style={styles.stepsList}>
              {dish.steps.map((step, index) => (
                <StepItem
                  key={step.id}
                  step={step}
                  isLast={index === dish.steps.length - 1}
                  failedImages={failedImages}
                  onImageError={markImageFailed}
                />
              ))}
            </View>
          )}
        </View>

        {dish.tips ? (
          <View style={styles.tipsSection}>
            <View style={styles.tipsIcon}>
              <Ionicons name="bulb-outline" size={20} color={stoveOrange} />
            </View>
            <View style={styles.tipsContent}>
              <Text style={styles.tipsTitle}>烹饪提示</Text>
              <Text style={styles.tipsText}>{dish.tips}</Text>
            </View>
          </View>
        ) : null}
      </ScrollView>

      {dish.steps.length > 0 ? (
        <View
          style={[
            styles.startBar,
            { paddingBottom: Math.max(insets.bottom, spacing.sm) },
          ]}
        >
          <TouchableOpacity
            style={styles.menuButton}
            onPress={openMealPlan}
            activeOpacity={0.75}
            accessibilityRole="button"
            accessibilityLabel="加入家庭菜单"
          >
            <Ionicons name="calendar-outline" size={18} color={colors.primary} />
            <Text style={styles.menuButtonText}>加入菜单</Text>
          </TouchableOpacity>
          <TouchableOpacity
            style={styles.startButton}
            onPress={() =>
              navigation.navigate('CookingMode', {
                dishId: dish.id,
                dishName: dish.name,
                servings,
              })
            }
            activeOpacity={0.78}
            accessibilityRole="button"
            accessibilityLabel="开始做菜"
          >
            <Ionicons name="play" size={18} color={colors.textOnPrimary} />
            <Text style={styles.startButtonText}>开始做菜</Text>
          </TouchableOpacity>
        </View>
      ) : null}

      <Modal transparent visible={menuOpen} animationType="slide" onRequestClose={() => setMenuOpen(false)}>
        <View style={styles.modalShade}>
          <TouchableOpacity style={StyleSheet.absoluteFill} activeOpacity={1} onPress={() => setMenuOpen(false)} />
          <View style={[styles.menuSheet, { paddingBottom: Math.max(insets.bottom, spacing.lg) }]}>
            <View style={styles.sheetHandle} />
            <View style={styles.sheetHeader}>
              <View><Text style={styles.sheetTitle}>加入家庭菜单</Text><Text style={styles.sheetSubtitle}>{dish.name} · {servings}人份</Text></View>
              <TouchableOpacity style={styles.sheetClose} onPress={() => setMenuOpen(false)}><Ionicons name="close" size={20} color={colors.textSecondary} /></TouchableOpacity>
            </View>
            {menuLoading && !familyId ? <View style={styles.sheetLoading}><ActivityIndicator color={colors.primary} /></View> : <>
              <Text style={styles.fieldLabel}>用餐日期</Text>
              <ScrollView horizontal showsHorizontalScrollIndicator={false} contentContainerStyle={styles.dateChoices}>
                {nextDates(7).map((date) => { const key = localDateKey(date); const active = key === mealDate; return <TouchableOpacity key={key} style={[styles.dateChoice, active && styles.dateChoiceActive]} onPress={() => setMealDate(key)}><Text style={[styles.dateWeekday, active && styles.choiceActiveText]}>{key === localDateKey(new Date()) ? '今天' : `周${'日一二三四五六'[date.getDay()]}`}</Text><Text style={[styles.dateNumber, active && styles.choiceActiveText]}>{date.getMonth()+1}/{date.getDate()}</Text></TouchableOpacity>; })}
              </ScrollView>
              <Text style={styles.fieldLabel}>餐次</Text>
              <View style={styles.mealChoices}>{([1,2,3] as MealType[]).map((type) => <TouchableOpacity key={type} style={[styles.mealChoice, mealType === type && styles.mealChoiceActive]} onPress={() => setMealType(type)}><Text style={[styles.mealChoiceText, mealType === type && styles.mealChoiceTextActive]}>{MealTypeLabel[type]}</Text></TouchableOpacity>)}</View>
              <Text style={styles.fieldLabel}>做饭负责人</Text>
              <ScrollView horizontal showsHorizontalScrollIndicator={false} contentContainerStyle={styles.memberChoices}><TouchableOpacity style={[styles.memberChoice, cookUserId == null && styles.memberChoiceActive]} onPress={() => setCookUserId(undefined)}><Text style={styles.memberChoiceText}>暂不指定</Text></TouchableOpacity>{members.map((member) => <TouchableOpacity key={member.user_id} style={[styles.memberChoice, cookUserId === member.user_id && styles.memberChoiceActive]} onPress={() => setCookUserId(member.user_id)}><Text style={styles.memberChoiceText}>{member.display_name || member.nickname}</Text></TouchableOpacity>)}</ScrollView>
              <TouchableOpacity style={styles.confirmMenuButton} disabled={menuLoading} onPress={addToMealPlan}>{menuLoading ? <ActivityIndicator size="small" color="#fff" /> : <><Ionicons name="checkmark" size={18} color="#fff" /><Text style={styles.confirmMenuText}>确认加入</Text></>}</TouchableOpacity>
            </>}
          </View>
        </View>
      </Modal>
    </View>
  );
}

function localDateKey(date: Date) {
  return `${date.getFullYear()}-${String(date.getMonth()+1).padStart(2,'0')}-${String(date.getDate()).padStart(2,'0')}`;
}

function nextDates(count: number) {
  const today = new Date();
  return Array.from({ length: count }, (_, index) => { const date = new Date(today); date.setDate(today.getDate() + index); return date; });
}

function formatMenuDate(value: string) {
  const [, month, day] = value.split('-');
  return `${Number(month)}月${Number(day)}日`;
}

function StepItem({
  step,
  isLast,
  failedImages,
  onImageError,
}: {
  step: DishStepInfo;
  isLast: boolean;
  failedImages: Set<string>;
  onImageError: (url: string) => void;
}) {
  const imageUrl = resolveDishImageUrl(step.image_key);

  return (
    <View style={styles.stepRow}>
      <View style={styles.stepRail}>
        <View style={styles.stepNumber}>
          <Text style={styles.stepNumberText}>{step.step_no}</Text>
        </View>
        {!isLast ? <View style={styles.stepLine} /> : null}
      </View>
      <View style={[styles.stepContent, !isLast && styles.stepContentSpaced]}>
        <Text style={styles.stepDescription}>{step.description}</Text>
        {imageUrl && !failedImages.has(imageUrl) ? (
          <Image
            source={{ uri: imageUrl }}
            style={styles.stepImage}
            resizeMode="cover"
            onError={() => onImageError(imageUrl)}
          />
        ) : null}
      </View>
    </View>
  );
}

const styles = StyleSheet.create({
  container: {
    flex: 1,
    backgroundColor: pageBackground,
  },
  hero: {
    height: 220,
    backgroundColor: colors.primarySubtle,
    position: 'relative',
  },
  heroImage: {
    width: '100%',
    height: '100%',
  },
  heroPlaceholder: {
    flex: 1,
    alignItems: 'center',
    justifyContent: 'center',
    backgroundColor: '#E7EEF9',
  },
  heroPlate: {
    width: 92,
    height: 92,
    borderRadius: radius.full,
    alignItems: 'center',
    justifyContent: 'center',
    backgroundColor: colors.surface,
    borderWidth: 8,
    borderColor: '#D9E4F5',
  },
  backButton: {
    position: 'absolute',
    left: spacing.lg,
    width: 44,
    height: 44,
    borderRadius: radius.full,
    alignItems: 'center',
    justifyContent: 'center',
    backgroundColor: 'rgba(255,255,255,0.94)',
    borderWidth: StyleSheet.hairlineWidth,
    borderColor: 'rgba(17,24,39,0.12)',
  },
  introSection: {
    backgroundColor: colors.surface,
    paddingHorizontal: spacing.lg,
    paddingTop: spacing.xl,
    paddingBottom: spacing.lg,
  },
  dishName: {
    color: colors.textPrimary,
    fontSize: 24,
    lineHeight: 32,
    fontWeight: '700',
    letterSpacing: 0,
  },
  description: {
    color: colors.textSecondary,
    fontSize: 14,
    lineHeight: 21,
    marginTop: spacing.xs,
    letterSpacing: 0,
  },
  metaRow: {
    flexDirection: 'row',
    alignItems: 'stretch',
    marginTop: spacing.lg,
    paddingTop: spacing.md,
    borderTopWidth: StyleSheet.hairlineWidth,
    borderTopColor: colors.border,
  },
  metaItem: {
    flex: 1,
    minWidth: 0,
    alignItems: 'center',
  },
  metaDivider: {
    width: StyleSheet.hairlineWidth,
    backgroundColor: colors.border,
    marginHorizontal: spacing.sm,
  },
  metaValue: {
    color: colors.textPrimary,
    fontSize: 13,
    lineHeight: 18,
    fontWeight: '700',
    marginTop: spacing.xs,
    letterSpacing: 0,
  },
  metaLabel: {
    color: colors.textSecondary,
    fontSize: 10,
    lineHeight: 15,
    marginTop: 2,
    letterSpacing: 0,
  },
  sectionGap: {
    height: spacing.sm,
    backgroundColor: pageBackground,
  },
  section: {
    backgroundColor: colors.surface,
    paddingHorizontal: spacing.lg,
    paddingVertical: spacing.xl,
    marginTop: spacing.sm,
  },
  sectionHeader: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    gap: spacing.md,
  },
  sectionEyebrow: {
    color: colors.primary,
    fontSize: 11,
    lineHeight: 16,
    fontWeight: '700',
    letterSpacing: 0,
  },
  sectionTitle: {
    color: colors.textPrimary,
    fontSize: 19,
    lineHeight: 26,
    fontWeight: '700',
    marginTop: 2,
    letterSpacing: 0,
  },
  servingsControl: {
    height: 32,
    flexDirection: 'row',
    alignItems: 'center',
    borderWidth: 1,
    borderColor: colors.border,
    borderRadius: radius.md,
    backgroundColor: colors.surface,
  },
  servingsButton: {
    width: 32,
    height: 30,
    alignItems: 'center',
    justifyContent: 'center',
  },
  servingsValue: {
    width: 28,
    color: colors.textPrimary,
    fontSize: 13,
    fontWeight: '700',
    textAlign: 'center',
    letterSpacing: 0,
  },
  ingredientGroup: {
    marginTop: spacing.lg,
  },
  groupName: {
    color: herbGreen,
    fontSize: 12,
    lineHeight: 18,
    fontWeight: '700',
    marginBottom: spacing.xs,
    letterSpacing: 0,
  },
  ingredientRow: {
    minHeight: 40,
    flexDirection: 'row',
    alignItems: 'center',
    borderBottomWidth: StyleSheet.hairlineWidth,
    borderBottomColor: colors.border,
  },
  ingredientName: {
    flex: 1,
    color: colors.textPrimary,
    fontSize: 14,
    lineHeight: 20,
    letterSpacing: 0,
  },
  ingredientAmount: {
    flexShrink: 0,
    color: colors.textSecondary,
    fontSize: 13,
    lineHeight: 18,
    fontWeight: '600',
    marginLeft: spacing.md,
    letterSpacing: 0,
  },
  stepsList: {
    marginTop: spacing.lg,
  },
  stepRow: {
    flexDirection: 'row',
    alignItems: 'stretch',
  },
  stepRail: {
    width: 36,
    alignItems: 'center',
  },
  stepNumber: {
    width: 28,
    height: 28,
    borderRadius: radius.full,
    alignItems: 'center',
    justifyContent: 'center',
    backgroundColor: colors.primary,
  },
  stepNumberText: {
    color: colors.textOnPrimary,
    fontSize: 12,
    lineHeight: 16,
    fontWeight: '700',
    letterSpacing: 0,
  },
  stepLine: {
    flex: 1,
    width: 2,
    minHeight: 30,
    backgroundColor: colors.primaryLight,
  },
  stepContent: {
    flex: 1,
    minWidth: 0,
    paddingLeft: spacing.sm,
    paddingTop: 2,
  },
  stepContentSpaced: {
    paddingBottom: spacing.xl,
  },
  stepDescription: {
    color: colors.textPrimary,
    fontSize: 14,
    lineHeight: 23,
    letterSpacing: 0,
  },
  stepImage: {
    width: '100%',
    aspectRatio: 16 / 9,
    borderRadius: radius.md,
    marginTop: spacing.md,
    backgroundColor: colors.primarySubtle,
  },
  tipsSection: {
    flexDirection: 'row',
    alignItems: 'flex-start',
    marginTop: spacing.sm,
    backgroundColor: stoveOrangeSoft,
    paddingHorizontal: spacing.lg,
    paddingVertical: spacing.xl,
  },
  tipsIcon: {
    width: 36,
    height: 36,
    borderRadius: radius.full,
    alignItems: 'center',
    justifyContent: 'center',
    backgroundColor: '#FFE8BA',
  },
  tipsContent: {
    flex: 1,
    minWidth: 0,
    marginLeft: spacing.md,
  },
  tipsTitle: {
    color: stoveOrange,
    fontSize: 14,
    lineHeight: 20,
    fontWeight: '700',
    letterSpacing: 0,
  },
  tipsText: {
    color: '#5F421B',
    fontSize: 13,
    lineHeight: 21,
    marginTop: spacing.xs,
    letterSpacing: 0,
  },
  inlineEmpty: {
    flexDirection: 'row',
    alignItems: 'center',
    marginTop: spacing.xl,
    paddingVertical: spacing.lg,
    borderTopWidth: StyleSheet.hairlineWidth,
    borderTopColor: colors.border,
  },
  inlineEmptyText: {
    flex: 1,
    color: colors.textSecondary,
    fontSize: 14,
    lineHeight: 21,
    marginLeft: spacing.md,
    letterSpacing: 0,
  },
  centerState: {
    flex: 1,
    alignItems: 'center',
    justifyContent: 'center',
    paddingHorizontal: spacing.xxl,
    backgroundColor: pageBackground,
  },
  stateBackButton: {
    top: spacing.lg,
  },
  errorIcon: {
    width: 72,
    height: 72,
    borderRadius: radius.full,
    alignItems: 'center',
    justifyContent: 'center',
    backgroundColor: colors.primarySubtle,
  },
  stateTitle: {
    color: colors.textPrimary,
    fontSize: 20,
    lineHeight: 28,
    fontWeight: '700',
    marginTop: spacing.lg,
    textAlign: 'center',
    letterSpacing: 0,
  },
  stateMessage: {
    color: colors.textSecondary,
    fontSize: 14,
    lineHeight: 22,
    marginTop: spacing.xs,
    textAlign: 'center',
    letterSpacing: 0,
  },
  retryButton: {
    height: 44,
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'center',
    gap: spacing.sm,
    marginTop: spacing.xl,
    paddingHorizontal: spacing.xl,
    borderRadius: radius.md,
    backgroundColor: colors.primary,
  },
  retryButtonText: {
    color: colors.textOnPrimary,
    fontSize: 15,
    lineHeight: 22,
    fontWeight: '700',
    letterSpacing: 0,
  },
  startBar: {
    backgroundColor: colors.surface,
    paddingTop: spacing.sm,
    paddingHorizontal: spacing.lg,
    borderTopWidth: StyleSheet.hairlineWidth,
    borderTopColor: colors.border,
    flexDirection: 'row',
    gap: spacing.sm,
  },
  menuButton: {
    height: 48,
    paddingHorizontal: spacing.md,
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'center',
    gap: spacing.xs,
    borderRadius: radius.md,
    borderWidth: 1,
    borderColor: colors.primary,
  },
  menuButtonText: { color: colors.primary, fontSize: 13, fontWeight: '700' },
  startButton: {
    flex: 1,
    height: 48,
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'center',
    gap: spacing.sm,
    borderRadius: radius.md,
    backgroundColor: colors.primary,
  },
  startButtonText: {
    color: colors.textOnPrimary,
    fontSize: 16,
    lineHeight: 22,
    fontWeight: '700',
    letterSpacing: 0,
  },
  modalShade: { flex: 1, justifyContent: 'flex-end', backgroundColor: 'rgba(17,24,39,0.42)' },
  menuSheet: { backgroundColor: colors.surface, borderTopLeftRadius: 16, borderTopRightRadius: 16, paddingHorizontal: spacing.lg, paddingTop: spacing.sm },
  sheetHandle: { width: 36, height: 4, borderRadius: 2, backgroundColor: colors.border, alignSelf: 'center', marginBottom: spacing.md },
  sheetHeader: { flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between' },
  sheetTitle: { fontSize: 17, lineHeight: 24, fontWeight: '700', color: colors.textPrimary },
  sheetSubtitle: { fontSize: 12, lineHeight: 18, color: colors.textSecondary, marginTop: 2 },
  sheetClose: { width: 36, height: 36, alignItems: 'center', justifyContent: 'center' },
  sheetLoading: { height: 220, alignItems: 'center', justifyContent: 'center' },
  fieldLabel: { fontSize: 12, lineHeight: 18, fontWeight: '600', color: colors.textPrimary, marginTop: spacing.lg, marginBottom: spacing.sm },
  dateChoices: { gap: spacing.sm, paddingRight: spacing.lg },
  dateChoice: { width: 58, height: 48, borderRadius: radius.md, borderWidth: 1, borderColor: colors.border, alignItems: 'center', justifyContent: 'center' },
  dateChoiceActive: { borderColor: colors.primary, backgroundColor: colors.primary },
  dateWeekday: { fontSize: 10, color: colors.textSecondary },
  dateNumber: { fontSize: 12, lineHeight: 18, fontWeight: '700', color: colors.textPrimary },
  choiceActiveText: { color: colors.textOnPrimary },
  mealChoices: { flexDirection: 'row', gap: spacing.sm },
  mealChoice: { flex: 1, height: 36, borderRadius: radius.md, borderWidth: 1, borderColor: colors.border, alignItems: 'center', justifyContent: 'center' },
  mealChoiceActive: { borderColor: colors.primary, backgroundColor: colors.primarySubtle },
  mealChoiceText: { fontSize: 12, color: colors.textSecondary },
  mealChoiceTextActive: { fontWeight: '700', color: colors.primary },
  memberChoices: { gap: spacing.sm, paddingRight: spacing.lg },
  memberChoice: { height: 34, borderRadius: radius.full, borderWidth: 1, borderColor: colors.border, paddingHorizontal: spacing.md, justifyContent: 'center' },
  memberChoiceActive: { borderColor: colors.primary, backgroundColor: colors.primarySubtle },
  memberChoiceText: { fontSize: 12, color: colors.textPrimary },
  confirmMenuButton: { height: 44, marginTop: spacing.xl, borderRadius: radius.md, backgroundColor: colors.primary, flexDirection: 'row', gap: spacing.sm, alignItems: 'center', justifyContent: 'center' },
  confirmMenuText: { fontSize: 14, fontWeight: '700', color: colors.textOnPrimary },
});
