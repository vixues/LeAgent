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

export function mapApiUser(data: Record<string, unknown> | null | undefined): AuthUser {
  const d = data || {};
  const role = String(d.role || 'user');
  const isSuper = Boolean(d.is_superuser) || role === 'admin';
  const username = String(d.username || d.display_name || 'user');
  return {
    id: String(d.id || ''),
    username,
    email: String(d.email || `${username}@localhost`),
    role: isSuper ? 'admin' : role,
    is_superuser: isSuper,
    permissions: Array.isArray(d.permissions) ? (d.permissions as string[]) : isSuper ? ['*'] : [],
    roles: Array.isArray(d.roles) ? (d.roles as string[]) : [isSuper ? 'admin' : role],
    default_workspace_id: (d.default_workspace_id as string | null) ?? null,
    displayName: String(d.display_name || d.displayName || username),
    avatar: (d.avatar as string | null) ?? null,
  };
}

export function isAdminUser(user?: AuthUser | null): boolean {
  if (!user) return false;
  return Boolean(user.is_superuser) || user.role === 'admin' || user.roles.includes('admin');
}

export function userHasPermissions(user: AuthUser | null | undefined, ...keys: string[]): boolean {
  if (!user) return false;
  if (user.permissions.includes('*') || user.is_superuser) return true;
  return keys.every((k) => user.permissions.includes(k) || user.roles.includes(k));
}

export function userHasAnyPermission(user: AuthUser | null | undefined, ...keys: string[]): boolean {
  if (!user) return false;
  if (user.permissions.includes('*') || user.is_superuser) return true;
  return keys.some((k) => user.permissions.includes(k) || user.roles.includes(k));
}
