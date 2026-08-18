import { createNavigationContainerRef } from '@react-navigation/native';
import type { AuthStackParamList } from '../types/auth';

export const navigationRef = createNavigationContainerRef<AuthStackParamList>();

export function resetToLogin(): void {
  if (navigationRef.isReady()) {
    navigationRef.resetRoot({ index: 0, routes: [{ name: 'Login' }] });
  }
}
