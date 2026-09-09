import { createContext, useContext, useState, useEffect, useCallback, type ReactNode } from 'react';
import { authAPI } from '../services/auth';
import type { User } from '../types';

interface AuthState {
  user: User | null;
  loading: boolean;
  /** 启动自检（/me）因 429 限流/网络抖动最终失败——token 未失效，给重试而非踢登录页 */
  bootFailed: boolean;
  login: (username: string, password: string) => Promise<void>;
  logout: () => void;
  retry: () => void;
  isLoggedIn: boolean;
}

const AuthContext = createContext<AuthState | null>(null);

/** StrictMode 下 mount effect 双跑守卫（retry() 直接调 boot 不经此标记） */
let bootStarted = false;

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<User | null>(null);
  const [loading, setLoading] = useState(true);
  const [bootFailed, setBootFailed] = useState(false);

  /** 启动自检：读 token → GET /me。401=token 失效清掉；429/网络抖动退避重试 3 次，
   * 仍败则置 bootFailed（保留 token，RequireAuth 出重试页）——修复「高频操作后刷新
   *  被 429 误踢登录页」（2026-08-24 只保住了 token 没保住路由）。 */
  const boot = useCallback(async (attempt: number): Promise<void> => {
    const token = localStorage.getItem('medagent_token');
    if (!token) {
      setLoading(false);
      return;
    }
    try {
      const res = await authAPI.me();
      setUser(res.data.data);
      setBootFailed(false);
    } catch (err) {
      const status = (err as { response?: { status?: number } })?.response?.status;
      if (status === 401) {
        localStorage.removeItem('medagent_token'); // interceptor 已清理并跳登录
      } else if (attempt < 3) {
        await new Promise((r) => setTimeout(r, 1500 * (attempt + 1)));
        return boot(attempt + 1);
      } else {
        setBootFailed(true);
      }
    }
    setLoading(false);
  }, []);

  useEffect(() => {
    if (bootStarted) return;
    bootStarted = true;
    void boot(0);
  }, [boot]);

  const retry = useCallback(() => {
    setLoading(true);
    setBootFailed(false);
    void boot(0);
  }, [boot]);

  const login = useCallback(async (username: string, password: string) => {
    const res = await authAPI.login(username, password);
    const { token, user } = res.data.data;
    localStorage.setItem('medagent_token', token);
    setUser(user);
    setBootFailed(false);
  }, []);

  const logout = useCallback(() => {
    localStorage.removeItem('medagent_token');
    setUser(null);
    setBootFailed(false);
  }, []);

  return (
    <AuthContext.Provider
      value={{ user, loading, bootFailed, login, logout, retry, isLoggedIn: !!user }}
    >
      {children}
    </AuthContext.Provider>
  );
}

export function useAuth(): AuthState {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error('useAuth must be used within AuthProvider');
  return ctx;
}
