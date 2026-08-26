import axios, { AxiosError, InternalAxiosRequestConfig } from 'axios';
import { useAuthStore } from '../store/authStore';

// Access backend API base URL. Adjust if your Django runs on a different port.
const API_BASE_URL = import.meta.env.VITE_API_URL || 'http://localhost:8000/app';

// --- Toast event bus (no external dependency) ---
export interface ToastEvent {
  type: 'warning' | 'error' | 'success';
  message: string;
}
type ToastListener = (event: ToastEvent) => void;
const toastListeners: ToastListener[] = [];

/** Subscribe to toast events. Returns an unsubscribe function. */
export const onToast = (listener: ToastListener): (() => void) => {
  toastListeners.push(listener);
  return () => {
    const idx = toastListeners.indexOf(listener);
    if (idx > -1) toastListeners.splice(idx, 1);
  };
};

/** Publish a toast event to all current subscribers. */
export const emitToast = (event: ToastEvent): void => {
  toastListeners.forEach((l) => l(event));
};

export const apiClient = axios.create({
  baseURL: API_BASE_URL,
  headers: {
    'Content-Type': 'application/json',
  },
});

// Flag to track token refreshing state
let isRefreshing = false;
let failedQueue: Array<{
  resolve: (value: unknown) => void;
  reject: (error: unknown) => void;
}> = [];

const processQueue = (error: Error | null, token: string | null = null) => {
  failedQueue.forEach((prom) => {
    if (error) {
      prom.reject(error);
    } else {
      prom.resolve(token);
    }
  });
  failedQueue = [];
};

// Request Interceptor: Attach JWT token to requests
apiClient.interceptors.request.use(
  (config: InternalAxiosRequestConfig) => {
    const token = useAuthStore.getState().accessToken;
    if (token) {
      config.headers.Authorization = `Bearer ${token}`;
    }
    return config;
  },
  (error) => Promise.reject(error)
);

// Response Interceptor: Handle 401 token expiry and refresh
apiClient.interceptors.response.use(
  (response) => response,
  async (error: AxiosError) => {
    const originalRequest = error.config;
    if (!originalRequest) return Promise.reject(error);

    // Handle 429 rate limit - emit toast
    if (error.response?.status === 429) {
      emitToast({ type: 'warning', message: 'Rate limit reached — please wait a moment before retrying.' });
      return Promise.reject(error);
    }

    // Handle 503 service unavailable - propagate for caller to handle
    if (error.response?.status === 503) {
      return Promise.reject(error);
    }

    // If 401 Unauthorized and not already retried
    const isUnauthorized = error.response?.status === 401;
    const isAuthRequest = originalRequest.url?.includes('/auth/login') || originalRequest.url?.includes('/auth/register');

    // Make sure we type-cast originalRequest to keep track of retry count
    const customConfig = originalRequest as InternalAxiosRequestConfig & { _retry?: boolean };

    if (isUnauthorized && !isAuthRequest && !customConfig._retry) {
      if (isRefreshing) {
        // If already refreshing, queue this request
        return new Promise((resolve, reject) => {
          failedQueue.push({ resolve, reject });
        })
          .then((token) => {
            customConfig.headers.Authorization = `Bearer ${token}`;
            return apiClient(customConfig);
          })
          .catch((err) => Promise.reject(err));
      }

      customConfig._retry = true;
      isRefreshing = true;

      const refreshToken = useAuthStore.getState().refreshToken;

      if (!refreshToken) {
        useAuthStore.getState().clearAuth();
        return Promise.reject(error);
      }

      try {
        // Make the token refresh request using a separate clean Axios instance to avoid loops
        const refreshResponse = await axios.post<{ access: string; refresh: string }>(
          `${API_BASE_URL}/auth/token/refresh`,
          { refresh: refreshToken }
        );

        const { access, refresh } = refreshResponse.data;

        // Store new tokens in Zustand (which saves to localStorage)
        useAuthStore.getState().updateTokens(access, refresh);

        // Update headers of original request and process the waiting queue
        apiClient.defaults.headers.common.Authorization = `Bearer ${access}`;
        processQueue(null, access);
        isRefreshing = false;

        customConfig.headers.Authorization = `Bearer ${access}`;
        return apiClient(customConfig);
      } catch (refreshError) {
        processQueue(refreshError as Error, null);
        isRefreshing = false;
        useAuthStore.getState().clearAuth();
        return Promise.reject(refreshError);
      }
    }

    return Promise.reject(error);
  }
);
