import { useEffect, useMemo, useState } from 'react';
import { useTranslation } from 'react-i18next';
import {
  Plus,
  Trash2,
  Settings2,
  Zap,
  CheckCircle2,
  XCircle,
  Circle,
  ExternalLink,
  Activity,
  DollarSign,
  Box,
  Eye,
  Wrench,
  Clock,
  Layers,
  Search,
  RefreshCw,
} from 'lucide-react';
import {
  Card,
  CardHeader,
  CardTitle,
  CardContent,
  Button,
  Input,
  Select,
  Switch,
  Textarea,
  Modal,
  ModalHeader,
  ModalBody,
  ModalFooter,
  Badge,
} from '@/components/ui';
import { useAdminStore } from '@/stores/admin';
import { PageLoader } from '@/components/common/PageLoader';
import { SectionHeader } from '@/components/common/SectionHeader';
import {
  useProviders,
  useCreateProvider,
  useUpdateProvider,
  useDeleteProvider,
  useTestProvider,
  usePresets,
  useDefaultModel,
  useSetDefaultModel,
  useModelUsageSummary,
  useDiscoverProviderModels,
  useSpeedTestProvider,
  useCheckAllProvidersHealth,
  useProviderUsage,
  useRequestLogs,
} from '@/hooks/useAdmin';
import type {
  DeepSeekBalanceResponse,
  ModelProvider,
  ModelProviderFormData,
  ProviderType,
  PresetInfo,
  TestResult,
  ProviderModelInfo,
  ModelUsageRow,
  DiscoveredModel,
  SpeedTestResult,
} from '@/types/admin';
import { adminApi } from '@/api/admin';
import { cn, parseApiDateTime } from '@/lib/utils';

// ---------------------------------------------------------------------------
// Provider branding: colors + icons per type
// ---------------------------------------------------------------------------

const PROVIDER_BRAND: Record<
  string,
  { bg: string; text: string; border: string; letter: string }
> = {
  openai: {
    bg: 'bg-emerald-100 dark:bg-emerald-900/30',
    text: 'text-emerald-700 dark:text-emerald-400',
    border: 'border-emerald-200 dark:border-emerald-800',
    letter: 'O',
  },
  anthropic: {
    bg: 'bg-orange-100 dark:bg-orange-900/30',
    text: 'text-orange-700 dark:text-orange-400',
    border: 'border-orange-200 dark:border-orange-800',
    letter: 'A',
  },
  qwen: {
    bg: 'bg-sky-100 dark:bg-sky-900/30',
    text: 'text-sky-800 dark:text-sky-400',
    border: 'border-sky-200 dark:border-sky-800',
    letter: 'Q',
  },
  dashscope: {
    bg: 'bg-sky-100 dark:bg-sky-900/30',
    text: 'text-sky-800 dark:text-sky-400',
    border: 'border-sky-200 dark:border-sky-800',
    letter: 'D',
  },
  deepseek: {
    bg: 'bg-blue-100 dark:bg-blue-900/30',
    text: 'text-blue-700 dark:text-blue-400',
    border: 'border-blue-200 dark:border-blue-800',
    letter: 'DS',
  },
  ollama: {
    bg: 'bg-gray-100 dark:bg-surface',
    text: 'text-gray-700 dark:text-gray-300',
    border: 'border-gray-200 dark:border-gray-700',
    letter: 'L',
  },
  custom: {
    bg: 'bg-slate-100 dark:bg-slate-800',
    text: 'text-slate-700 dark:text-slate-300',
    border: 'border-slate-200 dark:border-slate-700',
    letter: 'C',
  },
  azure: {
    bg: 'bg-sky-100 dark:bg-sky-900/30',
    text: 'text-sky-700 dark:text-sky-400',
    border: 'border-sky-200 dark:border-sky-800',
    letter: 'Az',
  },
};

const DEFAULT_BRAND: { bg: string; text: string; border: string; letter: string } = {
  bg: 'bg-slate-100 dark:bg-slate-800',
  text: 'text-slate-700 dark:text-slate-300',
  border: 'border-slate-200 dark:border-slate-700',
  letter: 'C',
};

function getBrand(type: string): (typeof PROVIDER_BRAND)[string] {
  return PROVIDER_BRAND[type] ?? DEFAULT_BRAND;
}

function ProviderIconMark({
  type,
  label,
  compact,
}: {
  type: string;
  label: string;
  compact?: boolean;
}) {
  const brand = getBrand(type);
  const common = compact ? 'h-3.5 w-3.5' : 'h-5 w-5';
  if (type === 'openai') {
    return <Activity className={common} aria-label={label} />;
  }
  if (type === 'anthropic') {
    return <Box className={common} aria-label={label} />;
  }
  if (type === 'ollama') {
    return <Wrench className={common} aria-label={label} />;
  }
  if (type === 'vllm') {
    return <Layers className={common} aria-label={label} />;
  }
  if (type === 'qwen' || type === 'dashscope') {
    return <Zap className={common} aria-label={label} />;
  }
  return <span aria-label={label}>{brand.letter}</span>;
}

function providerCategory(type: string): string {
  if (['qwen', 'dashscope', 'deepseek'].includes(type)) return 'China Cloud';
  if (['ollama', 'vllm'].includes(type)) return 'Local';
  if (['custom', 'azure'].includes(type)) return 'Custom';
  return 'Official Cloud';
}

// ---------------------------------------------------------------------------
// Formatting helpers
// ---------------------------------------------------------------------------

function formatCompactNumber(n: number | null | undefined): string {
  if (n == null || !Number.isFinite(n)) return '0';
  if (n < 1000) return String(n);
  if (n < 1_000_000) return `${(n / 1000).toFixed(n < 10_000 ? 1 : 0)}k`;
  if (n < 1_000_000_000) return `${(n / 1_000_000).toFixed(n < 10_000_000 ? 1 : 0)}M`;
  return `${(n / 1_000_000_000).toFixed(1)}B`;
}

function formatContext(ctx: number | undefined): string {
  if (!ctx) return '—';
  if (ctx >= 1_000_000) return `${(ctx / 1_000_000).toFixed(ctx % 1_000_000 === 0 ? 0 : 1)}M`;
  if (ctx >= 1000) return `${Math.round(ctx / 1000)}k`;
  return String(ctx);
}

function formatPrice(usd: number | undefined): string {
  if (!usd) return '—';
  return `$${usd.toFixed(usd < 1 ? 2 : 2)}`;
}

type DeepSeekBalanceStatus =
  | { state: 'loading' }
  | { state: 'success'; data: DeepSeekBalanceResponse }
  | { state: 'error'; error: string };

function formatDeepSeekBalance(data: DeepSeekBalanceResponse): string {
  const balances = data.balance_infos
    .map((item) => {
      const total = item.total_balance || item.topped_up_balance || item.granted_balance;
      return total ? `${total} ${item.currency}`.trim() : '';
    })
    .filter(Boolean);

  return balances.length > 0 ? balances.join(' · ') : '—';
}

/** Preset catalog entry from GET /models/presets (same shape as ProviderModelInfo). */
function presetRowToFormModel(m: ProviderModelInfo): ProviderModelInfo {
  return {
    name: m.name,
    tier: m.tier ?? '',
    context_window: m.context_window ?? 0,
    enabled: m.enabled !== false,
    description: m.description,
    price_input_per_1m: m.price_input_per_1m,
    price_output_per_1m: m.price_output_per_1m,
    supports_tools: m.supports_tools,
    supports_vision: m.supports_vision,
  };
}

function parseFreeformModelIds(input: string): string[] {
  return input
    .split(/\r?\n|,/g)
    .map((s) => s.trim())
    .filter(Boolean);
}

function formatRelativeTime(iso: string | null | undefined, t: (k: string, p?: Record<string, unknown>) => string): string {
  if (!iso) return t('admin.provider.neverUsed');
  const now = Date.now();
  const then = parseApiDateTime(iso).getTime();
  const diffSec = Math.max(0, Math.floor((now - then) / 1000));
  if (diffSec < 60) return t('admin.provider.justNow');
  if (diffSec < 3600) return t('admin.provider.minutesAgo', { n: Math.floor(diffSec / 60) });
  if (diffSec < 86_400) return t('admin.provider.hoursAgo', { n: Math.floor(diffSec / 3600) });
  const days = Math.floor(diffSec / 86_400);
  return t('admin.provider.daysAgo', { n: days });
}

// ---------------------------------------------------------------------------
// Health status dot
// ---------------------------------------------------------------------------

function HealthDot({
  status,
  size = 'md',
}: {
  status: boolean | null;
  size?: 'sm' | 'md';
}) {
  const cls = size === 'sm' ? 'w-3 h-3' : 'w-4 h-4';
  if (status === true) return <CheckCircle2 className={cn(cls, 'text-green-500')} />;
  if (status === false) return <XCircle className={cn(cls, 'text-red-500')} />;
  return <Circle className={cn(cls, 'text-gray-300 dark:text-gray-600')} />;
}

// ---------------------------------------------------------------------------
// Summary stats strip
// ---------------------------------------------------------------------------

interface StatCardProps {
  label: string;
  value: string | number;
  hint?: string;
  icon: React.ReactNode;
  accent?: string;
}

function StatCard({ label, value, hint, icon, accent = 'text-primary-600 dark:text-primary-400' }: StatCardProps) {
  return (
    <Card className="p-4">
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0">
          <p className="text-xs font-medium text-gray-500 dark:text-gray-400 uppercase tracking-wide">
            {label}
          </p>
          <p className="mt-1 text-2xl font-semibold text-gray-900 dark:text-white truncate">
            {value}
          </p>
          {hint && (
            <p className="mt-0.5 text-xs text-gray-500 dark:text-gray-400 truncate">{hint}</p>
          )}
        </div>
        <div className={cn('w-10 h-10 rounded-xl flex items-center justify-center bg-gray-50 dark:bg-surface-elevated', accent)}>
          {icon}
        </div>
      </div>
    </Card>
  );
}

// ---------------------------------------------------------------------------
// Default empty form
// ---------------------------------------------------------------------------

const EMPTY_FORM: ModelProviderFormData = {
  name: '',
  type: 'deepseek',
  base_url: '',
  api_key: '',
  models: [],
  enabled: true,
};

// ---------------------------------------------------------------------------
// Main component
// ---------------------------------------------------------------------------

export function ModelProviderConfig() {
  const { t } = useTranslation();
  const { data: providers, isLoading } = useProviders();
  const { data: presets } = usePresets();
  const { data: defaultModel } = useDefaultModel();
  const { data: usage } = useModelUsageSummary(30);
  const { data: providerUsage } = useProviderUsage(30);
  const { data: requestLogs } = useRequestLogs(7, 20);
  const createProvider = useCreateProvider();
  const updateProvider = useUpdateProvider();
  const deleteProvider = useDeleteProvider();
  const testProvider = useTestProvider();
  const discoverModels = useDiscoverProviderModels();
  const speedTestProvider = useSpeedTestProvider();
  const checkAllProviders = useCheckAllProvidersHealth();
  const setDefaultModel = useSetDefaultModel();

  const {
    selectedProvider,
    setSelectedProvider,
    isProviderModalOpen,
    setProviderModalOpen,
  } = useAdminStore();

  // Local UI state for the currently focused provider in the left pane. We
  // separate this from `selectedProvider` (which is reused by the add/edit
  // modal) so opening a modal doesn't wipe the detail pane.
  const [focusedProviderName, setFocusedProviderName] = useState<string | null>(null);

  const focusedProvider = useMemo(() => {
    if (!providers || providers.length === 0) return null;
    const name = focusedProviderName
      ?? providers.find((p) => p.enabled)?.name
      ?? providers[0]?.name;
    return providers.find((p) => p.name === name) ?? providers[0] ?? null;
  }, [providers, focusedProviderName]);

  // Add/edit modal state
  const [formData, setFormData] = useState<ModelProviderFormData>({ ...EMPTY_FORM });
  const [modelsInput, setModelsInput] = useState('');
  const [formError, setFormError] = useState('');
  const [testResult, setTestResult] = useState<TestResult | null>(null);
  const [discoveredModels, setDiscoveredModels] = useState<DiscoveredModel[]>([]);
  const [speedResults, setSpeedResults] = useState<SpeedTestResult[]>([]);
  const [providerSearch, setProviderSearch] = useState('');
  const [providerSort, setProviderSort] = useState<'custom' | 'name' | 'health' | 'usage'>('custom');
  const [step, setStep] = useState<'type' | 'config'>('type');

  const presetCatalog = useMemo(() => {
    const p = presets?.find((x) => x.type === formData.type);
    return p?.models?.length ? p.models : [];
  }, [presets, formData.type]);

  const usePresetModelMultiselect = presetCatalog.length > 0;

  const usageByModel = useMemo(() => {
    const map: Record<string, ModelUsageRow> = {};
    for (const row of usage?.rows ?? []) map[row.model] = row;
    return map;
  }, [usage]);

  const usageByProvider = useMemo(() => {
    const map: Record<string, number> = {};
    for (const row of providerUsage ?? []) map[row.provider_name] = row.request_count;
    return map;
  }, [providerUsage]);

  const filteredProviders = useMemo(() => {
    const q = providerSearch.trim().toLowerCase();
    const rows = [...(providers ?? [])].filter((p) => {
      if (!q) return true;
      return [p.name, p.label, p.type, p.base_url].some((v) => (v || '').toLowerCase().includes(q));
    });
    if (providerSort === 'name') rows.sort((a, b) => a.name.localeCompare(b.name));
    if (providerSort === 'health') {
      rows.sort((a, b) => Number(b.is_healthy === true) - Number(a.is_healthy === true));
    }
    if (providerSort === 'usage') {
      rows.sort((a, b) => (usageByProvider[b.name] ?? 0) - (usageByProvider[a.name] ?? 0));
    }
    return rows;
  }, [providerSearch, providerSort, providers, usageByProvider]);

  // ------------------------------------------------------------------------
  // Summary stats derivations
  // ------------------------------------------------------------------------

  const enabledProviders = providers?.filter((p) => p.enabled) ?? [];
  const healthyCount = providers?.filter((p) => p.is_healthy === true).length ?? 0;
  const unhealthyCount = providers?.filter((p) => p.is_healthy === false).length ?? 0;
  const unknownHealthCount = (providers?.length ?? 0) - healthyCount - unhealthyCount;
  const totalModels = providers?.reduce((sum, p) => sum + p.models.length, 0) ?? 0;
  const enabledModels = providers?.reduce(
    (sum, p) => sum + p.models.filter((m) => m.enabled !== false).length,
    0,
  ) ?? 0;

  // ------------------------------------------------------------------------
  // Modal handlers
  // ------------------------------------------------------------------------

  const applyPreset = (preset: PresetInfo) => {
    setFormData({
      ...EMPTY_FORM,
      type: preset.type as ProviderType,
      base_url: preset.default_base_url,
      models: preset.models.map((m) => presetRowToFormModel(m)),
    });
    setModelsInput(preset.models.map((m) => m.name).join('\n'));
    setFormError('');
    setStep('config');
  };

  const handleOpenCreate = () => {
    setSelectedProvider(null);
    setFormData({ ...EMPTY_FORM });
    setModelsInput('');
    setFormError('');
    setTestResult(null);
    setDiscoveredModels([]);
    setSpeedResults([]);
    setStep('type');
    setProviderModalOpen(true);
  };

  const handleOpenEdit = (provider: ModelProvider) => {
    setSelectedProvider(provider);
    setFormData({
      name: provider.name,
      type: provider.type,
      base_url: provider.base_url,
      api_key: '',
      // Preserve the full model payload (pricing, description, enabled…) so
      // that saving the modal does not accidentally strip those fields.
      models: provider.models.map((m) => ({ ...m })),
      enabled: provider.enabled,
      metadata: provider.metadata ?? {},
    });
    setModelsInput(provider.models.map((m) => m.name).join('\n'));
    setFormError('');
    setTestResult(null);
    setDiscoveredModels([]);
    setSpeedResults([]);
    setStep('config');
    setProviderModalOpen(true);
  };

  const handleClose = () => {
    setProviderModalOpen(false);
    setSelectedProvider(null);
    setFormData({ ...EMPTY_FORM });
    setModelsInput('');
    setFormError('');
    setTestResult(null);
    setDiscoveredModels([]);
    setSpeedResults([]);
    setStep('type');
  };

  const togglePresetCatalogModel = (catalogRow: ProviderModelInfo) => {
    setFormError('');
    const name = catalogRow.name;
    const has = (formData.models ?? []).some((m) => m.name === name);
    if (has) {
      setFormData((prev) => ({
        ...prev,
        models: (prev.models ?? []).filter((m) => m.name !== name),
      }));
    } else {
      setFormData((prev) => ({
        ...prev,
        models: [...(prev.models ?? []), presetRowToFormModel(catalogRow)],
      }));
    }
  };

  const handleSubmit = async () => {
    setFormError('');
    let models: ProviderModelInfo[];

    if (usePresetModelMultiselect) {
      const selected = formData.models ?? [];
      if (selected.length === 0) {
        setFormError(t('admin.provider.atLeastOneModel'));
        return;
      }
      const seen = new Set<string>();
      models = [];
      for (const m of selected) {
        if (seen.has(m.name)) continue;
        seen.add(m.name);
        models.push({
          name: m.name,
          tier: m.tier ?? '',
          context_window: m.context_window ?? 0,
          enabled: m.enabled,
          description: m.description,
          price_input_per_1m: m.price_input_per_1m,
          price_output_per_1m: m.price_output_per_1m,
          supports_tools: m.supports_tools,
          supports_vision: m.supports_vision,
        });
      }
      if (models.length === 0) {
        setFormError(t('admin.provider.atLeastOneModel'));
        return;
      }
    } else {
      const ids = parseFreeformModelIds(modelsInput);
      if (ids.length === 0) {
        setFormError(t('admin.provider.atLeastOneModel'));
        return;
      }
      const seen = new Set<string>();
      models = [];
      for (const name of ids) {
        if (seen.has(name)) {
          setFormError(t('admin.provider.duplicateModelName', { name }));
          return;
        }
        seen.add(name);
        const existing = formData.models?.find((m) => m.name === name);
        models.push(
          existing
            ? {
                name: existing.name,
                tier: existing.tier ?? '',
                context_window: existing.context_window ?? 0,
                enabled: existing.enabled,
                description: existing.description,
                price_input_per_1m: existing.price_input_per_1m,
                price_output_per_1m: existing.price_output_per_1m,
                supports_tools: existing.supports_tools,
                supports_vision: existing.supports_vision,
              }
            : { name, tier: '', context_window: 0 }
        );
      }
    }

    const payload: ModelProviderFormData = { ...formData, models };
    const warnings: string[] = [];
    if (requiresApiKey && !selectedProvider && !payload.api_key?.trim()) {
      warnings.push(t('admin.provider.softValidation.missingApiKey'));
    }
    if (showBaseUrl && !payload.base_url?.trim()) {
      warnings.push(t('admin.provider.softValidation.missingBaseUrl'));
    }
    if (warnings.length > 0 && !window.confirm(warnings.join('\n') + `\n\n${t('admin.provider.softValidation.saveAnyway')}`)) {
      return;
    }

    try {
      if (selectedProvider) {
        await updateProvider.mutateAsync({ name: selectedProvider.name, data: payload });
      } else {
        await createProvider.mutateAsync(payload);
        setFocusedProviderName(payload.name);
      }
      handleClose();
    } catch (e) {
      const msg = e instanceof Error ? e.message : String(e);
      setFormError(msg);
    }
  };

  const handleDelete = async (name: string) => {
    if (window.confirm(t('admin.provider.confirmDelete'))) {
      await deleteProvider.mutateAsync(name);
      if (focusedProviderName === name) setFocusedProviderName(null);
    }
  };

  const handleTest = async (name: string) => {
    setTestResult(null);
    try {
      const result = await testProvider.mutateAsync(name);
      setTestResult(result);
    } catch (error) {
      setTestResult({
        provider_name: name,
        model: '',
        is_healthy: false,
        latency_ms: 0,
        error: (error as Error).message,
      });
    }
  };

  const handleDiscoverModels = async () => {
    if (!selectedProvider) return;
    setFormError('');
    try {
      const rows = await discoverModels.mutateAsync(selectedProvider.name);
      setDiscoveredModels(rows);
    } catch (error) {
      setFormError(error instanceof Error ? error.message : String(error));
    }
  };

  const handleAddDiscoveredModel = (row: DiscoveredModel) => {
    const modelName = row.name || row.id;
    if (!modelName || (formData.models ?? []).some((m) => m.name === modelName)) return;
    const next = [...(formData.models ?? []), { name: modelName, tier: '', context_window: 0 }];
    setFormData((prev) => ({ ...prev, models: next }));
    setModelsInput(next.map((m) => m.name).join('\n'));
  };

  const handleSpeedTest = async () => {
    if (!selectedProvider) return;
    const candidates = [
      formData.base_url,
      selectedProvider.base_url,
      ...(Array.isArray(selectedProvider.metadata?.endpoint_candidates)
        ? selectedProvider.metadata.endpoint_candidates as string[]
        : []),
    ].filter((v): v is string => Boolean(v && v.trim()));
    if (candidates.length === 0) {
      setFormError(t('admin.provider.speedTest.noCandidates'));
      return;
    }
    try {
      const rows = await speedTestProvider.mutateAsync({ name: selectedProvider.name, candidates });
      setSpeedResults(rows);
      const fastest = rows.find((r) => r.ok);
      if (fastest) setFormData((prev) => ({ ...prev, base_url: fastest.url }));
    } catch (error) {
      setFormError(error instanceof Error ? error.message : String(error));
    }
  };

  // Per-model enable toggle: preserves all other model fields.
  const handleToggleModel = async (provider: ModelProvider, model: ProviderModelInfo) => {
    const nextModels = provider.models.map((m) => {
      if (m.name !== model.name) return m;
      return { ...m, enabled: m.enabled === false ? true : false };
    });
    await updateProvider.mutateAsync({
      name: provider.name,
      data: { models: nextModels },
    });
  };

  const handleSetDefaultModel = (providerName: string, modelName: string) => {
    setDefaultModel.mutate({ provider: providerName, model: modelName });
  };

  // Determine if type requires api_key in modal
  const currentPreset = presets?.find((p) => p.type === formData.type);
  const requiresApiKey = currentPreset?.requires_api_key ?? !['ollama'].includes(formData.type);
  const showBaseUrl = ['ollama', 'custom', 'azure', 'deepseek', 'qwen'].includes(formData.type)
    || formData.type === 'openai';

  if (isLoading) {
    return (
      <div className="flex items-center justify-center py-12">
        <PageLoader size="sm" message={t('common.loading')} />
      </div>
    );
  }

  // ------------------------------------------------------------------------
  // Render
  // ------------------------------------------------------------------------

  return (
    <div className="space-y-6">
      <SectionHeader
        titleAs="h2"
        title={t('admin.provider.title')}
        description={t('admin.provider.description')}
        titleClassName="text-xl"
        actions={
          <div className="flex gap-2">
            <Button
              size="sm"
              variant="secondary"
              leftIcon={<RefreshCw className="w-4 h-4" aria-hidden />}
              loading={checkAllProviders.isPending}
              onClick={() => checkAllProviders.mutate()}
            >
              {t('admin.provider.health.checkAll')}
            </Button>
            <Button
              size="sm"
              leftIcon={<Plus className="w-4 h-4" aria-hidden />}
              responsive="md"
              onClick={handleOpenCreate}
            >
              {t('admin.provider.add')}
            </Button>
          </div>
        }
      />

      {/* Summary stats strip */}
      <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-5 gap-4">
        <StatCard
          label={t('admin.provider.stats.providers')}
          value={providers?.length ?? 0}
          hint={t('admin.provider.stats.enabledCount', { n: enabledProviders.length })}
          icon={<Box className="w-5 h-5" />}
        />
        <StatCard
          label={t('admin.provider.stats.models')}
          value={totalModels}
          hint={t('admin.provider.stats.enabledCount', { n: enabledModels })}
          icon={<Layers className="w-5 h-5" />}
        />
        <StatCard
          label={t('admin.provider.stats.healthy')}
          value={healthyCount}
          hint={
            unhealthyCount > 0
              ? t('admin.provider.stats.unhealthyCount', { n: unhealthyCount })
              : unknownHealthCount > 0
              ? t('admin.provider.stats.unknownCount', { n: unknownHealthCount })
              : undefined
          }
          icon={<Activity className="w-5 h-5" />}
          accent="text-green-600 dark:text-green-400"
        />
        <StatCard
          label={t('admin.provider.stats.requests30d')}
          value={formatCompactNumber(usage?.total_requests)}
          hint={
            usage?.avg_latency_ms
              ? t('admin.provider.stats.avgLatency', {
                  ms: Math.round(usage.avg_latency_ms),
                })
              : undefined
          }
          icon={<Zap className="w-5 h-5" />}
          accent="text-amber-600 dark:text-amber-400"
        />
        <StatCard
          label={t('admin.provider.stats.tokens30d')}
          value={formatCompactNumber(usage?.total_tokens)}
          icon={<DollarSign className="w-5 h-5" />}
          accent="text-blue-600 dark:text-blue-400"
        />
      </div>

      {/* Default model card */}
      <Card padding="sm">
        <CardHeader className="mb-0 flex-col items-stretch gap-0 p-0 sm:flex-row sm:items-center sm:justify-between">
          <div className="flex min-w-0 flex-1 flex-col gap-0.5 pb-3 sm:pb-0 sm:pr-4">
            <CardTitle className="text-sm font-semibold leading-tight">
              {t('admin.provider.defaultModel.title')}
            </CardTitle>
            <p className="text-[11px] leading-snug text-gray-500 dark:text-gray-400">
              {t('admin.provider.defaultModel.desc')}
            </p>
          </div>
          <div className="relative w-full shrink-0 sm:w-auto sm:max-w-md">
            <Select
              value={
                defaultModel?.provider && defaultModel?.model
                  ? `${defaultModel.provider}/${defaultModel.model}`
                  : ''
              }
              onChange={(e) => {
                const [providerName = '', ...modelParts] = e.target.value.split('/');
                const model = modelParts.join('/');
                if (providerName && model) handleSetDefaultModel(providerName, model);
              }}
              className="h-9 max-w-md py-1.5 sm:min-w-[16rem]"
            >
                <option value="">{t('admin.provider.defaultModel.selectPlaceholder')}</option>
                {enabledProviders.map((p) => (
                  <optgroup key={p.name} label={p.label || p.name}>
                    {p.models
                      .filter((m) => m.enabled !== false)
                      .map((m) => (
                        <option key={`${p.name}/${m.name}`} value={`${p.name}/${m.name}`}>
                          {m.name}
                        </option>
                      ))}
                  </optgroup>
                ))}
              </Select>
          </div>
        </CardHeader>
      </Card>

      {/* Empty state */}
      {(!providers || providers.length === 0) && (
        <Card>
          <CardContent className="py-16 text-center">
            <div className="w-16 h-16 mx-auto mb-4 rounded-full bg-gray-100 dark:bg-surface flex items-center justify-center">
              <Zap className="w-8 h-8 text-gray-400" />
            </div>
            <p className="text-gray-500 dark:text-gray-400 mb-1">{t('admin.provider.empty')}</p>
            <p className="text-sm text-gray-400 dark:text-gray-500 mb-4">
              {t('admin.provider.emptyHint')}
            </p>
            <Button onClick={handleOpenCreate} leftIcon={<Plus className="w-4 h-4" />}>
              {t('admin.provider.add')}
            </Button>
          </CardContent>
        </Card>
      )}

      {/* Main split layout: provider list + detail panel */}
      {providers && providers.length > 0 && (
        <div className="grid gap-4 lg:grid-cols-[240px_1fr]">
          {/* Left pane: provider list */}
          <Card padding="sm" className="h-fit min-w-0 w-full overflow-hidden lg:sticky lg:top-4">
            <div className="space-y-2">
              <h3 className="text-[11px] font-medium uppercase tracking-wide text-gray-500 dark:text-gray-400">
                {t('admin.provider.listTitle')}
              </h3>
              <div className="flex gap-1.5">
                <div className="relative min-w-0 flex-1">
                  <Search className="absolute left-2 top-1/2 h-3.5 w-3.5 -translate-y-1/2 text-gray-400" />
                  <Input
                    className="h-8 pl-7 text-xs"
                    value={providerSearch}
                    onChange={(e) => setProviderSearch(e.target.value)}
                    placeholder={t('admin.provider.searchPlaceholder')}
                  />
                </div>
                <Select
                  value={providerSort}
                  onChange={(e) => setProviderSort(e.target.value as typeof providerSort)}
                  className="h-8 w-[4.5rem] shrink-0 px-1.5 text-xs"
                >
                  <option value="custom">{t('admin.provider.sort.custom')}</option>
                  <option value="name">{t('admin.provider.sort.name')}</option>
                  <option value="health">{t('admin.provider.sort.health')}</option>
                  <option value="usage">{t('admin.provider.sort.usage')}</option>
                </Select>
              </div>
              <div className="space-y-0.5">
                {filteredProviders.map((p, idx) => {
                  const brand = getBrand(p.type);
                  const isSelected = focusedProvider?.name === p.name;
                  const circuit = p.metadata?.circuit as { state?: string } | undefined;
                  const enabledModels = p.models.filter((m) => m.enabled !== false).length;
                  return (
                    <button
                      key={p.name}
                      type="button"
                      onClick={() => setFocusedProviderName(p.name)}
                      className={cn(
                        'flex w-full items-center gap-2 rounded-md px-2 py-1.5 text-left ring-1 ring-inset transition-colors',
                        isSelected
                          ? 'bg-primary-50 ring-primary-300 dark:bg-primary-900/20 dark:ring-primary-800'
                          : 'ring-transparent hover:bg-gray-50 dark:hover:bg-gray-800/60',
                        !p.enabled && 'opacity-60',
                      )}
                    >
                      <div
                        className={cn(
                          'flex h-7 w-7 shrink-0 items-center justify-center rounded-md text-[10px] font-bold',
                          brand.bg,
                          brand.text,
                        )}
                      >
                        <ProviderIconMark
                          type={p.type}
                          label={p.label || p.name}
                          compact
                        />
                      </div>
                      <div className="min-w-0 flex-1">
                        <div className="flex items-center gap-1">
                          <span className="truncate text-xs font-medium text-gray-900 dark:text-white">
                            {p.name}
                          </span>
                          <HealthDot status={p.is_healthy} size="sm" />
                          {circuit?.state === 'open' && (
                            <span className="shrink-0 rounded bg-yellow-100 px-1 text-[10px] font-medium text-yellow-800 dark:bg-yellow-900/40 dark:text-yellow-300">
                              CB
                            </span>
                          )}
                        </div>
                        <p className="truncate text-[10px] leading-tight text-gray-500 dark:text-gray-400">
                          {p.label}
                          {' · '}
                          {t('admin.provider.modelCount', { n: p.models.length })}
                          {' · '}
                          {t('admin.provider.enabledModelRatio', {
                            enabled: enabledModels,
                            total: p.models.length,
                          })}
                          {providerSort === 'usage' &&
                            ` · ${formatCompactNumber(usageByProvider[p.name] ?? 0)}`}
                        </p>
                      </div>
                      <div className="flex shrink-0 flex-col items-end gap-0.5">
                        {idx < 9 && (
                          <span className="font-mono text-[10px] leading-none text-gray-400 dark:text-gray-500">
                            P{idx + 1}
                          </span>
                        )}
                        <span
                          className={cn(
                            'text-[10px] leading-none',
                            p.enabled
                              ? 'text-green-600 dark:text-green-400'
                              : 'text-gray-400 dark:text-gray-500',
                          )}
                          title={
                            p.enabled
                              ? t('admin.provider.enabled')
                              : t('admin.provider.disabled')
                          }
                        >
                          {p.enabled ? '●' : '○'}
                        </span>
                      </div>
                    </button>
                  );
                })}
              </div>
            </div>
          </Card>

          {/* Right pane: provider details */}
          {focusedProvider && (
            <ProviderDetailPanel
              provider={focusedProvider}
              usageByModel={usageByModel}
              defaultModel={defaultModel ?? null}
              onEdit={() => handleOpenEdit(focusedProvider)}
              onTest={() => handleTest(focusedProvider.name)}
              onDelete={() => handleDelete(focusedProvider.name)}
              onToggleModel={(m) => handleToggleModel(focusedProvider, m)}
              onSetDefault={(m) => handleSetDefaultModel(focusedProvider.name, m.name)}
              testing={testProvider.isPending}
              updating={updateProvider.isPending}
            />
          )}
        </div>
      )}

      {/* Usage table */}
      {usage && usage.rows.length > 0 && (
        <Card>
          <CardHeader className="pb-3">
            <div className="flex items-center justify-between">
              <div>
                <CardTitle className="text-base">
                  {t('admin.provider.usage.title')}
                </CardTitle>
                <p className="text-xs text-gray-500 dark:text-gray-400 mt-0.5">
                  {t('admin.provider.usage.desc', { days: usage.days })}
                </p>
              </div>
            </div>
          </CardHeader>
          <CardContent className="pt-0 overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="text-left text-xs font-medium text-gray-500 dark:text-gray-400 uppercase tracking-wide border-b border-gray-200 dark:border-gray-700">
                  <th className="py-2 pr-4">{t('admin.provider.usage.model')}</th>
                  <th className="py-2 px-4 text-right">{t('admin.provider.usage.requests')}</th>
                  <th className="py-2 px-4 text-right">{t('admin.provider.usage.inTokens')}</th>
                  <th className="py-2 px-4 text-right">{t('admin.provider.usage.outTokens')}</th>
                  <th className="py-2 px-4 text-right">{t('admin.provider.usage.totalTokens')}</th>
                  <th className="py-2 px-4 text-right">{t('admin.provider.usage.avgLatency')}</th>
                  <th className="py-2 pl-4">{t('admin.provider.usage.lastUsed')}</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-gray-100 dark:divide-gray-800">
                {usage.rows.slice(0, 20).map((row) => (
                  <tr key={row.model}>
                    <td className="py-2 pr-4 font-mono text-xs text-gray-900 dark:text-white truncate max-w-xs">
                      {row.model}
                    </td>
                    <td className="py-2 px-4 text-right tabular-nums">
                      {formatCompactNumber(row.request_count)}
                    </td>
                    <td className="py-2 px-4 text-right tabular-nums text-gray-600 dark:text-gray-400">
                      {formatCompactNumber(row.total_input_tokens)}
                    </td>
                    <td className="py-2 px-4 text-right tabular-nums text-gray-600 dark:text-gray-400">
                      {formatCompactNumber(row.total_output_tokens)}
                    </td>
                    <td className="py-2 px-4 text-right tabular-nums font-medium">
                      {formatCompactNumber(row.total_tokens)}
                    </td>
                    <td className="py-2 px-4 text-right tabular-nums text-gray-600 dark:text-gray-400">
                      {row.avg_latency_ms ? `${Math.round(row.avg_latency_ms)} ms` : '—'}
                    </td>
                    <td className="py-2 pl-4 text-xs text-gray-500 dark:text-gray-400">
                      {formatRelativeTime(row.last_used_at, t)}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </CardContent>
        </Card>
      )}

      {requestLogs && requestLogs.length > 0 && (
        <Card>
          <CardHeader className="pb-3">
            <CardTitle className="text-base">{t('admin.provider.requestLog.title')}</CardTitle>
            <p className="text-xs text-gray-500 dark:text-gray-400">
              {t('admin.provider.requestLog.desc')}
            </p>
          </CardHeader>
          <CardContent className="pt-0 overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-gray-200 text-left text-xs uppercase tracking-wide text-gray-500 dark:border-gray-700 dark:text-gray-400">
                  <th className="py-2 pr-4">{t('admin.provider.requestLog.time')}</th>
                  <th className="py-2 px-4">{t('admin.provider.requestLog.provider')}</th>
                  <th className="py-2 px-4">{t('admin.provider.requestLog.model')}</th>
                  <th className="py-2 px-4 text-right">{t('admin.provider.requestLog.tokens')}</th>
                  <th className="py-2 px-4 text-right">{t('admin.provider.requestLog.cost')}</th>
                  <th className="py-2 pl-4 text-right">{t('admin.provider.requestLog.latency')}</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-gray-100 dark:divide-gray-800">
                {requestLogs.map((row) => (
                  <tr key={row.id}>
                    <td className="py-2 pr-4 text-xs text-gray-500">
                      {formatRelativeTime(row.created_at, t)}
                    </td>
                    <td className="py-2 px-4">{row.provider_name}</td>
                    <td className="py-2 px-4 font-mono text-xs">{row.model}</td>
                    <td className="py-2 px-4 text-right tabular-nums">
                      {formatCompactNumber(row.input_tokens + row.output_tokens)}
                    </td>
                    <td className="py-2 px-4 text-right tabular-nums">
                      ${row.total_cost_usd.toFixed(4)}
                    </td>
                    <td className="py-2 pl-4 text-right tabular-nums">
                      {Math.round(row.latency_ms)} ms
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </CardContent>
        </Card>
      )}

      {/* Test result toast */}
      {testResult && (
        <div
          className={cn(
            'fixed bottom-6 right-6 z-50 max-w-sm p-4 rounded-xl shadow-lg border',
            testResult.is_healthy
              ? 'bg-green-50 dark:bg-green-900/30 border-green-200 dark:border-green-800 text-green-800 dark:text-green-200'
              : 'bg-red-50 dark:bg-red-900/30 border-red-200 dark:border-red-800 text-red-800 dark:text-red-200',
          )}
        >
          <div className="flex items-start gap-3">
            {testResult.is_healthy ? (
              <CheckCircle2 className="w-5 h-5 text-green-500 shrink-0 mt-0.5" />
            ) : (
              <XCircle className="w-5 h-5 text-red-500 shrink-0 mt-0.5" />
            )}
            <div className="flex-1 min-w-0">
              <p className="font-medium text-sm">
                {testResult.provider_name} &mdash;{' '}
                {testResult.is_healthy ? t('admin.provider.testSuccess') : t('admin.provider.testFailed')}
              </p>
              {testResult.is_healthy && (
                <p className="text-xs mt-0.5 opacity-80">
                  {t('admin.provider.latencyMs', { ms: testResult.latency_ms.toFixed(0) })}
                </p>
              )}
              {testResult.error && (
                <p className="text-xs mt-0.5 opacity-80 truncate">{testResult.error}</p>
              )}
            </div>
            <button
              className="text-current opacity-60 hover:opacity-100"
              onClick={() => setTestResult(null)}
            >
              <XCircle className="w-4 h-4" />
            </button>
          </div>
        </div>
      )}

      {/* Add / Edit Modal */}
      <Modal isOpen={isProviderModalOpen} onClose={handleClose} size="lg">
        <ModalHeader onClose={handleClose}>
          {selectedProvider
            ? `${t('admin.provider.edit')} - ${selectedProvider.name}`
            : t('admin.provider.add')}
        </ModalHeader>
        <ModalBody className="space-y-5">
          {!selectedProvider && step === 'type' && (
            <div className="space-y-3">
              <p className="text-xs text-gray-500 dark:text-gray-400">
                {t('admin.provider.selectTypeDescription')}
              </p>
              <div className="grid grid-cols-1 sm:grid-cols-2 gap-2">
                {(presets ?? []).map((preset) => {
                  const brand = getBrand(preset.type);
                  const isRecommended = ['deepseek', 'qwen'].includes(preset.type);
                  return (
                    <button
                      key={preset.type}
                      className={cn(
                        'group relative flex items-center gap-3 rounded-lg border px-3 py-2.5',
                        'transition-all duration-150',
                        'border-gray-200 dark:border-gray-700',
                        'hover:border-primary-400 dark:hover:border-primary-600 hover:bg-primary-50/50 dark:hover:bg-primary-900/10',
                        'focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary-500/40',
                        isRecommended && 'border-primary-200 dark:border-primary-800/60 bg-primary-50/30 dark:bg-primary-900/5',
                      )}
                      onClick={() => applyPreset(preset)}
                    >
                      <div
                        className={cn(
                          'flex h-9 w-9 shrink-0 items-center justify-center rounded-lg text-sm font-bold',
                          brand.bg,
                          brand.text,
                        )}
                      >
                        <ProviderIconMark type={preset.type} label={preset.label} />
                      </div>
                      <div className="min-w-0 flex-1 text-left">
                        <div className="flex items-center gap-1.5">
                          <span className="text-sm font-medium text-gray-900 dark:text-white truncate">
                            {preset.label}
                          </span>
                          {isRecommended && (
                            <span className="shrink-0 rounded-full bg-primary-100 dark:bg-primary-900/30 px-1.5 py-px text-[10px] font-medium leading-tight text-primary-700 dark:text-primary-300">
                              {t('admin.provider.recommended')}
                            </span>
                          )}
                        </div>
                        <span className="text-[11px] leading-tight text-gray-400 dark:text-gray-500">
                          {preset.models.length > 0
                            ? t('admin.provider.presetModelCount', { count: preset.models.length })
                            : t('admin.provider.customModelsBadge')}
                        </span>
                      </div>
                      <svg
                        className="h-4 w-4 shrink-0 text-gray-300 dark:text-gray-600 transition-transform group-hover:translate-x-0.5 group-hover:text-primary-400"
                        fill="none"
                        viewBox="0 0 24 24"
                        stroke="currentColor"
                        strokeWidth={2}
                      >
                        <path strokeLinecap="round" strokeLinejoin="round" d="M9 5l7 7-7 7" />
                      </svg>
                    </button>
                  );
                })}
              </div>
            </div>
          )}

          {(selectedProvider || step === 'config') && (
            <>
              <div>
                <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">
                  {t('admin.provider.providerIdLabel')}
                </label>
                <Input
                  value={formData.name}
                  onChange={(e) => setFormData({ ...formData, name: e.target.value })}
                  placeholder={t('admin.provider.nameExample')}
                  disabled={!!selectedProvider}
                />
                {!selectedProvider && (
                  <p className="mt-1 text-xs text-gray-500">
                    {t('admin.provider.idImmutableHint')}
                  </p>
                )}
              </div>

              <div>
                <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">
                  {t('admin.provider.type')}
                </label>
                <Select
                  value={formData.type}
                  onChange={(e) => {
                    const newType = e.target.value as ProviderType;
                    const preset = presets?.find((p) => p.type === newType);
                    setFormError('');
                    if (preset && preset.models.length > 0 && !selectedProvider) {
                      setModelsInput(preset.models.map((m) => m.name).join('\n'));
                      setFormData((prev) => ({
                        ...prev,
                        type: newType,
                        base_url: preset.default_base_url ?? prev.base_url,
                        models: preset.models.map((m) => presetRowToFormModel(m)),
                      }));
                    } else if (!selectedProvider) {
                      setModelsInput('');
                      setFormData((prev) => ({
                        ...prev,
                        type: newType,
                        base_url: preset?.default_base_url ?? prev.base_url,
                        models: [],
                      }));
                    }
                  }}
                  disabled={!!selectedProvider}
                >
                  {(presets ?? []).map((p) => (
                    <option key={p.type} value={p.type}>
                      {p.label}
                    </option>
                  ))}
                </Select>
              </div>

              {requiresApiKey && (
                <div>
                  <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">
                    {t('admin.provider.apiKey')}
                  </label>
                  <Input
                    type="password"
                    value={formData.api_key ?? ''}
                    onChange={(e) => setFormData({ ...formData, api_key: e.target.value })}
                    placeholder={
                      selectedProvider
                        ? t('admin.provider.apiKeyKeepBlank')
                        : t('admin.provider.apiKeyEnter')
                    }
                  />
                  {formData.type === 'qwen' && (
                    <p className="mt-1 text-xs text-gray-500">
                      {t('admin.provider.qwenApiKeyHint')}
                    </p>
                  )}
                  {formData.type === 'deepseek' && (
                    <p className="mt-1 text-xs text-gray-500">
                      {t('admin.provider.deepseekApiKeyHint')}
                    </p>
                  )}
                </div>
              )}

              {showBaseUrl && (
                <div>
                  <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">
                    {t('admin.provider.endpointUrlLabel')}
                  </label>
                  <Input
                    value={formData.base_url ?? ''}
                    onChange={(e) => setFormData({ ...formData, base_url: e.target.value })}
                    placeholder={currentPreset?.default_base_url || 'https://api.example.com/v1'}
                  />
                  {selectedProvider && (
                    <div className="mt-2 space-y-2">
                      <Button
                        type="button"
                        size="sm"
                        variant="secondary"
                        onClick={handleSpeedTest}
                        loading={speedTestProvider.isPending}
                      >
                        {t('admin.provider.speedTest.run')}
                      </Button>
                      {speedResults.length > 0 && (
                        <div className="space-y-1 rounded-lg border border-gray-200 p-2 text-xs dark:border-gray-700">
                          {speedResults.map((r) => (
                            <button
                              key={r.url}
                              type="button"
                              className="flex w-full items-center justify-between gap-2 rounded px-2 py-1 text-left hover:bg-gray-50 dark:hover:bg-gray-800"
                              onClick={() => r.ok && setFormData({ ...formData, base_url: r.url })}
                            >
                              <span className="truncate font-mono">{r.url}</span>
                              <span className={r.ok ? 'text-green-600' : 'text-red-600'}>
                                {r.ok ? `${Math.round(r.latency_ms)} ms` : t('admin.provider.speedTest.failed')}
                              </span>
                            </button>
                          ))}
                        </div>
                      )}
                    </div>
                  )}
                </div>
              )}

              {formData.type === 'qwen' && (
                <div className="space-y-3 rounded-lg border border-sky-200 dark:border-sky-800 bg-sky-50 dark:bg-sky-900/20 p-3">
                  <p className="text-xs font-medium text-sky-700 dark:text-sky-400">
                    {t('admin.provider.qwenSettingsTitle')}
                  </p>
                  <div className="flex items-center justify-between">
                    <label className="text-sm text-gray-700 dark:text-gray-300">
                      {t('admin.provider.qwenEnableSearch')}
                    </label>
                    <Switch
                      checked={formData.extra?.enable_search ?? false}
                      onCheckedChange={(checked) =>
                        setFormData({
                          ...formData,
                          extra: { ...(formData.extra ?? {}), enable_search: checked },
                        })
                      }
                    />
                  </div>
                  <div className="flex items-center justify-between">
                    <label className="text-sm text-gray-700 dark:text-gray-300">
                      {t('admin.provider.qwenEnableThinking')}
                    </label>
                    <Switch
                      checked={formData.extra?.enable_thinking ?? true}
                      onCheckedChange={(checked) =>
                        setFormData({
                          ...formData,
                          extra: { ...(formData.extra ?? {}), enable_thinking: checked },
                        })
                      }
                    />
                  </div>
                  <a
                    href="https://bailian.console.aliyun.com/"
                    target="_blank"
                    rel="noopener noreferrer"
                    className="inline-flex items-center gap-1 text-xs text-sky-600 dark:text-sky-400 hover:underline"
                  >
                    <ExternalLink className="h-3 w-3" />
                    {t('admin.provider.qwenSetupGuide')}
                  </a>
                </div>
              )}

              <div>
                <div className="mb-1 flex items-center justify-between gap-2">
                  <label className="block text-sm font-medium text-gray-700 dark:text-gray-300">
                    {t('admin.provider.availableModelsLabel')}
                  </label>
                  {selectedProvider && (
                    <Button
                      type="button"
                      size="sm"
                      variant="secondary"
                      onClick={handleDiscoverModels}
                      loading={discoverModels.isPending}
                    >
                      {t('admin.provider.discovery.fetch')}
                    </Button>
                  )}
                </div>
                {usePresetModelMultiselect ? (
                  <div className="space-y-2 max-h-56 overflow-y-auto rounded-lg border border-gray-200 dark:border-gray-700 p-3">
                    {presetCatalog.map((m) => {
                      const checked = (formData.models ?? []).some((x) => x.name === m.name);
                      return (
                        <label
                          key={m.name}
                          className="flex items-start gap-2.5 cursor-pointer text-sm text-gray-800 dark:text-gray-200"
                        >
                          <input
                            type="checkbox"
                            className="mt-1 rounded border-gray-300 dark:border-gray-600"
                            checked={checked}
                            onChange={() => togglePresetCatalogModel(m)}
                          />
                          <span>
                            <span className="font-mono text-xs">{m.name}</span>
                            {m.description ? (
                              <span className="block text-xs text-gray-500 dark:text-gray-400 mt-0.5">
                                {m.description}
                              </span>
                            ) : null}
                          </span>
                        </label>
                      );
                    })}
                    <p className="text-xs text-gray-500 dark:text-gray-400 pt-1">
                      {t('admin.provider.modelsCheckboxHelp')}
                    </p>
                  </div>
                ) : (
                  <>
                    <Textarea
                      value={modelsInput}
                      onChange={(e) => {
                        setFormError('');
                        setModelsInput(e.target.value);
                      }}
                      placeholder={t('admin.provider.modelsOnePerLinePlaceholder')}
                      rows={5}
                      className="font-mono text-sm"
                    />
                    <p className="mt-1 text-xs text-gray-500">
                      {t('admin.provider.modelsOnePerLineHelp')}
                    </p>
                  </>
                )}
                {discoveredModels.length > 0 && (
                  <div className="mt-3 max-h-40 space-y-1 overflow-y-auto rounded-lg border border-gray-200 p-2 dark:border-gray-700">
                    {discoveredModels.slice(0, 50).map((row) => (
                      <button
                        key={row.id}
                        type="button"
                        disabled={row.already_configured || (formData.models ?? []).some((m) => m.name === (row.name || row.id))}
                        className="flex w-full items-center justify-between rounded px-2 py-1 text-left text-xs hover:bg-gray-50 disabled:cursor-not-allowed disabled:opacity-50 dark:hover:bg-gray-800"
                        onClick={() => handleAddDiscoveredModel(row)}
                      >
                        <span className="font-mono">{row.name || row.id}</span>
                        <span className="text-gray-500">
                          {row.already_configured ? t('admin.provider.discovery.configured') : row.owned_by}
                        </span>
                      </button>
                    ))}
                  </div>
                )}
                {formError ? (
                  <p className="mt-2 text-sm text-red-600 dark:text-red-400" role="alert">
                    {formError}
                  </p>
                ) : null}
              </div>

              <div className="rounded-lg border border-gray-200 p-3 dark:border-gray-700">
                <p className="mb-3 text-sm font-medium text-gray-700 dark:text-gray-300">
                  {t('admin.provider.advanced.title')}
                </p>
                <div className="grid gap-3 sm:grid-cols-2">
                  <Input
                    placeholder={t('admin.provider.advanced.testModel')}
                    value={String((formData.metadata?.test_config as Record<string, unknown> | undefined)?.test_model ?? '')}
                    onChange={(e) => setFormData({
                      ...formData,
                      metadata: {
                        ...(formData.metadata ?? {}),
                        test_config: {
                          ...((formData.metadata?.test_config as Record<string, unknown> | undefined) ?? {}),
                          test_model: e.target.value,
                        },
                      },
                    })}
                  />
                  <Input
                    type="number"
                    placeholder={t('admin.provider.advanced.degradedThreshold')}
                    value={String((formData.metadata?.test_config as Record<string, unknown> | undefined)?.degraded_threshold_ms ?? '')}
                    onChange={(e) => setFormData({
                      ...formData,
                      metadata: {
                        ...(formData.metadata ?? {}),
                        test_config: {
                          ...((formData.metadata?.test_config as Record<string, unknown> | undefined) ?? {}),
                          degraded_threshold_ms: Number(e.target.value || 0),
                        },
                      },
                    })}
                  />
                  <Input
                    type="number"
                    placeholder={t('admin.provider.advanced.dailyLimit')}
                    value={String((formData.metadata?.limits as Record<string, unknown> | undefined)?.daily_usd ?? '')}
                    onChange={(e) => setFormData({
                      ...formData,
                      metadata: {
                        ...(formData.metadata ?? {}),
                        limits: {
                          ...((formData.metadata?.limits as Record<string, unknown> | undefined) ?? {}),
                          daily_usd: Number(e.target.value || 0),
                        },
                      },
                    })}
                  />
                  <Input
                    type="number"
                    placeholder={t('admin.provider.advanced.monthlyLimit')}
                    value={String((formData.metadata?.limits as Record<string, unknown> | undefined)?.monthly_usd ?? '')}
                    onChange={(e) => setFormData({
                      ...formData,
                      metadata: {
                        ...(formData.metadata ?? {}),
                        limits: {
                          ...((formData.metadata?.limits as Record<string, unknown> | undefined) ?? {}),
                          monthly_usd: Number(e.target.value || 0),
                        },
                      },
                    })}
                  />
                </div>
              </div>

              <div className="flex items-center gap-2">
                <Switch
                  checked={formData.enabled}
                  onChange={(e) => setFormData({ ...formData, enabled: e.target.checked })}
                />
                <span className="text-sm text-gray-700 dark:text-gray-300">
                  {t('admin.provider.enableProvider')}
                </span>
              </div>

              {selectedProvider && testResult && (
                <div
                  className={cn(
                    'p-3 rounded-lg text-sm flex items-center gap-2',
                    testResult.is_healthy
                      ? 'bg-green-50 dark:bg-green-900/20 text-green-700 dark:text-green-300'
                      : 'bg-red-50 dark:bg-red-900/20 text-red-700 dark:text-red-300',
                  )}
                >
                  {testResult.is_healthy ? (
                    <CheckCircle2 className="w-4 h-4 shrink-0" />
                  ) : (
                    <XCircle className="w-4 h-4 shrink-0" />
                  )}
                  <span>
                    {testResult.is_healthy
                      ? t('admin.provider.inModalTestOk', { ms: testResult.latency_ms.toFixed(0) })
                      : testResult.error || t('admin.provider.testFailed')}
                  </span>
                </div>
              )}
            </>
          )}
        </ModalBody>
        <ModalFooter>
          {!selectedProvider && step === 'config' && (
            <Button variant="secondary" onClick={() => setStep('type')} className="mr-auto">
              {t('common.back')}
            </Button>
          )}
          <Button variant="secondary" onClick={handleClose}>
            {t('common.cancel')}
          </Button>
          {selectedProvider && (
            <Button
              variant="secondary"
              onClick={() => handleTest(selectedProvider.name)}
              loading={testProvider.isPending}
              leftIcon={<Zap className="w-4 h-4" aria-hidden />}
            >
              {t('admin.provider.test')}
            </Button>
          )}
          {(selectedProvider || step === 'config') && (
            <Button
              onClick={handleSubmit}
              loading={createProvider.isPending || updateProvider.isPending}
              disabled={!formData.name}
            >
              {selectedProvider ? t('common.save') : t('common.create')}
            </Button>
          )}
        </ModalFooter>
      </Modal>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Provider detail pane
// ---------------------------------------------------------------------------

interface ProviderDetailPanelProps {
  provider: ModelProvider;
  usageByModel: Record<string, ModelUsageRow>;
  defaultModel: { provider: string; model: string } | null;
  onEdit: () => void;
  onTest: () => void;
  onDelete: () => void;
  onToggleModel: (model: ProviderModelInfo) => void;
  onSetDefault: (model: ProviderModelInfo) => void;
  testing: boolean;
  updating: boolean;
}

function ProviderDetailPanel({
  provider,
  usageByModel,
  defaultModel,
  onEdit,
  onTest,
  onDelete,
  onToggleModel,
  onSetDefault,
  testing,
  updating,
}: ProviderDetailPanelProps) {
  const { t } = useTranslation();
  const brand = getBrand(provider.type);
  const [deepSeekBalance, setDeepSeekBalance] = useState<DeepSeekBalanceStatus | null>(null);

  useEffect(() => {
    if (provider.type !== 'deepseek' || !provider.enabled || !provider.api_key_set) {
      setDeepSeekBalance(null);
      return;
    }

    let cancelled = false;
    setDeepSeekBalance({ state: 'loading' });

    void adminApi.providers.balance(provider.name)
      .then((data) => {
        if (!cancelled) setDeepSeekBalance({ state: 'success', data });
      })
      .catch((error) => {
        if (!cancelled) {
          setDeepSeekBalance({
            state: 'error',
            error: error instanceof Error ? error.message : String(error),
          });
        }
      });

    return () => {
      cancelled = true;
    };
  }, [provider.api_key_set, provider.enabled, provider.name, provider.type]);

  return (
    <div className="space-y-4">
      {/* Header card */}
      <Card>
        <CardHeader>
          <div className="flex items-start gap-3">
            <div
              className={cn(
                'w-12 h-12 rounded-xl flex items-center justify-center font-bold text-base shrink-0',
                brand.bg,
                brand.text,
              )}
            >
              <ProviderIconMark type={provider.type} label={provider.label || provider.name} />
            </div>
            <div className="flex-1 min-w-0">
              <div className="flex items-center gap-2 flex-wrap">
                <CardTitle className="text-lg">{provider.name}</CardTitle>
                <HealthDot status={provider.is_healthy} />
                <Badge variant={provider.enabled ? 'success' : 'default'} size="sm">
                  {provider.enabled ? t('admin.provider.enabled') : t('admin.provider.disabled')}
                </Badge>
              </div>
              <p className="text-sm text-gray-500 dark:text-gray-400 mt-0.5">
                {provider.label} · {provider.type}
                {provider.type === 'deepseek' && provider.api_key_set && (
                  <>
                    {' · '}
                    {t('settings.deepseekBalanceLabel', { defaultValue: 'Balance' })}:{' '}
                    {deepSeekBalance?.state === 'success'
                      ? formatDeepSeekBalance(deepSeekBalance.data)
                      : deepSeekBalance?.state === 'error'
                        ? t('settings.deepseekBalanceUnavailable', { defaultValue: 'Unavailable' })
                        : t('settings.deepseekBalanceLoading', { defaultValue: 'Loading…' })}
                    {deepSeekBalance?.state === 'success' && !deepSeekBalance.data.is_available && (
                      <span className="ml-1 text-amber-600 dark:text-amber-400">
                        {t('settings.deepseekBalanceInsufficient', { defaultValue: 'insufficient' })}
                      </span>
                    )}
                  </>
                )}
              </p>
            </div>
            <div className="flex items-center gap-1 shrink-0">
              <Button
                variant="ghost"
                size="sm"
                onClick={onEdit}
                leftIcon={<Settings2 className="w-3.5 h-3.5" aria-hidden />}
              >
                {t('common.edit')}
              </Button>
              <Button
                variant="ghost"
                size="sm"
                onClick={onTest}
                loading={testing}
                leftIcon={<Zap className="w-3.5 h-3.5" aria-hidden />}
              >
                {t('admin.provider.test')}
              </Button>
              <Button
                variant="ghost"
                size="icon"
                className="text-red-600 hover:text-red-700 hover:bg-red-50 dark:hover:bg-red-900/20"
                onClick={onDelete}
                aria-label={t('common.delete')}
                title={t('common.delete')}
              >
                <Trash2 className="w-3.5 h-3.5" aria-hidden />
              </Button>
            </div>
          </div>
        </CardHeader>
        <CardContent className="pt-0">
          <dl className="grid gap-3 sm:grid-cols-2">
            <div>
              <dt className="text-xs font-medium text-gray-500 dark:text-gray-400 uppercase tracking-wide">
                {t('admin.provider.endpointUrlLabel')}
              </dt>
              <dd className="mt-0.5 text-sm text-gray-900 dark:text-white font-mono truncate flex items-center gap-1">
                {provider.base_url ? (
                  <>
                    <ExternalLink className="w-3.5 h-3.5 shrink-0 text-gray-400" />
                    <span className="truncate">{provider.base_url}</span>
                  </>
                ) : (
                  <span className="text-gray-400">—</span>
                )}
              </dd>
            </div>
            <div>
              <dt className="text-xs font-medium text-gray-500 dark:text-gray-400 uppercase tracking-wide">
                {t('admin.provider.apiKey')}
              </dt>
              <dd className="mt-0.5 text-sm text-gray-900 dark:text-white">
                {provider.requires_api_key === false ? (
                  <span className="inline-flex items-center gap-1 text-gray-500 dark:text-gray-400">
                    <Circle className="w-3.5 h-3.5" />
                    {t('admin.provider.apiKeyNotRequired')}
                  </span>
                ) : provider.api_key_set ? (
                  <span className="inline-flex items-center gap-1 text-green-600 dark:text-green-400">
                    <CheckCircle2 className="w-3.5 h-3.5 shrink-0" />
                    {t('admin.provider.apiKeyConfigured')}
                  </span>
                ) : (
                  <span className="inline-flex items-center gap-1 text-amber-600 dark:text-amber-400">
                    <Circle className="w-3.5 h-3.5 shrink-0" />
                    {t('admin.provider.apiKeyNotConfigured')}
                  </span>
                )}
              </dd>
            </div>
            <div>
              <dt className="text-xs font-medium text-gray-500 dark:text-gray-400 uppercase tracking-wide">
                {t('admin.provider.capabilities')}
              </dt>
              <dd className="mt-0.5 flex flex-wrap gap-1">
                {provider.supports_streaming && (
                  <span className="text-xs px-2 py-0.5 rounded bg-blue-50 dark:bg-blue-900/20 text-blue-600 dark:text-blue-400">
                    Streaming
                  </span>
                )}
                {provider.supports_tools && (
                  <span className="text-xs px-2 py-0.5 rounded bg-sky-50 dark:bg-sky-900/20 text-sky-700 dark:text-sky-400">
                    Tools
                  </span>
                )}
                {provider.supports_embeddings && (
                  <span className="text-xs px-2 py-0.5 rounded bg-amber-50 dark:bg-amber-900/20 text-amber-600 dark:text-amber-400">
                    Embeddings
                  </span>
                )}
                {!provider.supports_streaming
                  && !provider.supports_tools
                  && !provider.supports_embeddings && (
                    <span className="text-xs text-gray-400">—</span>
                  )}
              </dd>
            </div>
            <div>
              <dt className="text-xs font-medium text-gray-500 dark:text-gray-400 uppercase tracking-wide">
                {t('admin.provider.timeout')}
              </dt>
              <dd className="mt-0.5 text-sm text-gray-900 dark:text-white flex items-center gap-1">
                <Clock className="w-3.5 h-3.5 text-gray-400" />
                {provider.timeout}s
              </dd>
            </div>
          </dl>
        </CardContent>
      </Card>

      {/* Models table */}
      <Card>
        <CardHeader className="pb-3">
          <div className="flex items-center justify-between">
            <div>
              <CardTitle className="text-base">{t('admin.provider.modelsTable.title')}</CardTitle>
              <p className="text-xs text-gray-500 dark:text-gray-400 mt-0.5">
                {t('admin.provider.modelsTable.desc')}
              </p>
            </div>
          </div>
        </CardHeader>
        <CardContent className="pt-0 overflow-x-auto">
          {provider.models.length === 0 ? (
            <p className="text-sm text-gray-500 dark:text-gray-400 py-6 text-center">
              {t('admin.provider.modelsTable.empty')}
            </p>
          ) : (
            <table className="w-full text-sm">
              <thead>
                <tr className="text-left text-xs font-medium text-gray-500 dark:text-gray-400 uppercase tracking-wide border-b border-gray-200 dark:border-gray-700">
                  <th className="py-2 pr-3 w-10">{t('admin.provider.modelsTable.on')}</th>
                  <th className="py-2 px-3">{t('admin.provider.modelsTable.model')}</th>
                  <th className="py-2 px-3">{t('admin.provider.modelsTable.tier')}</th>
                  <th className="py-2 px-3 text-right">{t('admin.provider.modelsTable.context')}</th>
                  <th className="py-2 px-3 text-right">
                    {t('admin.provider.modelsTable.inputPrice')}
                  </th>
                  <th className="py-2 px-3 text-right">
                    {t('admin.provider.modelsTable.outputPrice')}
                  </th>
                  <th className="py-2 px-3 text-center">
                    {t('admin.provider.modelsTable.caps')}
                  </th>
                  <th className="py-2 px-3 text-right">
                    {t('admin.provider.modelsTable.requests30d')}
                  </th>
                  <th className="py-2 pl-3 w-24">{t('admin.provider.modelsTable.actions')}</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-gray-100 dark:divide-gray-800">
                {provider.models.map((m) => {
                  const isEnabled = m.enabled !== false;
                  const isDefault = defaultModel?.provider === provider.name
                    && defaultModel?.model === m.name;
                  const usage = usageByModel[m.name];
                  return (
                    <tr key={m.name} className={cn(!isEnabled && 'opacity-50')}>
                      <td className="py-2 pr-3">
                        <Switch
                          checked={isEnabled}
                          onChange={() => onToggleModel(m)}
                          disabled={updating}
                          aria-label={t('admin.provider.modelsTable.toggleAria', { model: m.name })}
                        />
                      </td>
                      <td className="py-2 px-3">
                        <div className="flex items-center gap-2 min-w-0">
                          <span className="font-mono text-xs text-gray-900 dark:text-white truncate">
                            {m.name}
                          </span>
                          {isDefault && (
                            <Badge variant="success" size="sm">
                              {t('admin.provider.modelsTable.defaultTag')}
                            </Badge>
                          )}
                        </div>
                        {m.description && (
                          <p className="text-xs text-gray-500 dark:text-gray-400 mt-0.5 truncate max-w-md">
                            {m.description}
                          </p>
                        )}
                      </td>
                      <td className="py-2 px-3">
                        {m.tier ? (
                          <Badge variant="default" size="sm">
                            {m.tier}
                          </Badge>
                        ) : (
                          <span className="text-gray-400">—</span>
                        )}
                      </td>
                      <td className="py-2 px-3 text-right tabular-nums text-gray-600 dark:text-gray-400">
                        {formatContext(m.context_window)}
                      </td>
                      <td className="py-2 px-3 text-right tabular-nums text-gray-600 dark:text-gray-400">
                        {formatPrice(m.price_input_per_1m)}
                      </td>
                      <td className="py-2 px-3 text-right tabular-nums text-gray-600 dark:text-gray-400">
                        {formatPrice(m.price_output_per_1m)}
                      </td>
                      <td className="py-2 px-3">
                        <div className="flex items-center justify-center gap-1">
                          {m.supports_tools && (
                            <span
                              title={t('admin.provider.modelsTable.toolsTip')}
                              className="text-sky-600 dark:text-sky-400"
                            >
                              <Wrench className="w-3.5 h-3.5" />
                            </span>
                          )}
                          {m.supports_vision && (
                            <span
                              title={t('admin.provider.modelsTable.visionTip')}
                              className="text-blue-500"
                            >
                              <Eye className="w-3.5 h-3.5" />
                            </span>
                          )}
                          {!m.supports_tools && !m.supports_vision && (
                            <span className="text-gray-400">—</span>
                          )}
                        </div>
                      </td>
                      <td className="py-2 px-3 text-right tabular-nums">
                        {usage ? (
                          <span className="text-gray-900 dark:text-white">
                            {formatCompactNumber(usage.request_count)}
                          </span>
                        ) : (
                          <span className="text-gray-400">0</span>
                        )}
                      </td>
                      <td className="py-2 pl-3">
                        <Button
                          variant="ghost"
                          size="sm"
                          disabled={!provider.enabled || !isEnabled || isDefault}
                          onClick={() => onSetDefault(m)}
                        >
                          {isDefault
                            ? t('admin.provider.modelsTable.isDefault')
                            : t('admin.provider.modelsTable.makeDefault')}
                        </Button>
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          )}
        </CardContent>
      </Card>
    </div>
  );
}
