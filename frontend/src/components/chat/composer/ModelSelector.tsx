import { useState, useRef, useEffect, useMemo } from 'react';
import { useTranslation } from 'react-i18next';
import { ChevronDown, Sparkles, Bot, Wrench, Eye, DollarSign } from 'lucide-react';
import { useProviders } from '@/hooks/useAdmin';
import { cn } from '@/lib/utils';

interface ModelOption {
  id: string;
  label: string;
  provider?: string;
  priceLevel?: '$' | '$$' | '$$$';
  supportsTools?: boolean | null;
  supportsVision?: boolean | null;
  icon: React.ReactNode;
}

interface ModelSelectorProps {
  value?: string;
  onChange?: (modelId: string) => void;
  className?: string;
}

export function ModelSelector({
  value = 'auto',
  onChange,
  className,
}: ModelSelectorProps) {
  const { t } = useTranslation();
  const { data: providers } = useProviders();
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
    const autoOption: ModelOption = {
      id: 'auto',
      label: t('chat.modelSelectorAuto', { defaultValue: 'Auto' }),
      icon: <Sparkles className="w-3.5 h-3.5" />,
    };

    const enabledModelOptions =
      providers
        ?.filter((provider) => provider.enabled)
        .flatMap((provider) =>
          provider.models
            .filter((model) => model.enabled !== false)
            .map((model) => ({
              id: `${provider.name}/${model.name}`,
              label: model.name,
              provider: provider.label || provider.name,
              supportsTools: model.supports_tools,
              supportsVision: model.supports_vision,
              priceLevel: priceLevel(model.price_input_per_1m, model.price_output_per_1m),
              icon: <Bot className="w-3.5 h-3.5" />,
            })),
        ) ?? [];

    return [autoOption, ...enabledModelOptions];
  }, [providers, t]);

  const selected = models.find((m) => m.id === value) ?? models[0]!;
  const recentOptions = models.filter((m) => recentModels.includes(m.id) && m.id !== 'auto');
  const providerGroups = useMemo(() => {
    const groups = new Map<string, ModelOption[]>();
    for (const option of models.filter((m) => m.id !== 'auto' && !recentModels.includes(m.id))) {
      const key = option.provider || 'Other';
      groups.set(key, [...(groups.get(key) ?? []), option]);
    }
    return [...groups.entries()];
  }, [models, recentModels]);

  const selectModel = (modelId: string) => {
    onChange?.(modelId);
    if (modelId !== 'auto') {
      const next = [modelId, ...recentModels.filter((id) => id !== modelId)].slice(0, 5);
      setRecentModels(next);
      localStorage.setItem('leagent.recentModels', JSON.stringify(next));
    }
    setOpen(false);
  };

  useEffect(() => {
    if (!providers || value === 'auto') return;
    if (!models.some((model) => model.id === value)) {
      onChange?.('auto');
    }
  }, [models, onChange, providers, value]);

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
        <span>{selected.label}</span>
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
            'w-72 rounded-xl border border-border-subtle bg-surface shadow-soft',
            'p-1',
            'chat-palette-dialog',
          )}
          role="listbox"
          aria-label={t('chat.modelSelector', {
            defaultValue: 'Select model',
          })}
        >
          <ModelOptionButton
            model={models[0]!}
            selected={models[0]!.id === value}
            onSelect={selectModel}
          />
          {recentOptions.length > 0 && (
            <ModelGroup title={t('chat.modelSelectorRecent', { defaultValue: 'Recent' })}>
              {recentOptions.map((model) => (
                <ModelOptionButton
                  key={model.id}
                  model={model}
                  selected={model.id === value}
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
                  selected={model.id === value}
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
      <span className="min-w-0 flex-1 truncate">{model.label}</span>
      {model.supportsTools && <Wrench className="h-3 w-3" />}
      {model.supportsVision && <Eye className="h-3 w-3" />}
      {model.priceLevel && (
        <span className="inline-flex items-center gap-0.5 text-[10px]">
          <DollarSign className="h-3 w-3" />
          {model.priceLevel}
        </span>
      )}
            </button>
  );
}

function priceLevel(input = 0, output = 0): '$' | '$$' | '$$$' {
  const blended = Number(input || 0) + Number(output || 0);
  if (blended >= 30) return '$$$';
  if (blended >= 5) return '$$';
  return '$';
}
