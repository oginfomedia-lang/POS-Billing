// Zustand store: JWT tokens + logged-in user, with silent auto-refresh on 401.
import axios from 'axios';
import { create } from 'zustand';
import { persist } from 'zustand/middleware';
import { login as apiLogin, refreshToken as apiRefresh } from '../services/api/authApi';
import { httpClient } from '../services/api/httpClient';
import i18n from '../i18n';
import type { UserOut } from '../types/api';

interface AuthState {
  token: string | null;
  refreshToken: string | null;
  user: UserOut | null;
  /** Why the app logged the person out by itself (shown on the login screen), or null. */
  endedReason: string | null;
  login: (username: string, pin: string) => Promise<void>;
  logout: () => void;
  endSession: (reason: string) => void;
  refreshAccessToken: () => Promise<string>;
}

export const useAuthStore = create<AuthState>()(
  persist(
    (set, get) => ({
      token: null,
      refreshToken: null,
      user: null,
      endedReason: null,

      login: async (username, pin) => {
        const data = await apiLogin(username, pin);
        httpClient.defaults.headers.common['Authorization'] = `Bearer ${data.access_token}`;
        set({ token: data.access_token, refreshToken: data.refresh_token, user: data.user, endedReason: null });
      },

      logout: () => {
        delete httpClient.defaults.headers.common['Authorization'];
        set({ token: null, refreshToken: null, user: null });
      },

      endSession: (reason) => {
        delete httpClient.defaults.headers.common['Authorization'];
        set({ token: null, refreshToken: null, user: null, endedReason: reason });
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
        // An admin reset the PIN / changed role or store: say so on the login screen.
        const ended = axios.isAxiosError(refreshErr) && refreshErr.response?.data?.error?.code === 'SESSION_ENDED';
        if (ended) useAuthStore.getState().endSession(i18n.t('login.sessionEnded'));
        else useAuthStore.getState().logout();
        return Promise.reject(refreshErr);
      } finally {
        isRefreshing = false;
      }
    }

    return Promise.reject(error);
  },
);
