import { render, screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';

import { GenUiInlineMarkdown, GenUiMarkdown } from '@/components/canvas/genUi/GenUiMarkdown';

describe('GenUI markdown rendering', () => {
  it('renders inline strong markdown without showing literal markers', () => {
    render(<GenUiInlineMarkdown value="**高级前端工程师**" />);

    const strong = screen.getByText('高级前端工程师');
    expect(strong.tagName.toLowerCase()).toBe('strong');
    expect(screen.queryByText(/\*\*/)).not.toBeInTheDocument();
  });

  it('accepts value as a fallback for Markdown nodes', () => {
    render(
      <GenUiMarkdown
        node={{
          nodeId: 'md',
          kind: 'Markdown',
          props: { value: '**计算机科学与技术** · 硕士' },
        }}
      />,
    );

    expect(screen.getByText('计算机科学与技术').tagName.toLowerCase()).toBe('strong');
    expect(screen.getByText(/硕士/)).toBeInTheDocument();
  });
});
