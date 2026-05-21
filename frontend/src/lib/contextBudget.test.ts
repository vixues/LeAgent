import { describe, expect, it } from 'vitest';
import { FALLBACK_CONTEXT_BUDGET_TOKENS, resolveContextBudgetTokens } from './contextBudget';
import type { ModelProvider } from '@/types/admin';

const providers: ModelProvider[] = [
  {
    name: 'deepseek',
    type: 'deepseek',
    enabled: true,
    models: [
      { name: 'deepseek-v4-flash', tier: 'tier2', context_window: 1_000_000 },
      { name: 'deepseek-v4-pro', tier: 'tier1', context_window: 1_000_000 },
    ],
  },
  {
    name: 'qwen',
    type: 'qwen',
    enabled: true,
    models: [
      { name: 'qwen-max', tier: 'tier1', context_window: 32_000 },
      { name: 'qwen-long', tier: 'tier1', context_window: 1_000_000 },
    ],
  },
];

describe('resolveContextBudgetTokens', () => {
  it('uses selected model context_window', () => {
    expect(
      resolveContextBudgetTokens('qwen/qwen-max', providers, {
        provider: 'deepseek',
        model: 'deepseek-v4-flash',
      }),
    ).toBe(32_000);
  });

  it('uses default model for auto', () => {
    expect(
      resolveContextBudgetTokens('auto', providers, {
        provider: 'qwen',
        model: 'qwen-max',
      }),
    ).toBe(32_000);
  });

  it('falls back to max enabled window when auto has no default', () => {
    expect(resolveContextBudgetTokens('auto', providers, { provider: '', model: '' })).toBe(
      1_000_000,
    );
  });

  it('uses global fallback when providers are empty', () => {
    expect(resolveContextBudgetTokens('auto', [], undefined)).toBe(
      FALLBACK_CONTEXT_BUDGET_TOKENS,
    );
  });
});
