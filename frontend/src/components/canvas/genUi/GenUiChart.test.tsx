import { describe, it, expect, beforeAll, vi } from 'vitest';
import { render, screen } from '@testing-library/react';
import { GenUiChart } from './GenUiChart';

beforeAll(() => {
  vi.stubGlobal(
    'ResizeObserver',
    class {
      observe() {}
      unobserve() {}
      disconnect() {}
    },
  );
});

describe('GenUiChart', () => {
  it('renders empty state when series is empty for line chart', () => {
    render(
      <GenUiChart
        node={{
          nodeId: 'n1',
          kind: 'Chart',
          props: { chart: 'line', categories: ['A'], series: [] },
        }}
      />,
    );
    expect(screen.getByText(/No chart data/i)).toBeInTheDocument();
  });
});
