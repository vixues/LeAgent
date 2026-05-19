import { describe, expect, it } from 'vitest';
import { shouldPromptForDeepSeekKey, shouldShowProviderNudge } from '@/lib/deepseekSetupNudge';
import type { ModelProvider } from '@/types/admin';

describe('shouldPromptForDeepSeekKey', () => {
  it('returns true when DEEPSEEK_API_KEY row is missing', () => {
    expect(shouldPromptForDeepSeekKey([{ env_key: 'OPENAI_API_KEY', set: true }])).toBe(true);
  });

  it('returns true when DEEPSEEK_API_KEY is unset', () => {
    expect(
      shouldPromptForDeepSeekKey([
        { env_key: 'DEEPSEEK_API_KEY', set: false },
        { env_key: 'OPENAI_API_KEY', set: true },
      ])
    ).toBe(true);
  });

  it('returns false when DEEPSEEK_API_KEY is set', () => {
    expect(
      shouldPromptForDeepSeekKey([
        { env_key: 'DEEPSEEK_API_KEY', set: true },
        { env_key: 'OPENAI_API_KEY', set: false },
      ])
    ).toBe(false);
  });
});

describe('shouldShowProviderNudge', () => {
  it('returns true for empty providers array', () => {
    expect(shouldShowProviderNudge([])).toBe(true);
  });

  it('returns true when providers require API keys but none are configured', () => {
    const provider = {
      name: 'deepseek',
      type: 'deepseek',
      enabled: true,
      requires_api_key: true,
      api_key_set: false,
    } as ModelProvider;
    expect(shouldShowProviderNudge([provider])).toBe(true);
  });

  it('returns false when an API-key provider has a configured key', () => {
    const provider = {
      name: 'deepseek',
      type: 'deepseek',
      enabled: true,
      requires_api_key: true,
      api_key_set: true,
    } as ModelProvider;
    expect(shouldShowProviderNudge([provider])).toBe(false);
  });

  it('returns false when an enabled provider does not require an API key', () => {
    const provider = {
      name: 'ollama',
      type: 'ollama',
      enabled: true,
      requires_api_key: false,
      api_key_set: false,
    } as ModelProvider;
    expect(shouldShowProviderNudge([provider])).toBe(false);
  });
});
