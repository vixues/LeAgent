import { useState, useEffect, useMemo } from 'react';
import { useTranslation } from 'react-i18next';
import { cn } from '@/lib/utils';
import { X, Save } from 'lucide-react';
import { Input, Select, Textarea, Button, Switch } from '@/components/ui';
import { useCronJobNextRuns, type CronJobDetail, type CreateCronJobInput } from '@/controllers/API/queries/cron';
import { CronExpressionBuilder } from './CronExpressionBuilder';
import { useGetFlows } from '@/controllers/API/queries/flows';
import { PageLoader } from '@/components/common/PageLoader';
import {
  buildCronJobCreatePayload,
  validateCronJobForm,
} from '@/pages/CronPage/cronJobPayload';

const INITIAL_FORM: CreateCronJobInput = {
  name: '',
  description: '',
  job_type: 'flow',
  cron_expression: '0 0 * * *',
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
};

interface CronJobModalProps {
  open: boolean;
  onClose: () => void;
  onSave: (data: CreateCronJobInput) => Promise<void>;
  mode: 'create' | 'edit';
  job?: CronJobDetail;
  /** True while fetching GET /cron/{id} for edit */
  detailLoading?: boolean;
  /** True when GET /cron/{id} failed */
  detailError?: boolean;
  isLoading?: boolean;
}

export function CronJobModal({
  open,
  onClose,
  onSave,
  mode,
  job,
  detailLoading = false,
  detailError = false,
  isLoading,
}: CronJobModalProps) {
  const { t } = useTranslation();
  const isEdit = mode === 'edit';
  const jobTypeOptions = useMemo(
    () =>
      [
        { value: 'flow' as const, label: t('cron.typeFlow'), description: t('cron.modal.typeFlowDesc') },
        {
          value: 'task' as const,
          label: t('cron.typeTask'),
          description: t('cron.modal.typeTaskDesc'),
        },
        { value: 'webhook' as const, label: t('cron.typeWebhook'), description: t('cron.modal.typeWebhookDesc') },
        { value: 'script' as const, label: t('cron.typeScript'), description: t('cron.modal.typeScriptDesc') },
      ] as const,
    [t]
  );
  const [form, setForm] = useState<CreateCronJobInput>(INITIAL_FORM);
  const [payloadStr, setPayloadStr] = useState('{}');
  const [payloadError, setPayloadError] = useState('');
  const [submitError, setSubmitError] = useState('');
  const [scriptArgsStr, setScriptArgsStr] = useState('[]');
  const [scriptArgsError, setScriptArgsError] = useState('');
  const [scriptEnvStr, setScriptEnvStr] = useState('{}');
  const [scriptEnvError, setScriptEnvError] = useState('');

  const { data: flowsData } = useGetFlows({ pageSize: 100 });

  const { data: nextRunsData, isLoading: nextRunsLoading } = useCronJobNextRuns(job?.id ?? '', 10, {
    enabled: isEdit && !!job?.id,
  });

  useEffect(() => {
    if (!open) return;
    if (mode === 'create') {
      setForm(INITIAL_FORM);
      setPayloadStr('{}');
      setPayloadError('');
      setSubmitError('');
      setScriptArgsStr('[]');
      setScriptArgsError('');
      setScriptEnvStr('{}');
      setScriptEnvError('');
    }
  }, [open, mode]);

  useEffect(() => {
    if (job) {
      setForm({
        name: job.name,
        description: job.description || '',
        job_type: job.job_type,
        cron_expression: job.cron_expression,
        target_id: job.target_id || '',
        payload: job.payload ?? {},
        enabled: job.enabled,
        timezone: job.timezone,
        max_retries: job.max_retries,
        timeout_sec: job.timeout_sec,
        notify_on_start: job.notify_on_start,
        notify_on_complete: job.notify_on_complete,
        notify_on_fail: job.notify_on_fail,
        tags: job.tags,
      });
      setPayloadStr(JSON.stringify(job.payload ?? {}, null, 2));
      setSubmitError('');
      const p = job.payload ?? {};
      const args = p.args;
      setScriptArgsStr(JSON.stringify(Array.isArray(args) ? args : [], null, 2));
      setScriptEnvStr(JSON.stringify((p.env as Record<string, unknown>) ?? {}, null, 2));
      setScriptArgsError('');
      setScriptEnvError('');
    }
  }, [job]);

  const showFlowPayloadJson = form.job_type === 'flow';

  const handlePayloadChange = (str: string) => {
    setPayloadStr(str);
    try {
      const parsed = JSON.parse(str);
      setForm((f) => ({ ...f, payload: parsed }));
      setPayloadError('');
    } catch {
      setPayloadError(t('cron.modal.invalidJson'));
    }
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (payloadError || scriptArgsError || scriptEnvError) return;

    let payload = { ...(form.payload ?? {}) } as Record<string, unknown>;

    if (form.job_type === 'script') {
      try {
        const args = JSON.parse(scriptArgsStr || '[]');
        if (!Array.isArray(args)) {
          setScriptArgsError(t('cron.modal.scriptArgsInvalid'));
          return;
        }
        const env = JSON.parse(scriptEnvStr || '{}');
        if (typeof env !== 'object' || env === null || Array.isArray(env)) {
          setScriptEnvError(t('cron.modal.scriptEnvInvalid'));
          return;
        }
        payload = {
          ...payload,
          args,
          env,
        };
      } catch {
        setScriptArgsError(t('cron.modal.invalidJson'));
        return;
      }
    }

    const mergedForm: CreateCronJobInput = { ...form, payload };

    const i18nKey = validateCronJobForm(mergedForm);
    if (i18nKey) {
      setSubmitError(t(i18nKey));
      return;
    }
    setSubmitError('');
    await onSave(buildCronJobCreatePayload(mergedForm));
  };

  if (!open) return null;

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4">
      <div className="absolute inset-0 bg-black/50" onClick={onClose} />
      <div className="relative z-10 w-full max-w-2xl max-h-[90vh] flex flex-col bg-surface rounded-2xl shadow-2xl">
        <div className="flex items-center justify-between px-6 py-4 border-b border-gray-200 dark:border-gray-700">
          <h2 className="text-lg font-semibold text-gray-900 dark:text-white">
            {isEdit ? t('cron.modal.titleEdit') : t('cron.modal.titleNew')}
          </h2>
          <button
            type="button"
            onClick={onClose}
            className="p-1.5 rounded-lg text-gray-400 hover:text-gray-600 hover:bg-gray-100 dark:hover:bg-gray-800 transition-colors"
          >
            <X className="w-5 h-5" />
          </button>
        </div>

        {detailLoading && (
          <div className="flex justify-center py-16 px-6">
            <PageLoader size="sm" message={t('cron.modal.loadingDetail')} />
          </div>
        )}

        {isEdit && detailError && !detailLoading && !job && (
          <>
            <div className="mx-6 my-4 rounded-lg border border-red-200 dark:border-red-900/40 bg-red-50 dark:bg-red-900/20 px-4 py-3 text-sm text-red-800 dark:text-red-200">
              {t('cron.modal.loadDetailFailed')}
            </div>
            <div className="flex justify-end px-6 py-4 border-t border-gray-200 dark:border-gray-700">
              <Button type="button" variant="secondary" onClick={onClose}>
                {t('cron.modal.cancel')}
              </Button>
            </div>
          </>
        )}

        {!detailLoading && !(isEdit && detailError && !job) && (
          <form onSubmit={handleSubmit} className="flex-1 overflow-y-auto flex flex-col min-h-0">
            <div className="px-6 py-5 space-y-5">
              <div className="grid grid-cols-1 gap-4">
                <div>
                  <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">
                    {t('cron.modal.jobNameLabel')} <span className="text-red-500">*</span>
                  </label>
                  <Input
                    required
                    value={form.name}
                    onChange={(e) => setForm((f) => ({ ...f, name: e.target.value }))}
                    placeholder={t('cron.modal.namePlaceholder')}
                  />
                </div>
                <div>
                  <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">
                    {t('cron.modal.descriptionLabel')}
                  </label>
                  <Input
                    value={form.description}
                    onChange={(e) => setForm((f) => ({ ...f, description: e.target.value }))}
                    placeholder={t('cron.modal.descriptionPlaceholder')}
                  />
                </div>
              </div>

              <div>
                <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-2">
                  {t('cron.modal.jobTypeLabel')}
                </label>
                <div className="grid grid-cols-2 sm:grid-cols-4 gap-2">
                  {jobTypeOptions.map((opt) => (
                    <button
                      key={opt.value}
                      type="button"
                      disabled={isEdit}
                      onClick={() =>
                        setForm((f) => ({ ...f, job_type: opt.value as CreateCronJobInput['job_type'] }))
                      }
                      className={cn(
                        'p-3 rounded-lg border-2 text-left transition-[color,background-color,border-color,box-shadow,opacity,transform]',
                        isEdit && 'opacity-60 cursor-not-allowed',
                        form.job_type === opt.value
                          ? 'border-primary-500 bg-primary-50 dark:bg-primary-900/20'
                          : 'border-gray-200 dark:border-gray-700 hover:border-gray-300'
                      )}
                    >
                      <div
                        className={cn(
                          'text-sm font-medium',
                          form.job_type === opt.value
                            ? 'text-primary-700 dark:text-primary-300'
                            : 'text-gray-700 dark:text-gray-300'
                        )}
                      >
                        {opt.label}
                      </div>
                      <div className="text-xs text-gray-500 dark:text-gray-400 mt-0.5">{opt.description}</div>
                    </button>
                  ))}
                </div>
                {isEdit && (
                  <p className="text-xs text-gray-500 dark:text-gray-400 mt-2">{t('cron.modal.jobTypeLockedHint')}</p>
                )}
              </div>

              {form.job_type === 'task' && (
                <div className="space-y-3">
                  <div>
                    <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">
                      {t('cron.modal.taskTypeLabel')}
                    </label>
                    <Select
                      value={String(form.payload?.task_type ?? 'agent')}
                      onChange={(e) => {
                        const task_type = e.target.value;
                        const nextPayload = {
                          ...(form.payload ?? {}),
                          task_type,
                        } as Record<string, unknown>;
                        setForm((f) => ({ ...f, payload: nextPayload }));
                        setPayloadStr(JSON.stringify(nextPayload, null, 2));
                      }}
                    >
                      <option value="agent">agent</option>
                      <option value="shell">shell</option>
                      <option value="workflow">workflow</option>
                      <option value="tool">tool</option>
                      <option value="batch">batch</option>
                    </Select>
                    <p className="text-xs text-gray-500 dark:text-gray-400 mt-1">{t('cron.modal.taskTypeHint')}</p>
                  </div>
                  <div>
                    <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">
                      {t('cron.modal.taskInputLabel')}
                    </label>
                    <Textarea
                      rows={4}
                      className="font-mono text-xs resize-none"
                      value={JSON.stringify(
                        (form.payload?.input_data as Record<string, unknown>) ?? {},
                        null,
                        2
                      )}
                      onChange={(e) => {
                        try {
                          const parsed = JSON.parse(e.target.value || '{}');
                          const nextPayload = {
                            ...(form.payload ?? {}),
                            input_data: parsed,
                          } as Record<string, unknown>;
                          setForm((f) => ({ ...f, payload: nextPayload }));
                          setPayloadStr(JSON.stringify(nextPayload, null, 2));
                          setPayloadError('');
                        } catch {
                          setPayloadError(t('cron.modal.invalidJson'));
                        }
                      }}
                    />
                  </div>
                </div>
              )}

              {form.job_type === 'webhook' && (
                <div className="space-y-3 rounded-lg border border-gray-200 dark:border-gray-700 p-4 bg-gray-50/50 dark:bg-surface/50">
                  <p className="text-sm font-medium text-gray-800 dark:text-gray-200">{t('cron.modal.webhookSection')}</p>
                  <div>
                    <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">
                      {t('cron.modal.webhookUrl')} <span className="text-red-500">*</span>
                    </label>
                    <Input
                      value={String(form.payload?.url ?? '')}
                      onChange={(e) => {
                        const url = e.target.value;
                        const next = { ...(form.payload ?? {}), url } as Record<string, unknown>;
                        setForm((f) => ({ ...f, payload: next }));
                        setPayloadStr(JSON.stringify(next, null, 2));
                      }}
                      placeholder="https://"
                    />
                  </div>
                  <div className="grid sm:grid-cols-2 gap-3">
                    <div>
                      <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">
                        {t('cron.modal.webhookMethod')}
                      </label>
                      <Select
                        value={String(form.payload?.method ?? 'POST').toUpperCase()}
                        onChange={(e) => {
                          const method = e.target.value;
                          const next = { ...(form.payload ?? {}), method } as Record<string, unknown>;
                          setForm((f) => ({ ...f, payload: next }));
                          setPayloadStr(JSON.stringify(next, null, 2));
                        }}
                      >
                        <option value="GET">GET</option>
                        <option value="POST">POST</option>
                        <option value="PUT">PUT</option>
                        <option value="PATCH">PATCH</option>
                      </Select>
                    </div>
                    <div>
                      <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">
                        {t('cron.modal.webhookTimeoutSec')}
                      </label>
                      <Input
                        type="number"
                        min={1}
                        max={600}
                        value={Number(form.payload?.timeout ?? 30)}
                        onChange={(e) => {
                          const timeout = parseInt(e.target.value, 10) || 30;
                          const next = { ...(form.payload ?? {}), timeout } as Record<string, unknown>;
                          setForm((f) => ({ ...f, payload: next }));
                          setPayloadStr(JSON.stringify(next, null, 2));
                        }}
                      />
                    </div>
                  </div>
                  <div>
                    <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">
                      {t('cron.modal.webhookHeadersJson')}
                    </label>
                    <Textarea
                      rows={3}
                      className="font-mono text-xs resize-none"
                      value={JSON.stringify((form.payload?.headers as Record<string, unknown>) ?? {}, null, 2)}
                      onChange={(e) => {
                        try {
                          const headers = JSON.parse(e.target.value || '{}');
                          const next = { ...(form.payload ?? {}), headers } as Record<string, unknown>;
                          setForm((f) => ({ ...f, payload: next }));
                          setPayloadStr(JSON.stringify(next, null, 2));
                          setPayloadError('');
                        } catch {
                          setPayloadError(t('cron.modal.invalidJson'));
                        }
                      }}
                    />
                  </div>
                  <div>
                    <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">
                      {t('cron.modal.webhookBodyJson')}
                    </label>
                    <Textarea
                      rows={3}
                      className="font-mono text-xs resize-none"
                      value={JSON.stringify((form.payload?.body as Record<string, unknown>) ?? {}, null, 2)}
                      onChange={(e) => {
                        try {
                          const body = JSON.parse(e.target.value || '{}');
                          const next = { ...(form.payload ?? {}), body } as Record<string, unknown>;
                          setForm((f) => ({ ...f, payload: next }));
                          setPayloadStr(JSON.stringify(next, null, 2));
                          setPayloadError('');
                        } catch {
                          setPayloadError(t('cron.modal.invalidJson'));
                        }
                      }}
                    />
                  </div>
                </div>
              )}

              {form.job_type === 'script' && (
                <div className="space-y-3 rounded-lg border border-gray-200 dark:border-gray-700 p-4 bg-gray-50/50 dark:bg-surface/50">
                  <p className="text-sm font-medium text-gray-800 dark:text-gray-200">{t('cron.modal.scriptSection')}</p>
                  <div>
                    <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">
                      {t('cron.modal.scriptPath')}
                    </label>
                    <Input
                      value={String(form.payload?.script_path ?? '')}
                      onChange={(e) => {
                        const script_path = e.target.value;
                        const next = { ...(form.payload ?? {}), script_path } as Record<string, unknown>;
                        setForm((f) => ({ ...f, payload: next }));
                        setPayloadStr(JSON.stringify(next, null, 2));
                      }}
                      placeholder="/path/to/script.py"
                    />
                  </div>
                  <div>
                    <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">
                      {t('cron.modal.scriptArgsJson')}
                    </label>
                    <Textarea
                      rows={3}
                      className="font-mono text-xs resize-none"
                      value={scriptArgsStr}
                      error={scriptArgsError || undefined}
                      onChange={(e) => {
                        setScriptArgsStr(e.target.value);
                        try {
                          const parsed = JSON.parse(e.target.value || '[]');
                          if (!Array.isArray(parsed)) {
                            setScriptArgsError(t('cron.modal.scriptArgsInvalid'));
                            return;
                          }
                          setScriptArgsError('');
                          const next = { ...(form.payload ?? {}), args: parsed } as Record<string, unknown>;
                          setForm((f) => ({ ...f, payload: next }));
                          setPayloadStr(JSON.stringify(next, null, 2));
                        } catch {
                          setScriptArgsError(t('cron.modal.invalidJson'));
                        }
                      }}
                    />
                  </div>
                  <div>
                    <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">
                      {t('cron.modal.scriptEnvJson')}
                    </label>
                    <Textarea
                      rows={3}
                      className="font-mono text-xs resize-none"
                      value={scriptEnvStr}
                      error={scriptEnvError || undefined}
                      onChange={(e) => {
                        setScriptEnvStr(e.target.value);
                        try {
                          const parsed = JSON.parse(e.target.value || '{}');
                          if (typeof parsed !== 'object' || parsed === null || Array.isArray(parsed)) {
                            setScriptEnvError(t('cron.modal.scriptEnvInvalid'));
                            return;
                          }
                          setScriptEnvError('');
                          const next = { ...(form.payload ?? {}), env: parsed } as Record<string, unknown>;
                          setForm((f) => ({ ...f, payload: next }));
                          setPayloadStr(JSON.stringify(next, null, 2));
                        } catch {
                          setScriptEnvError(t('cron.modal.invalidJson'));
                        }
                      }}
                    />
                  </div>
                  <div>
                    <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">
                      {t('cron.modal.scriptPayloadTimeout')}
                    </label>
                    <Input
                      type="number"
                      min={1}
                      value={Number(form.payload?.timeout ?? 300)}
                      onChange={(e) => {
                        const timeout = parseInt(e.target.value, 10) || 300;
                        const next = { ...(form.payload ?? {}), timeout } as Record<string, unknown>;
                        setForm((f) => ({ ...f, payload: next }));
                        setPayloadStr(JSON.stringify(next, null, 2));
                      }}
                    />
                  </div>
                  <div>
                    <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">
                      {t('cron.modal.scriptInline')}
                    </label>
                    <Textarea
                      rows={2}
                      className="font-mono text-xs resize-none"
                      value={String(form.payload?.script ?? '')}
                      onChange={(e) => {
                        const script = e.target.value;
                        const next = { ...(form.payload ?? {}), script } as Record<string, unknown>;
                        setForm((f) => ({ ...f, payload: next }));
                        setPayloadStr(JSON.stringify(next, null, 2));
                      }}
                      placeholder="#!/bin/bash ..."
                    />
                    <p className="text-xs text-amber-700 dark:text-amber-300/90 mt-1">{t('cron.modal.scriptInlineHint')}</p>
                  </div>
                </div>
              )}

              {form.job_type === 'flow' && (
                <div>
                  <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">
                    {t('cron.modal.workflowLabel')} <span className="text-red-500">*</span>
                  </label>
                  <Select
                    value={form.target_id}
                    onChange={(e) => setForm((f) => ({ ...f, target_id: e.target.value }))}
                  >
                    <option value="">{t('cron.modal.selectWorkflow')}</option>
                    {(flowsData?.data || []).map((flow) => (
                      <option key={flow.id} value={flow.id}>
                        {flow.name}
                      </option>
                    ))}
                  </Select>
                </div>
              )}

              <div>
                <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-2">
                  {t('cron.modal.scheduleLabel')} <span className="text-red-500">*</span>
                </label>
                <CronExpressionBuilder
                  value={form.cron_expression}
                  onChange={(expr) => setForm((f) => ({ ...f, cron_expression: expr }))}
                />
              </div>

              {isEdit && job && (
                <div className="rounded-lg border border-gray-200 dark:border-gray-700 bg-gray-50 dark:bg-surface/50 p-3">
                  <p className="text-sm font-medium text-gray-700 dark:text-gray-300 mb-2">
                    {t('cron.modal.upcomingRuns')}
                  </p>
                  {nextRunsLoading ? (
                    <p className="text-xs text-gray-500 dark:text-gray-400">{t('cron.modal.loadingRuns')}</p>
                  ) : nextRunsData?.next_runs?.length ? (
                    <ul className="text-xs font-mono text-gray-800 dark:text-gray-200 space-y-1 max-h-36 overflow-y-auto">
                      {nextRunsData.next_runs.map((iso) => (
                        <li key={iso}>{new Date(iso).toLocaleString()}</li>
                      ))}
                    </ul>
                  ) : (
                    <p className="text-xs text-gray-500 dark:text-gray-400">{t('cron.modal.noUpcomingRuns')}</p>
                  )}
                </div>
              )}

              <div className="grid sm:grid-cols-2 gap-4">
                <div>
                  <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">
                    {t('cron.modal.timezone')}
                  </label>
                  <Select
                    value={form.timezone}
                    onChange={(e) => setForm((f) => ({ ...f, timezone: e.target.value }))}
                  >
                    <option value="UTC">UTC</option>
                    <option value="America/New_York">America/New_York</option>
                    <option value="America/Los_Angeles">America/Los_Angeles</option>
                    <option value="Europe/London">Europe/London</option>
                    <option value="Europe/Paris">Europe/Paris</option>
                    <option value="Asia/Shanghai">Asia/Shanghai</option>
                    <option value="Asia/Tokyo">Asia/Tokyo</option>
                  </Select>
                </div>
                <div>
                  <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">
                    {t('cron.modal.maxRetries')}
                  </label>
                  <Input
                    type="number"
                    min={0}
                    max={10}
                    value={form.max_retries}
                    onChange={(e) =>
                      setForm((f) => ({ ...f, max_retries: parseInt(e.target.value, 10) || 0 }))
                    }
                  />
                </div>
              </div>

              {showFlowPayloadJson && (
                <div>
                  <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">
                    {t('cron.modal.payloadJson')}
                  </label>
                  <Textarea
                    value={payloadStr}
                    onChange={(e) => handlePayloadChange(e.target.value)}
                    rows={4}
                    className="font-mono text-xs resize-none"
                    error={payloadError || undefined}
                  />
                  <p className="text-xs text-gray-500 dark:text-gray-400 mt-1">{t('cron.modal.flowPayloadHint')}</p>
                </div>
              )}

              <div>
                <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-2">
                  {t('cron.modal.notifications')}
                </label>
                <div className="space-y-2">
                  {[
                    { key: 'notify_on_start', label: t('cron.modal.notifyStart') },
                    { key: 'notify_on_complete', label: t('cron.modal.notifyComplete') },
                    { key: 'notify_on_fail', label: t('cron.modal.notifyFail') },
                  ].map(({ key, label }) => (
                    <Switch
                      key={key}
                      size="sm"
                      label={label}
                      checked={form[key as keyof CreateCronJobInput] as boolean}
                      onChange={(e) => setForm((f) => ({ ...f, [key]: e.target.checked }))}
                    />
                  ))}
                </div>
              </div>

              <div className="flex items-center justify-between p-3 rounded-lg bg-gray-50 dark:bg-surface border border-gray-200 dark:border-gray-700">
                <div>
                  <p className="text-sm font-medium text-gray-700 dark:text-gray-300">{t('cron.modal.enableJob')}</p>
                  <p className="text-xs text-gray-500 dark:text-gray-400">{t('cron.modal.enableJobHint')}</p>
                </div>
                <Switch
                  checked={form.enabled}
                  onChange={(e) => setForm((f) => ({ ...f, enabled: e.target.checked }))}
                />
              </div>

              {submitError && (
                <div className="rounded-lg border border-red-200 dark:border-red-900/40 bg-red-50 dark:bg-red-900/20 px-4 py-3 text-sm text-red-800 dark:text-red-200">
                  {submitError}
                </div>
              )}
            </div>

            <div className="flex items-center justify-end gap-3 px-6 py-4 border-t border-gray-200 dark:border-gray-700">
              <Button type="button" variant="secondary" onClick={onClose}>
                {t('cron.modal.cancel')}
              </Button>
              <Button
                type="submit"
                disabled={
                  isLoading ||
                  !!payloadError ||
                  !!scriptArgsError ||
                  !!scriptEnvError ||
                  (isEdit && detailError && !job)
                }
                loading={isLoading}
                leftIcon={<Save className="w-4 h-4" />}
              >
                {isEdit ? t('cron.modal.saveChanges') : t('cron.modal.createJob')}
              </Button>
            </div>
          </form>
        )}
      </div>
    </div>
  );
}
