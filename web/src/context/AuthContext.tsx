import { createContext, useContext, useState, useEffect, useCallback, type ReactNode } from 'react';
import { authAPI } from '../services/auth';
import type { User } from '../types';

interface AuthState {
  user: User | null;
  loading: boolean;
  login: (username: string, password: string) => Promise<void>;
  logout: () => void;
  isLoggedIn: boolean;
}

const AuthContext = createContext<AuthState | null>(null);

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<User | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    const token = localStorage.getItem('medagent_token');
    if (token) {
      authAPI.me()
        .then((res) => setUser(res.data.data))
        .catch(() => { localStorage.removeItem('medagent_token'); })
        .finally(() => setLoading(false));
    } else {
      setLoading(false);
    }
  }, []);

  const login = useCallback(async (username: string, password: string) => {
    const res = await authAPI.login(username, password);
    const { token, user } = res.data.data;
    localStorage.setItem('medagent_token', token);
    setUser(user);
  }, []);

  const logout = useCallback(() => {
    localStorage.removeItem('medagent_token');
    setUser(null);
  }, []);

  return (
    <AuthContext.Provider value={{ user, loading, login, logout, isLoggedIn: !!user }}>
      {children}
    </AuthContext.Provider>
  );
}

export function useAuth(): AuthState {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error('useAuth must be used within AuthProvider');
  return ctx;
}
