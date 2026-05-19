import { useState, useRef, useEffect, useMemo } from 'react';
import { useTranslation } from 'react-i18next';
import { ChevronDown, Sparkles, Bot } from 'lucide-react';
import { useProviders } from '@/hooks/useAdmin';
import { cn } from '@/lib/utils';

interface ModelOption {
  id: string;
  label: string;
  description: string;
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
  const containerRef = useRef<HTMLDivElement>(null);

  const models = useMemo<ModelOption[]>(() => {
    const autoOption: ModelOption = {
      id: 'auto',
      label: t('chat.modelSelectorAuto', { defaultValue: 'Auto' }),
      description: t('chat.modelSelectorAutoDescription', {
        defaultValue: 'Use the default configured model',
      }),
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
              description:
                model.description?.trim()
                  || provider.label
                  || provider.name,
              icon: <Bot className="w-3.5 h-3.5" />,
            })),
        ) ?? [];

    return [autoOption, ...enabledModelOptions];
  }, [providers, t]);

  const selected = models.find((m) => m.id === value) ?? models[0]!;

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
            'w-52 rounded-xl border border-border-subtle bg-surface shadow-soft',
            'p-1',
            'chat-palette-dialog',
          )}
          role="listbox"
          aria-label={t('chat.modelSelector', {
            defaultValue: 'Select model',
          })}
        >
          {models.map((model) => (
            <button
              key={model.id}
              type="button"
              role="option"
              aria-selected={model.id === value}
              onClick={() => {
                onChange?.(model.id);
                setOpen(false);
              }}
              className={cn(
                'w-full flex items-start gap-2.5 px-3 py-2 rounded-lg text-left transition-colors',
                model.id === value
                  ? 'bg-primary-50 dark:bg-primary-900/20 text-foreground'
                  : 'text-muted-foreground hover:bg-surface-sunken hover:text-foreground',
              )}
            >
              <span className="mt-0.5 flex-shrink-0">{model.icon}</span>
              <div className="min-w-0">
                <div className="text-xs font-medium">{model.label}</div>
                <div className="text-[11px] text-muted-foreground-tertiary">
                  {model.description}
                </div>
              </div>
            </button>
          ))}
        </div>
      )}
    </div>
  );
}
