import { apiClient } from './client';
import { User } from '../store/authStore';

export interface AuthResponse {
  message?: string;
  user: User;
  tokens: {
    access: string;
    refresh: string;
  };
}

export const authApi = {
  login: async (email: string, password: string): Promise<AuthResponse> => {
    const response = await apiClient.post<AuthResponse>('/auth/login', {
      email,
      password,
    });
    return response.data;
  },

  register: async (
    email: string,
    password: string,
    password2: string,
    role?: 'viewer' | 'editor' | 'admin',
    username?: string
  ): Promise<AuthResponse> => {
    const payload: Record<string, unknown> = {
      email,
      password,
      password2,
    };
    if (role) payload.role = role;
    if (username) payload.username = username;

    const response = await apiClient.post<AuthResponse>('/auth/register', payload);
    return response.data;
  },

  getMe: async (): Promise<User> => {
    const response = await apiClient.get<User>('/auth/me');
    return response.data;
  },
};
