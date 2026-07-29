import React, { useCallback, useEffect, useMemo, useState } from 'react';
import {
  ActivityIndicator,
  Image,
  Modal,
  ScrollView,
  StyleSheet,
  Text,
  TouchableOpacity,
  useWindowDimensions,
  View,
} from 'react-native';
import AsyncStorage from '@react-native-async-storage/async-storage';
import { Ionicons } from '@expo/vector-icons';
import { useKeepAwake } from 'expo-keep-awake';
import { useNavigation, useRoute } from '@react-navigation/native';
import type { RouteProp } from '@react-navigation/native';
import type { NativeStackNavigationProp } from '@react-navigation/native-stack';
import { useSafeAreaInsets } from 'react-native-safe-area-context';
import {
  fetchDishDetail,
  resolveStepImageUrls,
} from '../services/dish';
import type {
  DishDetailInfo,
  DishStepInfo,
  IngredientInfo,
} from '../services/dish';
import { colors, radius, spacing } from '../theme';
import type { AuthStackParamList } from '../types/auth';

type CookingPhase = 'prep' | 'cooking' | 'complete';

interface SavedTimerState {
  remainingSeconds: number;
  endAt: number | null;
}

interface SavedProgress {
  stepIndex: number;
  servings: number;
  updatedAt: number;
  timers?: Record<string, SavedTimerState>;
  // 兼容第一版只保存当前步骤计时器的数据。
  timerRemaining?: number;
  timerEndAt?: number | null;
}

const progressKey = (dishId: number) => `cooking-progress:${dishId}`;
const pageBackground = '#F5F7FB';
const herbGreen = '#287A4D';
const herbGreenSoft = '#EAF6EF';

function formatAmount(ingredient: IngredientInfo, scale: number): string {
  if (ingredient.amount === null) {
    return ingredient.amount_text || '适量';
  }
  const rounded = Math.round(ingredient.amount * scale * 100) / 100;
  const value = Number.isInteger(rounded)
    ? String(rounded)
    : rounded.toFixed(2).replace(/0+$/, '').replace(/\.$/, '');
  return `${value}${ingredient.unit}`;
}

function formatTimer(seconds: number): string {
  const safeSeconds = Math.max(0, Math.floor(seconds));
  const hours = Math.floor(safeSeconds / 3600);
  const minutes = Math.floor((safeSeconds % 3600) / 60);
  const remainingSeconds = safeSeconds % 60;
  if (hours > 0) {
    return `${String(hours).padStart(2, '0')}:${String(minutes).padStart(2, '0')}:${String(remainingSeconds).padStart(2, '0')}`;
  }
  return `${String(minutes).padStart(2, '0')}:${String(remainingSeconds).padStart(2, '0')}`;
}

function createInitialTimers(steps: DishStepInfo[]): Record<string, SavedTimerState> {
  return Object.fromEntries(
    steps.map((step) => [
      String(step.id),
      {
        remainingSeconds: Math.max(0, step.timer_seconds ?? 0),
        endAt: null,
      },
    ]),
  );
}

export default function CookingModeScreen() {
  useKeepAwake('familyos-cooking-mode');

  const insets = useSafeAreaInsets();
  const { width } = useWindowDimensions();
  const navigation =
    useNavigation<NativeStackNavigationProp<AuthStackParamList>>();
  const route = useRoute<RouteProp<AuthStackParamList, 'CookingMode'>>();

  const [dish, setDish] = useState<DishDetailInfo | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [phase, setPhase] = useState<CookingPhase>('prep');
  const [currentStepIndex, setCurrentStepIndex] = useState(0);
  const [servings, setServings] = useState(Math.max(1, route.params.servings));
  const [resumeProgress, setResumeProgress] = useState<SavedProgress | null>(null);
  const [stepListVisible, setStepListVisible] = useState(false);
  const [exitVisible, setExitVisible] = useState(false);
  const [timers, setTimers] = useState<Record<string, SavedTimerState>>({});
  const [timerTick, setTimerTick] = useState(Date.now());
  const [failedImages, setFailedImages] = useState<Set<string>>(
    () => new Set(),
  );

  const loadData = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const [detail, savedRaw] = await Promise.all([
        fetchDishDetail(route.params.dishId),
        AsyncStorage.getItem(progressKey(route.params.dishId)),
      ]);
      setDish(detail);
      setTimers(createInitialTimers(detail.steps));

      if (savedRaw) {
        const saved = JSON.parse(savedRaw) as SavedProgress;
        if (
          saved.stepIndex >= 0 &&
          saved.stepIndex < detail.steps.length &&
          saved.servings > 0
        ) {
          setResumeProgress(saved);
          setServings(saved.servings);
        }
      }
    } catch (e: any) {
      setError(e.message || '做菜模式加载失败');
    } finally {
      setLoading(false);
    }
  }, [route.params.dishId]);

  useEffect(() => {
    loadData();
  }, [loadData]);

  const baseServings = Math.max(1, dish?.servings || 1);
  const amountScale = servings / baseServings;
  const currentStep = dish?.steps[currentStepIndex];
  const currentTimer = currentStep
    ? timers[String(currentStep.id)] ?? {
        remainingSeconds: Math.max(0, currentStep.timer_seconds ?? 0),
        endAt: null,
      }
    : { remainingSeconds: 0, endAt: null };
  const timerRemaining = currentTimer.endAt
    ? Math.max(0, Math.ceil((currentTimer.endAt - timerTick) / 1000))
    : currentTimer.remainingSeconds;
  const timerRunning = currentTimer.endAt !== null && timerRemaining > 0;
  const progress = dish?.steps.length
    ? (currentStepIndex + 1) / dish.steps.length
    : 0;

  useEffect(() => {
    const hasRunningTimer = Object.values(timers).some(
      (timer) => timer.endAt !== null && timer.endAt > Date.now(),
    );
    if (!hasRunningTimer) return;
    setTimerTick(Date.now());
    const interval = setInterval(() => {
      const now = Date.now();
      setTimerTick(now);
      if (!Object.values(timers).some((timer) => timer.endAt !== null && timer.endAt > now)) {
        clearInterval(interval);
      }
    }, 1000);
    return () => clearInterval(interval);
  }, [timers]);

  const startTimer = useCallback(() => {
    if (!currentStep || timerRemaining <= 0 || timerRunning) return;
    setTimers((current) => ({
      ...current,
      [String(currentStep.id)]: {
        remainingSeconds: timerRemaining,
        endAt: Date.now() + timerRemaining * 1000,
      },
    }));
    setTimerTick(Date.now());
  }, [currentStep, timerRemaining, timerRunning]);

  const pauseTimer = useCallback(() => {
    if (!currentStep || !timerRunning) return;
    setTimers((current) => ({
      ...current,
      [String(currentStep.id)]: {
        remainingSeconds: timerRemaining,
        endAt: null,
      },
    }));
  }, [currentStep, timerRemaining, timerRunning]);

  const resetTimer = useCallback(() => {
    if (!currentStep) return;
    setTimers((current) => ({
      ...current,
      [String(currentStep.id)]: {
        remainingSeconds: Math.max(0, currentStep.timer_seconds ?? 0),
        endAt: null,
      },
    }));
  }, [currentStep]);

  const goToStep = useCallback(
    (index: number) => {
      if (!dish) return;
      const step = dish.steps[index];
      if (!step) return;

      setCurrentStepIndex(index);
      setTimerTick(Date.now());
    },
    [dish],
  );

  const startCooking = useCallback(async () => {
    if (dish) {
      setTimers(createInitialTimers(dish.steps));
    }
    goToStep(0);
    setResumeProgress(null);
    await AsyncStorage.removeItem(progressKey(route.params.dishId));
    setPhase('cooking');
  }, [dish, goToStep, route.params.dishId]);

  const resumeCooking = useCallback(() => {
    if (!resumeProgress) return;
    const step = dish?.steps[resumeProgress.stepIndex];
    if (!step) return;
    const restoredTimers = {
      ...createInitialTimers(dish.steps),
      ...(resumeProgress.timers ?? {}),
    };
    if (!resumeProgress.timers && resumeProgress.timerRemaining !== undefined) {
      restoredTimers[String(step.id)] = {
        remainingSeconds: Math.max(0, resumeProgress.timerRemaining),
        endAt: resumeProgress.timerEndAt ?? null,
      };
    }
    setTimers(restoredTimers);
    setTimerTick(Date.now());
    goToStep(resumeProgress.stepIndex);
    setServings(resumeProgress.servings);
    setPhase('cooking');
  }, [dish, goToStep, resumeProgress]);

  const completeCooking = useCallback(async () => {
    if (dish) {
      await AsyncStorage.removeItem(progressKey(dish.id));
    }
    setResumeProgress(null);
    setPhase('complete');
  }, [dish]);

  const goNext = useCallback(() => {
    if (!dish) return;
    if (currentStepIndex >= dish.steps.length - 1) {
      completeCooking();
      return;
    }
    goToStep(currentStepIndex + 1);
  }, [completeCooking, currentStepIndex, dish, goToStep]);

  const saveProgress = useCallback(async () => {
    if (phase !== 'cooking' || !dish) return;
    const progress: SavedProgress = {
      stepIndex: currentStepIndex,
      servings,
      updatedAt: Date.now(),
      timers,
    };
    await AsyncStorage.setItem(progressKey(dish.id), JSON.stringify(progress));
  }, [currentStepIndex, dish, phase, servings, timers]);

  useEffect(() => {
    saveProgress().catch(() => undefined);
  }, [saveProgress]);

  const exitToBackground = useCallback(async () => {
    await saveProgress();
    setExitVisible(false);
    navigation.goBack();
  }, [navigation, saveProgress]);

  const exitAndDiscard = useCallback(async () => {
    if (dish) {
      await AsyncStorage.removeItem(progressKey(dish.id));
    }
    setResumeProgress(null);
    setExitVisible(false);
    navigation.goBack();
  }, [dish, navigation]);

  const requestExit = useCallback(() => {
    if (phase === 'cooking') {
      setExitVisible(true);
    } else {
      navigation.goBack();
    }
  }, [navigation, phase]);

  const jumpToStep = useCallback((index: number) => {
    goToStep(index);
    setStepListVisible(false);
  }, [goToStep]);

  const markImageFailed = useCallback((url: string) => {
    setFailedImages((current) => {
      const next = new Set(current);
      next.add(url);
      return next;
    });
  }, []);

  if (loading) {
    return (
      <View style={styles.centerState}>
        <ActivityIndicator color={colors.primary} size="large" />
        <Text style={styles.stateTitle}>正在准备做菜模式</Text>
      </View>
    );
  }

  if (error || !dish || dish.steps.length === 0 || !currentStep) {
    return (
      <View style={[styles.centerState, { paddingTop: insets.top }]}> 
        <View style={styles.stateIcon}>
          <Ionicons name="restaurant-outline" size={32} color={colors.primary} />
        </View>
        <Text style={styles.stateTitle}>暂时无法开始做菜</Text>
        <Text style={styles.stateMessage}>
          {error || '这道菜还没有添加制作步骤'}
        </Text>
        <TouchableOpacity
          style={styles.stateButton}
          onPress={() => navigation.goBack()}
        >
          <Text style={styles.stateButtonText}>返回菜谱</Text>
        </TouchableOpacity>
      </View>
    );
  }

  if (phase === 'complete') {
    return (
      <View
        style={[
          styles.completeScreen,
          { paddingTop: insets.top + spacing.xxl, paddingBottom: insets.bottom + spacing.xl },
        ]}
      >
        <View style={styles.completeIcon}>
          <Ionicons name="checkmark" size={42} color={colors.textOnPrimary} />
        </View>
        <Text style={styles.completeTitle}>{dish.name}做好了</Text>
        <Text style={styles.completeMessage}>
          共完成 {dish.steps.length} 个步骤
        </Text>
        <View style={styles.completeActions}>
          <TouchableOpacity
            style={styles.primaryButton}
            onPress={() => navigation.goBack()}
          >
            <Text style={styles.primaryButtonText}>返回菜谱详情</Text>
          </TouchableOpacity>
          <TouchableOpacity
            style={styles.secondaryFullButton}
            onPress={() => {
              setTimers(createInitialTimers(dish.steps));
              goToStep(0);
              setPhase('cooking');
            }}
          >
            <Text style={styles.secondaryFullButtonText}>再看一遍步骤</Text>
          </TouchableOpacity>
        </View>
      </View>
    );
  }

  return (
    <View style={styles.container}>
      <CookingHeader
        dishName={dish.name}
        phase={phase}
        stepIndex={currentStepIndex}
        stepCount={dish.steps.length}
        progress={progress}
        topInset={insets.top}
        onClose={requestExit}
        onOpenSteps={() => setStepListVisible(true)}
      />

      {phase === 'prep' ? (
        <ScrollView
          style={styles.content}
          contentContainerStyle={styles.prepContent}
          showsVerticalScrollIndicator={false}
        >
          <Text style={styles.eyebrow}>开始前</Text>
          <Text style={styles.prepTitle}>准备材料</Text>
          <Text style={styles.prepDescription}>
            {servings}人份 · 共{dish.ingredient_groups.reduce(
              (total, group) => total + group.ingredients.length,
              0,
            )}种用料
          </Text>

          {resumeProgress ? (
            <View style={styles.resumeBand}>
              <View style={styles.resumeIcon}>
                <Ionicons name="play" size={18} color={colors.primary} />
              </View>
              <View style={styles.resumeText}>
                <Text style={styles.resumeTitle}>上次做到第 {resumeProgress.stepIndex + 1} 步</Text>
                <Text style={styles.resumeMessage}>进度保存在这台设备上</Text>
              </View>
              <TouchableOpacity onPress={resumeCooking} style={styles.resumeButton}>
                <Text style={styles.resumeButtonText}>继续</Text>
              </TouchableOpacity>
            </View>
          ) : null}

          {dish.ingredient_groups.map((group) => (
            <View key={group.name || '未分组'} style={styles.ingredientGroup}>
              {group.name ? <Text style={styles.groupName}>{group.name}</Text> : null}
              {group.ingredients.map((ingredient) => (
                <View key={ingredient.id} style={styles.ingredientRow}>
                  <Text style={styles.ingredientName}>{ingredient.name}</Text>
                  <Text style={styles.ingredientAmount}>
                    {formatAmount(ingredient, amountScale)}
                  </Text>
                </View>
              ))}
            </View>
          ))}
        </ScrollView>
      ) : (
        <ScrollView
          style={styles.content}
          contentContainerStyle={styles.stepContent}
          showsVerticalScrollIndicator={false}
        >
          <StepImageGallery
            step={currentStep}
            availableWidth={width}
            failedImages={failedImages}
            onImageError={markImageFailed}
          />
          <Text style={styles.stepDescription}>{currentStep.description}</Text>
          <TimerCard
            totalSeconds={currentStep.timer_seconds ?? 0}
            remainingSeconds={timerRemaining}
            running={timerRunning}
            onStart={startTimer}
            onPause={pauseTimer}
            onReset={resetTimer}
          />
        </ScrollView>
      )}

      <View
        style={[
          styles.bottomBar,
          { paddingBottom: Math.max(insets.bottom, spacing.sm) },
        ]}
      >
        {phase === 'prep' ? (
          <TouchableOpacity style={styles.primaryButton} onPress={startCooking}>
            <Ionicons name="play" size={18} color={colors.textOnPrimary} />
            <Text style={styles.primaryButtonText}>材料已备齐，开始做菜</Text>
          </TouchableOpacity>
        ) : (
          <View style={styles.stepActions}>
            <TouchableOpacity
              style={[
                styles.previousButton,
                currentStepIndex === 0 && styles.disabledButton,
              ]}
              onPress={() => goToStep(Math.max(0, currentStepIndex - 1))}
              disabled={currentStepIndex === 0}
            >
              <Ionicons
                name="chevron-back"
                size={20}
                color={currentStepIndex === 0 ? colors.border : colors.textPrimary}
              />
              <Text
                style={[
                  styles.previousButtonText,
                  currentStepIndex === 0 && styles.disabledButtonText,
                ]}
              >
                上一步
              </Text>
            </TouchableOpacity>
            <TouchableOpacity style={styles.nextButton} onPress={goNext}>
              <Text style={styles.nextButtonText}>
                {currentStepIndex === dish.steps.length - 1 ? '完成' : '下一步'}
              </Text>
              <Ionicons
                name={currentStepIndex === dish.steps.length - 1 ? 'checkmark' : 'chevron-forward'}
                size={20}
                color={colors.textOnPrimary}
              />
            </TouchableOpacity>
          </View>
        )}
      </View>

      <StepListModal
        visible={stepListVisible}
        steps={dish.steps}
        currentIndex={currentStepIndex}
        bottomInset={insets.bottom}
        onClose={() => setStepListVisible(false)}
        onSelect={jumpToStep}
      />

      <ExitModal
        visible={exitVisible}
        onContinue={() => setExitVisible(false)}
        onBackgroundExit={exitToBackground}
        onDiscard={exitAndDiscard}
      />
    </View>
  );
}

function CookingHeader({
  dishName,
  phase,
  stepIndex,
  stepCount,
  progress,
  topInset,
  onClose,
  onOpenSteps,
}: {
  dishName: string;
  phase: CookingPhase;
  stepIndex: number;
  stepCount: number;
  progress: number;
  topInset: number;
  onClose: () => void;
  onOpenSteps: () => void;
}) {
  return (
    <View style={[styles.header, { paddingTop: topInset }]}> 
      <View style={styles.headerRow}>
        <TouchableOpacity
          style={styles.iconButton}
          onPress={onClose}
          accessibilityLabel="退出做菜模式"
        >
          <Ionicons name="close" size={24} color={colors.textPrimary} />
        </TouchableOpacity>
        <View style={styles.headerTitleArea}>
          <Text style={styles.headerTitle} numberOfLines={1}>{dishName}</Text>
          <Text style={styles.headerSubtitle}>
            {phase === 'prep' ? '准备材料' : `第 ${stepIndex + 1} / ${stepCount} 步`}
          </Text>
        </View>
        {phase === 'cooking' ? (
          <TouchableOpacity
            style={styles.iconButton}
            onPress={onOpenSteps}
            accessibilityLabel="查看全部步骤"
          >
            <Ionicons name="list" size={23} color={colors.textPrimary} />
          </TouchableOpacity>
        ) : (
          <View style={styles.iconButton} />
        )}
      </View>
      {phase === 'cooking' ? (
        <View style={styles.progressTrack}>
          <View style={[styles.progressFill, { width: `${progress * 100}%` }]} />
        </View>
      ) : null}
    </View>
  );
}

function StepImageGallery({
  step,
  availableWidth,
  failedImages,
  onImageError,
}: {
  step: DishStepInfo;
  availableWidth: number;
  failedImages: Set<string>;
  onImageError: (url: string) => void;
}) {
  const images = useMemo(() => resolveStepImageUrls(step), [step]);
  const [activeIndex, setActiveIndex] = useState(0);
  const galleryWidth = Math.min(availableWidth - spacing.xxl, 560);

  useEffect(() => {
    setActiveIndex(0);
  }, [step.id]);

  if (images.length === 0) return null;

  return (
    <View style={[styles.gallery, { width: galleryWidth }]}> 
      <ScrollView
        horizontal
        pagingEnabled
        showsHorizontalScrollIndicator={false}
        onMomentumScrollEnd={(event) => {
          const index = Math.round(
            event.nativeEvent.contentOffset.x / galleryWidth,
          );
          setActiveIndex(Math.max(0, Math.min(images.length - 1, index)));
        }}
      >
        {images.map((url, index) => (
          <View key={url} style={{ width: galleryWidth }}>
            {failedImages.has(url) ? (
              <View style={styles.failedImage}>
                <Ionicons name="image-outline" size={30} color={colors.textSecondary} />
                <Text style={styles.failedImageText}>图片加载失败</Text>
              </View>
            ) : (
              <Image
                source={{ uri: url }}
                style={styles.galleryImage}
                resizeMode="cover"
                onError={() => onImageError(url)}
                accessibilityLabel={`步骤图片 ${index + 1}`}
              />
            )}
          </View>
        ))}
      </ScrollView>
      {images.length > 1 ? (
        <View style={styles.galleryDots}>
          {images.map((url, index) => (
            <View
              key={url}
              style={[styles.galleryDot, index === activeIndex && styles.galleryDotActive]}
            />
          ))}
        </View>
      ) : null}
    </View>
  );
}

function TimerCard({
  totalSeconds,
  remainingSeconds,
  running,
  onStart,
  onPause,
  onReset,
}: {
  totalSeconds: number;
  remainingSeconds: number;
  running: boolean;
  onStart: () => void;
  onPause: () => void;
  onReset: () => void;
}) {
  if (totalSeconds <= 0) return null;

  const finished = remainingSeconds === 0 && !running;
  return (
    <View style={styles.timerToolbar}>
      <View style={styles.timerLabelRow}>
        <Ionicons name="timer-outline" size={19} color={herbGreen} />
        <Text style={styles.timerLabel}>计时</Text>
      </View>
      <Text style={[styles.timerValue, running && styles.timerValueRunning]}>
        {formatTimer(remainingSeconds)}
      </Text>
      <Text style={[styles.timerStatus, finished && styles.timerStatusFinished]}>
        {finished ? '时间到' : running ? '计时中' : '待开始'}
      </Text>
      <TouchableOpacity
        style={[styles.timerIconButton, finished && styles.timerIconButtonDisabled]}
        onPress={running ? onPause : onStart}
        disabled={finished}
        accessibilityRole="button"
        accessibilityLabel={running ? '暂停计时' : '开始计时'}
      >
        <Ionicons
          name={running ? 'pause' : 'play'}
          size={17}
          color={finished ? colors.textSecondary : colors.textOnPrimary}
        />
      </TouchableOpacity>
      <TouchableOpacity
        style={styles.timerIconButtonSecondary}
        onPress={onReset}
        accessibilityRole="button"
        accessibilityLabel="重置计时"
      >
        <Ionicons name="refresh" size={17} color={colors.textPrimary} />
      </TouchableOpacity>
    </View>
  );
}

function StepListModal({
  visible,
  steps,
  currentIndex,
  bottomInset,
  onClose,
  onSelect,
}: {
  visible: boolean;
  steps: DishStepInfo[];
  currentIndex: number;
  bottomInset: number;
  onClose: () => void;
  onSelect: (index: number) => void;
}) {
  return (
    <Modal visible={visible} transparent animationType="slide" onRequestClose={onClose}>
      <View style={styles.modalRoot}>
        <TouchableOpacity style={styles.modalBackdrop} onPress={onClose} />
        <View style={[styles.stepSheet, { paddingBottom: bottomInset + spacing.lg }]}> 
          <View style={styles.sheetHandle} />
          <View style={styles.sheetHeader}>
            <Text style={styles.sheetTitle}>全部步骤</Text>
            <TouchableOpacity style={styles.sheetClose} onPress={onClose}>
              <Ionicons name="close" size={22} color={colors.textPrimary} />
            </TouchableOpacity>
          </View>
          <ScrollView showsVerticalScrollIndicator={false}>
            {steps.map((step, index) => {
              const active = index === currentIndex;
              const completed = index < currentIndex;
              return (
                <TouchableOpacity
                  key={step.id}
                  style={[styles.sheetStep, active && styles.sheetStepActive]}
                  onPress={() => onSelect(index)}
                >
                  <View
                    style={[
                      styles.sheetStepNumber,
                      (active || completed) && styles.sheetStepNumberActive,
                    ]}
                  >
                    {completed ? (
                      <Ionicons name="checkmark" size={14} color={colors.textOnPrimary} />
                    ) : (
                      <Text
                        style={[
                          styles.sheetStepNumberText,
                          active && styles.sheetStepNumberTextActive,
                        ]}
                      >
                        {step.step_no}
                      </Text>
                    )}
                  </View>
                  <Text
                    style={[styles.sheetStepText, active && styles.sheetStepTextActive]}
                    numberOfLines={2}
                  >
                    {step.description}
                  </Text>
                  <Ionicons name="chevron-forward" size={17} color={colors.textSecondary} />
                </TouchableOpacity>
              );
            })}
          </ScrollView>
        </View>
      </View>
    </Modal>
  );
}

function ExitModal({
  visible,
  onContinue,
  onBackgroundExit,
  onDiscard,
}: {
  visible: boolean;
  onContinue: () => void;
  onBackgroundExit: () => void;
  onDiscard: () => void;
}) {
  return (
    <Modal visible={visible} transparent animationType="fade" onRequestClose={onContinue}>
      <View style={styles.confirmRoot}>
        <View style={styles.confirmDialog}>
          <Text style={styles.confirmTitle}>退出做菜模式？</Text>
          <Text style={styles.confirmMessage}>选择退出方式，计时状态会按你的选择处理。</Text>
          <TouchableOpacity style={styles.primaryButton} onPress={onContinue}>
            <Text style={styles.primaryButtonText}>继续做菜</Text>
          </TouchableOpacity>
          <TouchableOpacity style={styles.backgroundExitButton} onPress={onBackgroundExit}>
            <Ionicons name="time-outline" size={18} color={colors.primary} />
            <Text style={styles.backgroundExitText}>后台继续计时并退出</Text>
          </TouchableOpacity>
          <TouchableOpacity style={styles.confirmExitButton} onPress={onDiscard}>
            <Text style={styles.confirmExitText}>停止计时并退出</Text>
          </TouchableOpacity>
        </View>
      </View>
    </Modal>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1, backgroundColor: pageBackground },
  content: { flex: 1 },
  header: {
    backgroundColor: colors.surface,
    borderBottomWidth: StyleSheet.hairlineWidth,
    borderBottomColor: colors.border,
  },
  headerRow: {
    height: 60,
    flexDirection: 'row',
    alignItems: 'center',
    paddingHorizontal: spacing.sm,
  },
  iconButton: {
    width: 44,
    height: 44,
    alignItems: 'center',
    justifyContent: 'center',
  },
  headerTitleArea: { flex: 1, minWidth: 0, alignItems: 'center' },
  headerTitle: {
    maxWidth: '100%',
    color: colors.textPrimary,
    fontSize: 15,
    lineHeight: 21,
    fontWeight: '700',
    letterSpacing: 0,
  },
  headerSubtitle: {
    color: colors.textSecondary,
    fontSize: 11,
    lineHeight: 16,
    marginTop: 1,
    letterSpacing: 0,
  },
  progressTrack: { height: 3, backgroundColor: colors.primaryLight },
  progressFill: { height: 3, backgroundColor: colors.primary },
  prepContent: { paddingHorizontal: spacing.lg, paddingVertical: spacing.xxl },
  eyebrow: {
    color: colors.primary,
    fontSize: 12,
    lineHeight: 18,
    fontWeight: '700',
    letterSpacing: 0,
  },
  prepTitle: {
    color: colors.textPrimary,
    fontSize: 24,
    lineHeight: 32,
    fontWeight: '700',
    marginTop: 2,
    letterSpacing: 0,
  },
  prepDescription: {
    color: colors.textSecondary,
    fontSize: 14,
    lineHeight: 21,
    marginTop: spacing.xs,
    letterSpacing: 0,
  },
  resumeBand: {
    flexDirection: 'row',
    alignItems: 'center',
    backgroundColor: colors.primarySubtle,
    marginHorizontal: -spacing.lg,
    marginTop: spacing.xl,
    paddingHorizontal: spacing.lg,
    paddingVertical: spacing.md,
  },
  resumeIcon: {
    width: 36,
    height: 36,
    borderRadius: radius.full,
    alignItems: 'center',
    justifyContent: 'center',
    backgroundColor: colors.surface,
  },
  resumeText: { flex: 1, minWidth: 0, marginLeft: spacing.md },
  resumeTitle: {
    color: colors.textPrimary,
    fontSize: 14,
    lineHeight: 20,
    fontWeight: '700',
    letterSpacing: 0,
  },
  resumeMessage: {
    color: colors.textSecondary,
    fontSize: 11,
    lineHeight: 16,
    marginTop: 2,
    letterSpacing: 0,
  },
  resumeButton: { paddingHorizontal: spacing.md, paddingVertical: spacing.sm },
  resumeButtonText: {
    color: colors.primary,
    fontSize: 14,
    lineHeight: 20,
    fontWeight: '700',
    letterSpacing: 0,
  },
  ingredientGroup: { marginTop: spacing.xl },
  groupName: {
    color: herbGreen,
    fontSize: 12,
    lineHeight: 18,
    fontWeight: '700',
    marginBottom: spacing.xs,
    letterSpacing: 0,
  },
  ingredientRow: {
    minHeight: 42,
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
    color: colors.textSecondary,
    fontSize: 13,
    lineHeight: 18,
    fontWeight: '600',
    marginLeft: spacing.md,
    letterSpacing: 0,
  },
  stepContent: {
    flexGrow: 1,
    alignItems: 'center',
    paddingHorizontal: spacing.lg,
    paddingTop: spacing.xl,
    paddingBottom: spacing.xxxl,
  },
  stepDescription: {
    width: '100%',
    color: colors.textPrimary,
    fontSize: 20,
    lineHeight: 31,
    fontWeight: '500',
    marginTop: spacing.lg,
    letterSpacing: 0,
  },
  timerToolbar: {
    width: '100%',
    marginTop: spacing.xl,
    paddingVertical: spacing.md,
    flexDirection: 'row',
    alignItems: 'center',
    borderTopWidth: StyleSheet.hairlineWidth,
    borderBottomWidth: StyleSheet.hairlineWidth,
    borderColor: colors.border,
  },
  timerLabelRow: { flexDirection: 'row', alignItems: 'center', gap: spacing.xs },
  timerLabel: {
    color: colors.textPrimary,
    fontSize: 14,
    lineHeight: 20,
    fontWeight: '700',
    letterSpacing: 0,
  },
  timerStatus: {
    color: colors.textSecondary,
    fontSize: 12,
    lineHeight: 18,
    minWidth: 42,
    marginLeft: spacing.sm,
    textAlign: 'right',
    letterSpacing: 0,
  },
  timerStatusFinished: { color: herbGreen, fontWeight: '700' },
  timerValue: {
    color: colors.textPrimary,
    fontSize: 25,
    lineHeight: 32,
    fontWeight: '700',
    marginLeft: 'auto',
    fontVariant: ['tabular-nums'],
    letterSpacing: 0,
  },
  timerValueRunning: { color: herbGreen },
  timerIconButton: {
    width: 38,
    height: 38,
    alignItems: 'center',
    justifyContent: 'center',
    borderRadius: radius.full,
    backgroundColor: herbGreen,
    marginLeft: spacing.md,
  },
  timerIconButtonDisabled: { backgroundColor: colors.primarySubtle },
  timerIconButtonSecondary: {
    width: 38,
    height: 38,
    alignItems: 'center',
    justifyContent: 'center',
    borderRadius: radius.full,
    borderWidth: 1,
    borderColor: colors.border,
    backgroundColor: colors.surface,
    marginLeft: spacing.sm,
  },
  gallery: { alignSelf: 'center' },
  galleryImage: {
    width: '100%',
    aspectRatio: 16 / 9,
    borderRadius: radius.md,
    backgroundColor: colors.primarySubtle,
  },
  failedImage: {
    width: '100%',
    aspectRatio: 16 / 9,
    borderRadius: radius.md,
    alignItems: 'center',
    justifyContent: 'center',
    backgroundColor: colors.primarySubtle,
  },
  failedImageText: {
    color: colors.textSecondary,
    fontSize: 12,
    lineHeight: 18,
    marginTop: spacing.sm,
    letterSpacing: 0,
  },
  galleryDots: {
    height: 20,
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'center',
    gap: spacing.xs,
  },
  galleryDot: {
    width: 6,
    height: 6,
    borderRadius: radius.full,
    backgroundColor: colors.border,
  },
  galleryDotActive: { width: 16, backgroundColor: colors.primary },
  bottomBar: {
    backgroundColor: colors.surface,
    paddingTop: spacing.sm,
    paddingHorizontal: spacing.lg,
    borderTopWidth: StyleSheet.hairlineWidth,
    borderTopColor: colors.border,
  },
  primaryButton: {
    minHeight: 48,
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'center',
    gap: spacing.sm,
    borderRadius: radius.md,
    backgroundColor: colors.primary,
    paddingHorizontal: spacing.lg,
  },
  primaryButtonText: {
    color: colors.textOnPrimary,
    fontSize: 16,
    lineHeight: 22,
    fontWeight: '700',
    letterSpacing: 0,
  },
  stepActions: { flexDirection: 'row', gap: spacing.sm },
  previousButton: {
    width: 116,
    minHeight: 48,
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'center',
    borderRadius: radius.md,
    borderWidth: 1,
    borderColor: colors.border,
    backgroundColor: colors.surface,
  },
  disabledButton: { backgroundColor: '#F8FAFC' },
  previousButtonText: {
    color: colors.textPrimary,
    fontSize: 15,
    lineHeight: 21,
    fontWeight: '700',
    letterSpacing: 0,
  },
  disabledButtonText: { color: colors.border },
  nextButton: {
    flex: 1,
    minHeight: 48,
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'center',
    borderRadius: radius.md,
    backgroundColor: colors.primary,
  },
  nextButtonText: {
    color: colors.textOnPrimary,
    fontSize: 15,
    lineHeight: 21,
    fontWeight: '700',
    letterSpacing: 0,
  },
  completeScreen: {
    flex: 1,
    alignItems: 'center',
    justifyContent: 'center',
    backgroundColor: pageBackground,
    paddingHorizontal: spacing.xxl,
  },
  completeIcon: {
    width: 88,
    height: 88,
    borderRadius: radius.full,
    alignItems: 'center',
    justifyContent: 'center',
    backgroundColor: herbGreen,
  },
  completeTitle: {
    color: colors.textPrimary,
    fontSize: 24,
    lineHeight: 32,
    fontWeight: '700',
    marginTop: spacing.xxl,
    textAlign: 'center',
    letterSpacing: 0,
  },
  completeMessage: {
    color: colors.textSecondary,
    fontSize: 14,
    lineHeight: 21,
    marginTop: spacing.xs,
    letterSpacing: 0,
  },
  completeActions: { width: '100%', marginTop: spacing.xxxl, gap: spacing.md },
  secondaryFullButton: {
    minHeight: 48,
    alignItems: 'center',
    justifyContent: 'center',
    borderRadius: radius.md,
    borderWidth: 1,
    borderColor: colors.border,
    backgroundColor: colors.surface,
  },
  secondaryFullButtonText: {
    color: colors.textPrimary,
    fontSize: 15,
    lineHeight: 21,
    fontWeight: '700',
    letterSpacing: 0,
  },
  centerState: {
    flex: 1,
    alignItems: 'center',
    justifyContent: 'center',
    backgroundColor: pageBackground,
    paddingHorizontal: spacing.xxl,
  },
  stateIcon: {
    width: 68,
    height: 68,
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
    lineHeight: 21,
    marginTop: spacing.xs,
    textAlign: 'center',
    letterSpacing: 0,
  },
  stateButton: {
    minHeight: 44,
    alignItems: 'center',
    justifyContent: 'center',
    backgroundColor: colors.primary,
    borderRadius: radius.md,
    marginTop: spacing.xl,
    paddingHorizontal: spacing.xl,
  },
  stateButtonText: {
    color: colors.textOnPrimary,
    fontSize: 15,
    lineHeight: 21,
    fontWeight: '700',
    letterSpacing: 0,
  },
  modalRoot: { flex: 1, justifyContent: 'flex-end' },
  modalBackdrop: {
    ...StyleSheet.absoluteFill,
    backgroundColor: 'rgba(17,24,39,0.42)',
  },
  stepSheet: {
    maxHeight: '76%',
    backgroundColor: colors.surface,
    borderTopLeftRadius: radius.lg,
    borderTopRightRadius: radius.lg,
    paddingHorizontal: spacing.lg,
  },
  sheetHandle: {
    width: 36,
    height: 4,
    alignSelf: 'center',
    borderRadius: radius.full,
    backgroundColor: colors.border,
    marginTop: spacing.sm,
  },
  sheetHeader: {
    height: 56,
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
  },
  sheetTitle: {
    color: colors.textPrimary,
    fontSize: 18,
    lineHeight: 24,
    fontWeight: '700',
    letterSpacing: 0,
  },
  sheetClose: { width: 40, height: 40, alignItems: 'center', justifyContent: 'center' },
  sheetStep: {
    minHeight: 58,
    flexDirection: 'row',
    alignItems: 'center',
    borderBottomWidth: StyleSheet.hairlineWidth,
    borderBottomColor: colors.border,
    paddingHorizontal: spacing.sm,
  },
  sheetStepActive: { backgroundColor: colors.primarySubtle },
  sheetStepNumber: {
    width: 28,
    height: 28,
    borderRadius: radius.full,
    alignItems: 'center',
    justifyContent: 'center',
    borderWidth: 1,
    borderColor: colors.border,
  },
  sheetStepNumberActive: {
    backgroundColor: colors.primary,
    borderColor: colors.primary,
  },
  sheetStepNumberText: {
    color: colors.textSecondary,
    fontSize: 12,
    lineHeight: 16,
    fontWeight: '700',
    letterSpacing: 0,
  },
  sheetStepNumberTextActive: { color: colors.textOnPrimary },
  sheetStepText: {
    flex: 1,
    minWidth: 0,
    color: colors.textPrimary,
    fontSize: 14,
    lineHeight: 20,
    marginHorizontal: spacing.md,
    letterSpacing: 0,
  },
  sheetStepTextActive: { color: colors.primary, fontWeight: '700' },
  confirmRoot: {
    flex: 1,
    alignItems: 'center',
    justifyContent: 'center',
    backgroundColor: 'rgba(17,24,39,0.42)',
    paddingHorizontal: spacing.xxl,
  },
  confirmDialog: {
    width: '100%',
    maxWidth: 360,
    backgroundColor: colors.surface,
    borderRadius: radius.lg,
    padding: spacing.xl,
  },
  confirmTitle: {
    color: colors.textPrimary,
    fontSize: 19,
    lineHeight: 26,
    fontWeight: '700',
    textAlign: 'center',
    letterSpacing: 0,
  },
  confirmMessage: {
    color: colors.textSecondary,
    fontSize: 14,
    lineHeight: 21,
    textAlign: 'center',
    marginTop: spacing.sm,
    marginBottom: spacing.xl,
    letterSpacing: 0,
  },
  backgroundExitButton: {
    minHeight: 44,
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'center',
    gap: spacing.xs,
    borderRadius: radius.md,
    backgroundColor: herbGreenSoft,
    marginTop: spacing.sm,
  },
  backgroundExitText: {
    color: colors.primary,
    fontSize: 14,
    lineHeight: 20,
    fontWeight: '700',
    letterSpacing: 0,
  },
  confirmExitButton: {
    minHeight: 44,
    alignItems: 'center',
    justifyContent: 'center',
    marginTop: spacing.sm,
  },
  confirmExitText: {
    color: colors.textSecondary,
    fontSize: 15,
    lineHeight: 21,
    fontWeight: '600',
    letterSpacing: 0,
  },
});
