import React, { useEffect, useState } from 'react';
import { createNativeStackNavigator } from '@react-navigation/native-stack';
import { createBottomTabNavigator } from '@react-navigation/bottom-tabs';
import { Ionicons } from '@expo/vector-icons';
import { getAccessToken } from '../services/api';
import { getProfile } from '../services/auth';
import { useUser } from '../contexts/UserContext';
import { colors } from '../theme';
import type { AuthStackParamList, MainTabParamList } from '../types/auth';

import LoginScreen from '../screens/LoginScreen';
import RegisterScreen from '../screens/RegisterScreen';
import HomeScreen from '../screens/HomeScreen';
import RecipeScreen from '../screens/RecipeScreen';
import RecipeDetailScreen from '../screens/RecipeDetailScreen';
import CookingModeScreen from '../screens/CookingModeScreen';
import ProfileScreen from '../screens/ProfileScreen';
import ProfileDetailScreen from '../screens/ProfileDetailScreen';
import DietaryPreferencesScreen from '../screens/DietaryPreferencesScreen';
import FamilyDietaryProfileScreen from '../screens/FamilyDietaryProfileScreen';
import FamilyManagementScreen from '../screens/FamilyManagementScreen';
import CreateFamilyScreen from '../screens/CreateFamilyScreen';
import EditFamilyScreen from '../screens/EditFamilyScreen';
import JoinFamilyScreen from '../screens/JoinFamilyScreen';
import FamilyMemberEditScreen from '../screens/FamilyMemberEditScreen';
import FamilyMealPlanScreen from '../screens/FamilyMealPlanScreen';
import ShoppingListScreen from '../screens/ShoppingListScreen';
import PersonalKnowledgeScreen from '../screens/PersonalKnowledgeScreen';

const Stack = createNativeStackNavigator<AuthStackParamList>();
const Tab = createBottomTabNavigator<MainTabParamList>();

function MainTabs() {
  return (
    <Tab.Navigator
      screenOptions={{
        headerShown: false,
        tabBarActiveTintColor: colors.primary,
        tabBarInactiveTintColor: colors.textSecondary,
        tabBarStyle: {
          backgroundColor: colors.surface,
          borderTopColor: colors.border,
          borderTopWidth: 0.5,
          paddingTop: 4,
          paddingBottom: 4,
          height: 56,
        },
        tabBarLabelStyle: {
          fontSize: 11,
          fontWeight: '600',
        },
      }}
    >
      <Tab.Screen
        name="HomeTab"
        component={HomeScreen}
        options={{
          tabBarLabel: '首页',
          tabBarIcon: ({ color, size }) => (
            <Ionicons name="home-outline" size={size} color={color} />
          ),
        }}
      />
      <Tab.Screen
        name="Recipes"
        component={RecipeScreen}
        options={{
          tabBarLabel: '菜谱',
          tabBarIcon: ({ color, size }) => (
            <Ionicons name="book-outline" size={size} color={color} />
          ),
        }}
      />
      <Tab.Screen
        name="Profile"
        component={ProfileScreen}
        options={{
          tabBarLabel: '我的',
          tabBarIcon: ({ color, size }) => (
            <Ionicons name="person-outline" size={size} color={color} />
          ),
        }}
      />
    </Tab.Navigator>
  );
}

export default function AppNavigator() {
  const [initialRoute, setInitialRoute] =
    useState<keyof AuthStackParamList>('Login');
  const [isLoading, setIsLoading] = useState(true);
  const { setUser, setFamilyName } = useUser();

  useEffect(() => {
    (async () => {
      const token = await getAccessToken();
      if (!token) {
        setInitialRoute('Login');
        setIsLoading(false);
        return;
      }

      // 有 token，尝试从服务端拉取最新用户数据
      try {
        const profile = await getProfile();
        if (profile.user) {
          setUser(profile.user);
          setFamilyName(profile.family_name ?? '');
        }
      } catch {
        // 刷新失败会清空凭证，此时必须回到登录页。
        if (!(await getAccessToken())) {
          setInitialRoute('Login');
          setIsLoading(false);
          return;
        }
      }

      setInitialRoute('Main');
      setIsLoading(false);
    })();
  }, []);

  if (isLoading) return null;

  return (
    <Stack.Navigator
      initialRouteName={initialRoute}
      screenOptions={{ headerShown: false, animation: 'fade' }}
    >
      <Stack.Screen name="Login" component={LoginScreen} />
      <Stack.Screen name="Register" component={RegisterScreen} />
      <Stack.Screen name="Main" component={MainTabs} />
      <Stack.Screen
        name="RecipeDetail"
        component={RecipeDetailScreen}
        options={{ animation: 'slide_from_right' }}
      />
      <Stack.Screen
        name="CookingMode"
        component={CookingModeScreen}
        options={{ animation: 'slide_from_bottom' }}
      />
      <Stack.Screen
        name="FamilyMealPlan"
        component={FamilyMealPlanScreen}
        options={{ animation: 'slide_from_right' }}
      />
      <Stack.Screen
        name="ShoppingList"
        component={ShoppingListScreen}
        options={{ animation: 'slide_from_right' }}
      />
      <Stack.Screen
        name="ProfileDetail"
        component={ProfileDetailScreen}
        options={{ animation: 'slide_from_right' }}
      />
      <Stack.Screen
        name="DietaryPreferences"
        component={DietaryPreferencesScreen}
        options={{ animation: 'slide_from_right' }}
      />
      <Stack.Screen
        name="FamilyDietaryProfile"
        component={FamilyDietaryProfileScreen}
        options={{ animation: 'slide_from_right' }}
      />
      <Stack.Screen
        name="FamilyManagement"
        component={FamilyManagementScreen}
        options={{ animation: 'slide_from_right' }}
      />
      <Stack.Screen
        name="CreateFamily"
        component={CreateFamilyScreen}
        options={{ animation: 'slide_from_right' }}
      />
      <Stack.Screen
        name="EditFamily"
        component={EditFamilyScreen}
        options={{ animation: 'slide_from_right' }}
      />
      <Stack.Screen
        name="JoinFamily"
        component={JoinFamilyScreen}
        options={{ animation: 'slide_from_right' }}
      />
      <Stack.Screen
        name="FamilyMemberEdit"
        component={FamilyMemberEditScreen}
        options={{ animation: 'slide_from_right' }}
      />
      <Stack.Screen name="PersonalKnowledge" component={PersonalKnowledgeScreen} options={{ animation: 'slide_from_right' }} />
    </Stack.Navigator>
  );
}
