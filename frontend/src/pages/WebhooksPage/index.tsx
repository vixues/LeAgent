import { useEffect, useMemo, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { Plus, Webhook, Trash2, Edit2, FlaskConical } from 'lucide-react';
import { PageShell } from '@/components/layout/PageShell';
import { EmptyState } from '@/components/common/EmptyState';
import { PageLoader } from '@/components/common/PageLoader';
import {
  Button,
  Card,
  CardContent,
  Input,
  Switch,
  Modal,
  ModalHeader,
  ModalBody,
  ModalFooter,
  Textarea,
  Select,
  Badge,
} from '@/components/ui';
import {
  Accordion,
  AccordionContent,
  AccordionItem,
  AccordionTrigger,
} from '@/components/ui/Accordion';
import { useToast } from '@/components/ui/Toaster';
import {
  useWebhooksList,
  useWebhookDetail,
  useCreateWebhook,
  useUpdateWebhook,
  useDeleteWebhook,
  useTestWebhook,
  useWebhookDeliveries,
  useEnableWebhook,
  useDisableWebhook,
  WEBHOOK_EVENT_OPTIONS,
  type WebhookInfo,
  type WebhookDetail,
} from '@/hooks/useWebhooks';

const STATUS_BADGE: Record<string, 'success' | 'default' | 'error'> = {
  active: 'success',
  inactive: 'default',
  failed: 'error',
};

function emptyForm() {
  return {
    name: '',
    url: '',
    events: [] as string[],
    description: '',
    secret: '',
    retry_count: 3,
    timeout_seconds: 30,
  };
}

function truncateUrl(url: string, max = 48) {
  if (url.length <= max) return url;
  return `${url.slice(0, max)}…`;
}

function formatWhen(iso: string | null | undefined, locale: string) {
  if (!iso) return null;
  try {
    return new Date(iso).toLocaleString(locale);
  } catch {
    return iso;
  }
}

export default function WebhooksPage() {
  const { t, i18n } = useTranslation();
  const { toast } = useToast();

  const [statusFilter, setStatusFilter] = useState('');
  const [eventFilter, setEventFilter] = useState('');
  const [modalOpen, setModalOpen] = useState(false);
  const [editingId, setEditingId] = useState<string | null>(null);
  const [form, setForm] = useState(emptyForm);
  const [deliveryOpenId, setDeliveryOpenId] = useState<string | null>(null);
  const [testingId, setTestingId] = useState<string | null>(null);
  const [inlineTestById, setInlineTestById] = useState<Record<string, string>>({});

  const filters = useMemo(
    () => ({
      status: statusFilter || undefined,
      event: eventFilter || undefined,
    }),
    [statusFilter, eventFilter]
  );

  const { data: listData, isLoading } = useWebhooksList(filters);
  const { data: detail } = useWebhookDetail(editingId ?? '', {
    enabled: modalOpen && !!editingId,
  });

  const createMutation = useCreateWebhook();
  const updateMutation = useUpdateWebhook();
  const deleteMutation = useDeleteWebhook();
  const testMutation = useTestWebhook();
  const enableMutation = useEnableWebhook();
  const disableMutation = useDisableWebhook();

  const { data: deliveriesData, isLoading: deliveriesLoading } = useWebhookDeliveries(
    deliveryOpenId ?? '',
    { enabled: !!deliveryOpenId }
  );

  useEffect(() => {
    if (!modalOpen) return;
    if (editingId && detail) {
      setForm({
        name: detail.name,
        url: detail.url,
        events: [...detail.events],
        description: detail.description ?? '',
        secret: detail.secret ?? '',
        retry_count: detail.retry_count ?? 3,
        timeout_seconds: detail.timeout_seconds ?? 30,
      });
    }
    if (!editingId && modalOpen) {
      setForm(emptyForm());
    }
  }, [modalOpen, editingId, detail]);

  const webhooks = listData?.webhooks ?? [];

  const openCreate = () => {
    setEditingId(null);
    setForm(emptyForm());
    setModalOpen(true);
  };

  const openEdit = (w: WebhookInfo) => {
    setEditingId(w.id);
    setForm({
      name: w.name,
      url: w.url,
      events: [...w.events],
      description: w.description ?? '',
      secret: '',
      retry_count: 3,
      timeout_seconds: 30,
    });
    setModalOpen(true);
  };

  const handleSave = async () => {
    if (!form.name.trim() || !form.url.trim()) {
      toast({
        title: t('webhooks.validation'),
        description: t('webhooks.nameUrlRequired'),
        variant: 'error',
      });
      return;
    }
    if (form.events.length === 0) {
      toast({
        title: t('webhooks.validation'),
        description: t('webhooks.eventsRequired'),
        variant: 'error',
      });
      return;
    }

    const retry = Number(form.retry_count);
    const timeout = Number(form.timeout_seconds);
    if (Number.isNaN(retry) || retry < 0 || retry > 10) {
      toast({
        title: t('webhooks.validation'),
        description: t('webhooks.retryInvalid'),
        variant: 'error',
      });
      return;
    }
    if (Number.isNaN(timeout) || timeout < 5 || timeout > 120) {
      toast({
        title: t('webhooks.validation'),
        description: t('webhooks.timeoutInvalid'),
        variant: 'error',
      });
      return;
    }

    try {
      if (editingId) {
        await updateMutation.mutateAsync({
          id: editingId,
          name: form.name.trim(),
          url: form.url.trim(),
          events: form.events,
          description: form.description.trim() || undefined,
          secret: form.secret.trim() || undefined,
          retry_count: retry,
          timeout_seconds: timeout,
        });
        toast({ title: t('webhooks.updated') });
      } else {
        await createMutation.mutateAsync({
          name: form.name.trim(),
          url: form.url.trim(),
          events: form.events,
          description: form.description.trim() || undefined,
          secret: form.secret.trim() || undefined,
          retry_count: retry,
          timeout_seconds: timeout,
          enabled: true,
        });
        toast({ title: t('webhooks.created') });
      }
      setModalOpen(false);
      setEditingId(null);
    } catch (e: unknown) {
      toast({ title: t('common.error'), description: String(e), variant: 'error' });
    }
  };

  const handleDelete = async (w: WebhookInfo) => {
    if (!window.confirm(t('webhooks.confirmDelete', { name: w.name }))) return;
    try {
      await deleteMutation.mutateAsync(w.id);
      toast({ title: t('webhooks.deleted') });
    } catch (e: unknown) {
      toast({ title: t('common.error'), description: String(e), variant: 'error' });
    }
  };

  const handleTest = async (id: string) => {
    setTestingId(id);
    setInlineTestById((prev) => {
      const next = { ...prev };
      delete next[id];
      return next;
    });
    try {
      const res = await testMutation.mutateAsync(id);
      const desc = res.success
        ? t('webhooks.testOk', {
            code: res.status_code ?? '—',
            ms: res.response_time_ms,
          })
        : res.error || t('webhooks.testFailed');
      toast({
        title: t('webhooks.testSent'),
        description: desc,
        variant: res.success ? 'default' : 'error',
      });
      setInlineTestById((prev) => ({
        ...prev,
        [id]: res.success
          ? t('webhooks.testInlineOk', { ms: res.response_time_ms })
          : (res.error ?? t('webhooks.testInlineFail')),
      }));
    } catch (e: unknown) {
      toast({ title: t('common.error'), description: String(e), variant: 'error' });
      setInlineTestById((prev) => ({
        ...prev,
        [id]: t('webhooks.testInlineError'),
      }));
    } finally {
      setTestingId(null);
    }
  };

  const handleEnabledToggle = async (w: WebhookInfo, enabled: boolean) => {
    try {
      if (enabled) await enableMutation.mutateAsync(w.id);
      else await disableMutation.mutateAsync(w.id);
      toast({
        title: enabled ? t('webhooks.enabled') : t('webhooks.disabled'),
      });
    } catch (e: unknown) {
      toast({ title: t('common.error'), description: String(e), variant: 'error' });
    }
  };

  const lastDeliveryLabel = (w: WebhookInfo) => {
    const at = formatWhen(w.last_delivery_at, i18n.language);
    if (!at) {
      return t('webhooks.lastDeliveryNever');
    }
    return t('webhooks.lastDeliveryAt', { time: at });
  };

  const lastDeliveryStatusLabel = (w: WebhookInfo) => {
    const dc = w.delivery_count ?? 0;
    const fc = w.failure_count ?? 0;
    if (dc === 0) {
      return t('webhooks.lastDeliveryStatusNone');
    }
    if (fc > 0) {
      return t('webhooks.lastDeliveryStatusMixed', {
        fail: fc,
        ok: Math.max(0, dc - fc),
      });
    }
    return t('webhooks.lastDeliveryStatusOk');
  };

  return (
    <PageShell
      title={t('webhooks.title')}
      description={t('webhooks.subtitle')}
      icon={<Webhook className="w-5 h-5" />}
      actions={
        <Button
          onClick={openCreate}
          leftIcon={<Plus className="w-4 h-4" />}
          className="shadow-glow hover:shadow-glow-lg transition-shadow"
        >
          {t('webhooks.new')}
        </Button>
      }
    >
        <div className="flex flex-wrap gap-3">
          <Select
            className="w-44"
            value={statusFilter}
            onChange={(e) => setStatusFilter(e.target.value)}
            aria-label={t('webhooks.filterStatus')}
          >
            <option value="">{t('webhooks.allStatuses')}</option>
            <option value="active">active</option>
            <option value="inactive">inactive</option>
            <option value="failed">failed</option>
          </Select>
          <Select
            className="min-w-[200px] max-w-xs"
            value={eventFilter}
            onChange={(e) => setEventFilter(e.target.value)}
            aria-label={t('webhooks.filterEvent')}
          >
            <option value="">{t('webhooks.allEvents')}</option>
            {WEBHOOK_EVENT_OPTIONS.map((ev) => (
              <option key={ev} value={ev}>
                {ev}
              </option>
            ))}
          </Select>
        </div>

        {isLoading ? (
          <div className="flex justify-center py-20">
            <PageLoader size="md" message={t('common.loading')} />
          </div>
        ) : webhooks.length === 0 ? (
          <EmptyState
            title={t('webhooks.empty')}
            description={t('webhooks.emptyHint')}
            action={{ label: t('webhooks.new'), onClick: openCreate }}
          />
        ) : (
          <div className="grid gap-6 sm:grid-cols-2 xl:grid-cols-3">
            {webhooks.map((w) => (
              <Card key={w.id} padding="md" className="flex flex-col">
                <CardContent padding="none" className="flex flex-col flex-1 gap-3">
                  <div className="flex items-start justify-between gap-2">
                    <div className="min-w-0 flex-1">
                      <h3 className="font-semibold text-gray-900 dark:text-white truncate">{w.name}</h3>
                      <p
                        className="text-xs font-mono text-gray-500 dark:text-gray-400 mt-1"
                        title={w.url}
                      >
                        {truncateUrl(w.url)}
                      </p>
                    </div>
                    <div className="flex flex-col items-end gap-1 shrink-0">
                      <Badge variant={STATUS_BADGE[w.status] ?? 'default'} size="sm">
                        {w.status}
                      </Badge>
                      <Badge variant={w.enabled ? 'success' : 'default'} size="sm">
                        {w.enabled
                          ? t('webhooks.enabledLabel')
                          : t('webhooks.disabledLabel')}
                      </Badge>
                    </div>
                  </div>

                  <div className="flex flex-wrap gap-1">
                    {w.events.slice(0, 5).map((ev) => (
                      <Badge key={ev} size="sm" variant="default">
                        {ev}
                      </Badge>
                    ))}
                    {w.events.length > 5 && (
                      <Badge size="sm" variant="default">
                        +{w.events.length - 5}
                      </Badge>
                    )}
                  </div>

                  <div className="rounded-lg border border-gray-100 dark:border-gray-800 bg-gray-50/80 dark:bg-surface/40 px-3 py-2 text-xs text-gray-600 dark:text-gray-300 space-y-1">
                    <p>{lastDeliveryLabel(w)}</p>
                    <p className="text-gray-500 dark:text-gray-400">{lastDeliveryStatusLabel(w)}</p>
                    {inlineTestById[w.id] && (
                      <p className="text-primary-600 dark:text-primary-400 font-medium pt-1 border-t border-gray-200 dark:border-gray-700">
                        {t('webhooks.testResult')}: {inlineTestById[w.id]}
                      </p>
                    )}
                  </div>

                  <div className="flex items-center justify-between pt-2 border-t border-gray-100 dark:border-gray-800">
                    <span className="text-sm text-gray-600 dark:text-gray-400">
                      {t('webhooks.toggleEnable')}
                    </span>
                    <Switch
                      checked={w.enabled}
                      onChange={(e) => handleEnabledToggle(w, e.target.checked)}
                      disabled={enableMutation.isPending || disableMutation.isPending}
                    />
                  </div>

                  <div className="flex flex-wrap gap-2 mt-auto">
                    <Button
                      type="button"
                      variant="ghost"
                      size="sm"
                      leftIcon={<FlaskConical className="w-4 h-4" />}
                      onClick={() => handleTest(w.id)}
                      loading={testingId === w.id}
                    >
                      {t('webhooks.test')}
                    </Button>
                    <Button
                      type="button"
                      variant="ghost"
                      size="sm"
                      leftIcon={<Edit2 className="w-4 h-4" />}
                      onClick={() => openEdit(w)}
                    >
                      {t('common.edit')}
                    </Button>
                    <Button
                      type="button"
                      variant="ghost"
                      size="sm"
                      className="text-red-600 dark:text-red-400"
                      leftIcon={<Trash2 className="w-4 h-4" />}
                      onClick={() => handleDelete(w)}
                    >
                      {t('common.delete')}
                    </Button>
                  </div>
                </CardContent>
              </Card>
            ))}
          </div>
        )}

        {webhooks.length > 0 && (
          <div className="mt-10">
            <h2 className="text-lg font-semibold text-gray-900 dark:text-white mb-2">
              {t('webhooks.deliveryLog')}
            </h2>
            <p className="text-sm text-gray-500 dark:text-gray-400 mb-4">
              {t('webhooks.deliveryLogHint')}
            </p>
            <Accordion
              type="single"
              collapsible
              value={deliveryOpenId ?? ''}
              onValueChange={(v) => setDeliveryOpenId(v || null)}
              className="rounded-xl border border-gray-200 dark:border-gray-700 bg-surface/40"
            >
              {webhooks.map((w) => (
                <AccordionItem key={w.id} value={w.id} className="px-4">
                  <AccordionTrigger className="hover:no-underline">
                    <span className="flex items-center gap-2 min-w-0">
                      <span className="font-medium truncate">{w.name}</span>
                      <span className="text-xs text-gray-500 font-normal truncate max-w-[200px]">
                        {truncateUrl(w.url, 36)}
                      </span>
                    </span>
                  </AccordionTrigger>
                  <AccordionContent>
                    {deliveryOpenId === w.id && (
                      <div className="space-y-2 pb-4">
                        {deliveriesLoading && (
                          <PageLoader size="sm" message={t('common.loading')} />
                        )}
                        {!deliveriesLoading &&
                          (deliveriesData?.length ? (
                            <ul className="space-y-2">
                              {deliveriesData.map((d) => (
                                <li
                                  key={d.id}
                                  className="rounded-lg border border-gray-100 dark:border-gray-700 p-3 text-xs"
                                >
                                  <div className="flex flex-wrap gap-2 justify-between">
                                    <span className="font-mono text-gray-700 dark:text-gray-300">
                                      {d.id}
                                    </span>
                                    <Badge
                                      size="sm"
                                      variant={d.success ? 'success' : 'error'}
                                    >
                                      {d.success
                                        ? t('webhooks.deliveryOk')
                                        : t('webhooks.deliveryFail')}
                                    </Badge>
                                  </div>
                                  {d.event && (
                                    <p className="mt-1 text-gray-600 dark:text-gray-400 font-mono">
                                      {d.event}
                                    </p>
                                  )}
                                  {d.status_code != null && (
                                    <p className="text-gray-500">
                                      HTTP {d.status_code} · {d.response_time_ms} ms
                                    </p>
                                  )}
                                  {d.error && (
                                    <p className="text-red-600 dark:text-red-400 mt-1">{d.error}</p>
                                  )}
                                  <p className="text-gray-400 mt-1">{d.created_at}</p>
                                </li>
                              ))}
                            </ul>
                          ) : (
                            <p className="text-sm text-gray-500">
                              {t('webhooks.noDeliveries')}
                            </p>
                          ))}
                      </div>
                    )}
                  </AccordionContent>
                </AccordionItem>
              ))}
            </Accordion>
          </div>
        )}

        <Modal isOpen={modalOpen} onClose={() => setModalOpen(false)} size="lg">
          <ModalHeader onClose={() => setModalOpen(false)}>
            {editingId ? t('webhooks.edit') : t('webhooks.create')}
          </ModalHeader>
          <ModalBody className="space-y-4 max-h-[70vh] overflow-y-auto">
            <div>
              <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">
                {t('webhooks.fields.name')}
              </label>
              <Input
                value={form.name}
                onChange={(e) => setForm((f) => ({ ...f, name: e.target.value }))}
              />
            </div>
            <div>
              <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">
                {t('webhooks.fields.url')}
              </label>
              <Input
                value={form.url}
                onChange={(e) => setForm((f) => ({ ...f, url: e.target.value }))}
                placeholder={t('integrations.placeholderUrl')}
              />
            </div>
            <div>
              <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-2">
                {t('webhooks.fields.events')}
              </label>
              <div className="grid grid-cols-1 sm:grid-cols-2 gap-2 max-h-52 overflow-y-auto rounded-lg border border-gray-200 dark:border-gray-700 p-3">
                {WEBHOOK_EVENT_OPTIONS.map((ev) => (
                  <label key={ev} className="flex items-center gap-2 text-sm cursor-pointer">
                    <input
                      type="checkbox"
                      className="rounded border-gray-300"
                      checked={form.events.includes(ev)}
                      onChange={(e) => {
                        setForm((f) => ({
                          ...f,
                          events: e.target.checked
                            ? [...f.events, ev]
                            : f.events.filter((x) => x !== ev),
                        }));
                      }}
                    />
                    <span className="font-mono text-xs">{ev}</span>
                  </label>
                ))}
              </div>
            </div>
            <div>
              <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">
                {t('webhooks.fields.description')}
              </label>
              <Textarea
                value={form.description}
                onChange={(e) => setForm((f) => ({ ...f, description: e.target.value }))}
                rows={2}
              />
            </div>
            <div>
              <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">
                {t('webhooks.fields.secret')}
              </label>
              <Input
                type="password"
                value={form.secret}
                onChange={(e) => setForm((f) => ({ ...f, secret: e.target.value }))}
                placeholder={editingId ? t('webhooks.secretOptional') : ''}
                autoComplete="off"
              />
            </div>
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
              <div>
                <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">
                  {t('webhooks.fields.retryCount')}
                </label>
                <Input
                  type="number"
                  min={0}
                  max={10}
                  value={form.retry_count}
                  onChange={(e) =>
                    setForm((f) => ({ ...f, retry_count: Number(e.target.value) }))
                  }
                />
              </div>
              <div>
                <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">
                  {t('webhooks.fields.timeoutSeconds')}
                </label>
                <Input
                  type="number"
                  min={5}
                  max={120}
                  value={form.timeout_seconds}
                  onChange={(e) =>
                    setForm((f) => ({ ...f, timeout_seconds: Number(e.target.value) }))
                  }
                />
              </div>
            </div>
            {editingId && detail && (
              <div className="text-xs text-gray-500 space-y-1 border-t border-gray-200 dark:border-gray-700 pt-3">
                {(detail as WebhookDetail).last_error && (
                  <p className="text-red-600 dark:text-red-400">
                    {t('webhooks.lastError')}: {(detail as WebhookDetail).last_error}
                  </p>
                )}
              </div>
            )}
          </ModalBody>
          <ModalFooter>
            <Button variant="secondary" onClick={() => setModalOpen(false)}>
              {t('common.cancel')}
            </Button>
            <Button
              onClick={handleSave}
              loading={createMutation.isPending || updateMutation.isPending}
            >
              {t('common.save')}
            </Button>
          </ModalFooter>
        </Modal>
    </PageShell>
  );
}
