import { create } from 'zustand';

export interface User {
  id: number;
  email: string;
  username: string;
  role: 'admin' | 'editor' | 'viewer';
  date_joined: string;
  is_active: boolean;
}

interface AuthState {
  user: User | null;
  accessToken: string | null;
  refreshToken: string | null;
  isAuthenticated: boolean;
  isLoading: boolean;
  setAuth: (user: User, accessToken: string, refreshToken: string) => void;
  clearAuth: () => void;
  updateAccessToken: (accessToken: string) => void;
  updateTokens: (accessToken: string, refreshToken: string) => void;
  setLoading: (isLoading: boolean) => void;
}

export const useAuthStore = create<AuthState>((set) => {
  // Read initial credentials from localStorage
  const storedUser = localStorage.getItem('user');
  const storedAccess = localStorage.getItem('accessToken');
  const storedRefresh = localStorage.getItem('refreshToken');

  let user: User | null = null;
  if (storedUser) {
    try {
      user = JSON.parse(storedUser);
    } catch (e) {
      console.error('Failed to parse stored user', e);
    }
  }

  return {
    user,
    accessToken: storedAccess,
    refreshToken: storedRefresh,
    isAuthenticated: !!storedAccess,
    isLoading: false,

    setAuth: (user: User, accessToken: string, refreshToken: string) => {
      localStorage.setItem('user', JSON.stringify(user));
      localStorage.setItem('accessToken', accessToken);
      localStorage.setItem('refreshToken', refreshToken);
      set({ user, accessToken, refreshToken, isAuthenticated: true });
    },

    clearAuth: () => {
      localStorage.removeItem('user');
      localStorage.removeItem('accessToken');
      localStorage.removeItem('refreshToken');
      set({ user: null, accessToken: null, refreshToken: null, isAuthenticated: false });
    },

    updateAccessToken: (accessToken: string) => {
      localStorage.setItem('accessToken', accessToken);
      set({ accessToken, isAuthenticated: true });
    },

    updateTokens: (accessToken: string, refreshToken: string) => {
      localStorage.setItem('accessToken', accessToken);
      localStorage.setItem('refreshToken', refreshToken);
      set({ accessToken, refreshToken, isAuthenticated: true });
    },

    setLoading: (isLoading: boolean) => set({ isLoading }),
  };
});
