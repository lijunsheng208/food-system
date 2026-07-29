import React, { createContext, useContext, useState, useCallback } from 'react';
import type { UserInfo } from '../types/auth';

interface UserContextValue {
  user: UserInfo | null;
  familyName: string;
  setUser: (user: UserInfo) => void;
  setFamilyName: (name: string) => void;
  clearUser: () => void;
  isLoggedIn: boolean;
}

const UserContext = createContext<UserContextValue>({
  user: null,
  familyName: '',
  setUser: () => {},
  setFamilyName: () => {},
  clearUser: () => {},
  isLoggedIn: false,
});

export function UserProvider({ children }: { children: React.ReactNode }) {
  const [user, setUserState] = useState<UserInfo | null>(null);
  const [familyName, setFamilyNameState] = useState('');

  const setUser = useCallback((u: UserInfo) => setUserState(u), []);
  const setFamilyName = useCallback((n: string) => setFamilyNameState(n), []);
  const clearUser = useCallback(() => {
    setUserState(null);
    setFamilyNameState('');
  }, []);

  return (
    <UserContext.Provider
      value={{ user, familyName, setUser, setFamilyName, clearUser, isLoggedIn: user !== null }}
    >
      {children}
    </UserContext.Provider>
  );
}

export function useUser() {
  return useContext(UserContext);
}
