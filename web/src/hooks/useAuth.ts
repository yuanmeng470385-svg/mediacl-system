import { useState, useEffect, useCallback } from 'react';
import { authAPI } from '../services/auth';
import type { User } from '../types';

export function useAuth() {
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

  return { user, loading, login, logout, isLoggedIn: !!user };
}
