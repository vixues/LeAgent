import type { ReactElement } from 'react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { PetDockWidget } from './PetDockWidget';

vi.mock('@/hooks/usePetDockPreview', () => ({
  usePetDockPreview: () => ({
    data: {
      projectId: 'p1',
      previewFileId: null,
      mimeType: null,
      appearanceBuiltin: null,
      appearancePreviewOriginalName: null,
      settings: {},
      rawSettings: null,
      nestBackgroundFileId: null,
      nestBackgroundMime: null,
      nestBackgroundOriginalName: null,
      projectFiles: [],
    },
    isPending: false,
    isError: false,
  }),
}));

vi.mock('@/hooks/useAuthedFileBlobUrl', () => ({
  useAuthedFileBlobUrl: () => ({ url: null, isPending: false }),
}));

vi.mock('@/hooks/useMobile', () => ({
  usePrefersReducedMotion: () => false,
}));

vi.mock('@/stores/chat', () => ({
  useChatStore: (selector: (s: { isStreaming: boolean }) => boolean) =>
    selector({ isStreaming: false }),
}));

function wrap(ui: ReactElement) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <MemoryRouter>{ui}</MemoryRouter>
    </QueryClientProvider>,
  );
}

describe('PetDockWidget', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('renders expanded dock as a single control', () => {
    wrap(<PetDockWidget collapsed={false} active={false} />);
    expect(screen.getByRole('button')).toBeInTheDocument();
  });

  it('renders collapsed dock as a single control', () => {
    wrap(<PetDockWidget collapsed active={false} />);
    expect(screen.getByRole('button')).toBeInTheDocument();
  });
});
