import { describe, expect, it } from 'vitest';

import { formatHttpErrorDetail } from '../formatApiError';

describe('formatHttpErrorDetail', () => {
  it('formats validation_errors objects from workflow 422 responses', () => {
    const msg = formatHttpErrorDetail(
      {
        validation_errors: {
          image_1: [{ type: 'required_input_missing', message: "Required input 'prompt' missing on 'image_1'" }],
          __root__: [{ type: 'missing_end', message: "end node 'end' is not defined" }],
        },
      },
      422,
    );
    expect(msg).toContain("image_1: Required input 'prompt' missing");
    expect(msg).toContain('__root__: end node');
  });

  it('falls back to HTTP status', () => {
    expect(formatHttpErrorDetail(undefined, 500)).toBe('HTTP 500');
  });
});
