import type { ModelProvider } from '@/types/admin';

export interface TokenKeyStatusRow {
  env_key: string;
  set: boolean;
}

/** @deprecated Use `shouldShowProviderNudge` instead. */
export function shouldPromptForDeepSeekKey(keys: TokenKeyStatusRow[]): boolean {
  const row = keys.find((k) => k.env_key === 'DEEPSEEK_API_KEY');
  if (!row) return true;
  return !row.set;
}

/** True when no usable model provider is configured yet. */
export function shouldShowProviderNudge(providers: ModelProvider[]): boolean {
  if (!providers || providers.length === 0) return true;

  const hasUsableProvider = providers.some((provider) => {
    if (provider.enabled === false) return false;
    if (provider.requires_api_key === false) return true;
    return provider.api_key_set === true;
  });

  return !hasUsableProvider;
}
