import { describe, expect, it } from 'vitest';
import {
  getCodingProjectStatusPollInterval,
  type StatusResponse,
} from '@/hooks/useCodingProjects';

const base: Pick<
  StatusResponse,
  'project_id' | 'runtime_kind' | 'is_running'
> = {
  project_id: 'p1',
  runtime_kind: 'frontend',
  is_running: false,
};

const opts = {
  activeIntervalMs: 5_000,
  transitionalIntervalMs: 2_500,
};

describe('getCodingProjectStatusPollInterval', () => {
  it('returns false with no data', () => {
    expect(getCodingProjectStatusPollInterval(undefined, opts)).toBe(false);
  });

  it('returns false when idle and not running', () => {
    const data: StatusResponse = {
      ...base,
      status: 'idle',
      is_running: false,
    };
    expect(getCodingProjectStatusPollInterval(data, opts)).toBe(false);
  });

  it('returns false when crashed', () => {
    const data: StatusResponse = {
      ...base,
      status: 'crashed',
      is_running: false,
    };
    expect(getCodingProjectStatusPollInterval(data, opts)).toBe(false);
  });

  it('uses transitional interval for starting and stopping', () => {
    expect(
      getCodingProjectStatusPollInterval(
        { ...base, status: 'starting', is_running: false },
        opts,
      ),
    ).toBe(2_500);
    expect(
      getCodingProjectStatusPollInterval(
        { ...base, status: 'stopping', is_running: true },
        opts,
      ),
    ).toBe(2_500);
  });

  it('uses active interval when running', () => {
    expect(
      getCodingProjectStatusPollInterval(
        { ...base, status: 'running', is_running: true },
        opts,
      ),
    ).toBe(5_000);
  });
});
