import { describe, it, expect } from 'vitest';
import {
  buildCronJobCreatePayload,
  buildCronJobUpdatePayload,
  validateCronJobForm,
  CRON_I18N_FLOW_TARGET_REQUIRED,
  CRON_I18N_WEBHOOK_URL_REQUIRED,
  mapCronJobStatusToBadge,
} from './cronJobPayload';
import type { CreateCronJobInput } from '@/controllers/API/queries/cron';

const baseForm = (): CreateCronJobInput => ({
  name: '  Job  ',
  description: '  desc  ',
  job_type: 'flow',
  cron_expression: ' 0 0 * * * ',
  target_id: '',
  payload: {},
  enabled: true,
  timezone: 'UTC',
  max_retries: 3,
  timeout_sec: 3600,
  notify_on_start: false,
  notify_on_complete: true,
  notify_on_fail: true,
  tags: [],
});

describe('buildCronJobCreatePayload', () => {
  it('omits empty target_id', () => {
    const out = buildCronJobCreatePayload(baseForm());
    expect(out.target_id).toBeUndefined();
  });

  it('trims target_id when present', () => {
    const f = baseForm();
    f.target_id = '  abc-123  ';
    const out = buildCronJobCreatePayload(f);
    expect(out.target_id).toBe('abc-123');
  });

  it('trims name and cron_expression', () => {
    const out = buildCronJobCreatePayload(baseForm());
    expect(out.name).toBe('Job');
    expect(out.cron_expression).toBe('0 0 * * *');
  });
});

describe('validateCronJobForm', () => {
  it('requires workflow for flow jobs', () => {
    const f = baseForm();
    f.job_type = 'flow';
    f.target_id = '';
    expect(validateCronJobForm(f)).toBe(CRON_I18N_FLOW_TARGET_REQUIRED);
    f.target_id = '550e8400-e29b-41d4-a716-446655440000';
    expect(validateCronJobForm(f)).toBeNull();
  });

  it('requires payload.url for webhook jobs', () => {
    const f = baseForm();
    f.job_type = 'webhook';
    f.payload = {};
    expect(validateCronJobForm(f)).toBe(CRON_I18N_WEBHOOK_URL_REQUIRED);
    f.payload = { url: ' https://example.com/hook ' };
    expect(validateCronJobForm(f)).toBeNull();
  });
});

describe('buildCronJobUpdatePayload', () => {
  it('includes job id and normalized fields', () => {
    const f = baseForm();
    f.target_id = '550e8400-e29b-41d4-a716-446655440000';
    const out = buildCronJobUpdatePayload('jid', f);
    expect(out.id).toBe('jid');
    expect(out.target_id).toBe('550e8400-e29b-41d4-a716-446655440000');
    expect(out.name).toBe('Job');
  });
});

describe('mapCronJobStatusToBadge', () => {
  it('maps failed and disabled', () => {
    expect(mapCronJobStatusToBadge('failed')).toBe('error');
    expect(mapCronJobStatusToBadge('disabled')).toBe('inactive');
    expect(mapCronJobStatusToBadge('active')).toBe('active');
  });
});
