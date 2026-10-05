// Zustand store: JWT tokens + logged-in user, with silent auto-refresh on 401.
import { create } from 'zustand';
import { persist } from 'zustand/middleware';
import { login as apiLogin, refreshToken as apiRefresh } from '../services/api/authApi';
import { httpClient } from '../services/api/httpClient';
import type { UserOut } from '../types/api';

interface AuthState {
  token: string | null;
  refreshToken: string | null;
  user: UserOut | null;
  login: (username: string, pin: string) => Promise<void>;
  logout: () => void;
  refreshAccessToken: () => Promise<string>;
}

export const useAuthStore = create<AuthState>()(
  persist(
    (set, get) => ({
      token: null,
      refreshToken: null,
      user: null,

      login: async (username, pin) => {
        const data = await apiLogin(username, pin);
        httpClient.defaults.headers.common['Authorization'] = `Bearer ${data.access_token}`;
        set({ token: data.access_token, refreshToken: data.refresh_token, user: data.user });
      },

      logout: () => {
        delete httpClient.defaults.headers.common['Authorization'];
        set({ token: null, refreshToken: null, user: null });
      },

      refreshAccessToken: async () => {
        const rt = get().refreshToken;
        if (!rt) throw new Error('No refresh token available.');
        const data = await apiRefresh(rt);
        httpClient.defaults.headers.common['Authorization'] = `Bearer ${data.access_token}`;
        set({ token: data.access_token });
        return data.access_token;
      },
    }),
    {
      name: 'pos-auth',
      onRehydrateStorage: () => (state) => {
        if (state?.token) {
          httpClient.defaults.headers.common['Authorization'] = `Bearer ${state.token}`;
        }
      },
    },
  ),
);

// ── 401 auto-refresh interceptor ────────────────────────────────────────────
// Uses a queue so concurrent requests all wait for one refresh, then retry.

type QueueEntry = { resolve: (token: string) => void; reject: (err: unknown) => void };
let isRefreshing = false;
let queue: QueueEntry[] = [];

function flushQueue(err: unknown, token: string | null = null) {
  queue.forEach(({ resolve, reject }) => (err ? reject(err) : resolve(token!)));
  queue = [];
}

httpClient.interceptors.response.use(
  (res) => res,
  async (error) => {
    const original = error.config as typeof error.config & { _retry?: boolean };

    // Only intercept 401s on non-auth endpoints, and only once per request.
    const isAuthEndpoint =
      original.url?.includes('/auth/login') || original.url?.includes('/auth/refresh');

    if (error.response?.status === 401 && !original._retry && !isAuthEndpoint) {
      if (isRefreshing) {
        // Another request is already refreshing — queue this one.
        return new Promise<string>((resolve, reject) => {
          queue.push({ resolve, reject });
        }).then((newToken) => {
          original.headers['Authorization'] = `Bearer ${newToken}`;
          return httpClient(original);
        });
      }

      original._retry = true;
      isRefreshing = true;

      try {
        const newToken = await useAuthStore.getState().refreshAccessToken();
        flushQueue(null, newToken);
        original.headers['Authorization'] = `Bearer ${newToken}`;
        return httpClient(original);
      } catch (refreshErr) {
        flushQueue(refreshErr, null);
        useAuthStore.getState().logout();
        return Promise.reject(refreshErr);
      } finally {
        isRefreshing = false;
      }
    }

    return Promise.reject(error);
  },
);
