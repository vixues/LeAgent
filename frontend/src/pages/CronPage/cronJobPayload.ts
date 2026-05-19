import type { CreateCronJobInput, CronJobInfo, UpdateCronJobInput } from '@/controllers/API/queries/cron';
import type { StatusType } from '@/components/common/StatusBadge';

/** i18n key — flow jobs require a workflow UUID */
export const CRON_I18N_FLOW_TARGET_REQUIRED = 'cron.validation.flowTargetRequired';
/** i18n key — webhook jobs need payload.url */
export const CRON_I18N_WEBHOOK_URL_REQUIRED = 'cron.validation.webhookUrlRequired';

export function mapCronJobStatusToBadge(status: CronJobInfo['status']): StatusType {
  switch (status) {
    case 'failed':
      return 'error';
    case 'disabled':
      return 'inactive';
    case 'active':
    case 'paused':
    case 'running':
      return status;
    default:
      return 'unknown';
  }
}

/**
 * Normalize fields for the cron REST API: omit empty target_id (avoid UUID 422),
 * trim strings.
 */
export function buildCronJobCreatePayload(form: CreateCronJobInput): CreateCronJobInput {
  const target_id = form.target_id?.trim();
  return {
    ...form,
    name: form.name.trim(),
    description: form.description?.trim() || undefined,
    target_id: target_id || undefined,
    cron_expression: form.cron_expression.trim(),
  };
}

export function buildCronJobUpdatePayload(id: string, form: CreateCronJobInput): UpdateCronJobInput {
  const base = buildCronJobCreatePayload(form);
  return {
    id,
    name: base.name,
    description: base.description,
    cron_expression: base.cron_expression,
    target_id: base.target_id,
    payload: base.payload,
    enabled: base.enabled,
    timezone: base.timezone,
    max_retries: base.max_retries,
    timeout_sec: base.timeout_sec,
    notify_on_start: base.notify_on_start,
    notify_on_complete: base.notify_on_complete,
    notify_on_fail: base.notify_on_fail,
    tags: base.tags,
  };
}

/**
 * Returns an i18n key (under `cron.validation.*`) or null if valid.
 */
export function validateCronJobForm(form: CreateCronJobInput): string | null {
  if (form.job_type === 'flow') {
    if (!form.target_id?.trim()) {
      return CRON_I18N_FLOW_TARGET_REQUIRED;
    }
  }
  if (form.job_type === 'webhook') {
    const url = String(form.payload?.url ?? '').trim();
    if (!url) {
      return CRON_I18N_WEBHOOK_URL_REQUIRED;
    }
  }
  return null;
}
