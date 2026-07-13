import { create } from 'zustand';
import type { AuthUser } from '@/lib/authUser';
import { mapApiUser } from '@/lib/authUser';
import { apiClient, clearAuthTokens, getAccessToken, setAuthTokens } from '@/api/client';
import { URL_KEYS } from '@/controllers/API/helpers/constants';

interface AuthStatus {
  enforce_auth: boolean;
  setup_complete: boolean;
  desktop_mode: boolean;
  require_unlock_on_desktop: boolean;
  multi_user: boolean;
}

interface AuthState {
  user: AuthUser | null;
  token: string | null;
  isAuthenticated: boolean;
  isHydratingAuth: boolean;
  authStatus: AuthStatus | null;
  login: (password: string, username?: string) => Promise<void>;
  setup: (password: string, confirmPassword?: string) => Promise<void>;
  register: () => Promise<void>;
  logout: () => void;
  bootstrapSession: () => Promise<void>;
  updateProfile: () => Promise<void>;
}

const TOKEN_KEY = 'leagent_access_token';
const REFRESH_KEY = 'leagent_refresh_token';

function persistTokens(access: string, refresh?: string) {
  try {
    localStorage.setItem(TOKEN_KEY, access);
    if (refresh) localStorage.setItem(REFRESH_KEY, refresh);
  } catch {
    /* ignore */
  }
  setAuthTokens(access, refresh);
}

function loadStoredAccess(): string | null {
  try {
    return localStorage.getItem(TOKEN_KEY);
  } catch {
    return null;
  }
}

function clearStored() {
  try {
    localStorage.removeItem(TOKEN_KEY);
    localStorage.removeItem(REFRESH_KEY);
  } catch {
    /* ignore */
  }
  clearAuthTokens();
}

export const useAuthStore = create<AuthState>((set, get) => ({
  user: null,
  token: null,
  isAuthenticated: false,
  isHydratingAuth: true,
  authStatus: null,

  login: async (password: string, username?: string) => {
    const body: Record<string, string> = { password };
    if (username) body.username = username;
    const res = await apiClient.post<{
      access_token: string;
      refresh_token: string;
      token_type: string;
    }>(URL_KEYS.AUTH_LOGIN, body, { skipAuth: true });
    persistTokens(res.access_token, res.refresh_token);
    const me = await apiClient.get<Record<string, unknown>>(URL_KEYS.AUTH_PROFILE);
    set({
      token: res.access_token,
      user: mapApiUser(me),
      isAuthenticated: true,
    });
  },

  setup: async (password: string, confirmPassword?: string) => {
    const res = await apiClient.post<{
      access_token: string;
      refresh_token: string;
    }>(
      '/auth/setup',
      {
        password,
        confirm_password: confirmPassword ?? password,
      },
      { skipAuth: true },
    );
    persistTokens(res.access_token, res.refresh_token);
    const me = await apiClient.get<Record<string, unknown>>(URL_KEYS.AUTH_PROFILE);
    set({
      token: res.access_token,
      user: mapApiUser(me),
      isAuthenticated: true,
      authStatus: {
        ...(get().authStatus || {
          enforce_auth: true,
          desktop_mode: false,
          require_unlock_on_desktop: false,
          multi_user: true,
        }),
        setup_complete: true,
        enforce_auth: true,
      },
    });
  },

  register: async () => {},

  logout: () => {
    const token = get().token || getAccessToken();
    if (token) {
      void apiClient.post(URL_KEYS.AUTH_LOGOUT, undefined).catch(() => undefined);
    }
    clearStored();
    set({ user: null, token: null, isAuthenticated: false });
  },

  bootstrapSession: async () => {
    set({ isHydratingAuth: true });
    try {
      const status = await apiClient.get<AuthStatus>('/auth/status', undefined, {
        skipAuth: true,
      });
      set({ authStatus: status });

      const stored = loadStoredAccess();
      if (stored) {
        setAuthTokens(stored);
        try {
          const me = await apiClient.get<Record<string, unknown>>(URL_KEYS.AUTH_PROFILE);
          set({
            token: stored,
            user: mapApiUser(me),
            isAuthenticated: true,
          });
          return;
        } catch {
          clearStored();
        }
      }

      if (!status.enforce_auth) {
        // Local / desktop passthrough — optional desktop bootstrap for a real token.
        if (status.desktop_mode) {
          try {
            const res = await apiClient.post<{
              access_token: string;
              refresh_token: string;
            }>('/auth/desktop-bootstrap', undefined, { skipAuth: true });
            persistTokens(res.access_token, res.refresh_token);
            const me = await apiClient.get<Record<string, unknown>>(URL_KEYS.AUTH_PROFILE);
            set({
              token: res.access_token,
              user: mapApiUser(me),
              isAuthenticated: true,
            });
            return;
          } catch {
            /* fall through to anonymous local principal */
          }
        }
        set({
          isAuthenticated: true,
          user: mapApiUser({
            id: '00000000-0000-0000-0000-000000000001',
            username: 'local',
            display_name: 'local',
            role: 'admin',
            is_superuser: true,
            permissions: ['*'],
            roles: ['admin'],
          }),
          token: null,
        });
        return;
      }

      set({ isAuthenticated: false, user: null, token: null });
    } finally {
      set({ isHydratingAuth: false });
    }
  },

  updateProfile: async () => {
    const me = await apiClient.get<Record<string, unknown>>(URL_KEYS.AUTH_PROFILE);
    set({ user: mapApiUser(me) });
  },
}));
