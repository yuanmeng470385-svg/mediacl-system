/**
 * 认证上下文 - 全局登录状态管理
 */
import React, {
  createContext,
  useContext,
  useState,
  useEffect,
  useCallback,
  type ReactNode,
} from 'react';
import { authAPI } from '../api/auth';
import { apiClient, APIError } from '../api/client';
import type { User } from '../types';

interface AuthState {
  user: User | null;
  token: string | null;
  isLoading: boolean;
  isLoggedIn: boolean;
  /** 深链分身激活 token：未登录收到 medagent-doctor://twin/:token 时暂存，登录成功后消费 */
  pendingToken: string | null;
  setPendingToken: (token: string | null) => void;
  login: (phone: string, code: string) => Promise<void>;
  loginByPassword: (username: string, password: string) => Promise<void>;
  /** 医生自助注册（验证码制）：注册即登录 */
  register: (payload: {
    phone: string;
    code: string;
    full_name: string;
    password?: string;
    hospital?: string;
    department?: string;
    title?: string;
  }) => Promise<void>;
  logout: () => Promise<void>;
  refreshProfile: () => Promise<void>;
}

const AuthContext = createContext<AuthState | null>(null);

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<User | null>(null);
  const [token, setToken] = useState<string | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [pendingToken, setPendingToken] = useState<string | null>(null);

  // 启动时检查登录态
  useEffect(() => {
    checkAuth();
  }, []);

  // token 失效（任意请求 401）：client 层已清 token，这里同步清 UI 状态。
  // authAPI.logout 只清本地存储不发请求 → 不会递归触发 401
  useEffect(() => {
    apiClient.setOnUnauthorized(() => {
      authAPI.logout().then(() => {
        setUser(null);
        setToken(null);
      });
    });
    return () => apiClient.setOnUnauthorized(null);
  }, []);

  const checkAuth = async () => {
    try {
      const loggedIn = await authAPI.isLoggedIn();
      if (loggedIn) {
        // 先用本地缓存的用户兜底：启动瞬间的网络抖动不把已登录用户踢出
        const cachedUser = await authAPI.getCachedUser();
        if (cachedUser) setUser(cachedUser);
        setToken(await authAPI.getToken());
        try {
          // 再尝试用真实 profile 校验 token
          const profile = await authAPI.getProfile();
          setUser(profile);
          await authAPI.cacheUser(profile);
        } catch (err) {
          // 仅 HTTP 401（token 过期/无效，网关返回 2000/2001/2002）才清除登录态；
          // 网络错误（APIError.status 为空）保留 token + 缓存用户，避免一次网络抖动就 logout
          if (err instanceof APIError && err.status === 401) {
            await authAPI.logout();
          }
        }
      }
    } finally {
      setIsLoading(false);
    }
  };

  const login = useCallback(async (phone: string, code: string) => {
    const result = await authAPI.login(phone, code);
    setUser(result.user);
    setToken(result.token);
  }, []);

  const loginByPassword = useCallback(async (username: string, password: string) => {
    const result = await authAPI.loginByPassword(username, password);
    setUser(result.user);
    setToken(result.token);
  }, []);

  const register = useCallback(async (payload: Parameters<typeof authAPI.register>[0]) => {
    const result = await authAPI.register(payload);
    setUser(result.user);
    setToken(result.token);
  }, []);

  const logout = useCallback(async () => {
    await authAPI.logout();
    setUser(null);
    setToken(null);
  }, []);

  const refreshProfile = useCallback(async () => {
    try {
      const profile = await authAPI.getProfile();
      setUser(profile);
    } catch {
      // 静默失败
    }
  }, []);

  return (
    <AuthContext.Provider
      value={{
        user,
        token,
        isLoading,
        isLoggedIn: !!token && !!user,
        pendingToken,
        setPendingToken,
        login,
        loginByPassword,
        register,
        logout,
        refreshProfile,
      }}
    >
      {children}
    </AuthContext.Provider>
  );
}

export function useAuth(): AuthState {
  const ctx = useContext(AuthContext);
  if (!ctx) {
    throw new Error('useAuth must be used within AuthProvider');
  }
  return ctx;
}
