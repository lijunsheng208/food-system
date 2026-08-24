import React, { useCallback, useMemo, useState } from 'react';
import {
  ActivityIndicator,
  KeyboardAvoidingView,
  Modal,
  Platform,
  ScrollView,
  StyleSheet,
  Text,
  TouchableOpacity,
  View,
} from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import { useFocusEffect, useNavigation, useRoute } from '@react-navigation/native';
import type { NativeStackNavigationProp } from '@react-navigation/native-stack';
import type { RouteProp } from '@react-navigation/native';
import { useSafeAreaInsets } from 'react-native-safe-area-context';
import { useUser } from '../contexts/UserContext';
import {
  addManualShoppingItem,
  deleteShoppingItem,
  generateShoppingList,
  getMyFamily,
  getShoppingList,
  updateShoppingItemPurchased,
} from '../services/family';
import type { AuthStackParamList } from '../types/auth';
import type { ShoppingItemInfo, ShoppingListInfo } from '../types/family';
import { colors, radius, spacing, typography } from '../theme';
import TextInput from '../components/TextInput';

type Navigation = NativeStackNavigationProp<AuthStackParamList>;

// formatDate 将本地日期格式化为后端使用的日期字符串。
function formatDate(date: Date) {
  const year = date.getFullYear();
  const month = String(date.getMonth() + 1).padStart(2, '0');
  const day = String(date.getDate()).padStart(2, '0');
  return `${year}-${month}-${day}`;
}

// startOfWeek 返回以周一为起点的日期，作为默认购物范围。
function startOfWeek(date: Date) {
  const result = new Date(date);
  const offset = result.getDay() === 0 ? -6 : 1 - result.getDay();
  result.setDate(result.getDate() + offset);
  result.setHours(0, 0, 0, 0);
  return result;
}

// rangeLabel 将日期范围转换为便于用户扫描的中文标题。
function rangeLabel(list: ShoppingListInfo | null, start: Date, end: Date) {
  if (list) return `${list.start_date.slice(5)} - ${list.end_date.slice(5)}`;
  return `${formatDate(start).slice(5)} - ${formatDate(end).slice(5)}`;
}

// itemAmount 格式化数值和文本用量，避免显示无意义的小数尾零。
function itemAmount(item: ShoppingItemInfo) {
  if (item.quantity_text) return item.quantity_text;
  if (item.quantity == null) return '';
  return Number.isInteger(item.quantity) ? String(item.quantity) : String(item.quantity).replace(/0+$/, '').replace(/\.$/, '');
}

// itemRemainingAmount 计算数值食材尚未购买的数量。
function itemRemainingAmount(item: ShoppingItemInfo) {
  if (item.quantity == null) return '';
  const remaining = Math.max(0, item.quantity - (item.purchased_quantity || 0));
  return Number.isInteger(remaining) ? String(remaining) : String(remaining).replace(/0+$/, '').replace(/\.$/, '');
}

// ShoppingListScreen 提供家庭购物清单的生成、勾选、添加和删除操作。
export default function ShoppingListScreen() {
  const navigation = useNavigation<Navigation>();
  const route = useRoute<RouteProp<AuthStackParamList, 'ShoppingList'>>();
  const insets = useSafeAreaInsets();
  const { user } = useUser();
  const [familyID, setFamilyID] = useState<number | null>(null);
  const [list, setList] = useState<ShoppingListInfo | null>(null);
  const [items, setItems] = useState<ShoppingItemInfo[]>([]);
  const [weekStart, setWeekStart] = useState(startOfWeek(new Date()));
  const [loading, setLoading] = useState(true);
  const [generating, setGenerating] = useState(false);
  const [error, setError] = useState('');
  const [modalVisible, setModalVisible] = useState(false);
  const [ingredientName, setIngredientName] = useState('');
  const [quantity, setQuantity] = useState('');
  const [quantityText, setQuantityText] = useState('');
  const [unit, setUnit] = useState('');
  const [savingItem, setSavingItem] = useState(false);
  const [formError, setFormError] = useState('');

  const weekEnd = useMemo(() => {
    const result = new Date(weekStart);
    result.setDate(result.getDate() + 6);
    return result;
  }, [weekStart]);

  const loadList = useCallback(async (listID: number) => {
    const result = await getShoppingList(listID);
    setList(result.list);
    setItems(result.items);
  }, []);

  const load = useCallback(async () => {
    if (!user) return;
    setLoading(true);
    setError('');
    try {
      const family = await getMyFamily();
      if (!family) {
        setFamilyID(null);
        setList(null);
        setItems([]);
        setError('请先创建或加入家庭，再生成购物清单');
        return;
      }
      setFamilyID(family.id);
      if (route.params?.listId) {
        await loadList(route.params.listId);
      } else {
        // 进入页面时同步当前周菜单，确保刚新增的菜品立即进入清单。
        const result = await generateShoppingList({
          family_id: family.id,
          start_date: formatDate(weekStart),
          end_date: formatDate(weekEnd),
        });
        setList(result.list);
        setItems(result.items);
      }
    } catch (e: any) {
      setError(e?.message || '购物清单加载失败');
    } finally {
      setLoading(false);
    }
  }, [loadList, route.params?.listId, user, weekStart, weekEnd]);

  useFocusEffect(useCallback(() => { load(); }, [load]));

  const purchasedCount = items.filter((item) => item.is_purchased).length;
  const progress = items.length ? purchasedCount / items.length : 0;
  const pendingItems = items.filter((item) => item.quantity != null ? (item.purchased_quantity || 0) < item.quantity : !item.is_purchased);
  const purchasedItems = items.filter((item) => item.quantity != null ? (item.purchased_quantity || 0) > 0 : item.is_purchased);

  // generate 当前日期范围内重新生成一份购物清单。
  const generate = async () => {
    if (!familyID) return;
    setGenerating(true);
    setError('');
    try {
      const result = await generateShoppingList({
        family_id: familyID,
        start_date: formatDate(weekStart),
        end_date: formatDate(weekEnd),
      });
      setList(result.list);
      setItems(result.items);
    } catch (e: any) {
      setError(e?.message || '生成购物清单失败');
    } finally {
      setGenerating(false);
    }
  };

  // shiftWeek 切换购物清单的默认日期范围。
  const shiftWeek = (amount: number) => {
    const next = new Date(weekStart);
    next.setDate(next.getDate() + amount * 7);
    setWeekStart(next);
    setList(null);
    setItems([]);
  };

  // toggleItem 乐观更新勾选状态，失败时恢复提交前的完整列表。
  const toggleItem = async (item: ShoppingItemInfo) => {
    const previousItems = items;
    const hasNumericQuantity = item.quantity != null;
    const nextValue = !item.is_purchased;
    const nextQuantity = hasNumericQuantity ? (nextValue ? item.quantity! : 0) : 0;
    setItems((current) => current.map((value) => value.id === item.id ? { ...value, purchased_quantity: nextQuantity, is_purchased: nextValue } : value));
    try {
      await updateShoppingItemPurchased(item.id, nextQuantity, nextValue);
    } catch (e: any) {
      setItems(previousItems);
      setError(e?.message || '更新购买状态失败');
    }
  };

  // resetPurchasedItem 清空食材的已购买数量，使其完整回到待购买状态。
  const resetPurchasedItem = async (item: ShoppingItemInfo) => {
    const previousItems = items;
    setItems((current) => current.map((value) => value.id === item.id ? { ...value, purchased_quantity: 0, is_purchased: false } : value));
    try {
      await updateShoppingItemPurchased(item.id, 0, false);
    } catch (e: any) {
      setItems(previousItems);
      setError(e?.message || '取消购买失败');
    }
  };

  // submitManualItem 校验并保存手动添加的购物项目。
  const submitManualItem = async () => {
    if (!list) return;
    const trimmedName = ingredientName.trim();
    if (!trimmedName) {
      setFormError('请输入食材名称');
      return;
    }
    const parsedQuantity = quantity.trim() ? Number(quantity) : undefined;
    if (parsedQuantity !== undefined && (!Number.isFinite(parsedQuantity) || parsedQuantity < 0)) {
      setFormError('数量请输入非负数字');
      return;
    }
    if (parsedQuantity === undefined && !quantityText.trim()) {
      setFormError('请输入数量或文字用量');
      return;
    }
    setSavingItem(true);
    setFormError('');
    try {
      const item = await addManualShoppingItem({
        shopping_list_id: list.id,
        ingredient_name: trimmedName,
        quantity: parsedQuantity,
        quantity_text: quantityText.trim(),
        unit: unit.trim(),
      });
      setItems((current) => [...current, item]);
      setIngredientName('');
      setQuantity('');
      setQuantityText('');
      setUnit('');
      setModalVisible(false);
    } catch (e: any) {
      setFormError(e?.message || '添加购物项目失败');
    } finally {
      setSavingItem(false);
    }
  };

  // removeItem 删除项目并从当前列表移除。
  const removeItem = async (item: ShoppingItemInfo) => {
    try {
      await deleteShoppingItem(item.id);
      setItems((current) => current.filter((value) => value.id !== item.id));
    } catch (e: any) {
      setError(e?.message || '删除购物项目失败');
    }
  };

  // renderItem 渲染单个食材行，未购买项目优先呈现操作控件。
  const renderItem = (item: ShoppingItemInfo, completed = false) => (
    <View key={item.id} style={[styles.itemRow, completed && styles.itemRowCompleted]}>
      <TouchableOpacity
        style={styles.checkButton}
        onPress={() => completed ? resetPurchasedItem(item) : toggleItem(item)}
        accessibilityRole="checkbox"
        accessibilityState={{ checked: completed || item.is_purchased }}
        accessibilityLabel={`${item.ingredient_name}，${completed || item.is_purchased ? '已有购买记录' : '未购买'}`}
      >
        <Ionicons name={completed || item.is_purchased ? 'checkmark-circle' : 'ellipse-outline'} size={25} color={completed || item.is_purchased ? colors.success : colors.border} />
      </TouchableOpacity>
      <View style={styles.itemCopy}>
        <Text style={[styles.itemName, completed && styles.itemNameCompleted]}>{item.ingredient_name}</Text>
        <Text style={styles.itemAmount}>{item.quantity != null ? (completed ? `已买 ${item.purchased_quantity || 0} ${item.unit}` : `还需 ${itemRemainingAmount(item)} ${item.unit}`) : `${itemAmount(item)} ${item.unit}`}</Text>
      </View>
      <TouchableOpacity
        style={styles.deleteButton}
        onPress={() => completed ? resetPurchasedItem(item) : removeItem(item)}
        accessibilityLabel={completed ? `取消购买${item.ingredient_name}` : `删除${item.ingredient_name}`}
      >
        <Ionicons name={completed ? 'arrow-undo-outline' : 'trash-outline'} size={18} color={colors.textSecondary} />
      </TouchableOpacity>
    </View>
  );

  return (
    <View style={[styles.container, { paddingTop: insets.top }]}> 
      <View style={styles.header}>
        <TouchableOpacity style={styles.iconButton} onPress={() => navigation.goBack()} accessibilityLabel="返回">
          <Ionicons name="chevron-back" size={22} color={colors.textPrimary} />
        </TouchableOpacity>
        <View style={styles.headerCopy}>
          <Text style={styles.title}>购物清单</Text>
          <Text style={styles.subtitle}>{rangeLabel(list, weekStart, weekEnd)}</Text>
        </View>
        <TouchableOpacity style={styles.iconButton} onPress={load} accessibilityLabel="刷新">
          <Ionicons name="refresh-outline" size={20} color={colors.primary} />
        </TouchableOpacity>
      </View>

      {loading ? (
        <View style={styles.state}><ActivityIndicator color={colors.primary} /><Text style={styles.stateText}>正在整理清单</Text></View>
      ) : error && !familyID ? (
        <View style={styles.state}><Ionicons name="basket-outline" size={34} color={colors.textSecondary} /><Text style={styles.stateText}>{error}</Text></View>
      ) : (
        <ScrollView contentContainerStyle={[styles.content, { paddingBottom: insets.bottom + spacing.xxxl }]}>
          <View style={styles.rangePanel}>
            <View style={styles.rangeTop}>
              <View><Text style={styles.eyebrow}>本周备餐</Text><Text style={styles.rangeTitle}>{rangeLabel(list, weekStart, weekEnd)}</Text></View>
              <TouchableOpacity style={styles.generateButton} onPress={generate} disabled={generating || !familyID}>
                {generating ? <ActivityIndicator size="small" color={colors.textOnPrimary} /> : <Ionicons name="sparkles-outline" size={16} color={colors.textOnPrimary} />}
                <Text style={styles.generateText}>{generating ? '生成中' : list ? '重新生成' : '生成清单'}</Text>
              </TouchableOpacity>
            </View>
            <View style={styles.weekControls}>
              <TouchableOpacity style={styles.weekButton} onPress={() => shiftWeek(-1)} accessibilityLabel="上一周"><Ionicons name="chevron-back" size={17} color={colors.primary} /></TouchableOpacity>
              <Text style={styles.weekHint}>按菜单汇总食材</Text>
              <TouchableOpacity style={styles.weekButton} onPress={() => shiftWeek(1)} accessibilityLabel="下一周"><Ionicons name="chevron-forward" size={17} color={colors.primary} /></TouchableOpacity>
            </View>
          </View>

          {error ? <View style={styles.inlineError}><Ionicons name="alert-circle-outline" size={17} color={colors.error} /><Text style={styles.inlineErrorText}>{error}</Text></View> : null}

          {!list ? (
            <View style={styles.emptyState}>
              <View style={styles.emptyIcon}><Ionicons name="basket-outline" size={30} color={colors.primary} /></View>
              <Text style={styles.emptyTitle}>这周还没有清单</Text>
              <Text style={styles.emptyDescription}>从家庭菜单汇总食材，买菜时逐项勾选。</Text>
            </View>
          ) : (
            <>
              <View style={styles.progressPanel}>
                <View style={styles.progressHeader}><Text style={styles.progressLabel}>采购进度</Text><Text style={styles.progressValue}>{purchasedCount}/{items.length} 已购买</Text></View>
                <View style={styles.progressTrack}><View style={[styles.progressFill, { width: `${progress * 100}%` }]} /></View>
              </View>
              <View style={styles.sectionHeader}><Text style={styles.sectionTitle}>待购买</Text><Text style={styles.sectionCount}>{pendingItems.length} 项</Text></View>
              <View style={styles.itemList}>
                {pendingItems.length ? pendingItems.map((item) => renderItem(item)) : <View style={styles.doneState}><Ionicons name="checkmark-circle" size={23} color={colors.success} /><Text style={styles.doneText}>采购清单已完成</Text></View>}
              </View>
              <TouchableOpacity style={styles.addItemButton} onPress={() => { setFormError(''); setModalVisible(true); }}><Ionicons name="add" size={19} color={colors.primary} /><Text style={styles.addItemText}>手动添加食材</Text></TouchableOpacity>
              {purchasedItems.length ? <><View style={[styles.sectionHeader, styles.completedHeader]}><Text style={styles.sectionTitle}>已购买</Text><Text style={styles.sectionCount}>{purchasedItems.length} 项</Text></View><View style={styles.itemList}>{purchasedItems.map((item) => renderItem(item, true))}</View></> : null}
            </>
          )}
        </ScrollView>
      )}

      <Modal transparent visible={modalVisible} animationType="slide" onRequestClose={() => setModalVisible(false)}>
        <KeyboardAvoidingView style={styles.modalShade} behavior={Platform.OS === 'ios' ? 'padding' : undefined}>
          <View style={[styles.sheet, { paddingBottom: Math.max(insets.bottom, spacing.lg) }]}>
            <View style={styles.sheetHandle} />
            <View style={styles.sheetHeading}><View><Text style={styles.sheetTitle}>添加食材</Text><Text style={styles.sheetSubtitle}>补充菜单之外的采购项</Text></View><TouchableOpacity onPress={() => setModalVisible(false)} accessibilityLabel="关闭"><Ionicons name="close" size={22} color={colors.textSecondary} /></TouchableOpacity></View>
            <TextInput label="食材名称" value={ingredientName} onChangeText={setIngredientName} placeholder="例如：牛奶" autoFocus />
            <View style={styles.formRow}><TextInput containerStyle={styles.quantityField} label="数量" value={quantity} onChangeText={setQuantity} placeholder="2" keyboardType="decimal-pad" /><TextInput containerStyle={styles.unitField} label="单位" value={unit} onChangeText={setUnit} placeholder="盒" /></View>
            <TextInput label="文字用量（可选）" value={quantityText} onChangeText={setQuantityText} placeholder="例如：适量、少许" />
            {formError ? <Text style={styles.formError}>{formError}</Text> : null}
            <TouchableOpacity style={styles.saveButton} onPress={submitManualItem} disabled={savingItem}>{savingItem ? <ActivityIndicator color={colors.textOnPrimary} /> : <Text style={styles.saveText}>加入清单</Text>}</TouchableOpacity>
          </View>
        </KeyboardAvoidingView>
      </Modal>
    </View>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1, backgroundColor: colors.background },
  header: { height: 60, flexDirection: 'row', alignItems: 'center', paddingHorizontal: spacing.md, backgroundColor: colors.surface, borderBottomWidth: StyleSheet.hairlineWidth, borderBottomColor: colors.border },
  iconButton: { width: 40, height: 40, alignItems: 'center', justifyContent: 'center' },
  headerCopy: { flex: 1, alignItems: 'center' },
  title: { ...typography.h2, color: colors.textPrimary },
  subtitle: { ...typography.caption, color: colors.textSecondary, fontSize: 11 },
  content: { padding: spacing.lg, gap: spacing.lg },
  rangePanel: { backgroundColor: colors.primary, borderRadius: radius.lg, padding: spacing.lg },
  rangeTop: { flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between' },
  eyebrow: { ...typography.caption, color: '#BFD5FF', fontSize: 11 },
  rangeTitle: { fontSize: 22, lineHeight: 30, fontWeight: '700', color: colors.textOnPrimary, marginTop: 2 },
  generateButton: { minHeight: 38, flexDirection: 'row', alignItems: 'center', gap: spacing.xs, paddingHorizontal: spacing.md, borderRadius: radius.md, backgroundColor: colors.primaryDark },
  generateText: { fontSize: 12, fontWeight: '700', color: colors.textOnPrimary },
  weekControls: { flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', marginTop: spacing.lg, paddingTop: spacing.md, borderTopWidth: StyleSheet.hairlineWidth, borderTopColor: 'rgba(255,255,255,0.28)' },
  weekButton: { width: 30, height: 28, borderRadius: radius.sm, backgroundColor: '#DCE8FF', alignItems: 'center', justifyContent: 'center' },
  weekHint: { fontSize: 11, color: '#DCE8FF' },
  progressPanel: { backgroundColor: colors.surface, borderRadius: radius.md, padding: spacing.lg, borderWidth: StyleSheet.hairlineWidth, borderColor: colors.border },
  progressHeader: { flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center' },
  progressLabel: { fontSize: 13, fontWeight: '700', color: colors.textPrimary },
  progressValue: { fontSize: 12, color: colors.textSecondary },
  progressTrack: { height: 8, borderRadius: 4, backgroundColor: colors.primarySubtle, overflow: 'hidden', marginTop: spacing.md },
  progressFill: { height: '100%', borderRadius: 4, backgroundColor: colors.success },
  sectionHeader: { flexDirection: 'row', alignItems: 'baseline', justifyContent: 'space-between', paddingHorizontal: spacing.xs },
  completedHeader: { marginTop: spacing.sm },
  sectionTitle: { fontSize: 16, fontWeight: '700', color: colors.textPrimary },
  sectionCount: { fontSize: 12, color: colors.textSecondary },
  itemList: { backgroundColor: colors.surface, borderRadius: radius.md, borderWidth: StyleSheet.hairlineWidth, borderColor: colors.border, overflow: 'hidden' },
  itemRow: { minHeight: 62, flexDirection: 'row', alignItems: 'center', paddingHorizontal: spacing.md, borderBottomWidth: StyleSheet.hairlineWidth, borderBottomColor: colors.border },
  itemRowCompleted: { backgroundColor: '#FAFAFB' },
  checkButton: { width: 34, height: 44, alignItems: 'flex-start', justifyContent: 'center' },
  itemCopy: { flex: 1, minWidth: 0 },
  itemName: { fontSize: 14, lineHeight: 20, fontWeight: '600', color: colors.textPrimary },
  itemNameCompleted: { color: colors.textSecondary, textDecorationLine: 'line-through' },
  itemAmount: { fontSize: 12, lineHeight: 18, color: colors.textSecondary, marginTop: 1 },
  deleteButton: { width: 34, height: 44, alignItems: 'flex-end', justifyContent: 'center' },
  addItemButton: { height: 46, flexDirection: 'row', alignItems: 'center', justifyContent: 'center', gap: spacing.xs, borderWidth: 1, borderStyle: 'dashed', borderColor: colors.primary, borderRadius: radius.md, backgroundColor: colors.primarySubtle },
  addItemText: { fontSize: 13, fontWeight: '700', color: colors.primary },
  doneState: { minHeight: 66, flexDirection: 'row', alignItems: 'center', justifyContent: 'center', gap: spacing.sm },
  doneText: { fontSize: 13, color: colors.success, fontWeight: '600' },
  emptyState: { alignItems: 'center', paddingVertical: spacing.huge, paddingHorizontal: spacing.xxl },
  emptyIcon: { width: 64, height: 64, borderRadius: 32, backgroundColor: colors.primarySubtle, alignItems: 'center', justifyContent: 'center' },
  emptyTitle: { fontSize: 17, fontWeight: '700', color: colors.textPrimary, marginTop: spacing.lg },
  emptyDescription: { fontSize: 13, lineHeight: 20, color: colors.textSecondary, textAlign: 'center', marginTop: spacing.sm },
  inlineError: { flexDirection: 'row', alignItems: 'center', gap: spacing.sm, padding: spacing.md, borderRadius: radius.md, backgroundColor: colors.errorBackground },
  inlineErrorText: { flex: 1, fontSize: 12, color: colors.error },
  state: { flex: 1, alignItems: 'center', justifyContent: 'center', padding: spacing.xxxl, gap: spacing.md },
  stateText: { fontSize: 13, color: colors.textSecondary, textAlign: 'center' },
  modalShade: { flex: 1, justifyContent: 'flex-end', backgroundColor: 'rgba(17,24,39,0.42)' },
  sheet: { backgroundColor: colors.surface, borderTopLeftRadius: radius.xl, borderTopRightRadius: radius.xl, paddingHorizontal: spacing.lg, paddingTop: spacing.sm },
  sheetHandle: { width: 36, height: 4, borderRadius: 2, backgroundColor: colors.border, alignSelf: 'center', marginBottom: spacing.md },
  sheetHeading: { flexDirection: 'row', justifyContent: 'space-between', alignItems: 'flex-start', marginBottom: spacing.lg },
  sheetTitle: { fontSize: 18, fontWeight: '700', color: colors.textPrimary },
  sheetSubtitle: { fontSize: 12, color: colors.textSecondary, marginTop: 2 },
  formRow: { flexDirection: 'row', gap: spacing.md },
  quantityField: { flex: 1 },
  unitField: { flex: 1 },
  formError: { fontSize: 12, color: colors.error, marginBottom: spacing.md },
  saveButton: { height: 46, borderRadius: radius.md, alignItems: 'center', justifyContent: 'center', backgroundColor: colors.primary, marginTop: spacing.sm },
  saveText: { fontSize: 14, fontWeight: '700', color: colors.textOnPrimary },
});
