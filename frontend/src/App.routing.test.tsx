import type { ReactElement } from 'react';
import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import App from './App';
import { ProductMetaProvider } from '@/hooks/useProductMeta';
import { PROTECTED_DYNAMIC_EXAMPLES, PROTECTED_STATIC_PATHS } from '@/routes/appPaths';

vi.mock('@/hooks/useMobile', () => ({
  useMobile: () => ({
    isMobile: false,
    isTablet: false,
    isDesktop: true,
    isTouchDevice: false,
    isLandscape: true,
    isPortrait: false,
    screenWidth: 1280,
    screenHeight: 800,
    deviceType: 'desktop' as const,
    platform: 'linux' as const,
  }),
  usePrefersReducedMotion: () => false,
}));

const originalFetch = globalThis.fetch;

/** Stub /api/v1 calls so lazy pages settle without real network (avoids hangs + heap growth in Vitest). */
function installApiFetchStub() {
  globalThis.fetch = vi.fn(async (input: RequestInfo | URL) => {
    const url = typeof input === 'string' ? input : input instanceof URL ? input.href : input.url;
    if (!url.includes('/api/')) {
      return new Response('not found', { status: 404 });
    }
    const json = (data: unknown) =>
      new Response(JSON.stringify(data), { status: 200, headers: { 'Content-Type': 'application/json' } });

    if (url.includes('/meta') && !url.includes('/templates')) {
      return json({
        app_name: 'LeAgent',
        edition: 'saas',
        version: '0.0.0-test',
        desktop_mode: false,
        local_mode: false,
        build_git_sha: 'test',
        build_time: '',
        offline_registry_configured: false,
      });
    }

    if (url.includes('/stats/home')) {
      return json({
        totalFlows: 0,
        runningTasks: 0,
        completedToday: 0,
        successRate: 0,
      });
    }
    if (url.includes('/stats/dashboard')) {
      return json({
        tasksToday: 0,
        tasksChange: 0,
        successRate: 0,
        successRateChange: 0,
        failedTasks: 0,
        failedChange: 0,
        avgDuration: '0',
        durationChange: 0,
      });
    }
    if (url.includes('/stats/usage')) {
      return json([]);
    }
    if (url.includes('/activities')) {
      return json([]);
    }
    if (url.includes('/tasks') && !url.match(/\/tasks\/[^/?]+/)) {
      return json({
        items: [],
        total: 0,
        page: 1,
        page_size: 20,
        has_next: false,
        has_prev: false,
      });
    }
    if (url.includes('/workflow/flows/recent')) {
      return json([]);
    }
    if (url.includes('/workflow/flows/executions/')) {
      return json({
        id: '00000000-0000-4000-8000-000000000001',
        status: 'completed',
        trigger_type: 'manual',
        node_count: 0,
        duration_ms: 0,
        created_at: new Date().toISOString(),
        inputs: {},
        outputs: {},
        execution_history: [],
      });
    }
    if (url.match(/\/flows\/[0-9a-f-]+\/executions/i)) {
      return json({ executions: [], total: 0 });
    }
    if (url.match(/\/flows\/[0-9a-f-]+$/i)) {
      return json({
        id: '00000000-0000-4000-8000-000000000001',
        name: 'Test flow',
        nodes: [],
        edges: [],
      });
    }
    if (url.includes('/workflow/flows')) {
      return json({
        items: [],
        total: 0,
        page: 1,
        page_size: 20,
        has_next: false,
        has_prev: false,
      });
    }
    if (url.includes('/templates/categories')) {
      return json({ categories: [] });
    }
    if (url.includes('/templates')) {
      return json({ templates: [], total: 0 });
    }
    if (url.includes('/cron/health')) {
      return json({
        running: true,
        scheduler_running: true,
        instance_id: 'test',
        total_jobs: 0,
        active_jobs: 0,
        paused_jobs: 0,
        failed_jobs: 0,
        running_executions: 0,
        next_runs: [],
      });
    }
    if (url.includes('/cron/stats')) {
      return json({
        total_jobs: 0,
        active_jobs: 0,
        paused_jobs: 0,
        failed_jobs: 0,
        running_executions: 0,
        total_runs_all_jobs: 0,
        scheduler_running: true,
        next_runs: [],
      });
    }
    if (url.includes('/cron/') && url.includes('/next-runs')) {
      return json({ cron_expression: '0 * * * *', next_runs: [] });
    }
    if (url.includes('/cron')) {
      return json({ jobs: [], total: 0 });
    }
    if (url.includes('/pet-space/projects') && url.includes('/files')) {
      return json([]);
    }
    if (url.includes('/pet-space/projects')) {
      return json([]);
    }
    return json([]);
  }) as typeof fetch;
}

function createTestQueryClient() {
  return new QueryClient({
    defaultOptions: {
      queries: { retry: false, gcTime: 0 },
    },
  });
}

function renderWithProviders(ui: ReactElement) {
  const client = createTestQueryClient();
  return render(
    <QueryClientProvider client={client}>
      <ProductMetaProvider>{ui}</ProductMetaProvider>
    </QueryClientProvider>
  );
}

describe('App nested routes', () => {
  beforeEach(() => {
    installApiFetchStub();
  });

  afterEach(() => {
    globalThis.fetch = originalFetch;
  });

  it('renders chat shell on /home', async () => {
    renderWithProviders(
      <MemoryRouter initialEntries={['/home']}>
        <App />
      </MemoryRouter>
    );

    await waitFor(() => {
      expect(document.querySelector('aside')).toBeTruthy();
    });
  });

  /** Smoke: every path in appPaths must render the sidebar (no blank / stuck shell). */
  it('exposes all protected shell paths from appPaths', () => {
    expect(PROTECTED_STATIC_PATHS.length).toBeGreaterThan(10);
    expect(PROTECTED_DYNAMIC_EXAMPLES.length).toBeGreaterThan(0);
  });

  /** No Flow editor routes — @xyflow/react can hang or OOM jsdom; cover those in E2E. */
  const smokePaths = [
    '/overview',
    '/dashboard',
    '/workflows',
    '/templates',
    '/cron',
    '/docs',
    '/pet-space',
  ] as const;

  it.each(smokePaths)('renders app shell for %s', async (path) => {
    const { unmount } = renderWithProviders(
      <MemoryRouter initialEntries={[path]}>
        <App />
      </MemoryRouter>
    );

    await waitFor(
      () => {
        expect(document.querySelector('aside')).toBeTruthy();
      },
      { timeout: 12_000 }
    );
    unmount();
  });

  it('shows in-app 404 for unknown child path but keeps shell', async () => {
    renderWithProviders(
      <MemoryRouter initialEntries={['/totally-unknown-route-xyz']}>
        <App />
      </MemoryRouter>
    );

    await waitFor(() => {
      expect(document.querySelector('aside')).toBeTruthy();
      expect(screen.getByRole('heading', { level: 1, name: '404' })).toBeInTheDocument();
    });
  });
});
