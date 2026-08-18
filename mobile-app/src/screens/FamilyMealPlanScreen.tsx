import React, { useCallback, useEffect, useMemo, useState } from 'react';
import {
  ActivityIndicator, Alert, Image, Modal, ScrollView, StyleSheet, Text,
  TouchableOpacity, View,
} from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import { useNavigation, useRoute } from '@react-navigation/native';
import type { RouteProp } from '@react-navigation/native';
import type { NativeStackNavigationProp } from '@react-navigation/native-stack';
import { useSafeAreaInsets } from 'react-native-safe-area-context';
import { useUser } from '../contexts/UserContext';
import { deleteMealPlan, getMyFamily, listFamilyMembers, listMealPlans, updateMealPlan } from '../services/family';
import { resolveDishImageUrl } from '../services/dish';
import type { FamilyMealPlanInfo, FamilyMemberInfo, MealType } from '../types/family';
import { MealTypeLabel } from '../types/family';
import type { AuthStackParamList } from '../types/auth';
import { colors, radius, spacing } from '../theme';

const mealTypes: MealType[] = [1, 2, 3];
const weekdays = ['日', '一', '二', '三', '四', '五', '六'];

function dateKey(date: Date) {
  const y = date.getFullYear();
  const m = String(date.getMonth() + 1).padStart(2, '0');
  const d = String(date.getDate()).padStart(2, '0');
  return `${y}-${m}-${d}`;
}

function parseDate(value?: string) {
  if (!value) return new Date();
  const [y, m, d] = value.split('-').map(Number);
  return new Date(y, m - 1, d);
}

function weekDates(anchor: Date) {
  const mondayOffset = anchor.getDay() === 0 ? -6 : 1 - anchor.getDay();
  const monday = new Date(anchor);
  monday.setDate(anchor.getDate() + mondayOffset);
  return Array.from({ length: 7 }, (_, index) => {
    const value = new Date(monday);
    value.setDate(monday.getDate() + index);
    return value;
  });
}

export default function FamilyMealPlanScreen() {
  const insets = useSafeAreaInsets();
  const navigation = useNavigation<NativeStackNavigationProp<AuthStackParamList>>();
  const route = useRoute<RouteProp<AuthStackParamList, 'FamilyMealPlan'>>();
  const { user } = useUser();
  const [selectedDate, setSelectedDate] = useState(parseDate(route.params?.initialDate));
  const [anchorDate, setAnchorDate] = useState(parseDate(route.params?.initialDate));
  const [plans, setPlans] = useState<FamilyMealPlanInfo[]>([]);
  const [members, setMembers] = useState<FamilyMemberInfo[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [editing, setEditing] = useState<FamilyMealPlanInfo | null>(null);
  const [saving, setSaving] = useState(false);
  const dates = useMemo(() => weekDates(anchorDate), [anchorDate]);

  const load = useCallback(async () => {
    if (!user) return;
    setLoading(true);
    setError('');
    try {
    const family = await getMyFamily();
      if (!family) {
        setError('请先创建或加入家庭，再安排家庭菜单');
        setPlans([]);
        return;
      }
      const [nextPlans, nextMembers] = await Promise.all([
    listMealPlans(family.id, dateKey(dates[0]), dateKey(dates[6])),
    listFamilyMembers(family.id),
      ]);
      setPlans(nextPlans);
      setMembers(nextMembers);
    } catch (e: any) {
      setError(e.message || '家庭菜单加载失败');
    } finally {
      setLoading(false);
    }
  }, [dates, user]);

  useEffect(() => { load(); }, [load]);

  const selectedKey = dateKey(selectedDate);
  const dayPlans = plans.filter((plan) => plan.meal_date === selectedKey);

  const shiftWeek = (amount: number) => {
    const next = new Date(anchorDate);
    next.setDate(next.getDate() + amount * 7);
    setAnchorDate(next);
    setSelectedDate(weekDates(next)[0]);
  };

  const saveEdit = async () => {
    if (!editing || !user) return;
    setSaving(true);
    try {
      await updateMealPlan(editing.id, {
        meal_type: editing.meal_type,
        servings: editing.servings,
        cook_user_id: editing.cook_user_id ?? 0,
      });
      setEditing(null);
      await load();
    } catch (e: any) {
      Alert.alert('修改失败', e.message || '请稍后重试');
    } finally {
      setSaving(false);
    }
  };

  const remove = (plan: FamilyMealPlanInfo) => {
    if (!user) return;
    Alert.alert('移出家庭菜单', `确定移除“${plan.dish_name}”吗？`, [
      { text: '取消', style: 'cancel' },
      { text: '移除', style: 'destructive', onPress: async () => {
        try {
      await deleteMealPlan(plan.id);
          setPlans((current) => current.filter((item) => item.id !== plan.id));
        } catch (e: any) {
          Alert.alert('删除失败', e.message || '请稍后重试');
        }
      } },
    ]);
  };

  return (
    <View style={[styles.container, { paddingTop: insets.top }]}> 
      <View style={styles.header}>
        <TouchableOpacity style={styles.iconButton} onPress={() => navigation.goBack()} accessibilityLabel="返回">
          <Ionicons name="chevron-back" size={22} color={colors.textPrimary} />
        </TouchableOpacity>
        <View style={styles.headerText}><Text style={styles.title}>家庭菜单</Text><Text style={styles.subtitle}>一周用餐安排</Text></View>
        <TouchableOpacity style={styles.iconButton} onPress={load} accessibilityLabel="刷新">
          <Ionicons name="refresh" size={20} color={colors.primary} />
        </TouchableOpacity>
      </View>

      <View style={styles.weekNav}>
        <TouchableOpacity style={styles.weekArrow} onPress={() => shiftWeek(-1)}><Ionicons name="chevron-back" size={18} color={colors.textSecondary} /></TouchableOpacity>
        <Text style={styles.weekLabel}>{dates[0].getMonth() + 1}月{dates[0].getDate()}日 - {dates[6].getMonth() + 1}月{dates[6].getDate()}日</Text>
        <TouchableOpacity style={styles.weekArrow} onPress={() => shiftWeek(1)}><Ionicons name="chevron-forward" size={18} color={colors.textSecondary} /></TouchableOpacity>
      </View>
      <View style={styles.dateRow}>
        {dates.map((date) => {
          const active = dateKey(date) === selectedKey;
          const hasPlan = plans.some((plan) => plan.meal_date === dateKey(date));
          return <TouchableOpacity key={dateKey(date)} style={[styles.dateItem, active && styles.dateItemActive]} onPress={() => setSelectedDate(date)}>
            <Text style={[styles.weekday, active && styles.activeText]}>周{weekdays[date.getDay()]}</Text>
            <Text style={[styles.dayNumber, active && styles.activeText]}>{date.getDate()}</Text>
            <View style={[styles.dot, hasPlan && styles.dotVisible, active && hasPlan && styles.dotActive]} />
          </TouchableOpacity>;
        })}
      </View>

      {loading ? <View style={styles.state}><ActivityIndicator color={colors.primary} /><Text style={styles.stateText}>正在加载菜单</Text></View> :
        error ? <View style={styles.state}><Ionicons name="home-outline" size={32} color={colors.textSecondary} /><Text style={styles.stateText}>{error}</Text><TouchableOpacity style={styles.retry} onPress={load}><Text style={styles.retryText}>重新加载</Text></TouchableOpacity></View> :
        <ScrollView contentContainerStyle={[styles.content, { paddingBottom: insets.bottom + spacing.xxl }]}>
          {mealTypes.map((type) => {
            const items = dayPlans.filter((plan) => plan.meal_type === type);
            return <View key={type} style={styles.mealSection}>
              <View style={styles.mealHeading}><Text style={styles.mealTitle}>{MealTypeLabel[type]}</Text><Text style={styles.mealCount}>{items.length ? `${items.length} 道` : '未安排'}</Text></View>
              {items.length === 0 ? <View style={styles.emptyMeal}><Ionicons name="add-circle-outline" size={18} color={colors.textSecondary} /><Text style={styles.emptyText}>从菜谱详情加入一道菜</Text></View> : items.map((plan) => {
                const imageUrl = resolveDishImageUrl(plan.dish_image_key);
                return <View key={plan.id} style={styles.planRow}>
                  <TouchableOpacity style={styles.planMain} onPress={() => navigation.navigate('RecipeDetail', { dishId: plan.dish_id, dishName: plan.dish_name })}>
                    {imageUrl ? <Image source={{ uri: imageUrl }} style={styles.thumb} /> : <View style={[styles.thumb, styles.thumbEmpty]}><Ionicons name="restaurant-outline" size={20} color={colors.primary} /></View>}
                    <View style={styles.planText}><Text style={styles.dishName} numberOfLines={1}>{plan.dish_name}</Text><Text style={styles.planMeta}>{plan.servings}人份 · {plan.cook_user_name || '待定负责人'}</Text></View>
                  </TouchableOpacity>
                  <TouchableOpacity style={styles.moreButton} onPress={() => setEditing(plan)} accessibilityLabel="修改菜单"><Ionicons name="ellipsis-horizontal" size={20} color={colors.textSecondary} /></TouchableOpacity>
                </View>;
              })}
            </View>;
          })}
        </ScrollView>}

      <Modal transparent visible={Boolean(editing)} animationType="slide" onRequestClose={() => setEditing(null)}>
        <View style={styles.modalShade}><View style={[styles.sheet, { paddingBottom: Math.max(insets.bottom, spacing.lg) }]}>
          <View style={styles.sheetHandle} /><Text style={styles.sheetTitle}>修改菜单安排</Text><Text style={styles.sheetDish}>{editing?.dish_name}</Text>
          <Text style={styles.fieldLabel}>餐次</Text><View style={styles.segmentRow}>{mealTypes.map((type) => <TouchableOpacity key={type} style={[styles.segment, editing?.meal_type === type && styles.segmentActive]} onPress={() => setEditing((p) => p ? { ...p, meal_type: type } : p)}><Text style={[styles.segmentText, editing?.meal_type === type && styles.segmentTextActive]}>{MealTypeLabel[type]}</Text></TouchableOpacity>)}</View>
          <Text style={styles.fieldLabel}>份量</Text><View style={styles.stepper}><TouchableOpacity style={styles.stepperButton} onPress={() => setEditing((p) => p ? { ...p, servings: Math.max(1, p.servings - 1) } : p)}><Ionicons name="remove" size={18} color={colors.primary} /></TouchableOpacity><Text style={styles.stepperValue}>{editing?.servings} 人份</Text><TouchableOpacity style={styles.stepperButton} onPress={() => setEditing((p) => p ? { ...p, servings: Math.min(20, p.servings + 1) } : p)}><Ionicons name="add" size={18} color={colors.primary} /></TouchableOpacity></View>
          <Text style={styles.fieldLabel}>做饭负责人</Text><ScrollView horizontal showsHorizontalScrollIndicator={false} contentContainerStyle={styles.memberRow}><TouchableOpacity style={[styles.memberChip, editing?.cook_user_id == null && styles.memberChipActive]} onPress={() => setEditing((p) => p ? { ...p, cook_user_id: null, cook_user_name: '' } : p)}><Text style={styles.memberChipText}>待定</Text></TouchableOpacity>{members.map((member) => <TouchableOpacity key={member.user_id} style={[styles.memberChip, editing?.cook_user_id === member.user_id && styles.memberChipActive]} onPress={() => setEditing((p) => p ? { ...p, cook_user_id: member.user_id, cook_user_name: member.display_name || member.nickname } : p)}><Text style={styles.memberChipText}>{member.display_name || member.nickname}</Text></TouchableOpacity>)}</ScrollView>
          <View style={styles.sheetActions}><TouchableOpacity style={styles.deleteButton} onPress={() => { const value = editing; setEditing(null); if (value) remove(value); }}><Ionicons name="trash-outline" size={18} color={colors.error} /><Text style={styles.deleteText}>移除</Text></TouchableOpacity><TouchableOpacity style={styles.saveButton} disabled={saving} onPress={saveEdit}>{saving ? <ActivityIndicator size="small" color="#fff" /> : <Text style={styles.saveText}>保存修改</Text>}</TouchableOpacity></View>
        </View></View>
      </Modal>
    </View>
  );
}

const styles = StyleSheet.create({
  container:{flex:1,backgroundColor:'#F5F7FB'}, header:{height:58,flexDirection:'row',alignItems:'center',paddingHorizontal:spacing.md,backgroundColor:colors.surface,borderBottomWidth:StyleSheet.hairlineWidth,borderBottomColor:colors.border}, iconButton:{width:40,height:40,alignItems:'center',justifyContent:'center'}, headerText:{flex:1,alignItems:'center'}, title:{fontSize:18,lineHeight:24,fontWeight:'700',color:colors.textPrimary}, subtitle:{fontSize:10,lineHeight:14,color:colors.textSecondary},
  weekNav:{height:38,flexDirection:'row',alignItems:'center',justifyContent:'center',backgroundColor:colors.surface}, weekArrow:{width:38,height:34,alignItems:'center',justifyContent:'center'}, weekLabel:{fontSize:12,fontWeight:'600',color:colors.textSecondary,minWidth:150,textAlign:'center'}, dateRow:{height:70,flexDirection:'row',paddingHorizontal:spacing.sm,paddingBottom:spacing.sm,backgroundColor:colors.surface}, dateItem:{flex:1,minWidth:0,alignItems:'center',justifyContent:'center',borderRadius:radius.md}, dateItemActive:{backgroundColor:colors.primary}, weekday:{fontSize:10,color:colors.textSecondary}, dayNumber:{fontSize:15,lineHeight:22,fontWeight:'700',color:colors.textPrimary}, activeText:{color:colors.textOnPrimary}, dot:{width:4,height:4,borderRadius:2,marginTop:2}, dotVisible:{backgroundColor:colors.primary}, dotActive:{backgroundColor:colors.textOnPrimary},
  content:{padding:spacing.lg,gap:spacing.lg}, mealSection:{backgroundColor:colors.surface,borderRadius:radius.md,overflow:'hidden',borderWidth:StyleSheet.hairlineWidth,borderColor:colors.border}, mealHeading:{height:42,flexDirection:'row',alignItems:'center',justifyContent:'space-between',paddingHorizontal:spacing.md,backgroundColor:'#F9FAFB'}, mealTitle:{fontSize:14,fontWeight:'700',color:colors.textPrimary}, mealCount:{fontSize:11,color:colors.textSecondary}, emptyMeal:{height:54,flexDirection:'row',alignItems:'center',gap:spacing.sm,paddingHorizontal:spacing.md}, emptyText:{fontSize:12,color:colors.textSecondary}, planRow:{minHeight:66,flexDirection:'row',alignItems:'center',borderTopWidth:StyleSheet.hairlineWidth,borderTopColor:colors.border}, planMain:{flex:1,minWidth:0,flexDirection:'row',alignItems:'center',padding:spacing.sm}, thumb:{width:48,height:48,borderRadius:radius.sm,backgroundColor:colors.primarySubtle}, thumbEmpty:{alignItems:'center',justifyContent:'center'}, planText:{flex:1,minWidth:0,marginLeft:spacing.md}, dishName:{fontSize:14,lineHeight:20,fontWeight:'600',color:colors.textPrimary}, planMeta:{fontSize:11,lineHeight:17,color:colors.textSecondary,marginTop:2}, moreButton:{width:44,height:54,alignItems:'center',justifyContent:'center'},
  state:{flex:1,alignItems:'center',justifyContent:'center',padding:32,gap:spacing.md}, stateText:{fontSize:13,lineHeight:20,color:colors.textSecondary,textAlign:'center'}, retry:{height:34,paddingHorizontal:spacing.lg,borderRadius:radius.md,backgroundColor:colors.primary,justifyContent:'center'}, retryText:{fontSize:12,fontWeight:'600',color:'#fff'},
  modalShade:{flex:1,justifyContent:'flex-end',backgroundColor:'rgba(17,24,39,0.42)'}, sheet:{backgroundColor:colors.surface,borderTopLeftRadius:16,borderTopRightRadius:16,paddingHorizontal:spacing.lg,paddingTop:spacing.sm}, sheetHandle:{width:36,height:4,borderRadius:2,backgroundColor:colors.border,alignSelf:'center',marginBottom:spacing.md}, sheetTitle:{fontSize:17,fontWeight:'700',color:colors.textPrimary}, sheetDish:{fontSize:12,color:colors.textSecondary,marginTop:2}, fieldLabel:{fontSize:12,fontWeight:'600',color:colors.textPrimary,marginTop:spacing.lg,marginBottom:spacing.sm}, segmentRow:{flexDirection:'row',gap:spacing.sm}, segment:{flex:1,height:36,borderRadius:radius.md,borderWidth:1,borderColor:colors.border,alignItems:'center',justifyContent:'center'}, segmentActive:{backgroundColor:colors.primarySubtle,borderColor:colors.primary}, segmentText:{fontSize:12,color:colors.textSecondary}, segmentTextActive:{fontWeight:'700',color:colors.primary}, stepper:{height:38,alignSelf:'flex-start',flexDirection:'row',alignItems:'center',borderWidth:1,borderColor:colors.border,borderRadius:radius.md}, stepperButton:{width:40,height:36,alignItems:'center',justifyContent:'center'}, stepperValue:{width:70,textAlign:'center',fontSize:12,fontWeight:'600',color:colors.textPrimary}, memberRow:{gap:spacing.sm,paddingRight:spacing.lg}, memberChip:{height:34,paddingHorizontal:spacing.md,borderRadius:radius.full,borderWidth:1,borderColor:colors.border,justifyContent:'center'}, memberChipActive:{borderColor:colors.primary,backgroundColor:colors.primarySubtle}, memberChipText:{fontSize:12,color:colors.textPrimary}, sheetActions:{flexDirection:'row',gap:spacing.md,marginTop:spacing.xl}, deleteButton:{height:42,paddingHorizontal:spacing.lg,flexDirection:'row',alignItems:'center',justifyContent:'center',gap:spacing.xs,borderWidth:1,borderColor:'#FCA5A5',borderRadius:radius.md}, deleteText:{fontSize:13,fontWeight:'600',color:colors.error}, saveButton:{flex:1,height:42,borderRadius:radius.md,backgroundColor:colors.primary,alignItems:'center',justifyContent:'center'}, saveText:{fontSize:13,fontWeight:'700',color:'#fff'},
});
