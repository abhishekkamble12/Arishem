import { create } from 'zustand';

export interface Workspace {
  id: number;
  name: string;
  created_at: string;
}

export interface User {
  id: number;
  email: string;
  username: string;
  role: 'admin' | 'editor' | 'viewer';
  workspaces: Workspace[];
  date_joined: string;
  is_active: boolean;
}

interface AuthState {
  user: User | null;
  accessToken: string | null;
  refreshToken: string | null;
  isAuthenticated: boolean;
  isLoading: boolean;
  activeWorkspaceId: number | null;
  setAuth: (user: User, accessToken: string, refreshToken: string) => void;
  clearAuth: () => void;
  updateAccessToken: (accessToken: string) => void;
  updateTokens: (accessToken: string, refreshToken: string) => void;
  setLoading: (isLoading: boolean) => void;
  setActiveWorkspaceId: (id: number | null) => void;
}

export const useAuthStore = create<AuthState>((set) => {
  // Read initial credentials from localStorage
  const storedUser = localStorage.getItem('user');
  const storedAccess = localStorage.getItem('accessToken');
  const storedRefresh = localStorage.getItem('refreshToken');
  const storedActiveWs = localStorage.getItem('activeWorkspaceId');

  let user: User | null = null;
  if (storedUser) {
    try {
      user = JSON.parse(storedUser);
    } catch (e) {
      console.error('Failed to parse stored user', e);
    }
  }

  const activeWorkspaceId = storedActiveWs 
    ? parseInt(storedActiveWs, 10) 
    : (user?.workspaces?.[0]?.id || null);

  return {
    user,
    accessToken: storedAccess,
    refreshToken: storedRefresh,
    isAuthenticated: !!storedAccess,
    isLoading: false,
    activeWorkspaceId,

    setAuth: (user: User, accessToken: string, refreshToken: string) => {
      localStorage.setItem('user', JSON.stringify(user));
      localStorage.setItem('accessToken', accessToken);
      localStorage.setItem('refreshToken', refreshToken);
      
      const workspaceId = user.workspaces?.[0]?.id || null;
      if (workspaceId !== null) {
        localStorage.setItem('activeWorkspaceId', workspaceId.toString());
      } else {
        localStorage.removeItem('activeWorkspaceId');
      }
      
      set({ user, accessToken, refreshToken, isAuthenticated: true, activeWorkspaceId: workspaceId });
    },

    clearAuth: () => {
      localStorage.removeItem('user');
      localStorage.removeItem('accessToken');
      localStorage.removeItem('refreshToken');
      localStorage.removeItem('activeWorkspaceId');
      set({ user: null, accessToken: null, refreshToken: null, isAuthenticated: false, activeWorkspaceId: null });
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

    setActiveWorkspaceId: (id: number | null) => {
      if (id !== null) {
        localStorage.setItem('activeWorkspaceId', id.toString());
      } else {
        localStorage.removeItem('activeWorkspaceId');
      }
      set({ activeWorkspaceId: id });
    },
  };
});
