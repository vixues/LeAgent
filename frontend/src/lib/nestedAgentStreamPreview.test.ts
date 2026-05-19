import { describe, expect, it } from 'vitest';
import { extractNestedPreviewText, languageForNestedPreview } from './nestedAgentStreamPreview';

describe('nestedAgentStreamPreview', () => {
  it('extracts streaming project_write content from partial JSON', () => {
    const raw = '{"path":"src/a.ts","content":"const x = 1';
    const text = extractNestedPreviewText('project_write', raw, {});
    expect(text).toContain('const x = 1');
  });

  it('uses python for code_execution', () => {
    expect(languageForNestedPreview('code_execution', {})).toBe('python');
  });

  it('uses path extension when present', () => {
    expect(languageForNestedPreview('project_write', { path: 'foo/bar.tsx' })).toBe('typescript');
  });
});
