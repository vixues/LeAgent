import type { DefaultModelConfig, ModelProvider } from '@/types/admin';

/** Fallback when no provider model metadata is available. */
export const FALLBACK_CONTEXT_BUDGET_TOKENS = 128_000;

function contextWindowForProviderModel(
  providers: ModelProvider[],
  providerName: string,
  modelName: string,
): number | undefined {
  const provider = providers.find((p) => p.name === providerName);
  if (!provider) return undefined;
  const model = provider.models.find((m) => m.name === modelName);
  const cw = model?.context_window;
  return cw != null && cw > 0 ? cw : undefined;
}

/**
 * Resolve the context window (token budget) for the context usage ring.
 *
 * - Explicit ``provider/model`` selection uses that model's ``context_window``.
 * - ``auto`` uses the configured default model, then the largest enabled window.
 */
export function resolveContextBudgetTokens(
  modelId: string | undefined,
  providers: ModelProvider[] | undefined,
  defaultModel: DefaultModelConfig | undefined,
): number {
  const list = providers ?? [];

  if (modelId && modelId !== 'auto') {
    const slash = modelId.indexOf('/');
    if (slash > 0) {
      const providerName = modelId.slice(0, slash);
      const modelName = modelId.slice(slash + 1);
      const cw = contextWindowForProviderModel(list, providerName, modelName);
      if (cw != null) return cw;
    }
  }

  const defProvider = defaultModel?.provider?.trim();
  const defModel = defaultModel?.model?.trim();
  if (defProvider && defModel) {
    const cw = contextWindowForProviderModel(list, defProvider, defModel);
    if (cw != null) return cw;
  }

  let max = 0;
  for (const p of list) {
    if (p.enabled === false) continue;
    for (const m of p.models) {
      if (m.enabled === false) continue;
      if (m.context_window > max) max = m.context_window;
    }
  }
  return max > 0 ? max : FALLBACK_CONTEXT_BUDGET_TOKENS;
}
