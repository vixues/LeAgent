import type { AvailableModel, DefaultModelConfig } from '@/types/admin';

/** Normalize legacy ids (model name only) to ``provider/model``. */
export function normalizeComposerModelId(
  modelId: string,
  availableModels: AvailableModel[] | undefined,
): string {
  const trimmed = (modelId || '').trim();
  if (!trimmed || trimmed === 'auto') return 'auto';
  if (trimmed.includes('/')) return trimmed;
  const match = availableModels?.find((m) => m.model_name === trimmed);
  if (match) return `${match.provider_name}/${match.model_name}`;
  return trimmed;
}

export function parseComposerModelId(modelId: string): {
  provider: string;
  model: string;
} | null {
  const slash = modelId.indexOf('/');
  if (slash <= 0) return null;
  const provider = modelId.slice(0, slash).trim();
  const model = modelId.slice(slash + 1).trim();
  if (!provider || !model) return null;
  return { provider, model };
}

export function formatModelDisplayLabel(
  modelId: string,
  modelName: string,
  providerLabel?: string,
): string {
  if (modelId === 'auto') return modelName;
  const provider = (providerLabel || '').trim();
  if (provider) return `${provider} · ${modelName}`;
  return modelName;
}

/** Mirrors backend chat task routing: use configured default chat model. */
export function resolveAutoAvailableModel(
  availableModels: AvailableModel[] | undefined,
  defaultModel: DefaultModelConfig | undefined,
): AvailableModel | undefined {
  const list = availableModels ?? [];
  if (!list.length) return undefined;

  const defaultProviderName =
    defaultModel?.provider?.trim() ||
    list.find((m) => m.is_default)?.provider_name;
  const providerModels = defaultProviderName
    ? list.filter((m) => m.provider_name === defaultProviderName)
    : [];
  const candidates = providerModels.length
    ? providerModels
    : list.filter((m) => m.provider_name === list[0]?.provider_name);
  if (!candidates.length) return undefined;

  const defaultModelName = defaultModel?.model?.trim();
  const configuredDefault = defaultModelName
    ? candidates.find((m) => m.model_name === defaultModelName)
    : undefined;
  return configuredDefault ?? candidates.find((m) => m.kind === 'chat') ?? candidates[0];
}
