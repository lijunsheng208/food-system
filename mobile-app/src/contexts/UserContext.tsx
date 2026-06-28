import React, { createContext, useContext, useState, useCallback } from 'react';
import type { UserInfo } from '../types/auth';

interface UserContextValue {
  user: UserInfo | null;
  setUser: (user: UserInfo) => void;
  clearUser: () => void;
  isLoggedIn: boolean;
}

const UserContext = createContext<UserContextValue>({
  user: null,
  setUser: () => {},
  clearUser: () => {},
  isLoggedIn: false,
});

export function UserProvider({ children }: { children: React.ReactNode }) {
  const [user, setUserState] = useState<UserInfo | null>(null);

  const setUser = useCallback((u: UserInfo) => setUserState(u), []);
  const clearUser = useCallback(() => setUserState(null), []);

  return (
    <UserContext.Provider
      value={{ user, setUser, clearUser, isLoggedIn: user !== null }}
    >
      {children}
    </UserContext.Provider>
  );
}

export function useUser() {
  return useContext(UserContext);
}
