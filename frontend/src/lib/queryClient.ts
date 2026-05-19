import { QueryClient, type QueryKey } from '@tanstack/react-query';

/**
 * Shared QueryClient instance. Lives in its own module so non-React code
 * (e.g. route lazy factories) can prefetch into the same cache that
 * `QueryClientProvider` consumes in `main.tsx`.
 */
export const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      staleTime: 1000 * 60 * 5,
      retry: 1,
      refetchOnWindowFocus: false,
    },
  },
});

/**
 * Build a workspace-scoped React Query key.
 *
 * Prevents cache bleed across workspaces: the same `['todos']` key in two
 * different workspaces would otherwise share entries. Wrapping everything in
 * `['ws', workspaceId, ...]` ensures a workspace switch does not surface stale
 * data from the previous tenant.
 *
 * Callers that don't have a workspace yet (e.g. public routes) should fall
 * through to `'none'` so keys remain stable.
 */
export function wsKey(workspaceId: string | null | undefined, key: QueryKey): QueryKey {
  return ['ws', workspaceId ?? 'none', ...(Array.isArray(key) ? key : [key])];
}

/**
 * Clear the entire query cache — typically on logout or a workspace switch
 * so the next render starts cold.
 */
export function clearQueryCache(): void {
  queryClient.clear();
}
