import { useEffect } from 'react';
import { StatusBar } from 'expo-status-bar';
import { NavigationContainer } from '@react-navigation/native';
import { SafeAreaProvider } from 'react-native-safe-area-context';
import { UserProvider, useUser } from './src/contexts/UserContext';
import AppNavigator from './src/navigation/AppNavigator';
import { navigationRef, resetToLogin } from './src/navigation/navigationRef';
import { setAuthFailureHandler } from './src/services/api';

function AuthFailureBridge() {
  const { clearUser } = useUser();
  useEffect(() => {
    setAuthFailureHandler(() => {
      clearUser();
      resetToLogin();
    });
    return () => setAuthFailureHandler(null);
  }, [clearUser]);
  return null;
}

export default function App() {
  return (
    <SafeAreaProvider>
      <UserProvider>
        <AuthFailureBridge />
        <NavigationContainer ref={navigationRef}>
          <StatusBar style="dark" />
          <AppNavigator />
        </NavigationContainer>
      </UserProvider>
    </SafeAreaProvider>
  );
}
