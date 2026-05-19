export function usePermissions() {
  return {
    hasPermission: () => true,
    can: () => true,
    canAny: () => true,
    hasRole: () => true,
    isSuperuser: true,
    permissions: [] as string[],
    roles: ['admin'] as string[],
    user: null,
  };
}

export default usePermissions;
