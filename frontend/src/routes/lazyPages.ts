import { lazy, useEffect, type ComponentType, type LazyExoticComponent } from 'react';
import { lazyImportWithRetry } from '@/lib/lazyImportWithRetry';
import { queryClient } from '@/lib/queryClient';
import { QUERY_KEYS } from '@/controllers/API/helpers/constants';
import { fetchFlow } from '@/pages/WorkflowsPage/fetchFlow';

function lazyPage<T extends ComponentType<unknown>>(
  loader: () => Promise<{ default: T }>
): LazyExoticComponent<T> {
  return lazy(() => lazyImportWithRetry(loader));
}

/**
 * If the current URL is `/workflows/:id` (not `/new` or `/templates`), fire
 * the GET /flows/:id request in parallel with the WorkflowsPage chunk
 * download so the editor finds either a hot cache entry or an
 * already-in-flight promise instead of starting the API call only after the
 * chunk is parsed.
 *
 * Safe to call on every WorkflowsPage import: `prefetchQuery` respects
 * `staleTime` and deduplicates in-flight requests.
 */
function prefetchFlowForCurrentUrl(): void {
  if (typeof window === 'undefined') return;
  const match = window.location.pathname.match(/\/workflows\/([^/?#]+)/);
  const id = match?.[1];
  if (!id || id === 'new' || id === 'templates') return;
  void queryClient.prefetchQuery({
    queryKey: QUERY_KEYS.FLOW(id),
    queryFn: () => fetchFlow(id),
    staleTime: 30_000,
  });
}

/** Dynamic import factories — reused for React.lazy and route prefetch. */
export const loadChatView = () => import('../pages/ChatView');
export const loadHomePage = () => import('../pages/HomePage');
export const loadDashboardPage = () => import('../pages/DashboardPage');
export const loadWorkflowsPage = () => {
  prefetchFlowForCurrentUrl();
  return import('../pages/WorkflowsPage');
};
export const loadExecutionPage = () => import('../pages/ExecutionPage');
export const loadCronPage = () => import('../pages/CronPage');
export const loadTemplatesPage = () => import('../pages/TemplatesPage');
export const loadPlaygroundPage = () => import('../pages/PlaygroundPage');
export const loadKnowledgePage = () => import('../pages/KnowledgePage');
export const loadToolsPage = () => import('../pages/ToolsPage');
export const loadMCPPage = () => import('../pages/MCPPage');
export const loadSkillsPage = () => import('../pages/SkillsPage');
export const loadWebhooksPage = () => import('../pages/WebhooksPage');
export const loadChannelsPage = () => import('../pages/ChannelsPage');
export const loadRulesPage = () => import('../pages/RulesPage');
export const loadAdminPage = () => import('../pages/AdminPage');
export const loadSettingsPage = () => import('../pages/SettingsPage');
export const loadDocsPage = () => import('../pages/DocsPage');
export const loadFolderPage = () => import('../pages/FolderPage');
export const loadTasksPage = () => import('../pages/TasksPage');
export const loadPetSpacePage = () => import('../pages/PetSpacePage');
export const loadCodingProjectsPage = () => import('../pages/CodingProjects');

export const ChatView = lazyPage(loadChatView);
export const HomePage = lazyPage(loadHomePage);
export const DashboardPage = lazyPage(loadDashboardPage);
export const WorkflowsPage = lazyPage(loadWorkflowsPage);
export const ExecutionPage = lazyPage(loadExecutionPage);
export const CronPage = lazyPage(loadCronPage);
export const TemplatesPage = lazyPage(loadTemplatesPage);
export const PlaygroundPage = lazyPage(loadPlaygroundPage);
export const KnowledgePage = lazyPage(loadKnowledgePage);
export const ToolsPage = lazyPage(loadToolsPage);
export const MCPPage = lazyPage(loadMCPPage);
export const SkillsPage = lazyPage(loadSkillsPage);
export const WebhooksPage = lazyPage(loadWebhooksPage);
export const ChannelsPage = lazyPage(loadChannelsPage);
export const RulesPage = lazyPage(loadRulesPage);
export const AdminPage = lazyPage(loadAdminPage);
export const SettingsPage = lazyPage(loadSettingsPage);
export const DocsPage = lazyPage(loadDocsPage);
export const FolderPage = lazyPage(loadFolderPage);
export const TasksPage = lazyPage(loadTasksPage);
export const PetSpacePage = lazyPage(loadPetSpacePage);
export const CodingProjectsPage = lazyPage(loadCodingProjectsPage);

const prefetchByHref: Record<string, () => void> = {
  '/home': () => {
    void loadChatView();
  },
  '/overview': () => {
    void loadHomePage();
  },
  '/dashboard': () => {
    void loadDashboardPage();
  },
  '/workflows': () => {
    void loadWorkflowsPage();
  },
  '/workflows/new': () => {
    void loadWorkflowsPage();
  },
  '/workflows/templates': () => {
    void loadWorkflowsPage();
  },
  '/playground': () => {
    void loadPlaygroundPage();
  },
  '/templates': () => {
    void loadTemplatesPage();
  },
  '/cron': () => {
    void loadCronPage();
  },
  '/knowledge': () => {
    void loadKnowledgePage();
  },
  '/folders': () => {
    void loadFolderPage();
  },
  '/tools': () => {
    void loadToolsPage();
  },
  '/mcp': () => {
    void loadMCPPage();
  },
  '/skills': () => {
    void loadSkillsPage();
  },
  '/rules': () => {
    void loadRulesPage();
  },
  '/webhooks': () => {
    void loadWebhooksPage();
  },
  '/channels': () => {
    void loadChannelsPage();
  },
  '/docs': () => {
    void loadDocsPage();
  },
  '/settings': () => {
    void loadSettingsPage();
  },
  '/admin': () => {
    void loadAdminPage();
  },
  '/tasks': () => {
    void loadTasksPage();
  },
  '/pet-space': () => {
    void loadPetSpacePage();
  },
};

/**
 * Warm the route chunk for a nav href (hover/focus). No-op for unknown paths.
 *
 * Also handles dynamic `/workflows/:id` links by warming the WorkflowsPage chunk
 * and prefetching the flow data so a click feels instant.
 */
export function prefetchRoute(href: string): void {
  const rawPath = href.split('?')[0] ?? href;
  const path = rawPath.replace(/\/$/, '') || '/';
  const run = prefetchByHref[path];
  if (run) {
    run();
    return;
  }
  const flowMatch = path.match(/^\/workflows\/([^/]+)$/);
  if (flowMatch && flowMatch[1] !== 'new' && flowMatch[1] !== 'templates') {
    void loadWorkflowsPage();
    void queryClient.prefetchQuery({
      queryKey: QUERY_KEYS.FLOW(flowMatch[1]!),
      queryFn: () => fetchFlow(flowMatch[1]!),
      staleTime: 30_000,
    });
  }
}

/**
 * Routes we eagerly warm during browser idle time. These are the most
 * commonly-visited destinations right after landing on Home, so prewarming
 * them shaves the first-click chunk fetch (~100–300 ms on slow 4G) down to
 * a cache hit.
 *
 * Keep this list short — prewarming too much will compete with real user
 * work and hurt LCP on cold loads. 4–5 entries is the sweet spot.
 */
const PREWARM_TOP_ROUTES: ReadonlyArray<() => Promise<unknown>> = [
  loadHomePage,
  loadDashboardPage,
  loadWorkflowsPage,
  loadKnowledgePage,
  loadSettingsPage,
];

type RicFn = (cb: () => void, opts?: { timeout?: number }) => number;
type CicFn = (id: number) => void;

/**
 * Hook that, after mount, waits until the browser is idle and then
 * progressively warms the top route chunks. Falls back to a short
 * `setTimeout` on browsers without `requestIdleCallback` (Safari).
 *
 * Safe to call multiple times — chunk loads are memoized by the bundler
 * so re-invoking `load*Page()` is a no-op after the first run.
 */
function isElectronDesktopShell(): boolean {
  return typeof window !== 'undefined' && Boolean(
    (window as Window & { leagentDesktop?: object }).leagentDesktop
  );
}

export function usePrewarmRoutes(): void {
  useEffect(() => {
    if (isElectronDesktopShell()) {
      return;
    }
    const ric = (window as unknown as { requestIdleCallback?: RicFn })
      .requestIdleCallback;
    const cic = (window as unknown as { cancelIdleCallback?: CicFn })
      .cancelIdleCallback;

    const schedule: (cb: () => void) => number = ric
      ? (cb) => ric(cb, { timeout: 2000 })
      : (cb) => window.setTimeout(cb, 1200);
    const cancel: (id: number) => void = cic
      ? (id) => cic(id)
      : (id) => window.clearTimeout(id);

    // Spread the prewarms across separate idle slots so we don't jam a
    // single idle window with five parallel network requests.
    const handles: number[] = PREWARM_TOP_ROUTES.map((load) =>
      schedule(() => {
        void load().catch(() => {
          // prewarming is best-effort — swallow errors (they will surface
          // again if/when the user actually navigates)
        });
      })
    );

    return () => {
      handles.forEach(cancel);
    };
  }, []);
}
