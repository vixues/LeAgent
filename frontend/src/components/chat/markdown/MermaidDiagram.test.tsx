import { render, screen, act, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it, vi, beforeEach, afterEach } from 'vitest';

const FAKE_SVG = '<svg data-testid="mermaid-svg"><text>A</text></svg>';
const SANITIZED_SVG = '<svg data-testid="mermaid-svg"><text>A</text></svg>';

const mermaidRenderMock = vi.fn().mockResolvedValue({ svg: FAKE_SVG });
const mermaidInitMock = vi.fn();

vi.mock('mermaid', () => ({
  default: {
    initialize: (...args: unknown[]) => mermaidInitMock(...args),
    render: (...args: unknown[]) => mermaidRenderMock(...args),
  },
}));

const sanitizeMock = vi.fn((_html: string) => SANITIZED_SVG);

vi.mock('dompurify', () => ({
  default: {
    sanitize: (...args: unknown[]) => sanitizeMock(...(args as [string])),
  },
}));

import { MermaidDiagram } from './MermaidDiagram';

const SOURCE = 'graph TD; A-->B';

function setColorMode(mode: 'light' | 'dark') {
  document.documentElement.classList.remove('light', 'dark');
  document.documentElement.classList.add(mode);
}

async function renderAndWait(source = SOURCE) {
  const result = render(<MermaidDiagram source={source} />);
  await act(async () => { vi.advanceTimersByTime(350); });
  await waitFor(() => {
    expect(result.container.querySelector('[data-testid="mermaid-svg"]')).toBeTruthy();
  });
  return result;
}

beforeEach(() => {
  vi.useFakeTimers({ shouldAdvanceTime: true });
  setColorMode('light');
  mermaidRenderMock.mockClear();
  mermaidInitMock.mockClear();
  sanitizeMock.mockClear();
  mermaidRenderMock.mockResolvedValue({ svg: FAKE_SVG });
});

afterEach(() => {
  vi.useRealTimers();
});

describe('MermaidDiagram', () => {
  it('shows loading spinner before render completes', () => {
    const { container } = render(<MermaidDiagram source={SOURCE} />);
    expect(container.querySelector('.animate-spin')).toBeInTheDocument();
    expect(screen.queryByText('Mermaid render error')).not.toBeInTheDocument();
  });

  it('renders SVG after debounce + mermaid.render', async () => {
    await renderAndWait('graph TD; X-->Y');
    expect(mermaidRenderMock).toHaveBeenCalledTimes(1);
    expect(sanitizeMock).toHaveBeenCalledTimes(1);
  });

  it('sanitizes SVG with DOMPurify before rendering', async () => {
    await renderAndWait('graph LR; A-->B');
    expect(sanitizeMock).toHaveBeenCalledWith(
      FAKE_SVG,
      expect.objectContaining({
        USE_PROFILES: expect.objectContaining({ svg: true }),
      }),
    );
  });

  it('displays error UI when mermaid.render throws', async () => {
    mermaidRenderMock.mockRejectedValueOnce(new Error('Parse error'));
    render(<MermaidDiagram source="invalid mermaid" />);
    await act(async () => { vi.advanceTimersByTime(350); });
    await waitFor(() => {
      expect(screen.getByText('Parse error')).toBeInTheDocument();
    });
  });

  it('initializes mermaid with dark theme when in dark mode', async () => {
    setColorMode('dark');
    render(<MermaidDiagram source="graph TD; D-->E" />);
    await act(async () => { vi.advanceTimersByTime(350); });
    await waitFor(() => {
      expect(mermaidInitMock).toHaveBeenCalledWith(
        expect.objectContaining({ theme: 'dark' }),
      );
    });
  });

  it('initializes mermaid with default theme when in light mode', async () => {
    setColorMode('light');
    render(<MermaidDiagram source="graph TD; L-->M" />);
    await act(async () => { vi.advanceTimersByTime(350); });
    await waitFor(() => {
      expect(mermaidInitMock).toHaveBeenCalledWith(
        expect.objectContaining({ theme: 'default' }),
      );
    });
  });

  it('debounces rapid source changes during streaming', async () => {
    const { rerender } = render(<MermaidDiagram source="graph TD; A" />);
    await act(async () => { vi.advanceTimersByTime(100); });
    rerender(<MermaidDiagram source="graph TD; A--" />);
    await act(async () => { vi.advanceTimersByTime(100); });
    rerender(<MermaidDiagram source="graph TD; A-->B" />);
    await act(async () => { vi.advanceTimersByTime(350); });
    await waitFor(() => {
      expect(mermaidRenderMock).toHaveBeenCalledTimes(1);
    });
    expect(mermaidRenderMock).toHaveBeenCalledWith(expect.any(String), 'graph TD; A-->B');
  });

  /* ── Toolbar buttons ── */

  it('shows toolbar with code, edit, download, and expand buttons', async () => {
    await renderAndWait();
    expect(screen.getByRole('button', { name: /view source/i })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /edit/i })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /download/i })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /expand/i })).toBeInTheDocument();
  });

  it('toggles raw code view when code button is clicked', async () => {
    const user = userEvent.setup({ advanceTimers: vi.advanceTimersByTime });
    await renderAndWait();

    expect(screen.queryByText(SOURCE)).not.toBeInTheDocument();

    await user.click(screen.getByRole('button', { name: /view source/i }));
    expect(screen.getByText(SOURCE)).toBeInTheDocument();

    await user.click(screen.getByRole('button', { name: /view source/i }));
    expect(screen.queryByText(SOURCE)).not.toBeInTheDocument();
  });

  it('opens edit dialog when edit button is clicked', async () => {
    const user = userEvent.setup({ advanceTimers: vi.advanceTimersByTime });
    await renderAndWait();

    await user.click(screen.getByRole('button', { name: /edit/i }));

    await waitFor(() => {
      expect(screen.getByText('Edit Mermaid Diagram')).toBeInTheDocument();
    });

    const textarea = document.body.querySelector('textarea');
    expect(textarea).toBeInTheDocument();
    expect(textarea!.value).toBe(SOURCE);
  });

  it('expand button opens fullscreen dialog', async () => {
    const user = userEvent.setup({ advanceTimers: vi.advanceTimersByTime });
    await renderAndWait('graph LR; P-->Q');

    await user.click(screen.getByRole('button', { name: /expand/i }));

    await waitFor(() => {
      const svgs = document.body.querySelectorAll('[data-testid="mermaid-svg"]');
      expect(svgs.length).toBeGreaterThanOrEqual(2);
    });
  });
});
