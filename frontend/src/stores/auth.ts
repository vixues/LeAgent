import { create } from 'zustand';
import type { AuthUser } from '@/lib/authUser';

interface AuthState {
  user: AuthUser;
  token: string | null;
  isAuthenticated: boolean;
  isHydratingAuth: boolean;
  login: () => Promise<void>;
  register: () => Promise<void>;
  logout: () => void;
  bootstrapSession: () => Promise<void>;
  updateProfile: () => Promise<void>;
}

const LOCAL_USER: AuthUser = {
  id: '00000000-0000-0000-0000-000000000001',
  username: 'local',
  displayName: 'Local User',
  email: 'local@localhost',
  role: 'admin',
  is_superuser: true,
  permissions: [],
  roles: ['admin'],
  default_workspace_id: null,
};

export const useAuthStore = create<AuthState>()(() => ({
  user: LOCAL_USER,
  token: null,
  isAuthenticated: true,
  isHydratingAuth: false,
  login: async () => {},
  register: async () => {},
  logout: () => {},
  bootstrapSession: async () => {},
  updateProfile: async () => {},
}));
