import { createContext, createElement, useContext, type ReactNode } from 'react';
import { useQuery, type UseQueryResult } from '@tanstack/react-query';
import { apiClient } from '@/api/client';

export type ProductMeta = {
  app_name: string;
  edition: 'saas';
  version: string;
  desktop_mode: boolean;
  local_mode: boolean;
  build_git_sha: string;
  build_time: string;
  offline_registry_configured?: boolean;
};

const ProductMetaContext = createContext<UseQueryResult<ProductMeta, Error> | null>(null);

/**
 * Mount once near the app root (inside ``QueryClientProvider``) so every
 * ``useProductMeta()`` consumer shares a single ``useQuery`` subscription.
 * Multiple parallel ``useQuery`` calls for the same key have been observed to
 * trigger React 19 ``Should have a queue`` / invalid hook churn in dev.
 */
export function ProductMetaProvider({ children }: { children: ReactNode }) {
  const query = useQuery({
    queryKey: ['product-meta'],
    queryFn: () =>
      apiClient.get<ProductMeta>('/meta', undefined, {
        skipAuth: true,
        timeoutMs: 15_000,
      }),
    staleTime: 60 * 60 * 1000,
    retry: 1,
  });

  return createElement(ProductMetaContext.Provider, { value: query }, children);
}

export function useProductMeta(): UseQueryResult<ProductMeta, Error> {
  const ctx = useContext(ProductMetaContext);
  if (!ctx) {
    throw new Error('useProductMeta must be used within <ProductMetaProvider> (see main.tsx).');
  }
  return ctx;
}
