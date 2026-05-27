import type { DefaultModelConfig, ModelProvider } from '@/types/admin';

/** Fallback when no provider model metadata is available. */
export const FALLBACK_CONTEXT_BUDGET_TOKENS = 128_000;

function enabledModels(provider: ModelProvider | undefined): ModelProvider['models'] {
  if (!provider || provider.enabled === false) return [];
  return provider.models.filter((m) => m.enabled !== false);
}

function findProvider(providers: ModelProvider[], providerName: string): ModelProvider | undefined {
  return providers.find((p) => p.name === providerName && p.enabled !== false);
}

function findProviderModel(
  providers: ModelProvider[],
  providerName: string,
  modelName: string,
): { provider: ModelProvider; model: ModelProvider['models'][number] } | undefined {
  const provider = findProvider(providers, providerName);
  if (!provider) return undefined;
  const model = enabledModels(provider).find((m) => m.name === modelName);
  if (!model) return undefined;
  return { provider, model };
}

function modelContextWindow(model: ModelProvider['models'][number] | undefined): number | undefined {
  const cw = model?.context_window;
  return cw != null && cw > 0 ? cw : undefined;
}

function resolveAutoProviderModel(
  providers: ModelProvider[],
  defaultModel: DefaultModelConfig | undefined,
): { provider: ModelProvider; model: ModelProvider['models'][number] } | undefined {
  const providerName = defaultModel?.provider?.trim();
  const configuredProvider = providerName ? findProvider(providers, providerName) : undefined;
  const provider = configuredProvider ?? providers.find((p) => p.enabled !== false && enabledModels(p).length > 0);
  const models = enabledModels(provider);
  if (!provider || !models.length) return undefined;

  const tier1Model = models.find((m) => (m.tier || '').trim().toLowerCase() === 'tier1');
  if (tier1Model) return { provider, model: tier1Model };

  const modelName = defaultModel?.model?.trim();
  const defaultProviderModel = modelName ? models.find((m) => m.name === modelName) : undefined;
  return { provider, model: defaultProviderModel ?? models[0]! };
}

export interface ResolvedContextBudget {
  tokens: number;
  providerName?: string;
  modelName?: string;
}

/**
 * Resolve the context window (token budget) for the context usage ring.
 *
 * - Explicit ``provider/model`` selection uses that model's ``context_window``.
 * - ``auto`` mirrors chat routing: tier1 model on the default provider, then a
 *   valid fallback provider/model.
 */
export function resolveContextBudget(
  modelId: string | undefined,
  providers: ModelProvider[] | undefined,
  defaultModel: DefaultModelConfig | undefined,
): ResolvedContextBudget {
  const list = providers ?? [];

  if (modelId && modelId !== 'auto') {
    const slash = modelId.indexOf('/');
    if (slash > 0) {
      const providerName = modelId.slice(0, slash);
      const modelName = modelId.slice(slash + 1);
      const found = findProviderModel(list, providerName, modelName);
      if (found) {
        return {
          tokens: modelContextWindow(found.model) ?? FALLBACK_CONTEXT_BUDGET_TOKENS,
          providerName: found.provider.name,
          modelName: found.model.name,
        };
      }
    }
  }

  const autoModel = resolveAutoProviderModel(list, defaultModel);
  if (autoModel) {
    return {
      tokens: modelContextWindow(autoModel.model) ?? FALLBACK_CONTEXT_BUDGET_TOKENS,
      providerName: autoModel.provider.name,
      modelName: autoModel.model.name,
    };
  }

  return { tokens: FALLBACK_CONTEXT_BUDGET_TOKENS };
}

export function resolveContextBudgetTokens(
  modelId: string | undefined,
  providers: ModelProvider[] | undefined,
  defaultModel: DefaultModelConfig | undefined,
): number {
  return resolveContextBudget(modelId, providers, defaultModel).tokens;
}
