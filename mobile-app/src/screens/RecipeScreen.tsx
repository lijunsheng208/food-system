import React, { useEffect, useState, useCallback, useRef } from 'react';
import {
  View,
  Text,
  StyleSheet,
  FlatList,
  TouchableOpacity,
  ActivityIndicator,
  TextInput,
} from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import { useSafeAreaInsets } from 'react-native-safe-area-context';
import { useNavigation } from '@react-navigation/native';
import type { NativeStackNavigationProp } from '@react-navigation/native-stack';
import { colors, typography, spacing, radius, shadow } from '../theme';
import {
  fetchCategories,
  fetchDishesByCategory,
  searchDishes,
} from '../services/dish';
import type { CategoryInfo, DishInfo } from '../services/dish';
import type { AuthStackParamList } from '../types/auth';

const SIDEBAR_WIDTH = 80;

const THUMB_SIZE = 56;

/** 缩略图占位底色轮换 */
const PLACEHOLDER_PALETTE = [
  '#DBEAFE', '#E0E7FF', '#D1FAE5',
  '#FEF3C7', '#FEE2E2', '#EDE9FE',
];

export default function RecipeScreen() {
  const insets = useSafeAreaInsets();
  const navigation =
    useNavigation<NativeStackNavigationProp<AuthStackParamList>>();

  // 分类
  const [categories, setCategories] = useState<CategoryInfo[]>([]);
  const [selectedId, setSelectedId] = useState<number | null>(null);
  const [categoriesLoading, setCategoriesLoading] = useState(true);

  // 菜谱
  const [dishes, setDishes] = useState<DishInfo[]>([]);
  const [dishesLoading, setDishesLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // 搜索
  const [searchQuery, setSearchQuery] = useState('');
  const [searchResults, setSearchResults] = useState<DishInfo[]>([]);
  const [searchLoading, setSearchLoading] = useState(false);
  const debounceRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  const isSearching = searchQuery.trim().length > 0;

  // 搜索菜谱（带 300ms 防抖）
  const doSearch = useCallback((keyword: string) => {
    if (debounceRef.current) clearTimeout(debounceRef.current);
    debounceRef.current = setTimeout(async () => {
      const trimmed = keyword.trim();
      if (trimmed.length === 0) {
        setSearchResults([]);
        setSearchLoading(false);
        return;
      }
      setSearchLoading(true);
      try {
        const list = await searchDishes(trimmed);
        setSearchResults(list);
      } catch {
        setSearchResults([]);
      } finally {
        setSearchLoading(false);
      }
    }, 300);
  }, []);

  const handleSearchChange = (text: string) => {
    setSearchQuery(text);
    doSearch(text);
  };

  const handleClearSearch = () => {
    setSearchQuery('');
    setSearchResults([]);
    setSearchLoading(false);
    if (debounceRef.current) clearTimeout(debounceRef.current);
  };

  // 初始加载分类
  useEffect(() => {
    (async () => {
      try {
        const cats = await fetchCategories();
        setCategories(cats);
        if (cats.length > 0) {
          setSelectedId(cats[0].id);
        }
      } catch (e: any) {
        setError(e.message || '加载分类失败');
      } finally {
        setCategoriesLoading(false);
      }
    })();
  }, []);

  // 选中分类后加载菜谱
  useEffect(() => {
    if (selectedId === null) return;
    (async () => {
      setDishesLoading(true);
      setError(null);
      try {
        const list = await fetchDishesByCategory(selectedId);
        setDishes(list);
      } catch (e: any) {
        setError(e.message || '加载菜谱失败');
        setDishes([]);
      } finally {
        setDishesLoading(false);
      }
    })();
  }, [selectedId]);

  const handleSelectCategory = useCallback((id: number) => {
    setSelectedId(id);
  }, []);

  // ---- 渲染：分类侧边栏项 ----
  const renderCategory = ({ item }: { item: CategoryInfo }) => {
    const isActive = item.id === selectedId;
    return (
      <TouchableOpacity
        style={[styles.categoryItem, isActive && styles.categoryItemActive]}
        onPress={() => handleSelectCategory(item.id)}
        activeOpacity={0.6}
      >
        {/* 激活指示条 */}
        {isActive && <View style={styles.activeIndicator} />}
        <Text
          style={[
            styles.categoryText,
            isActive && styles.categoryTextActive,
          ]}
          numberOfLines={2}
        >
          {item.name}
        </Text>
      </TouchableOpacity>
    );
  };

  // ---- 渲染：菜谱列表行 ----
  const renderDish = ({ item, index }: { item: DishInfo; index: number }) => {
    const bg = PLACEHOLDER_PALETTE[index % PLACEHOLDER_PALETTE.length];
    return (
      <TouchableOpacity
        style={styles.dishRow}
        onPress={() =>
          navigation.navigate('RecipeDetail', {
            dishId: item.id,
            dishName: item.name,
          })
        }
        activeOpacity={0.72}
        accessibilityRole="button"
        accessibilityLabel={`查看${item.name}菜谱`}
      >
        {/* 缩略图占位 */}
        <View style={[styles.dishThumb, { backgroundColor: bg }]}>
          <Ionicons name="restaurant-outline" size={22} color={colors.primary} />
        </View>
        {/* 菜名 + 描述 */}
        <View style={styles.dishInfo}>
          <Text style={styles.dishName} numberOfLines={1}>
            {item.name}
          </Text>
          {item.description ? (
            <Text style={styles.dishDesc} numberOfLines={2}>
              {item.description}
            </Text>
          ) : null}
        </View>
        {/* 箭头 */}
        <Ionicons
          name="chevron-forward"
          size={16}
          color={colors.textSecondary}
        />
      </TouchableOpacity>
    );
  };

  // ---- 分割线 ----
  const renderSeparator = () => <View style={styles.separator} />;

  // ---- 空状态 ----
  const renderEmptyDishes = () => {
    if (dishesLoading) return null;
    return (
      <View style={styles.emptyContainer}>
        <Ionicons
          name="restaurant-outline"
          size={48}
          color={colors.border}
        />
        <Text style={styles.emptyText}>暂无菜谱</Text>
      </View>
    );
  };

  // ---- 主体 ----
  return (
    <View style={[styles.container, { paddingTop: insets.top }]}>
      {/* 页面标题 */}
      <Text style={styles.pageTitle}>菜谱</Text>

      {/* ====== 搜索栏 ====== */}
      <View style={styles.searchBar}>
        <Ionicons name="search-outline" size={18} color={colors.textSecondary} />
        <TextInput
          style={styles.searchInput}
          placeholder="搜索菜谱…"
          placeholderTextColor={colors.textSecondary}
          value={searchQuery}
          onChangeText={handleSearchChange}
          returnKeyType="search"
          autoCorrect={false}
          clearButtonMode="never"
        />
        {searchQuery.length > 0 && (
          <TouchableOpacity onPress={handleClearSearch} hitSlop={{ top: 8, bottom: 8, left: 8, right: 8 }}>
            <Ionicons name="close-circle" size={18} color={colors.textSecondary} />
          </TouchableOpacity>
        )}
      </View>

      {/* ====== 搜索模式：全宽搜索结果 ====== */}
      {isSearching ? (
        <View style={styles.dishArea}>
          {searchLoading ? (
            <ActivityIndicator color={colors.primary} style={styles.dishLoading} />
          ) : searchResults.length === 0 ? (
            <View style={styles.emptyContainer}>
              <Ionicons name="search-outline" size={48} color={colors.border} />
              <Text style={styles.emptyText}>未找到相关菜谱</Text>
            </View>
          ) : (
            <FlatList
              data={searchResults}
              keyExtractor={(item) => `${item.id}`}
              renderItem={renderDish}
              showsVerticalScrollIndicator={false}
              contentContainerStyle={styles.dishList}
              ItemSeparatorComponent={renderSeparator}
              keyboardShouldPersistTaps="handled"
            />
          )}
        </View>
      ) : (
        /* ====== 正常模式：左侧分类 + 右侧菜谱 ====== */
        <View style={styles.body}>
          {/* 左侧分类侧边栏 */}
          <View style={styles.sidebar}>
            {categoriesLoading ? (
              <ActivityIndicator
                color={colors.primary}
                style={styles.sidebarLoading}
              />
            ) : (
              <FlatList
                data={categories}
                keyExtractor={(item) => `${item.id}`}
                renderItem={renderCategory}
                showsVerticalScrollIndicator={false}
                contentContainerStyle={styles.categoryList}
              />
            )}
          </View>

          {/* 右侧菜谱列表 */}
          <View style={styles.dishArea}>
            {error ? (
              <View style={styles.emptyContainer}>
                <Ionicons
                  name="cloud-offline-outline"
                  size={48}
                  color={colors.border}
                />
                <Text style={styles.emptyText}>{error}</Text>
                <TouchableOpacity
                  style={styles.retryButton}
                  onPress={() => selectedId && handleSelectCategory(selectedId)}
                >
                  <Text style={styles.retryText}>重试</Text>
                </TouchableOpacity>
              </View>
            ) : (
              <FlatList
                data={dishes}
                keyExtractor={(item) => `${item.id}`}
                renderItem={renderDish}
                showsVerticalScrollIndicator={false}
                contentContainerStyle={styles.dishList}
                ItemSeparatorComponent={renderSeparator}
                ListEmptyComponent={renderEmptyDishes}
                ListFooterComponent={
                  dishesLoading ? (
                    <ActivityIndicator
                      color={colors.primary}
                      style={styles.dishLoading}
                    />
                  ) : null
                }
              />
            )}
          </View>
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

  /* 页面标题 */
  pageTitle: {
    ...typography.h1,
    color: colors.textPrimary,
    paddingHorizontal: spacing.lg,
    marginTop: spacing.lg,
    marginBottom: spacing.md,
  },

  /* 搜索栏 */
  searchBar: {
    flexDirection: 'row',
    alignItems: 'center',
    marginHorizontal: spacing.lg,
    marginBottom: spacing.md,
    backgroundColor: colors.surface,
    borderRadius: radius.md,
    paddingHorizontal: spacing.md,
    height: 40,
    borderWidth: 1,
    borderColor: colors.border,
  },
  searchInput: {
    flex: 1,
    marginLeft: spacing.sm,
    fontSize: 15,
    color: colors.textPrimary,
    paddingVertical: 0,
  },

  /* 主体左右分栏 */
  body: {
    flex: 1,
    flexDirection: 'row',
  },

  /* ====== 左侧分类 ====== */
  sidebar: {
    width: SIDEBAR_WIDTH,
    borderRightWidth: StyleSheet.hairlineWidth,
    borderRightColor: colors.border,
    backgroundColor: colors.surface,
  },
  sidebarLoading: {
    marginTop: spacing.xxxl,
  },
  categoryList: {
    paddingVertical: spacing.sm,
  },
  categoryItem: {
    height: 48,
    justifyContent: 'center',
    alignItems: 'center',
    paddingHorizontal: spacing.sm,
    position: 'relative',
    borderRadius: radius.md,
    marginHorizontal: spacing.xs,
    marginVertical: 2,
  },
  categoryItemActive: {
    backgroundColor: colors.primarySubtle,
  },
  activeIndicator: {
    position: 'absolute',
    left: 0,
    top: 10,
    bottom: 10,
    width: 3,
    borderRadius: 2,
    backgroundColor: colors.primary,
  },
  categoryText: {
    ...typography.caption,
    color: colors.textSecondary,
    textAlign: 'center',
  },
  categoryTextActive: {
    color: colors.primary,
    fontWeight: '700',
  },

  /* ====== 右侧菜谱列表 ====== */
  dishArea: {
    flex: 1,
    backgroundColor: colors.background,
  },
  dishList: {
    padding: spacing.md,
    flexGrow: 1,
  },
  dishLoading: {
    marginTop: spacing.xxl,
  },

  /* 列表行 */
  dishRow: {
    flexDirection: 'row',
    alignItems: 'center',
    backgroundColor: colors.surface,
    borderRadius: radius.md,
    padding: spacing.md,
  },
  dishThumb: {
    width: THUMB_SIZE,
    height: THUMB_SIZE,
    borderRadius: radius.md,
    alignItems: 'center',
    justifyContent: 'center',
    marginRight: spacing.md,
  },
  dishInfo: {
    flex: 1,
    marginRight: spacing.sm,
  },
  dishName: {
    fontSize: 15,
    fontWeight: '600',
    color: colors.textPrimary,
    marginBottom: 4,
  },
  dishDesc: {
    ...typography.caption,
    color: colors.textSecondary,
    lineHeight: 18,
  },

  /* 分割线 */
  separator: {
    height: spacing.sm,
  },

  /* 空态 & 错误 */
  emptyContainer: {
    flex: 1,
    justifyContent: 'center',
    alignItems: 'center',
    paddingHorizontal: spacing.xxl,
  },
  emptyText: {
    ...typography.body,
    color: colors.textSecondary,
    marginTop: spacing.md,
    textAlign: 'center',
  },
  retryButton: {
    marginTop: spacing.lg,
    paddingHorizontal: spacing.xxl,
    paddingVertical: spacing.sm,
    borderRadius: radius.md,
    backgroundColor: colors.primary,
  },
  retryText: {
    ...typography.button,
    color: colors.textOnPrimary,
  },
});
