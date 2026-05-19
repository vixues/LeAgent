export interface AuthUser {
  id: string;
  username: string;
  email: string;
  role: string;
  is_superuser: boolean;
  permissions: string[];
  roles: string[];
  default_workspace_id: string | null;
  displayName?: string;
  avatar?: string | null;
}

export function mapApiUser(_data: any): AuthUser {
  return {
    id: '00000000-0000-0000-0000-000000000001',
    username: 'local',
    email: 'local@localhost',
    role: 'admin',
    is_superuser: true,
    permissions: [],
    roles: ['admin'],
    default_workspace_id: null,
    displayName: 'Local User',
  };
}

export function isAdminUser(_user?: AuthUser | null): boolean {
  return true;
}

export function userHasPermissions(_user: AuthUser | null | undefined, ..._keys: string[]): boolean {
  return true;
}

export function userHasAnyPermission(_user: AuthUser | null | undefined, ..._keys: string[]): boolean {
  return true;
}
