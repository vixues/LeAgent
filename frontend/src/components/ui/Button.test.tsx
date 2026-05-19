import { describe, it, expect, vi } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import { Button } from './Button';

describe('Button', () => {
  it('should render children', () => {
    render(<Button>Click me</Button>);
    expect(screen.getByText('Click me')).toBeInTheDocument();
  });

  it('should handle click events', () => {
    const handleClick = vi.fn();
    render(<Button onClick={handleClick}>Click me</Button>);
    
    fireEvent.click(screen.getByText('Click me'));
    expect(handleClick).toHaveBeenCalledTimes(1);
  });

  it('should be disabled when disabled prop is true', () => {
    render(<Button disabled>Disabled</Button>);
    expect(screen.getByRole('button')).toBeDisabled();
  });

  it('should be disabled when loading is true', () => {
    render(<Button loading>Loading</Button>);
    expect(screen.getByRole('button')).toBeDisabled();
  });

  it('should show loading spinner when loading', () => {
    render(<Button loading>Loading</Button>);
    expect(screen.getByRole('button').querySelector('svg')).toBeInTheDocument();
  });

  it('should render with left icon', () => {
    render(<Button leftIcon={<span data-testid="left-icon">L</span>}>With Icon</Button>);
    expect(screen.getByTestId('left-icon')).toBeInTheDocument();
  });

  it('should render with right icon', () => {
    render(<Button rightIcon={<span data-testid="right-icon">R</span>}>With Icon</Button>);
    expect(screen.getByTestId('right-icon')).toBeInTheDocument();
  });

  it('should not call onClick when disabled', () => {
    const handleClick = vi.fn();
    render(<Button disabled onClick={handleClick}>Disabled</Button>);
    
    fireEvent.click(screen.getByRole('button'));
    expect(handleClick).not.toHaveBeenCalled();
  });

  describe('variants', () => {
    it('should apply primary variant by default', () => {
      render(<Button>Primary</Button>);
      expect(screen.getByRole('button')).toHaveClass('bg-primary-50');
    });

    it('should apply primarySolid variant', () => {
      render(<Button variant="primarySolid">Solid</Button>);
      expect(screen.getByRole('button')).toHaveClass('bg-primary-600');
    });

    it('should apply secondary variant', () => {
      render(<Button variant="secondary">Secondary</Button>);
      expect(screen.getByRole('button')).toHaveClass('bg-surface-sunken');
    });

    it('should apply ghost variant', () => {
      render(<Button variant="ghost">Ghost</Button>);
      expect(screen.getByRole('button')).toHaveClass('bg-transparent');
    });

    it('should apply danger variant', () => {
      render(<Button variant="danger">Danger</Button>);
      expect(screen.getByRole('button')).toHaveClass('bg-red-600');
    });

    it('should apply outline variant', () => {
      render(<Button variant="outline">Outline</Button>);
      expect(screen.getByRole('button')).toHaveClass('border');
    });
  });

  describe('sizes', () => {
    it('should apply md size by default', () => {
      render(<Button>Medium</Button>);
      expect(screen.getByRole('button')).toHaveClass('px-4');
    });

    it('should apply sm size', () => {
      render(<Button size="sm">Small</Button>);
      expect(screen.getByRole('button')).toHaveClass('px-3');
    });

    it('should apply lg size', () => {
      render(<Button size="lg">Large</Button>);
      expect(screen.getByRole('button')).toHaveClass('px-6');
    });

    it('should apply icon size', () => {
      render(<Button size="icon">Icon</Button>);
      expect(screen.getByRole('button')).toHaveClass('p-2');
    });
  });
});
