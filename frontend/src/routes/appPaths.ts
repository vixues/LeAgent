/**
 * Canonical URL paths for the SPA. Keep aligned with `src/App.tsx` `<Routes>`.
 */

/**
 * App shell paths. Each path must have a matching `<Route>`.
 * Dynamic segments use placeholders only in tests.
 */
export const PROTECTED_STATIC_PATHS = [
  '/home',
  '/overview',
  '/dashboard',
  '/workflows',
  '/workflows/new',
  '/templates',
  '/cron',
  '/playground',
  '/knowledge',
  '/folders',
  '/tools',
  '/mcp',
  '/skills',
  '/rules',
  '/webhooks',
  '/channels',
  '/settings',
  '/docs',
  '/admin',
  '/chat',
  '/pet-space',
] as const;

/** Example paths for param routes (must render page shell, not app 404) */
export const PROTECTED_DYNAMIC_EXAMPLES = [
  '/workflows/00000000-0000-4000-8000-000000000001',
  '/workflows/00000000-0000-4000-8000-000000000001/executions',
  '/executions/00000000-0000-4000-8000-000000000001',
  '/chat/00000000-0000-4000-8000-000000000001',
] as const;
