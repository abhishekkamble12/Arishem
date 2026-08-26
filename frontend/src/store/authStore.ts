import { create } from 'zustand';
import { workspaceApi, type Workspace } from '../api/workspace';

export type { Workspace } from '../api/workspace';

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
  workspaces: Workspace[];
  setAuth: (user: User, accessToken: string, refreshToken: string) => void;
  clearAuth: () => void;
  updateAccessToken: (accessToken: string) => void;
  updateTokens: (accessToken: string, refreshToken: string) => void;
  setLoading: (isLoading: boolean) => void;
  setActiveWorkspaceId: (id: number | null) => void;
  refreshWorkspaces: () => Promise<void>;
}

export const useAuthStore = create<AuthState>((set, get) => {
  // Read initial credentials from localStorage
  const storedUser = localStorage.getItem('user');
  const storedAccess = localStorage.getItem('accessToken');
  const storedRefresh = localStorage.getItem('refreshToken');
  const storedActiveWs = localStorage.getItem('activeWorkspaceId');
  const storedWorkspaces = localStorage.getItem('workspaces');

  let user: User | null = null;
  let workspaces: Workspace[] = [];

  if (storedUser) {
    try {
      user = JSON.parse(storedUser);
    } catch (e) {
      console.error('Failed to parse stored user', e);
    }
  }

  // Initialize workspaces from localStorage or user.workspaces
  if (storedWorkspaces) {
    try {
      workspaces = JSON.parse(storedWorkspaces);
    } catch (e) {
      console.error('Failed to parse stored workspaces', e);
      workspaces = user?.workspaces || [];
    }
  } else {
    workspaces = user?.workspaces || [];
  }

  const activeWorkspaceId = storedActiveWs
    ? parseInt(storedActiveWs, 10)
    : (workspaces[0]?.id || null);

  return {
    user,
    accessToken: storedAccess,
    refreshToken: storedRefresh,
    isAuthenticated: !!storedAccess,
    isLoading: false,
    activeWorkspaceId,
    workspaces,

    setAuth: (user: User, accessToken: string, refreshToken: string) => {
      localStorage.setItem('user', JSON.stringify(user));
      localStorage.setItem('accessToken', accessToken);
      localStorage.setItem('refreshToken', refreshToken);

      const userWorkspaces = user.workspaces || [];
      localStorage.setItem('workspaces', JSON.stringify(userWorkspaces));

      const workspaceId = userWorkspaces[0]?.id || null;
      if (workspaceId !== null) {
        localStorage.setItem('activeWorkspaceId', workspaceId.toString());
      } else {
        localStorage.removeItem('activeWorkspaceId');
      }

      set({
        user,
        accessToken,
        refreshToken,
        isAuthenticated: true,
        activeWorkspaceId: workspaceId,
        workspaces: userWorkspaces
      });
    },

    clearAuth: () => {
      localStorage.removeItem('user');
      localStorage.removeItem('accessToken');
      localStorage.removeItem('refreshToken');
      localStorage.removeItem('activeWorkspaceId');
      localStorage.removeItem('workspaces');
      set({ user: null, accessToken: null, refreshToken: null, isAuthenticated: false, activeWorkspaceId: null, workspaces: [] });
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

    refreshWorkspaces: async () => {
      try {
        const fresh = await workspaceApi.listWorkspaces();
        localStorage.setItem('workspaces', JSON.stringify(fresh));

        const currentActiveId = get().activeWorkspaceId;
        const isValid = fresh.some(ws => ws.id === currentActiveId);

        if (!isValid && fresh.length > 0) {
          localStorage.setItem('activeWorkspaceId', fresh[0].id.toString());
          set({ workspaces: fresh, activeWorkspaceId: fresh[0].id });
        } else {
          set({ workspaces: fresh });
        }
      } catch (error) {
        console.error('Failed to refresh workspaces:', error);
      }
    },
  };
});
