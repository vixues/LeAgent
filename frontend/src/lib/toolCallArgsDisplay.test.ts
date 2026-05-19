import { describe, expect, it, vi } from 'vitest';
import type { TFunction } from 'i18next';
import { redactLargeRawToolArguments, TOOL_CALL_RAW_REDACT_THRESHOLD } from './toolCallArgsDisplay';

describe('redactLargeRawToolArguments', () => {
  const t = vi.fn((key: string, opts?: { count?: number }) =>
    key === 'chat.toolArgsRawOmitted' ? `omitted-${opts?.count}` : key,
  ) as unknown as TFunction;

  it('leaves small __raw__ unchanged', () => {
    const raw = 'x'.repeat(TOOL_CALL_RAW_REDACT_THRESHOLD);
    const args = { __raw__: raw };
    expect(redactLargeRawToolArguments(args, t)).toBe(args);
    expect(t).not.toHaveBeenCalled();
  });

  it('omits oversized __raw__ for display', () => {
    const raw = 'x'.repeat(TOOL_CALL_RAW_REDACT_THRESHOLD + 1);
    const out = redactLargeRawToolArguments({ __raw__: raw, other: 1 }, t) as Record<string, unknown>;
    expect(out.other).toBe(1);
    expect(out.__raw__).toBeUndefined();
    expect(t).not.toHaveBeenCalled();
  });

  it('returns undefined when oversized __raw__ is the only argument', () => {
    const raw = 'x'.repeat(TOOL_CALL_RAW_REDACT_THRESHOLD + 1);
    expect(redactLargeRawToolArguments({ __raw__: raw }, t)).toBeUndefined();
  });

  it('ignores non-objects', () => {
    expect(redactLargeRawToolArguments(null, t)).toBe(null);
    expect(redactLargeRawToolArguments('str', t)).toBe('str');
  });
});
