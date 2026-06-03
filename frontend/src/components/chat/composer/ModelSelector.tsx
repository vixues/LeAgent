import { useState, useRef, useEffect, useMemo } from 'react';
import { useTranslation } from 'react-i18next';
import { ChevronDown, Sparkles, Bot, Wrench, Eye, Brain, DollarSign, Star } from 'lucide-react';
import { useAvailableModels, useDefaultModel } from '@/hooks/useAdmin';
import {
  formatModelDisplayLabel,
  normalizeComposerModelId,
  resolveAutoAvailableModel,
} from '@/lib/modelSelection';
import { useChatDraftStore } from '@/stores/chatDraft';
import { cn } from '@/lib/utils';

interface ModelOption {
  id: string;
  label: string;
  provider?: string;
  providerLabel?: string;
  priceLevel?: '$' | '$$' | '$$$';
  supportsTools?: boolean;
  supportsVision?: boolean;
  supportsThinking?: boolean;
  isDefault?: boolean;
  description?: string;
  contextWindow?: number;
  subtitle?: string;
  icon: React.ReactNode;
}

interface ModelSelectorProps {
  className?: string;
}

export function ModelSelector({ className }: ModelSelectorProps) {
  const value = useChatDraftStore((s) => s.composerModelId);
  const setComposerModelId = useChatDraftStore((s) => s.setComposerModelId);
  const { t } = useTranslation();
  const { data: availableModels } = useAvailableModels();
  const { data: defaultModel } = useDefaultModel();
  const [open, setOpen] = useState(false);
  const [recentModels, setRecentModels] = useState<string[]>(() => {
    try {
      return JSON.parse(localStorage.getItem('leagent.recentModels') || '[]');
    } catch {
      return [];
    }
  });
  const containerRef = useRef<HTMLDivElement>(null);

  const models = useMemo<ModelOption[]>(() => {
    const autoModel = resolveAutoAvailableModel(availableModels, defaultModel);
    const autoModelLabel = autoModel
      ? formatModelDisplayLabel(
          `${autoModel.provider_name}/${autoModel.model_name}`,
          autoModel.model_name,
          autoModel.provider_label || autoModel.provider_name,
        )
      : undefined;
    const autoOption: ModelOption = {
      id: 'auto',
      label: t('chat.modelSelectorAuto', { defaultValue: 'Auto' }),
      contextWindow: autoModel?.context_window,
      subtitle: autoModelLabel,
      icon: <Sparkles className="w-3.5 h-3.5" />,
    };

    const modelOptions =
      availableModels?.map((m) => ({
        id: `${m.provider_name}/${m.model_name}`,
        label: m.model_name,
        provider: m.provider_name,
        providerLabel: m.provider_label || m.provider_name,
        supportsTools: !!m.capabilities?.tool_call,
        supportsVision: !!m.capabilities?.input?.includes('image'),
        supportsThinking: !!m.capabilities?.reasoning,
        isDefault: m.is_default,
        description: m.description,
        contextWindow: m.context_window,
        priceLevel: priceLevel(m.pricing?.input_per_1m ?? 0, m.pricing?.output_per_1m ?? 0),
        icon: m.is_default ? <Star className="w-3.5 h-3.5 text-amber-500" /> : <Bot className="w-3.5 h-3.5" />,
      })) ?? [];

    return [autoOption, ...modelOptions];
  }, [availableModels, defaultModel, t]);

  const normalizedValue = normalizeComposerModelId(value, availableModels);
  const selected = models.find((m) => m.id === normalizedValue) ?? models[0]!;
  const selectedLabel = formatModelDisplayLabel(
    selected.id,
    selected.label,
    selected.providerLabel || selected.provider,
  );
  const recentOptions = models.filter((m) => recentModels.includes(m.id) && m.id !== 'auto');
  const providerGroups = useMemo(() => {
    const groups = new Map<string, ModelOption[]>();
    for (const option of models.filter((m) => m.id !== 'auto' && !recentModels.includes(m.id))) {
      const key = option.providerLabel || option.provider || 'Other';
      groups.set(key, [...(groups.get(key) ?? []), option]);
    }
    return [...groups.entries()];
  }, [models, recentModels]);

  const selectModel = (modelId: string) => {
    setComposerModelId(modelId);
    if (modelId !== 'auto') {
      const next = [modelId, ...recentModels.filter((id) => id !== modelId)].slice(0, 5);
      setRecentModels(next);
      localStorage.setItem('leagent.recentModels', JSON.stringify(next));
    }
    setOpen(false);
  };

  // Reconcile stale persisted ids (legacy bare model names, removed providers).
  useEffect(() => {
    if (!availableModels?.length || value === 'auto') return;
    const normalized = normalizeComposerModelId(value, availableModels);
    if (normalized !== value) {
      setComposerModelId(normalized);
      return;
    }
    if (models.some((model) => model.id === value)) return;

    if (!value.includes('/')) {
      const byName = availableModels.filter((m) => m.model_name === value);
      if (byName.length === 1) {
        const migrated = `${byName[0]!.provider_name}/${byName[0]!.model_name}`;
        if (migrated !== value) {
          setComposerModelId(migrated);
          return;
        }
      }
    }

    const fallback = availableModels.find((m) => m.is_default);
    const nextId = fallback
      ? `${fallback.provider_name}/${fallback.model_name}`
      : 'auto';
    if (nextId !== value) setComposerModelId(nextId);
  }, [availableModels, models, setComposerModelId, value]);

  useEffect(() => {
    if (!open) return;
    const handler = (e: MouseEvent) => {
      if (
        containerRef.current &&
        !containerRef.current.contains(e.target as Node)
      ) {
        setOpen(false);
      }
    };
    document.addEventListener('mousedown', handler);
    return () => document.removeEventListener('mousedown', handler);
  }, [open]);

  useEffect(() => {
    if (!open) return;
    const handler = (e: KeyboardEvent) => {
      if (e.key === 'Escape') setOpen(false);
    };
    document.addEventListener('keydown', handler);
    return () => document.removeEventListener('keydown', handler);
  }, [open]);

  return (
    <div ref={containerRef} className={cn('relative', className)}>
      <button
        type="button"
        onClick={() => setOpen(!open)}
        className={cn(
          'flex items-center gap-1.5 px-2 py-1 rounded-lg text-xs font-medium',
          'text-muted-foreground hover:text-foreground',
          'hover:bg-surface-sunken transition-colors',
          open && 'bg-surface-sunken text-foreground',
        )}
        aria-label={t('chat.modelSelector', {
          defaultValue: 'Select model',
        })}
        aria-expanded={open}
      >
        {selected.icon}
        <span className="max-w-[12rem] truncate">{selectedLabel}</span>
        {selected.contextWindow ? (
          <span
            className="rounded bg-surface-sunken px-1 py-0.5 text-[10px] font-medium tabular-nums text-muted-foreground-tertiary"
            title="Context window"
          >
            {formatContextWindow(selected.contextWindow)}
          </span>
        ) : null}
        <ChevronDown
          className={cn(
            'w-3 h-3 transition-transform',
            open && 'rotate-180',
          )}
        />
      </button>

      {open && (
        <div
          className={cn(
            'absolute bottom-full left-0 mb-1 z-50',
            'w-80 rounded-xl border border-border-subtle bg-surface shadow-soft',
            'p-1 max-h-96 overflow-y-auto',
            'chat-palette-dialog',
          )}
          role="listbox"
          aria-label={t('chat.modelSelector', {
            defaultValue: 'Select model',
          })}
        >
          <ModelOptionButton
            model={models[0]!}
            selected={models[0]!.id === normalizedValue}
            onSelect={selectModel}
          />
          {recentOptions.length > 0 && (
            <ModelGroup title={t('chat.modelSelectorRecent', { defaultValue: 'Recent' })}>
              {recentOptions.map((model) => (
                <ModelOptionButton
                  key={model.id}
                  model={model}
                  selected={model.id === normalizedValue}
                  onSelect={selectModel}
                />
              ))}
            </ModelGroup>
          )}
          {providerGroups.map(([provider, options]) => (
            <ModelGroup key={provider} title={provider}>
              {options.map((model) => (
                <ModelOptionButton
                  key={model.id}
                  model={model}
                  selected={model.id === normalizedValue}
                  onSelect={selectModel}
                />
              ))}
            </ModelGroup>
          ))}
        </div>
      )}
    </div>
  );
}

function ModelGroup({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <div className="mt-1 border-t border-border-subtle pt-1">
      <div className="px-3 py-1 text-[10px] font-semibold uppercase tracking-wide text-muted-foreground">
        {title}
      </div>
      {children}
    </div>
  );
}

function ModelOptionButton({
  model,
  selected,
  onSelect,
}: {
  model: ModelOption;
  selected: boolean;
  onSelect: (modelId: string) => void;
}) {
  return (
    <button
      key={model.id}
      type="button"
      role="option"
      aria-selected={selected}
      onClick={() => onSelect(model.id)}
      className={cn(
        'w-full flex items-center gap-2 px-3 py-2 rounded-lg text-left text-xs font-medium transition-colors',
        selected
          ? 'bg-primary-50 dark:bg-primary-900/20 text-foreground'
          : 'text-muted-foreground hover:bg-surface-sunken hover:text-foreground',
      )}
    >
      <span className="flex-shrink-0">{model.icon}</span>
      <span className="min-w-0 flex-1">
        <span className="block truncate">{formatModelOptionLabel(model)}</span>
        {model.subtitle ? (
          <span className="mt-0.5 block truncate text-[10px] font-normal text-muted-foreground-tertiary">
            {model.subtitle}
          </span>
        ) : null}
      </span>
      <span className="flex items-center gap-1 flex-shrink-0">
        {model.contextWindow ? (
          <span
            className="rounded bg-surface-sunken px-1 py-0.5 text-[10px] tabular-nums text-muted-foreground-tertiary"
            title="Context window"
          >
            {formatContextWindow(model.contextWindow)}
          </span>
        ) : null}
        {model.supportsTools && <span title="Tools"><Wrench className="h-3 w-3" /></span>}
        {model.supportsVision && <span title="Vision"><Eye className="h-3 w-3" /></span>}
        {model.supportsThinking && <span title="Thinking"><Brain className="h-3 w-3" /></span>}
        {model.priceLevel && (
          <span className="inline-flex items-center gap-0.5 text-[10px]">
            <DollarSign className="h-3 w-3" />
            {model.priceLevel}
          </span>
        )}
        {model.isDefault && (
          <span className="text-[9px] px-1 py-0.5 rounded bg-amber-100 dark:bg-amber-900/30 text-amber-700 dark:text-amber-400">
            default
          </span>
        )}
      </span>
    </button>
  );
}

function formatModelOptionLabel(model: ModelOption): string {
  if (model.id === 'auto') return model.label;
  const provider = model.providerLabel || model.provider;
  if (provider && provider !== model.label) {
    return `${provider} · ${model.label}`;
  }
  return model.label;
}

function priceLevel(input = 0, output = 0): '$' | '$$' | '$$$' {
  const blended = Number(input || 0) + Number(output || 0);
  if (blended >= 30) return '$$$';
  if (blended >= 5) return '$$';
  return '$';
}

function formatContextWindow(ctx: number | undefined): string {
  if (!ctx) return '—';
  if (ctx >= 1_000_000) return `${(ctx / 1_000_000).toFixed(ctx % 1_000_000 === 0 ? 0 : 1)}M`;
  if (ctx >= 1000) return `${Math.round(ctx / 1000)}k`;
  return String(ctx);
}
