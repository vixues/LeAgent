import { describe, expect, it } from 'vitest';
import { pickCodeExecutionSourcePreview } from './codeExecutionStreamPreview';

describe('pickCodeExecutionSourcePreview', () => {
  it('prefers partialArgs.source when set', () => {
    const raw = '{"source": "ignored"';
    expect(
      pickCodeExecutionSourcePreview(raw, { source: 'x = 1\n' }),
    ).toBe('x = 1\n');
  });

  it('parses complete JSON', () => {
    const raw = JSON.stringify({ source: 'print(1)' });
    expect(pickCodeExecutionSourcePreview(raw, {})).toBe('print(1)');
  });

  it('decodes a streaming JSON string for source with escapes', () => {
    const raw = `{"source": "line1\\nline2", "timeout_sec": 30`;
    expect(pickCodeExecutionSourcePreview(raw, {})).toBe('line1\nline2');
  });

  it('returns truncated raw when no source key yet', () => {
    const raw = '{"timeout_sec":';
    const out = pickCodeExecutionSourcePreview(raw, {});
    expect(out).toBe(raw);
  });
});
