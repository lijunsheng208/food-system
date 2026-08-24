import React, { useCallback, useMemo, useState } from 'react';
import {
  ActivityIndicator,
  Alert,
  Modal,
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
import { getDietaryPreferences, replaceDietaryPreferences } from '../services/auth';
import { colors, radius, spacing, typography } from '../theme';
import type { AuthStackParamList } from '../types/auth';
import type { DietaryPreferenceType, UserDietaryPreference, UserDietaryPreferenceInput } from '../types/dietary';

type Navigation = NativeStackNavigationProp<AuthStackParamList, 'DietaryPreferences'>;

type PreferenceSection = {
  type: DietaryPreferenceType;
  title: string;
  hint: string;
  icon: keyof typeof Ionicons.glyphMap;
  color: string;
  background: string;
  suggestions: string[];
};

const sections: PreferenceSection[] = [
  {
    type: 5,
    title: '过敏食材',
    hint: '会直接排除在推荐之外',
    icon: 'warning-outline',
    color: colors.error,
    background: colors.errorBackground,
    suggestions: ['花生', '虾', '蟹', '牛奶', '鸡蛋'],
  },
  {
    type: 4,
    title: '忌口食材',
    hint: '不希望经常出现在菜单里',
    icon: 'remove-circle-outline',
    color: '#B45309',
    background: '#FFFBEB',
    suggestions: ['香菜', '芹菜', '肥肉', '动物内脏', '辣椒'],
  },
  {
    type: 1,
    title: '口味',
    hint: '帮助推荐更合口味的菜',
    icon: 'sparkles-outline',
    color: colors.primary,
    background: colors.primarySubtle,
    suggestions: ['清淡', '微辣', '酸甜', '咸鲜', '鲜香'],
  },
  {
    type: 2,
    title: '菜系',
    hint: '偏爱的做法和风味方向',
    icon: 'restaurant-outline',
    color: colors.primary,
    background: colors.primarySubtle,
    suggestions: ['家常菜', '粤菜', '川菜', '东北菜', '面食'],
  },
  {
    type: 3,
    title: '饮食习惯',
    hint: '长期有效的饮食要求',
    icon: 'leaf-outline',
    color: colors.success,
    background: '#ECFDF5',
    suggestions: ['少油', '少盐', '高蛋白', '素食', '控糖'],
  },
];

// preferenceValueKey 生成本地标签的稳定键，避免同一分组重复添加。
function preferenceValueKey(type: DietaryPreferenceType, value: string) {
  return `${type}:${value.trim().toLocaleLowerCase()}`;
}

// DietaryPreferencesScreen 提供用户个人饮食偏好的读取、编辑和整体保存。
export default function DietaryPreferencesScreen() {
  const navigation = useNavigation<Navigation>();
  const insets = useSafeAreaInsets();
  const [preferences, setPreferences] = useState<UserDietaryPreference[]>([]);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState('');
  const [dirty, setDirty] = useState(false);
  const [modalType, setModalType] = useState<DietaryPreferenceType | null>(null);
  const [customValue, setCustomValue] = useState('');

  // loadPreferences 从服务端加载用户自己的偏好，页面聚焦时重新同步。
  const loadPreferences = useCallback(async () => {
    setLoading(true);
    setError('');
    try {
      setPreferences(await getDietaryPreferences());
      setDirty(false);
    } catch (requestError: unknown) {
      setError(requestError instanceof Error ? requestError.message : '饮食偏好加载失败');
    } finally {
      setLoading(false);
    }
  }, []);

  useFocusEffect(useCallback(() => {
    loadPreferences();
  }, [loadPreferences]));

  const groupedPreferences = useMemo(() => {
    const grouped = new Map<DietaryPreferenceType, UserDietaryPreference[]>();
    sections.forEach((section) => grouped.set(section.type, []));
    preferences.forEach((preference) => grouped.get(preference.preference_type)?.push(preference));
    return grouped;
  }, [preferences]);

  // toggleSuggestion 在推荐标签和自定义标签间切换，立即反馈本地状态。
  const toggleSuggestion = (type: DietaryPreferenceType, value: string) => {
    const trimmed = value.trim();
    const key = preferenceValueKey(type, trimmed);
    const existing = preferences.find(
      (preference) => preferenceValueKey(preference.preference_type, preference.preference_value) === key,
    );
    if (existing) {
      setPreferences((current) => current.filter((preference) => preference.id !== existing.id));
    } else {
      setPreferences((current) => [...current, {
        id: -Date.now(),
        preference_type: type,
        preference_value: trimmed,
        note: '',
        created_at: '',
        updated_at: '',
      }]);
    }
    setDirty(true);
    setError('');
  };

  // addCustomPreference 添加用户输入的自定义偏好，并拒绝同组重复项。
  const addCustomPreference = () => {
    if (!modalType) return;
    const value = customValue.trim();
    if (!value) return;
    const duplicate = preferences.some(
      (preference) => preferenceValueKey(preference.preference_type, preference.preference_value) === preferenceValueKey(modalType, value),
    );
    if (duplicate) {
      setError('这个偏好已经添加过了');
      return;
    }
    setPreferences((current) => [...current, {
      id: -Date.now(),
      preference_type: modalType,
      preference_value: value,
      note: '',
      created_at: '',
      updated_at: '',
    }]);
    setDirty(true);
    setCustomValue('');
    setModalType(null);
    setError('');
  };

  // removePreference 删除一个已保存或待保存的个人偏好。
  const removePreference = (preference: UserDietaryPreference) => {
    setPreferences((current) => current.filter((item) => item.id !== preference.id));
    setDirty(true);
  };

  // savePreferences 整体提交当前页面状态，后端事务保证不会留下半套偏好。
  const savePreferences = async () => {
    if (saving) return;
    setSaving(true);
    setError('');
    const inputs: UserDietaryPreferenceInput[] = preferences.map((preference) => ({
      preference_type: preference.preference_type,
      preference_value: preference.preference_value,
      note: preference.note,
    }));
    try {
      setPreferences(await replaceDietaryPreferences(inputs));
      setDirty(false);
    } catch (requestError: unknown) {
      setError(requestError instanceof Error ? requestError.message : '保存饮食偏好失败');
    } finally {
      setSaving(false);
    }
  };

  // goBackWithConfirmation 防止用户编辑后直接返回造成未保存内容丢失。
  const goBackWithConfirmation = () => {
    if (!dirty || saving) {
      navigation.goBack();
      return;
    }
    Alert.alert('未保存的偏好', '返回后本次修改不会保留。', [
      { text: '继续编辑', style: 'cancel' },
      { text: '放弃修改', style: 'destructive', onPress: () => navigation.goBack() },
    ]);
  };

  return (
    <View style={[styles.container, { paddingTop: insets.top }]}>
      <View style={styles.header}>
        <TouchableOpacity style={styles.headerButton} onPress={goBackWithConfirmation} accessibilityLabel="返回">
          <Ionicons name="chevron-back" size={24} color={colors.textPrimary} />
        </TouchableOpacity>
        <View style={styles.headerTitleWrap}>
          <Text style={styles.headerTitle}>饮食偏好</Text>
          <Text style={styles.headerSubtitle}>只属于你自己的设置</Text>
        </View>
        <TouchableOpacity
          style={[styles.saveButton, (!dirty || saving) && styles.saveButtonDisabled]}
          onPress={savePreferences}
          disabled={!dirty || saving}
          accessibilityRole="button"
        >
          {saving ? <ActivityIndicator size="small" color={colors.primary} /> : <Text style={styles.saveText}>保存</Text>}
        </TouchableOpacity>
      </View>

      {loading ? (
        <View style={styles.state}><ActivityIndicator color={colors.primary} /><Text style={styles.stateText}>正在读取你的偏好</Text></View>
      ) : (
        <ScrollView contentContainerStyle={styles.content} showsVerticalScrollIndicator={false} keyboardShouldPersistTaps="handled">
          {error ? (
            <View style={styles.errorBanner}>
              <Ionicons name="alert-circle-outline" size={18} color={colors.error} />
              <Text style={styles.errorText}>{error}</Text>
            </View>
          ) : null}

          {sections.map((section) => {
            const selected = groupedPreferences.get(section.type) ?? [];
            return (
              <View key={section.type} style={styles.section}>
                <View style={styles.sectionHeading}>
                  <View style={[styles.sectionIcon, { backgroundColor: section.background }]}>
                    <Ionicons name={section.icon} size={18} color={section.color} />
                  </View>
                  <View style={styles.sectionTitleWrap}>
                    <Text style={styles.sectionTitle}>{section.title}</Text>
                    <Text style={styles.sectionHint}>{section.hint}</Text>
                  </View>
                  <Text style={styles.count}>{selected.length || ''}</Text>
                </View>
                <View style={styles.chipWrap}>
                  {section.suggestions.map((suggestion) => {
                    const active = selected.some((preference) => preference.preference_value.toLocaleLowerCase() === suggestion.toLocaleLowerCase());
                    return (
                      <TouchableOpacity
                        key={suggestion}
                        style={[styles.chip, active && { borderColor: section.color, backgroundColor: section.background }]}
                        onPress={() => toggleSuggestion(section.type, suggestion)}
                        accessibilityRole="checkbox"
                        accessibilityState={{ checked: active }}
                      >
                        {active ? <Ionicons name="checkmark" size={14} color={section.color} /> : null}
                        <Text style={[styles.chipText, active && { color: section.color, fontWeight: '700' }]}>{suggestion}</Text>
                      </TouchableOpacity>
                    );
                  })}
                  {selected.filter((preference) => !section.suggestions.some((suggestion) => suggestion.toLocaleLowerCase() === preference.preference_value.toLocaleLowerCase())).map((preference) => (
                    <TouchableOpacity key={preference.id} style={[styles.chip, styles.customChip, { borderColor: section.color, backgroundColor: section.background }]} onPress={() => removePreference(preference)}>
                      <Text style={[styles.chipText, { color: section.color, fontWeight: '700' }]}>{preference.preference_value}</Text>
                      <Ionicons name="close" size={14} color={section.color} />
                    </TouchableOpacity>
                  ))}
                  <TouchableOpacity style={styles.addChip} onPress={() => setModalType(section.type)} accessibilityLabel={`添加${section.title}`}>
                    <Ionicons name="add" size={16} color={colors.primary} />
                    <Text style={styles.addChipText}>自定义</Text>
                  </TouchableOpacity>
                </View>
              </View>
            );
          })}

          <Text style={styles.footerNote}>你的个人偏好会在加入家庭后帮助生成更合适的家庭菜单。</Text>
        </ScrollView>
      )}

      <Modal visible={modalType !== null} transparent animationType="fade" onRequestClose={() => setModalType(null)}>
        <View style={styles.modalBackdrop}>
          <View style={styles.modalCard}>
            <Text style={styles.modalTitle}>添加自定义偏好</Text>
            <Text style={styles.modalHint}>例如：不吃生食、喜欢云南菜</Text>
            <TextInput
              style={styles.modalInput}
              value={customValue}
              onChangeText={setCustomValue}
              placeholder="输入内容"
              placeholderTextColor={colors.textSecondary}
              autoFocus
              maxLength={100}
              returnKeyType="done"
              onSubmitEditing={addCustomPreference}
            />
            <View style={styles.modalActions}>
              <TouchableOpacity style={styles.modalCancel} onPress={() => { setModalType(null); setCustomValue(''); }}>
                <Text style={styles.modalCancelText}>取消</Text>
              </TouchableOpacity>
              <TouchableOpacity style={styles.modalConfirm} onPress={addCustomPreference}>
                <Text style={styles.modalConfirmText}>添加</Text>
              </TouchableOpacity>
            </View>
          </View>
        </View>
      </Modal>
    </View>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1, backgroundColor: colors.background },
  header: { minHeight: 62, flexDirection: 'row', alignItems: 'center', paddingHorizontal: spacing.md, backgroundColor: colors.surface, borderBottomWidth: StyleSheet.hairlineWidth, borderBottomColor: colors.border },
  headerButton: { width: 42, height: 42, alignItems: 'flex-start', justifyContent: 'center' },
  headerTitleWrap: { flex: 1, alignItems: 'center' },
  headerTitle: { ...typography.h2, color: colors.textPrimary },
  headerSubtitle: { ...typography.caption, color: colors.textSecondary, marginTop: 1 },
  saveButton: { minWidth: 58, height: 36, alignItems: 'center', justifyContent: 'center', borderRadius: radius.md, backgroundColor: colors.primarySubtle },
  saveButtonDisabled: { opacity: 0.45 },
  saveText: { ...typography.caption, color: colors.primary, fontWeight: '700' },
  content: { padding: spacing.lg, paddingBottom: spacing.xxxl },
  errorBanner: { flexDirection: 'row', alignItems: 'center', gap: spacing.sm, backgroundColor: colors.errorBackground, padding: spacing.md, borderRadius: radius.md, marginBottom: spacing.md },
  errorText: { ...typography.caption, color: colors.error, flex: 1 },
  section: { backgroundColor: colors.surface, borderRadius: radius.md, padding: spacing.md, marginBottom: spacing.md, borderWidth: StyleSheet.hairlineWidth, borderColor: colors.border },
  sectionHeading: { flexDirection: 'row', alignItems: 'center', marginBottom: spacing.md },
  sectionIcon: { width: 34, height: 34, borderRadius: radius.sm, alignItems: 'center', justifyContent: 'center', marginRight: spacing.sm },
  sectionTitleWrap: { flex: 1 },
  sectionTitle: { ...typography.body, color: colors.textPrimary, fontWeight: '700' },
  sectionHint: { ...typography.caption, color: colors.textSecondary, marginTop: 1 },
  count: { ...typography.caption, color: colors.textSecondary, minWidth: 16, textAlign: 'right' },
  chipWrap: { flexDirection: 'row', flexWrap: 'wrap', gap: spacing.sm },
  chip: { minHeight: 34, flexDirection: 'row', alignItems: 'center', gap: 4, paddingHorizontal: spacing.md, borderRadius: 17, borderWidth: 1, borderColor: colors.border, backgroundColor: colors.background },
  customChip: { maxWidth: '100%' },
  chipText: { ...typography.caption, color: colors.textPrimary },
  addChip: { minHeight: 34, flexDirection: 'row', alignItems: 'center', gap: 3, paddingHorizontal: spacing.md, borderRadius: 17, borderWidth: 1, borderStyle: 'dashed', borderColor: colors.primary, backgroundColor: colors.surface },
  addChipText: { ...typography.caption, color: colors.primary, fontWeight: '600' },
  footerNote: { ...typography.caption, color: colors.textSecondary, lineHeight: 18, textAlign: 'center', marginTop: spacing.sm },
  state: { flex: 1, alignItems: 'center', justifyContent: 'center', gap: spacing.sm },
  stateText: { ...typography.caption, color: colors.textSecondary },
  modalBackdrop: { flex: 1, justifyContent: 'center', padding: spacing.lg, backgroundColor: 'rgba(17,24,39,0.42)' },
  modalCard: { backgroundColor: colors.surface, borderRadius: radius.lg, padding: spacing.xl },
  modalTitle: { ...typography.h2, color: colors.textPrimary },
  modalHint: { ...typography.caption, color: colors.textSecondary, marginTop: spacing.xs, marginBottom: spacing.lg },
  modalInput: { height: 48, borderWidth: 1, borderColor: colors.borderFocus, borderRadius: radius.md, paddingHorizontal: spacing.md, color: colors.textPrimary, fontSize: 15 },
  modalActions: { flexDirection: 'row', justifyContent: 'flex-end', gap: spacing.sm, marginTop: spacing.lg },
  modalCancel: { minHeight: 40, paddingHorizontal: spacing.lg, alignItems: 'center', justifyContent: 'center' },
  modalCancelText: { ...typography.body, color: colors.textSecondary },
  modalConfirm: { minHeight: 40, paddingHorizontal: spacing.xl, alignItems: 'center', justifyContent: 'center', borderRadius: radius.md, backgroundColor: colors.primary },
  modalConfirmText: { ...typography.body, color: colors.textOnPrimary, fontWeight: '700' },
});
