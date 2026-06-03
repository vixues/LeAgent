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
  Box,
  Eye,
  Brain,
  Wrench,
  Clock,
  Layers,
  Search,
  RefreshCw,
  ChevronDown,
  GripVertical,
  Pencil,
} from 'lucide-react';
import {
  Card,
  CardTitle,
  CardContent,
  Button,
  Input,
  Select,
  Switch,
  Modal,
  ModalHeader,
  ModalBody,
  ModalFooter,
  Badge,
} from '@/components/ui';
import { useAdminStore } from '@/stores/admin';
import { PageLoader } from '@/components/common/PageLoader';
import { SectionHeader } from '@/components/common/SectionHeader';
import { useToast } from '@/components/ui/Toaster';
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
import { cn } from '@/lib/utils';
import {
  formatCompactNumber,
  StatCard,
} from './shared/adminFormat';

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

// ---------------------------------------------------------------------------
// Formatting helpers
// ---------------------------------------------------------------------------

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

type ModelCapabilities = NonNullable<ProviderModelInfo['capabilities']>;

const MODEL_KINDS = ['chat', 'embedding', 'image_gen'] as const;
const INPUT_MODALITIES = ['text', 'image', 'audio', 'pdf'] as const;
const OUTPUT_MODALITIES = ['text', 'image'] as const;

function normalizeCapabilities(caps?: ModelCapabilities): ModelCapabilities {
  return {
    input: caps?.input?.length ? [...caps.input] : ['text'],
    output: caps?.output?.length ? [...caps.output] : ['text'],
    tool_call: Boolean(caps?.tool_call),
    reasoning: Boolean(caps?.reasoning),
  };
}

function modelSupportsTools(m: { capabilities?: ModelCapabilities }) {
  return Boolean(m.capabilities?.tool_call);
}

function modelSupportsVision(m: { capabilities?: ModelCapabilities }) {
  return m.capabilities?.input?.includes('image') ?? false;
}

function modelSupportsReasoning(m: { capabilities?: ModelCapabilities }) {
  return Boolean(m.capabilities?.reasoning);
}

function getInputPrice(m: { pricing?: ProviderModelInfo['pricing'] }) {
  return m.pricing?.input_per_1m;
}

function getOutputPrice(m: { pricing?: ProviderModelInfo['pricing'] }) {
  return m.pricing?.output_per_1m;
}

type ModelEntry = NonNullable<ModelProviderFormData['models']>[number];

function defaultNewModel(name: string): ModelEntry {
  return {
    name,
    kind: 'chat',
    capabilities: normalizeCapabilities(),
    context_window: 0,
    enabled: true,
  };
}

/** Preset catalog entry from GET /models/presets (same shape as ProviderModelInfo). */
function presetRowToFormModel(m: ProviderModelInfo): ModelEntry {
  return {
    name: m.name,
    kind: m.kind ?? 'chat',
    capabilities: normalizeCapabilities(m.capabilities),
    context_window: m.context_window ?? 0,
    enabled: m.enabled !== false,
    description: m.description,
    pricing: m.pricing ? { ...m.pricing } : undefined,
  };
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
// Model config editor — rich per-model property editing
// ---------------------------------------------------------------------------

interface ModelConfigEditorProps {
  models: ModelEntry[];
  onChange: (models: ModelEntry[]) => void;
  presetCatalog: ProviderModelInfo[];
  onError?: (msg: string) => void;
  discoveredModels?: DiscoveredModel[];
}

function ModelConfigEditor({
  models,
  onChange,
  presetCatalog,
  onError,
  discoveredModels,
}: ModelConfigEditorProps) {
  const { t } = useTranslation();
  const [expandedIdx, setExpandedIdx] = useState<number | null>(null);
  const [addInput, setAddInput] = useState('');
  const hasPresets = presetCatalog.length > 0;

  const selectedNames = useMemo(() => new Set(models.map((m) => m.name)), [models]);
  const unselectedPresets = useMemo(
    () => presetCatalog.filter((m) => !selectedNames.has(m.name)),
    [presetCatalog, selectedNames],
  );

  const updateModel = (idx: number, patch: Partial<ModelEntry>) => {
    const next = models.map((m, i) => (i === idx ? { ...m, ...patch } : m));
    onChange(next);
  };

  const updateCapabilities = (idx: number, patch: Partial<ModelCapabilities>) => {
    const current = normalizeCapabilities(models[idx]?.capabilities);
    updateModel(idx, { capabilities: { ...current, ...patch } });
  };

  const toggleModality = (
    idx: number,
    field: 'input' | 'output',
    modality: string,
    checked: boolean,
  ) => {
    const current = normalizeCapabilities(models[idx]?.capabilities);
    const set = new Set(current[field] ?? []);
    if (checked) set.add(modality);
    else set.delete(modality);
    const next = Array.from(set);
    if (field === 'input' && next.length === 0) next.push('text');
    if (field === 'output' && next.length === 0) next.push('text');
    updateCapabilities(idx, { [field]: next });
  };

  const updatePricing = (idx: number, field: 'input_per_1m' | 'output_per_1m', value: number) => {
    const current = models[idx]?.pricing ?? {};
    updateModel(idx, { pricing: { ...current, [field]: value } });
  };

  const removeModel = (idx: number) => {
    onChange(models.filter((_, i) => i !== idx));
    if (expandedIdx === idx) setExpandedIdx(null);
    else if (expandedIdx !== null && expandedIdx > idx) setExpandedIdx(expandedIdx - 1);
  };

  const addPreset = (preset: ProviderModelInfo) => {
    if (selectedNames.has(preset.name)) return;
    onChange([...models, presetRowToFormModel(preset)]);
  };

  const addCustomModel = () => {
    const names = addInput
      .split(/[,\n]/)
      .map((s) => s.trim())
      .filter(Boolean);
    if (names.length === 0) return;
    const newModels: ModelEntry[] = [];
    for (const name of names) {
      if (selectedNames.has(name) || newModels.some((m) => m.name === name)) {
        onError?.(t('admin.provider.duplicateModelName', { name }));
        return;
      }
      newModels.push(defaultNewModel(name));
    }
    onChange([...models, ...newModels]);
    setAddInput('');
  };

  const addDiscovered = (row: DiscoveredModel) => {
    const name = row.name || row.id;
    if (!name || selectedNames.has(name)) return;
    onChange([...models, defaultNewModel(name)]);
  };

  return (
    <div className="space-y-2">
      {/* Selected models with expandable config */}
      {models.length > 0 && (
        <div className="space-y-1 rounded-lg border border-gray-200 dark:border-gray-700 overflow-hidden">
          {models.map((m, idx) => {
            const isExpanded = expandedIdx === idx;
            return (
              <div
                key={m.name}
                className={cn(
                  'border-b border-gray-100 dark:border-gray-800 last:border-b-0',
                  isExpanded && 'bg-gray-50/50 dark:bg-gray-800/30',
                )}
              >
                {/* Collapsed row */}
                <div className="flex items-center gap-2 px-3 py-2">
                  <GripVertical className="w-3.5 h-3.5 text-gray-300 dark:text-gray-600 shrink-0" />
                  <Switch
                    checked={m.enabled !== false}
                    onCheckedChange={(checked) => updateModel(idx, { enabled: checked })}
                    size="sm"
                  />
                  <button
                    type="button"
                    className="flex-1 min-w-0 flex items-center gap-2 text-left"
                    onClick={() => setExpandedIdx(isExpanded ? null : idx)}
                  >
                    <span className="font-mono text-xs text-gray-900 dark:text-white truncate">
                      {m.name}
                    </span>
                    <span className="flex items-center gap-1 shrink-0">
                      {m.kind && (
                        <Badge variant="default" size="sm">{m.kind}</Badge>
                      )}
                      {m.context_window ? (
                        <span className="text-[10px] text-gray-400">{formatContext(m.context_window)}</span>
                      ) : null}
                      {modelSupportsTools(m) && <Wrench className="w-3 h-3 text-sky-500" />}
                      {modelSupportsVision(m) && <Eye className="w-3 h-3 text-blue-500" />}
                      {modelSupportsReasoning(m) && <Brain className="w-3 h-3 text-purple-500" />}
                    </span>
                  </button>
                  <button
                    type="button"
                    className="p-1 rounded text-gray-400 hover:text-gray-600 hover:bg-gray-100 dark:hover:text-gray-300 dark:hover:bg-gray-700 transition-colors"
                    onClick={() => setExpandedIdx(isExpanded ? null : idx)}
                    aria-label={t('admin.provider.modelEditor.configure')}
                  >
                    <ChevronDown className={cn('w-4 h-4 transition-transform', isExpanded && 'rotate-180')} />
                  </button>
                  <button
                    type="button"
                    className="p-1 rounded text-gray-400 hover:text-red-500 hover:bg-red-50 dark:hover:bg-red-900/20 transition-colors"
                    onClick={() => removeModel(idx)}
                    aria-label={t('common.delete')}
                  >
                    <Trash2 className="w-3.5 h-3.5" />
                  </button>
                </div>

                {/* Expanded config */}
                {isExpanded && (
                  <div className="px-3 pb-3 pt-1 border-t border-gray-100 dark:border-gray-800">
                    <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
                      <div>
                        <label className="block text-[11px] font-medium text-gray-500 dark:text-gray-400 mb-1 uppercase tracking-wide">
                          {t('admin.provider.modelEditor.kind')}
                        </label>
                        <Select
                          value={m.kind || 'chat'}
                          onChange={(e) => updateModel(idx, { kind: e.target.value as ModelEntry['kind'] })}
                          className="h-8 text-xs"
                        >
                          {MODEL_KINDS.map((kind) => (
                            <option key={kind} value={kind}>
                              {t(`admin.provider.modelEditor.kind_${kind}`)}
                            </option>
                          ))}
                        </Select>
                      </div>

                      <div>
                        <label className="block text-[11px] font-medium text-gray-500 dark:text-gray-400 mb-1 uppercase tracking-wide">
                          {t('admin.provider.modelEditor.contextWindow')}
                        </label>
                        <Input
                          type="number"
                          value={m.context_window || ''}
                          onChange={(e) => updateModel(idx, { context_window: Number(e.target.value) || 0 })}
                          placeholder="128000"
                          className="h-8 text-xs"
                        />
                      </div>

                      <div className="sm:col-span-2 lg:col-span-1">
                        <label className="block text-[11px] font-medium text-gray-500 dark:text-gray-400 mb-1 uppercase tracking-wide">
                          {t('admin.provider.modelEditor.description')}
                        </label>
                        <Input
                          value={m.description || ''}
                          onChange={(e) => updateModel(idx, { description: e.target.value })}
                          placeholder={t('admin.provider.modelEditor.descriptionPlaceholder')}
                          className="h-8 text-xs"
                        />
                      </div>

                      <div>
                        <label className="block text-[11px] font-medium text-gray-500 dark:text-gray-400 mb-1 uppercase tracking-wide">
                          {t('admin.provider.modelEditor.inputPrice')}
                        </label>
                        <Input
                          type="number"
                          step="0.01"
                          value={getInputPrice(m) ?? ''}
                          onChange={(e) => updatePricing(idx, 'input_per_1m', Number(e.target.value) || 0)}
                          placeholder="0.00"
                          className="h-8 text-xs"
                        />
                      </div>

                      <div>
                        <label className="block text-[11px] font-medium text-gray-500 dark:text-gray-400 mb-1 uppercase tracking-wide">
                          {t('admin.provider.modelEditor.outputPrice')}
                        </label>
                        <Input
                          type="number"
                          step="0.01"
                          value={getOutputPrice(m) ?? ''}
                          onChange={(e) => updatePricing(idx, 'output_per_1m', Number(e.target.value) || 0)}
                          placeholder="0.00"
                          className="h-8 text-xs"
                        />
                      </div>
                    </div>

                    <div className="mt-3 grid gap-3 sm:grid-cols-2">
                      <div>
                        <p className="text-[11px] font-medium text-gray-500 dark:text-gray-400 mb-1.5 uppercase tracking-wide">
                          {t('admin.provider.modelEditor.inputModalities')}
                        </p>
                        <div className="flex flex-wrap gap-2">
                          {INPUT_MODALITIES.map((modality) => (
                            <label key={modality} className="flex items-center gap-1.5 text-xs text-gray-700 dark:text-gray-300">
                              <input
                                type="checkbox"
                                checked={normalizeCapabilities(m.capabilities).input?.includes(modality) ?? false}
                                onChange={(e) => toggleModality(idx, 'input', modality, e.target.checked)}
                                className="rounded border-gray-300 text-primary-600"
                              />
                              {modality}
                            </label>
                          ))}
                        </div>
                      </div>
                      <div>
                        <p className="text-[11px] font-medium text-gray-500 dark:text-gray-400 mb-1.5 uppercase tracking-wide">
                          {t('admin.provider.modelEditor.outputModalities')}
                        </p>
                        <div className="flex flex-wrap gap-2">
                          {OUTPUT_MODALITIES.map((modality) => (
                            <label key={modality} className="flex items-center gap-1.5 text-xs text-gray-700 dark:text-gray-300">
                              <input
                                type="checkbox"
                                checked={normalizeCapabilities(m.capabilities).output?.includes(modality) ?? false}
                                onChange={(e) => toggleModality(idx, 'output', modality, e.target.checked)}
                                className="rounded border-gray-300 text-primary-600"
                              />
                              {modality}
                            </label>
                          ))}
                        </div>
                      </div>
                    </div>

                    <div className="mt-3 flex flex-wrap gap-x-5 gap-y-2">
                      <label className="flex items-center gap-2 cursor-pointer text-xs text-gray-700 dark:text-gray-300">
                        <Switch
                          checked={modelSupportsTools(m)}
                          onCheckedChange={(checked) => updateCapabilities(idx, { tool_call: checked })}
                          size="sm"
                        />
                        <Wrench className="w-3.5 h-3.5 text-sky-500" />
                        {t('admin.provider.modelEditor.supportsTools')}
                      </label>
                      <label className="flex items-center gap-2 cursor-pointer text-xs text-gray-700 dark:text-gray-300">
                        <Switch
                          checked={modelSupportsReasoning(m)}
                          onCheckedChange={(checked) => updateCapabilities(idx, { reasoning: checked })}
                          size="sm"
                        />
                        <Brain className="w-3.5 h-3.5 text-purple-500" />
                        {t('admin.provider.modelEditor.supportsThinking')}
                      </label>
                    </div>
                  </div>
                )}
              </div>
            );
          })}
        </div>
      )}

      {models.length === 0 && (
        <div className="rounded-lg border border-dashed border-gray-300 dark:border-gray-600 p-6 text-center">
          <Layers className="w-8 h-8 mx-auto mb-2 text-gray-300 dark:text-gray-600" />
          <p className="text-xs text-gray-500 dark:text-gray-400">
            {t('admin.provider.modelEditor.emptyHint')}
          </p>
        </div>
      )}

      {/* Add from presets */}
      {hasPresets && unselectedPresets.length > 0 && (
        <div className="space-y-1">
          <p className="text-[11px] font-medium text-gray-500 dark:text-gray-400 uppercase tracking-wide">
            {t('admin.provider.modelEditor.addFromCatalog')}
          </p>
          <div className="flex flex-wrap gap-1.5">
            {unselectedPresets.map((p) => (
              <button
                key={p.name}
                type="button"
                className={cn(
                  'inline-flex items-center gap-1 px-2 py-1 rounded-md text-xs font-medium',
                  'border border-dashed border-gray-300 dark:border-gray-600',
                  'text-gray-600 dark:text-gray-400',
                  'hover:border-primary-400 hover:text-primary-600 hover:bg-primary-50/50',
                  'dark:hover:border-primary-600 dark:hover:text-primary-400 dark:hover:bg-primary-900/20',
                  'transition-colors',
                )}
                onClick={() => addPreset(p)}
              >
                <Plus className="w-3 h-3" />
                {p.name}
              </button>
            ))}
          </div>
        </div>
      )}

      {/* Discovered models */}
      {discoveredModels && discoveredModels.length > 0 && (
        <div className="space-y-1">
          <p className="text-[11px] font-medium text-gray-500 dark:text-gray-400 uppercase tracking-wide">
            {t('admin.provider.modelEditor.discovered')}
          </p>
          <div className="flex flex-wrap gap-1.5 max-h-32 overflow-y-auto">
            {discoveredModels.filter((d) => !selectedNames.has(d.name || d.id)).slice(0, 30).map((d) => (
              <button
                key={d.id}
                type="button"
                className={cn(
                  'inline-flex items-center gap-1 px-2 py-1 rounded-md text-xs font-medium',
                  'border border-dashed border-gray-300 dark:border-gray-600',
                  'text-gray-600 dark:text-gray-400',
                  'hover:border-green-400 hover:text-green-600 hover:bg-green-50/50',
                  'dark:hover:border-green-600 dark:hover:text-green-400 dark:hover:bg-green-900/20',
                  'transition-colors',
                )}
                onClick={() => addDiscovered(d)}
              >
                <Plus className="w-3 h-3" />
                <span className="font-mono">{d.name || d.id}</span>
              </button>
            ))}
          </div>
        </div>
      )}

      {/* Custom model input */}
      <div className="flex gap-2">
        <Input
          value={addInput}
          onChange={(e) => setAddInput(e.target.value)}
          placeholder={t('admin.provider.modelEditor.addCustomPlaceholder')}
          className="h-8 text-xs font-mono flex-1"
          onKeyDown={(e) => {
            if (e.key === 'Enter') {
              e.preventDefault();
              addCustomModel();
            }
          }}
        />
        <Button
          type="button"
          size="sm"
          variant="secondary"
          onClick={addCustomModel}
          disabled={!addInput.trim()}
          className="shrink-0 flex-nowrap whitespace-nowrap"
          leftIcon={<Plus className="w-3.5 h-3.5" aria-hidden />}
        >
          {t('admin.provider.modelEditor.addButton')}
        </Button>
      </div>
    </div>
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
  const { toast } = useToast();
  const { data: providers, isLoading } = useProviders();
  const { data: presets } = usePresets();
  const { data: defaultModel } = useDefaultModel();
  const { data: usage } = useModelUsageSummary(30);
  const { data: providerUsage } = useProviderUsage(30);
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
    setFormError('');
    setStep('config');
  };

  const handleOpenCreate = () => {
    setSelectedProvider(null);
    setFormData({ ...EMPTY_FORM });
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
      models: provider.models.map((m) => ({ ...m })),
      enabled: provider.enabled,
      metadata: provider.metadata ?? {},
    });
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
    setFormError('');
    setTestResult(null);
    setDiscoveredModels([]);
    setSpeedResults([]);
    setStep('type');
  };

  const handleSubmit = async () => {
    setFormError('');
    const models = formData.models ?? [];
    if (models.length === 0) {
      setFormError(t('admin.provider.atLeastOneModel'));
      return;
    }

    const mergedMetadata = {
      ...(formData.metadata ?? {}),
      ...(formData.extra ?? {}),
    };
    const payload: ModelProviderFormData = {
      ...formData,
      models,
      metadata: Object.keys(mergedMetadata).length > 0 ? mergedMetadata : formData.metadata,
    };
    delete payload.extra;
    // When editing, strip empty api_key so the backend preserves the existing key.
    if (selectedProvider && !payload.api_key?.trim()) {
      delete payload.api_key;
    }
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

  const handleUpdateModel = async (
    provider: ModelProvider,
    model: ProviderModelInfo,
    patch: Partial<ProviderModelInfo>,
  ) => {
    const nextModels = provider.models.map((m) =>
      m.name === model.name ? { ...m, ...patch } : m,
    );
    await updateProvider.mutateAsync({
      name: provider.name,
      data: { models: nextModels },
    });
  };

  const handleSetDefaultModel = async (providerName: string, modelName: string) => {
    try {
      await setDefaultModel.mutateAsync({ provider: providerName, model: modelName });
      toast({
        variant: 'success',
        title: t('admin.provider.modelsTable.setDefaultSuccess'),
      });
    } catch (error) {
      toast({
        variant: 'error',
        title: t('admin.provider.modelsTable.setDefaultError'),
        description: error instanceof Error ? error.message : String(error),
      });
    }
  };

  // Determine if type requires api_key in modal
  const currentPreset = presets?.find((p) => p.type === formData.type);
  const requiresApiKey = currentPreset?.requires_api_key ?? !['ollama'].includes(formData.type);
  const showBaseUrl = ['ollama', 'custom', 'azure', 'deepseek', 'qwen', 'vllm'].includes(formData.type)
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
      <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
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
      </div>

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
              onUpdateModel={(m, patch) => handleUpdateModel(focusedProvider, m, patch)}
              onSetDefault={(m) => handleSetDefaultModel(focusedProvider.name, m.name)}
              testing={testProvider.isPending}
              updating={updateProvider.isPending}
              settingDefault={setDefaultModel.isPending}
            />
          )}
        </div>
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
                      setFormData((prev) => ({
                        ...prev,
                        type: newType,
                        base_url: preset.default_base_url ?? prev.base_url,
                        models: preset.models.map((m) => presetRowToFormModel(m)),
                      }));
                    } else if (!selectedProvider) {
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
                  {formData.type === 'custom' && (
                    <p className="mt-1 text-xs text-gray-500">
                      {t('admin.provider.customApiKeyHint')}
                    </p>
                  )}
                  {formData.type === 'vllm' && (
                    <p className="mt-1 text-xs text-gray-500">
                      {t('admin.provider.vllmApiKeyHint')}
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
                      checked={Boolean(formData.extra?.enable_search ?? false)}
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
                      checked={Boolean(formData.extra?.enable_thinking ?? true)}
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

              {formData.type === 'vllm' && (
                <div className="space-y-3 rounded-lg border border-sky-200 dark:border-sky-800 bg-sky-50 dark:bg-sky-900/20 p-3">
                  <p className="text-xs font-medium text-sky-700 dark:text-sky-400">
                    {t('admin.provider.vllmSettingsTitle')}
                  </p>
                  <div className="flex items-start justify-between gap-3">
                    <div>
                      <label className="text-sm text-gray-700 dark:text-gray-300">
                        {t('admin.provider.vllmEnableAutoToolChoice')}
                      </label>
                      <p className="mt-0.5 text-xs text-gray-500">
                        {t('admin.provider.vllmEnableAutoToolChoiceHelp')}
                      </p>
                    </div>
                    <Switch
                      checked={Boolean(formData.metadata?.enable_auto_tool_choice ?? false)}
                      onCheckedChange={(checked) =>
                        setFormData({
                          ...formData,
                          metadata: { ...(formData.metadata ?? {}), enable_auto_tool_choice: checked },
                        })
                      }
                    />
                  </div>
                </div>
              )}

              {['custom', 'openai', 'vllm', 'ollama'].includes(formData.type) && (
                <div className="space-y-3 rounded-lg border border-violet-200 dark:border-violet-800 bg-violet-50 dark:bg-violet-900/20 p-3">
                  <p className="text-xs font-medium text-violet-700 dark:text-violet-400">
                    {t('admin.provider.thinkingSettings', { defaultValue: '思考过程解析' })}
                  </p>
                  <div className="flex items-start justify-between gap-3">
                    <div>
                      <label className="text-sm text-gray-700 dark:text-gray-300">
                        {t('admin.provider.parseThinkTags', { defaultValue: '解析 <think> 标签' })}
                      </label>
                      <p className="mt-0.5 text-xs text-gray-500">
                        {t('admin.provider.parseThinkTagsHelp', {
                          defaultValue:
                            '启用后，模型输出中的 <think>…</think> 标签会被提取并显示为思考过程，而不出现在正文内容中。适用于 DeepSeek / QwQ 等本地或自定义部署模型。',
                        })}
                      </p>
                    </div>
                    <Switch
                      checked={
                        formData.metadata?.parse_think_tags != null
                          ? Boolean(formData.metadata.parse_think_tags)
                          : formData.type === 'custom'
                      }
                      onCheckedChange={(checked) =>
                        setFormData({
                          ...formData,
                          metadata: { ...(formData.metadata ?? {}), parse_think_tags: checked },
                        })
                      }
                    />
                  </div>
                </div>
              )}

              <div>
                <div className="mb-2 flex items-center justify-between gap-2">
                  <label className="block text-sm font-medium text-gray-700 dark:text-gray-300">
                    {t('admin.provider.availableModelsLabel')}
                    {(formData.models?.length ?? 0) > 0 && (
                      <span className="ml-1.5 text-xs font-normal text-gray-400">
                        ({formData.models?.length})
                      </span>
                    )}
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
                <ModelConfigEditor
                  models={formData.models ?? []}
                  onChange={(models) => {
                    setFormError('');
                    setFormData((prev) => ({ ...prev, models }));
                  }}
                  presetCatalog={presetCatalog}
                  onError={setFormError}
                  discoveredModels={discoveredModels.length > 0 ? discoveredModels : undefined}
                />
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
  onUpdateModel: (model: ProviderModelInfo, patch: Partial<ProviderModelInfo>) => void;
  onSetDefault: (model: ProviderModelInfo) => void;
  testing: boolean;
  updating: boolean;
  settingDefault: boolean;
}

function ProviderDetailPanel({
  provider,
  usageByModel,
  defaultModel,
  onEdit,
  onTest,
  onDelete,
  onToggleModel,
  onUpdateModel,
  onSetDefault,
  testing,
  updating,
  settingDefault,
}: ProviderDetailPanelProps) {
  const { t } = useTranslation();
  const brand = getBrand(provider.type);
  const [deepSeekBalance, setDeepSeekBalance] = useState<DeepSeekBalanceStatus | null>(null);
  const [editingModel, setEditingModel] = useState<string | null>(null);

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
    <Card padding="sm" className="overflow-hidden">
      {/* Provider header + connection meta */}
      <div className="flex flex-wrap items-start gap-3 gap-y-2 pb-3 border-b border-border">
        <div
          className={cn(
            'w-10 h-10 rounded-lg flex items-center justify-center font-bold text-sm shrink-0',
            brand.bg,
            brand.text,
          )}
        >
          <ProviderIconMark type={provider.type} label={provider.label || provider.name} compact />
        </div>
        <div className="min-w-0 flex-1">
          <div className="flex flex-wrap items-center gap-x-2 gap-y-1">
            <CardTitle className="text-base leading-tight">{provider.name}</CardTitle>
            <HealthDot status={provider.is_healthy} size="sm" />
            <Badge variant={provider.enabled ? 'success' : 'default'} size="sm">
              {provider.enabled ? t('admin.provider.enabled') : t('admin.provider.disabled')}
            </Badge>
          </div>
          <p className="text-xs text-muted-foreground mt-0.5 truncate">
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
        <div className="flex items-center gap-0.5 shrink-0 ml-auto">
          <Button
            variant="ghost"
            size="sm"
            className="h-8 px-2 text-xs"
            onClick={onEdit}
            leftIcon={<Settings2 className="w-3.5 h-3.5" aria-hidden />}
          >
            {t('common.edit')}
          </Button>
          <Button
            variant="ghost"
            size="sm"
            className="h-8 px-2 text-xs"
            onClick={onTest}
            loading={testing}
            leftIcon={<Zap className="w-3.5 h-3.5" aria-hidden />}
          >
            {t('admin.provider.test')}
          </Button>
          <Button
            variant="ghost"
            size="icon"
            className="h-8 w-8 text-red-600 hover:text-red-700 hover:bg-red-50 dark:hover:bg-red-900/20"
            onClick={onDelete}
            aria-label={t('common.delete')}
            title={t('common.delete')}
          >
            <Trash2 className="w-3.5 h-3.5" aria-hidden />
          </Button>
        </div>
      </div>

      <div className="grid grid-cols-2 gap-x-6 gap-y-3 py-3 text-xs border-b border-border">
        <div className="min-w-0">
          <span className="text-muted-foreground-tertiary uppercase tracking-wide text-[10px]">
            {t('admin.provider.endpointUrlLabel')}
          </span>
          <p className="mt-0.5 font-mono text-foreground truncate flex items-center gap-1">
            {provider.base_url ? (
              <>
                <ExternalLink className="w-3 h-3 shrink-0 text-muted-foreground-tertiary" />
                <span className="truncate">{provider.base_url}</span>
              </>
            ) : (
              <span className="text-muted-foreground-tertiary">—</span>
            )}
          </p>
        </div>
        <div>
          <span className="text-muted-foreground-tertiary uppercase tracking-wide text-[10px]">
            {t('admin.provider.apiKey')}
          </span>
          <p className="mt-0.5 text-foreground">
            {provider.requires_api_key === false ? (
              <span className="text-muted-foreground">{t('admin.provider.apiKeyNotRequired')}</span>
            ) : provider.api_key_set ? (
              <span className="inline-flex items-center gap-1 text-green-600 dark:text-green-400">
                <CheckCircle2 className="w-3 h-3 shrink-0" />
                {t('admin.provider.apiKeyConfigured')}
              </span>
            ) : (
              <span className="inline-flex items-center gap-1 text-amber-600 dark:text-amber-400">
                <Circle className="w-3 h-3 shrink-0" />
                {t('admin.provider.apiKeyNotConfigured')}
              </span>
            )}
          </p>
        </div>
        <div>
          <span className="text-muted-foreground-tertiary uppercase tracking-wide text-[10px]">
            {t('admin.provider.capabilities')}
          </span>
          <p className="mt-0.5 flex flex-wrap gap-1">
            {provider.supports_streaming && (
              <span className="px-1.5 py-px rounded bg-primary/10 text-primary text-[10px]">Streaming</span>
            )}
            {provider.supports_tools && (
              <span className="px-1.5 py-px rounded bg-sky-500/10 text-sky-700 dark:text-sky-400 text-[10px]">Tools</span>
            )}
            {provider.supports_embeddings && (
              <span className="px-1.5 py-px rounded bg-amber-500/10 text-amber-600 dark:text-amber-400 text-[10px]">Emb</span>
            )}
            {!provider.supports_streaming && !provider.supports_tools && !provider.supports_embeddings && (
              <span className="text-muted-foreground-tertiary">—</span>
            )}
          </p>
        </div>
        <div>
          <span className="text-muted-foreground-tertiary uppercase tracking-wide text-[10px]">
            {t('admin.provider.timeout')}
          </span>
          <p className="mt-0.5 text-foreground flex items-center gap-1">
            <Clock className="w-3 h-3 text-muted-foreground-tertiary" />
            {provider.timeout}s
          </p>
        </div>
      </div>

      {/* Models — same card, compact table */}
      <div className="pt-3">
        <div className="flex items-baseline justify-between gap-2 mb-2">
          <p className="text-xs font-medium text-foreground">
            {t('admin.provider.modelsTable.title')}
            <span className="ml-1.5 font-normal text-muted-foreground">
              ({provider.models.length})
            </span>
          </p>
          <p className="text-[10px] text-muted-foreground-tertiary hidden sm:block">
            {t('admin.provider.modelsTable.desc')}
          </p>
        </div>
        {provider.models.length === 0 ? (
          <p className="text-xs text-muted-foreground py-4 text-center">
            {t('admin.provider.modelsTable.empty')}
          </p>
        ) : (
          <div className="overflow-x-auto -mx-1">
            <table className="w-full text-xs">
              <thead>
                <tr className="text-left text-[10px] font-medium text-muted-foreground uppercase tracking-wide border-b border-border">
                  <th className="py-1.5 pr-2 w-8">{t('admin.provider.modelsTable.on')}</th>
                  <th className="py-1.5 px-2">{t('admin.provider.modelsTable.model')}</th>
                  <th className="py-1.5 px-2">{t('admin.provider.modelsTable.kind')}</th>
                  <th className="py-1.5 px-2 text-right">{t('admin.provider.modelsTable.context')}</th>
                  <th className="py-1.5 px-2 text-right hidden md:table-cell">
                    {t('admin.provider.modelsTable.inputPrice')}
                  </th>
                  <th className="py-1.5 px-2 text-right hidden md:table-cell">
                    {t('admin.provider.modelsTable.outputPrice')}
                  </th>
                  <th className="py-1.5 px-2 text-center">{t('admin.provider.modelsTable.caps')}</th>
                  <th className="py-1.5 px-2 text-right hidden sm:table-cell">
                    {t('admin.provider.modelsTable.requests30d')}
                  </th>
                  <th className="py-1.5 pl-2 w-20">{t('admin.provider.modelsTable.actions')}</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-border-subtle">
                {provider.models.map((m) => {
                  const isEnabled = m.enabled !== false;
                  const isDefault = defaultModel?.provider === provider.name
                    && defaultModel?.model === m.name;
                  const usage = usageByModel[m.name];
                  const isEditing = editingModel === m.name;
                  return (
                    <tr key={m.name} className={cn(!isEnabled && 'opacity-50')}>
                      <td className="py-1.5 pr-2">
                        <Switch
                          checked={isEnabled}
                          onChange={() => onToggleModel(m)}
                          disabled={updating}
                          size="sm"
                          aria-label={t('admin.provider.modelsTable.toggleAria', { model: m.name })}
                        />
                      </td>
                      <td className="py-1.5 px-2 max-w-[180px]">
                        <div className="flex items-center gap-1 min-w-0">
                          <span className="font-mono text-[11px] text-foreground truncate" title={m.name}>
                            {m.name}
                          </span>
                          {isDefault && (
                            <Badge variant="success" size="sm" className="shrink-0 text-[10px] px-1 py-0">
                              {t('admin.provider.modelsTable.defaultTag')}
                            </Badge>
                          )}
                        </div>
                        {m.description && (
                          <p className="text-[10px] text-muted-foreground-tertiary truncate" title={m.description}>
                            {m.description}
                          </p>
                        )}
                      </td>
                      <td className="py-1.5 px-2">
                        {isEditing ? (
                          <Select
                            value={m.kind || 'chat'}
                            onChange={(e) => onUpdateModel(m, { kind: e.target.value as ProviderModelInfo['kind'] })}
                            className="h-6 text-[10px] w-20"
                          >
                            {MODEL_KINDS.map((kind) => (
                              <option key={kind} value={kind}>{kind}</option>
                            ))}
                          </Select>
                        ) : m.kind ? (
                          <Badge variant="default" size="sm" className="text-[10px]">{m.kind}</Badge>
                        ) : (
                          <span className="text-muted-foreground-tertiary">—</span>
                        )}
                      </td>
                      <td className="py-1.5 px-2 text-right tabular-nums text-muted-foreground">
                        {isEditing ? (
                          <Input
                            type="number"
                            value={m.context_window || ''}
                            onChange={(e) => onUpdateModel(m, { context_window: Number(e.target.value) || 0 })}
                            className="h-6 text-[10px] w-20 text-right"
                            placeholder="128000"
                          />
                        ) : (
                          formatContext(m.context_window)
                        )}
                      </td>
                      <td className="py-1.5 px-2 text-right tabular-nums text-muted-foreground hidden md:table-cell">
                        {isEditing ? (
                          <Input
                            type="number"
                            step="0.01"
                            value={getInputPrice(m) ?? ''}
                            onChange={(e) => onUpdateModel(m, {
                              pricing: { ...(m.pricing ?? {}), input_per_1m: Number(e.target.value) || 0 },
                            })}
                            className="h-6 text-[10px] w-16 text-right"
                            placeholder="0.00"
                          />
                        ) : (
                          formatPrice(getInputPrice(m))
                        )}
                      </td>
                      <td className="py-1.5 px-2 text-right tabular-nums text-muted-foreground hidden md:table-cell">
                        {isEditing ? (
                          <Input
                            type="number"
                            step="0.01"
                            value={getOutputPrice(m) ?? ''}
                            onChange={(e) => onUpdateModel(m, {
                              pricing: { ...(m.pricing ?? {}), output_per_1m: Number(e.target.value) || 0 },
                            })}
                            className="h-6 text-[10px] w-16 text-right"
                            placeholder="0.00"
                          />
                        ) : (
                          formatPrice(getOutputPrice(m))
                        )}
                      </td>
                      <td className="py-1.5 px-2">
                        {isEditing ? (
                          <div className="flex items-center justify-center gap-1.5">
                            <label className="flex items-center cursor-pointer" title={t('admin.provider.modelsTable.toolsTip')}>
                              <input
                                type="checkbox"
                                checked={modelSupportsTools(m)}
                                onChange={(e) => onUpdateModel(m, {
                                  capabilities: {
                                    ...normalizeCapabilities(m.capabilities),
                                    tool_call: e.target.checked,
                                  },
                                })}
                                className="rounded border-gray-300 text-sky-600 w-3 h-3"
                              />
                            </label>
                            <label className="flex items-center cursor-pointer" title={t('admin.provider.modelsTable.visionTip')}>
                              <input
                                type="checkbox"
                                checked={modelSupportsVision(m)}
                                onChange={(e) => {
                                  const caps = normalizeCapabilities(m.capabilities);
                                  const input = new Set(caps.input ?? ['text']);
                                  if (e.target.checked) input.add('image');
                                  else input.delete('image');
                                  if (input.size === 0) input.add('text');
                                  onUpdateModel(m, { capabilities: { ...caps, input: Array.from(input) } });
                                }}
                                className="rounded border-gray-300 text-blue-600 w-3 h-3"
                              />
                            </label>
                            <label className="flex items-center cursor-pointer" title={t('admin.provider.modelsTable.thinkingTip')}>
                              <input
                                type="checkbox"
                                checked={modelSupportsReasoning(m)}
                                onChange={(e) => onUpdateModel(m, {
                                  capabilities: {
                                    ...normalizeCapabilities(m.capabilities),
                                    reasoning: e.target.checked,
                                  },
                                })}
                                className="rounded border-gray-300 text-purple-600 w-3 h-3"
                              />
                            </label>
                          </div>
                        ) : (
                          <div className="flex items-center justify-center gap-0.5">
                            {modelSupportsTools(m) && (
                              <span title={t('admin.provider.modelsTable.toolsTip')} className="text-sky-600 dark:text-sky-400">
                                <Wrench className="w-3 h-3" />
                              </span>
                            )}
                            {modelSupportsVision(m) && (
                              <span title={t('admin.provider.modelsTable.visionTip')} className="text-blue-500">
                                <Eye className="w-3 h-3" />
                              </span>
                            )}
                            {modelSupportsReasoning(m) && (
                              <span title={t('admin.provider.modelsTable.thinkingTip')} className="text-purple-600 dark:text-purple-400">
                                <Brain className="w-3 h-3" />
                              </span>
                            )}
                            {!modelSupportsTools(m) && !modelSupportsVision(m) && !modelSupportsReasoning(m) && (
                              <span className="text-muted-foreground-tertiary">—</span>
                            )}
                          </div>
                        )}
                      </td>
                      <td className="py-1.5 px-2 text-right tabular-nums hidden sm:table-cell">
                        {usage ? (
                          <span className="text-foreground">{formatCompactNumber(usage.request_count)}</span>
                        ) : (
                          <span className="text-muted-foreground-tertiary">0</span>
                        )}
                      </td>
                      <td className="py-1.5 pl-2">
                        <div className="flex items-center gap-0.5">
                          <Button
                            variant="ghost"
                            size="sm"
                            className="h-7 w-7 p-0"
                            onClick={() => setEditingModel(isEditing ? null : m.name)}
                            title={isEditing ? t('common.save') : t('admin.provider.modelsTable.editModel')}
                          >
                            <Pencil className={cn('w-3 h-3', isEditing && 'text-primary-600 dark:text-primary-400')} />
                          </Button>
                          <Button
                            variant="ghost"
                            size="sm"
                            className="h-7 px-1.5 text-[10px] min-w-0"
                            disabled={!provider.enabled || !isEnabled || isDefault || settingDefault}
                            loading={settingDefault && !isDefault}
                            onClick={() => onSetDefault(m)}
                          >
                            {isDefault
                              ? t('admin.provider.modelsTable.isDefault')
                              : t('admin.provider.modelsTable.makeDefault')}
                          </Button>
                        </div>
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </Card>
  );
}
