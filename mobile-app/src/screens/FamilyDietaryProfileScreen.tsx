import React, { useCallback, useState } from 'react';
import { ActivityIndicator, Alert, ScrollView, StyleSheet, Text, TextInput, TouchableOpacity, View } from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import { useFocusEffect, useNavigation, useRoute } from '@react-navigation/native';
import type { NativeStackNavigationProp } from '@react-navigation/native-stack';
import { useSafeAreaInsets } from 'react-native-safe-area-context';
import { getFamilyDietaryProfile, getMyFamily, saveFamilyDietaryProfile } from '../services/family';
import { colors, radius, spacing } from '../theme';
import type { AuthStackParamList } from '../types/auth';
import type { FamilyDietaryBudgetPeriod, FamilyDietaryProfileInput } from '../types/familyDietary';

type Navigation = NativeStackNavigationProp<AuthStackParamList, 'FamilyDietaryProfile'>;

const periods: { value: FamilyDietaryBudgetPeriod; label: string }[] = [
  { value: 1, label: '每天' },
  { value: 2, label: '每周' },
  { value: 3, label: '每月' },
];

// parseBudget 将金额输入转换为可提交的数值，空值表示不设置上下限。
function parseBudget(value: string): number | null {
  const trimmed = value.trim();
  if (!trimmed) return null;
  const amount = Number(trimmed);
  return Number.isFinite(amount) ? amount : null;
}

// FamilyDietaryProfileScreen 提供家庭预算和共同饮食说明的设置表单。
export default function FamilyDietaryProfileScreen() {
  const navigation = useNavigation<Navigation>();
  const route = useRoute();
  const { familyId } = route.params as { familyId: number };
  const insets = useSafeAreaInsets();
  const [min, setMin] = useState('');
  const [max, setMax] = useState('');
  const [period, setPeriod] = useState<FamilyDietaryBudgetPeriod>(2);
  const [notes, setNotes] = useState('');
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [dirty, setDirty] = useState(false);
  const [canEdit, setCanEdit] = useState(false);

  // loadProfile 页面聚焦时同步服务端数据和当前家庭角色权限。
  const loadProfile = useCallback(async () => {
    setLoading(true);
    try {
      const [profile, family] = await Promise.all([getFamilyDietaryProfile(familyId), getMyFamily()]);
      setCanEdit(family?.id === familyId && (family.my_role === 1 || family.my_role === 2));
      setMin(profile?.budget_min == null ? '' : String(profile.budget_min));
      setMax(profile?.budget_max == null ? '' : String(profile.budget_max));
      setPeriod(profile?.budget_period ?? 2);
      setNotes(profile?.notes ?? '');
      setDirty(false);
    } catch (error: unknown) {
      Alert.alert('加载失败', error instanceof Error ? error.message : '请稍后重试');
    } finally {
      setLoading(false);
    }
  }, [familyId]);

  useFocusEffect(useCallback(() => { loadProfile(); }, [loadProfile]));

  // saveProfile 校验金额范围后整体保存家庭饮食档案。
  const saveProfile = async () => {
    if (saving) return;
    const budgetMin = parseBudget(min);
    const budgetMax = parseBudget(max);
    if ((min.trim() && budgetMin === null) || (max.trim() && budgetMax === null)) {
      Alert.alert('预算格式不正确', '请输入有效的数字金额');
      return;
    }
    if ((budgetMin !== null && budgetMin < 0) || (budgetMax !== null && budgetMax < 0) || (budgetMin !== null && budgetMax !== null && budgetMin > budgetMax)) {
      Alert.alert('预算范围不正确', '最高预算不能低于最低预算');
      return;
    }
    setSaving(true);
    const input: FamilyDietaryProfileInput = { budget_min: budgetMin, budget_max: budgetMax, budget_currency: 'CNY', budget_period: period, notes: notes.trim() };
    try {
      await saveFamilyDietaryProfile(familyId, input);
      setDirty(false);
      Alert.alert('保存成功', '家庭饮食设置已更新');
    } catch (error: unknown) {
      Alert.alert('保存失败', error instanceof Error ? error.message : '请稍后重试');
    } finally {
      setSaving(false);
    }
  };

  // goBack 返回上一页，并避免误丢编辑中的内容。
  const goBack = () => {
    if (!dirty || saving) {
      navigation.goBack();
      return;
    }
    Alert.alert('未保存的设置', '返回后本次修改不会保留。', [
      { text: '继续编辑', style: 'cancel' },
      { text: '放弃修改', style: 'destructive', onPress: () => navigation.goBack() },
    ]);
  };

  return (
    <View style={[styles.container, { paddingTop: insets.top }]}> 
      <View style={styles.header}>
        <TouchableOpacity style={styles.backButton} onPress={goBack} accessibilityLabel="返回">
          <Ionicons name="chevron-back" size={22} color={colors.textPrimary} />
        </TouchableOpacity>
        <Text style={styles.headerTitle}>家庭饮食设置</Text>
        <TouchableOpacity style={[styles.saveButton, (!dirty || saving || !canEdit) && styles.disabled]} onPress={saveProfile} disabled={!dirty || saving || !canEdit}>
          {saving ? <ActivityIndicator size="small" color={colors.primary} /> : <Text style={styles.saveText}>保存</Text>}
        </TouchableOpacity>
      </View>

      {loading ? (
        <View style={styles.loading}><ActivityIndicator color={colors.primary} /><Text style={styles.loadingText}>正在加载设置</Text></View>
      ) : (
        <ScrollView contentContainerStyle={styles.content} showsVerticalScrollIndicator={false} keyboardShouldPersistTaps="handled">
          <View style={styles.pageLead}>
            <Text style={styles.pageTitle}>家庭饮食</Text>
            <Text style={styles.pageDescription}>设置家庭共同使用的预算和长期饮食要求。</Text>
          </View>

          <View style={styles.section}>
            <View style={styles.sectionHeader}><Text style={styles.sectionTitle}>预算范围</Text><Text style={styles.sectionHint}>可选</Text></View>
            <View style={styles.budgetLine}>
              <View style={styles.moneyField}><Text style={styles.fieldLabel}>最低预算</Text><View style={styles.moneyInput}><Text style={styles.currency}>¥</Text><TextInput editable={canEdit} value={min} onChangeText={(value) => { setMin(value); setDirty(true); }} keyboardType="decimal-pad" placeholder="不限" placeholderTextColor={colors.textSecondary} style={[styles.input, !canEdit && styles.readOnly]} /></View></View>
              <Text style={styles.toText}>至</Text>
              <View style={styles.moneyField}><Text style={styles.fieldLabel}>最高预算</Text><View style={styles.moneyInput}><Text style={styles.currency}>¥</Text><TextInput editable={canEdit} value={max} onChangeText={(value) => { setMax(value); setDirty(true); }} keyboardType="decimal-pad" placeholder="不限" placeholderTextColor={colors.textSecondary} style={[styles.input, !canEdit && styles.readOnly]} /></View></View>
            </View>
            <Text style={styles.fieldLabel}>预算周期</Text>
            <View style={styles.segmented}>
              {periods.map((item) => <TouchableOpacity key={item.value} disabled={!canEdit} style={[styles.segment, period === item.value && styles.segmentActive, !canEdit && styles.readOnlySegment]} onPress={() => { setPeriod(item.value); setDirty(true); }}><Text style={[styles.segmentText, period === item.value && styles.segmentTextActive]}>{item.label}</Text></TouchableOpacity>)}
            </View>
          </View>

          <View style={styles.section}>
            <View style={styles.sectionHeader}><Text style={styles.sectionTitle}>家庭饮食说明</Text><Text style={styles.sectionHint}>可选</Text></View>
            <Text style={styles.fieldHelp}>记录全家长期遵守的共同要求，例如少油少盐、工作日优先快手菜。</Text>
            <TextInput editable={canEdit} value={notes} onChangeText={(value) => { setNotes(value); setDirty(true); }} multiline maxLength={500} textAlignVertical="top" placeholder="输入家庭共同要求" placeholderTextColor={colors.textSecondary} style={[styles.notes, !canEdit && styles.readOnly]} />
            <Text style={styles.counter}>{notes.length}/500</Text>
          </View>

          <View style={styles.permissionNote}><Ionicons name="information-circle-outline" size={17} color={colors.textSecondary} /><Text style={styles.permissionText}>{canEdit ? '只有家庭所有者和管理员可以修改家庭设置。' : '你当前只能查看家庭设置。'}</Text></View>
        </ScrollView>
      )}
    </View>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1, backgroundColor: colors.background },
  header: { height: 56, flexDirection: 'row', alignItems: 'center', paddingHorizontal: spacing.md, backgroundColor: colors.surface, borderBottomWidth: StyleSheet.hairlineWidth, borderBottomColor: colors.border },
  backButton: { width: 40, height: 40, justifyContent: 'center' },
  headerTitle: { flex: 1, textAlign: 'center', fontSize: 17, fontWeight: '600', color: colors.textPrimary },
  saveButton: { minWidth: 52, height: 32, paddingHorizontal: spacing.sm, borderRadius: radius.sm, alignItems: 'center', justifyContent: 'center', backgroundColor: colors.primarySubtle },
  saveText: { fontSize: 13, fontWeight: '600', color: colors.primary },
  disabled: { opacity: 0.4 },
  content: { padding: spacing.lg, paddingBottom: spacing.xxxl },
  pageLead: { paddingBottom: spacing.lg },
  pageTitle: { fontSize: 21, lineHeight: 28, fontWeight: '700', color: colors.textPrimary },
  pageDescription: { marginTop: spacing.xs, fontSize: 13, lineHeight: 19, color: colors.textSecondary },
  section: { marginBottom: spacing.lg, padding: spacing.lg, backgroundColor: colors.surface, borderWidth: StyleSheet.hairlineWidth, borderColor: colors.border, borderRadius: radius.md },
  sectionHeader: { flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', marginBottom: spacing.md },
  sectionTitle: { fontSize: 15, lineHeight: 21, fontWeight: '600', color: colors.textPrimary },
  sectionHint: { fontSize: 12, color: colors.textSecondary },
  budgetLine: { flexDirection: 'row', alignItems: 'center', gap: spacing.sm, marginBottom: spacing.lg },
  moneyField: { flex: 1 },
  fieldLabel: { fontSize: 12, lineHeight: 17, color: colors.textSecondary, marginBottom: spacing.xs },
  moneyInput: { height: 42, flexDirection: 'row', alignItems: 'center', paddingHorizontal: spacing.md, borderWidth: 1, borderColor: colors.border, borderRadius: radius.sm, backgroundColor: colors.background },
  currency: { marginRight: 4, fontSize: 16, color: colors.textSecondary },
  input: { flex: 1, padding: 0, fontSize: 16, color: colors.textPrimary },
  readOnly: { color: colors.textSecondary },
  toText: { marginTop: spacing.lg, fontSize: 12, color: colors.textSecondary },
  segmented: { flexDirection: 'row', borderWidth: 1, borderColor: colors.border, borderRadius: radius.sm, overflow: 'hidden' },
  segment: { flex: 1, height: 38, alignItems: 'center', justifyContent: 'center', backgroundColor: colors.surface },
  segmentActive: { backgroundColor: colors.primarySubtle },
  readOnlySegment: { opacity: 0.7 },
  segmentText: { fontSize: 13, color: colors.textSecondary },
  segmentTextActive: { color: colors.primary, fontWeight: '600' },
  fieldHelp: { marginBottom: spacing.md, fontSize: 12, lineHeight: 18, color: colors.textSecondary },
  notes: { minHeight: 112, padding: spacing.md, borderWidth: 1, borderColor: colors.border, borderRadius: radius.sm, backgroundColor: colors.background, color: colors.textPrimary, fontSize: 14, lineHeight: 20 },
  counter: { marginTop: spacing.xs, textAlign: 'right', fontSize: 11, color: colors.textSecondary },
  permissionNote: { flexDirection: 'row', alignItems: 'center', justifyContent: 'center', gap: spacing.xs, marginTop: spacing.xs },
  permissionText: { fontSize: 12, color: colors.textSecondary },
  loading: { flex: 1, alignItems: 'center', justifyContent: 'center', gap: spacing.sm },
  loadingText: { fontSize: 13, color: colors.textSecondary },
});
