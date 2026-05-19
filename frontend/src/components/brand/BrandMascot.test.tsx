import { describe, it, expect } from 'vitest';
import { render, screen } from '@testing-library/react';
import { BrandMascot } from './BrandMascot';

describe('BrandMascot', () => {
  it('renders mascot with default aria-label', () => {
    render(<BrandMascot size="md" />);
    expect(screen.getByRole('img', { name: 'Doge' })).toBeInTheDocument();
  });

  it('renders static fallback when requested', () => {
    render(<BrandMascot size="sm" staticFallback />);
    expect(screen.getByRole('img', { name: 'Doge' })).toHaveTextContent('D');
  });
});
