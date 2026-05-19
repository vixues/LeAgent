import { useMemo } from 'react';

export function useNotifications() {
  return useMemo(
    () => ({
      unreadCount: 0,
      isLoading: false,
      refresh: () => {},
    }),
    []
  );
}
